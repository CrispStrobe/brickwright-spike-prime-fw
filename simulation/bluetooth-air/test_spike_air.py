#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""End to end: a virtual central talks to the Renode-emulated SPIKE firmware.

Renode runs the unchanged simulation-profile image and exports USART2 (the
CC2564C HCI UART) as a TCP socket. The shared air attaches a bumble controller
to that socket, so the firmware's own Zephyr host drives a simulated
controller. A bumble central on the same air then:

1. scans and finds the hub's LE advertisement;
2. connects, discovers the FD02 GATT service, and subscribes to TX;
3. writes an InfoRequest frame (COBS/XOR-framed, as the SPIKE app does) to RX;
4. receives and decodes the InfoResponse notification;
5. (Classic, --classic) opens BR/EDR, finds the SPP record over SDP, and
   opens RFCOMM.

With --scratch-link PORT, steps 1-4 run through the Scratch Link gateway, the
way a browser (Brickwright lite) would reach the hub.

Usage:
  test_spike_air.py --renode RENODE_DIR --images IMAGE_DIR [--classic]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike_codec import cobs_decode, cobs_encode  # noqa: E402


def air_tools(argv) -> Path:
    """The one bw-air/1 implementation lives in renode-spike-prime/tools/bw-air."""
    for index, value in enumerate(argv):
        if value == "--air-tools" and index + 1 < len(argv):
            return Path(argv[index + 1]).resolve()
        if value == "--renode" and index + 1 < len(argv):
            candidate = Path(argv[index + 1]).resolve() / "tools" / "bw-air"
            if candidate.is_dir():
                return candidate
    return Path(os.environ.get("BW_AIR_TOOLS", "")).resolve()


AIR_TOOLS = air_tools(sys.argv)
sys.path.insert(0, str(AIR_TOOLS))
from hci_node import Air  # noqa: E402

from bumble import hci  # noqa: E402
from bumble.core import UUID, PhysicalTransport  # noqa: E402
from bumble.device import Peer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "simulation" / "renode" / "spike-prime-custom-dma.repl"
DEVICES = ROOT / "simulation" / "renode" / "SpikePrimeDevices.cs"
HUB_ADDRESS = "02:B1:0E:5A:17:01"
CENTRAL_ADDRESS = "02:B1:0E:5A:17:C0"
FD02_SERVICE = UUID("0000fd02-0000-1000-8000-00805f9b34fb")
FD02_RX = UUID("0000fd02-0001-1000-8000-00805f9b34fb")
FD02_TX = UUID("0000fd02-0002-1000-8000-00805f9b34fb")
MICROBIT_ADDRESS = "C0:EE:AA:BB:CC:01"
UART_SERVICE = UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
DISPLAY_STUBS = ("tlc5955_initialize", "tlc5955_update_sync", "tlc5955_set_duty")

MILESTONES = ("__start", "bt_enable", "physical_start_host", "settings_load",
              "daemon_wait_for_stop", "btsensor_transport_set_visible",
              "bt_le_adv_start", "bt_br_set_discoverable")

log = logging.getLogger("spike-air-test")


def renode_script(images: Path, port: int, trace=(), callers=(), watches=(),
                  dumps=()) -> str:
    manifest = json.loads((images / "manifest.json").read_text())
    pc = int(manifest["reset_pc"], 16) & ~1
    lines = [
        f"include @{DEVICES}",
        "mach create \"spike\"",
        f"machine LoadPlatformDescription @{PLATFORM}",
        f"sysbus LoadELF @{images / 'nuttx'}",
        f"sysbus LoadELF @{images / 'nuttx_user.elf'}",
        "cpu VectorTableOffset 0x08008000",
        f"cpu SP {manifest['initial_sp']}",
        f"cpu PC 0x{pc:08x}",
        f"emulation CreateServerSocketTerminal {port} \"hci\" false",
        "connector Connect sysbus.usart2 hci",
    ]
    # The TLC5955 display is isolated exactly as in the existing HCI gate.
    for symbol in DISPLAY_STUBS:
        lines.append(f"cpu AddHook `sysbus GetSymbolAddress \"{symbol}\"` "
                     "\"self.PC = self.LR\"")
    # Milestones are logged to renode.log (no pause), for diagnosis.
    for symbol in (*MILESTONES, *trace):
        lines.append(f"cpu AddHook `sysbus GetSymbolAddress \"{symbol}\"` "
                     f"\"monitor.Parse('log \\\"MILESTONE {symbol}\\\"')\"")
    for symbol in callers:
        if "=" in symbol:  # NAME=ADDRESS, for symbols defined in both images
            name, address = symbol.split("=", 1)
            lines.append(f"cpu AddHook {address} "
                         f"\"monitor.Parse('log \\\"CALLER {name} lr=' + "
                         f"hex(self.GetRegisterUnsafe(14).RawValue) + ' r0=' + "
                         f"hex(self.GetRegisterUnsafe(0).RawValue) + ' r1=' + "
                         f"hex(self.GetRegisterUnsafe(1).RawValue) + ' r2=' + "
                         f"hex(self.GetRegisterUnsafe(2).RawValue) + ' sp=' + hex(self.GetRegisterUnsafe(13).RawValue) + '\\\"')\"")
            continue
        lines.append(f"cpu AddHook `sysbus GetSymbolAddress \"{symbol}\"` "
                     f"\"monitor.Parse('log \\\"CALLER {symbol} ' + "
                     f"hex(self.GetRegisterUnsafe(14).RawValue) + '\\\"')\"")
    for spec in dumps:  # HOOK=ADDRESS:WORDS logs WORDS words at ADDRESS on HOOK
        hook, rest = spec.split("=", 1)
        address, words = rest.split(":", 1)
        base = int(address, 16)
        reads = " + ' ' + ".join(
            f"hex(machine.SystemBus.ReadDoubleWord({base + 4 * i}))"
            for i in range(int(words)))
        lines.append(f"cpu AddHook {hook} \"monitor.Parse('log \\\"DUMP {address} ' + "
                     f"{reads} + '\\\"')\"")
    for address in watches:
        lines.append(f"sysbus AddWatchpointHook {address} DoubleWord Write "
                     f"\"monitor.Parse('log \\\"WATCH {address} pc=' + "
                     f"hex(cpu.PC.RawValue) + ' lr=' + "
                     f"hex(cpu.GetRegisterUnsafe(14).RawValue) + ' value=' + "
                     f"hex(value) + '\\\"')\"")
    lines.append("start")
    return "\n".join(lines) + "\n"


async def start_renode(renode_dir: Path, images: Path, port: int, workdir: Path,
                       trace=(), callers=(), watches=(), dumps=()):
    script = workdir / "spike-air.resc"
    script.write_text(renode_script(images, port, trace, callers, watches, dumps))
    logfile = open(workdir / "renode.log", "wb")
    process = await asyncio.create_subprocess_exec(
        str(renode_dir / "renode"), "--disable-gui", "--console", "--plain",
        str(script), stdin=asyncio.subprocess.PIPE, stdout=logfile,
        stderr=asyncio.subprocess.STDOUT, start_new_session=True)
    return process


async def find_hub(device, timeout: float):
    found: asyncio.Future = asyncio.get_running_loop().create_future()

    def on_advertisement(advertisement):
        if (str(advertisement.address).upper().startswith(HUB_ADDRESS)
                and not found.done()):
            found.set_result(advertisement)

    device.on("advertisement", on_advertisement)
    await device.start_scanning(filter_duplicates=True)
    try:
        return await asyncio.wait_for(found, timeout)
    finally:
        await device.stop_scanning()


async def le_round_trip(central, advertisement, results: dict) -> None:
    started = time.monotonic()
    connection = await central.connect(advertisement.address,
                                       transport=PhysicalTransport.LE,
                                       timeout=60)
    results["le_connect_s"] = round(time.monotonic() - started, 1)
    peer = Peer(connection)
    await peer.discover_services([FD02_SERVICE])
    services = peer.get_services_by_uuid(FD02_SERVICE)
    assert services, "FD02 service not found"
    await services[0].discover_characteristics()
    rx = services[0].get_characteristics_by_uuid(FD02_RX)[0]
    tx = services[0].get_characteristics_by_uuid(FD02_TX)[0]
    results["gatt_fd02"] = {"rx_handle": rx.handle, "tx_handle": tx.handle}

    frames: asyncio.Queue = asyncio.Queue()
    buffer = bytearray()

    def on_notify(value: bytes) -> None:
        buffer.extend(value)
        while 0x02 in buffer:
            end = buffer.index(0x02) + 1
            frames.put_nowait(bytes(buffer[:end]))
            del buffer[:end]

    await peer.subscribe(tx, on_notify)
    request = cobs_encode(b"\x00")  # InfoRequest
    results["info_request_frame"] = request.hex()
    await peer.write_value(rx, request, with_response=False)
    frame = await asyncio.wait_for(frames.get(), 60)
    payload = cobs_decode(frame)
    results["info_response_frame"] = frame.hex()
    results["info_response_payload"] = payload.hex()
    assert payload[0] == 0x01, f"expected InfoResponse, got {payload.hex()}"
    await connection.disconnect()


async def microbit_check(air, results: dict, timeout: float) -> None:
    """The SPIKE hub and an emulated micro:bit on one air: a central sees both
    advertisers, then connects to the micro:bit and finds its UART service."""
    central = (await air.add_peer("microbit-central", "02:B1:0E:5A:17:C2")).device
    loop = asyncio.get_running_loop()
    seen = {HUB_ADDRESS: loop.create_future(), MICROBIT_ADDRESS: loop.create_future()}

    def on_advertisement(advertisement):
        key = str(advertisement.address).split("/")[0].upper()
        if key in seen and not seen[key].done():
            seen[key].set_result(advertisement)

    central.on("advertisement", on_advertisement)
    await central.start_scanning(filter_duplicates=True)
    started = time.monotonic()
    hub_adv, microbit_adv = await asyncio.wait_for(
        asyncio.gather(seen[HUB_ADDRESS], seen[MICROBIT_ADDRESS]), timeout)
    await central.stop_scanning()
    results["one_air_saw"] = {"spike_hub": str(hub_adv.address),
                              "microbit": str(microbit_adv.address),
                              "after_s": round(time.monotonic() - started, 1)}
    connection = await central.connect(microbit_adv.address,
                                       transport=PhysicalTransport.LE, timeout=60)
    peer = Peer(connection)
    await asyncio.wait_for(peer.discover_services(), 60)
    results["microbit_services"] = [str(s.uuid) for s in peer.services]
    assert peer.get_services_by_uuid(UART_SERVICE), "micro:bit UART service not found"
    await connection.disconnect()
    await air.remove("microbit-central")


async def classic_round_trip(central, results: dict) -> None:
    from bumble.rfcomm import Client, find_rfcomm_channel_with_uuid
    from bumble.sdp import Client as SdpClient  # noqa: F401

    connection = await central.connect(HUB_ADDRESS,
                                       transport=PhysicalTransport.BR_EDR,
                                       timeout=60)
    results["classic_connected"] = True
    channel = await find_rfcomm_channel_with_uuid(
        connection, "00001101-0000-1000-8000-00805F9B34FB")
    results["spp_channel"] = channel
    assert channel, "SPP record not found"
    # The hub's RFCOMM server requires an authenticated, encrypted link, as
    # SPP on the physical hub does: pair (Secure Simple Pairing, just works),
    # then encrypt.
    await connection.authenticate()
    results["classic_authenticated"] = True
    await connection.encrypt()
    results["classic_encrypted"] = True
    multiplexer = await Client(connection).start()
    dlc = await multiplexer.open_dlc(channel)
    received: asyncio.Queue = asyncio.Queue()
    dlc.sink = received.put_nowait
    results["rfcomm_open"] = True
    # The hub's SPP speaks the btsensor line protocol (see
    # apps/btsensor/btsensor_cmd_neutral.c): PING answers OK PONG.
    request = b"PING\n"
    dlc.write(request)
    buffer = b""
    deadline = time.monotonic() + 30
    while b"PONG" not in buffer and time.monotonic() < deadline:
        try:
            buffer += await asyncio.wait_for(received.get(), 5)
        except asyncio.TimeoutError:
            continue
    results["spp_request"] = request.decode().strip()
    results["spp_reply"] = buffer.decode(errors="replace").strip()[-200:]
    assert b"OK PONG" in buffer, "no PONG over SPP"
    await connection.disconnect()


async def scratch_link_round_trip(air, port: int, results: dict) -> None:
    """The same InfoRequest, sent the way a browser would via Scratch Link."""
    import base64
    import websockets
    import scratch_link_node

    server = await scratch_link_node.serve(air, port=port)
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/scratch/ble") as ws:
            ids = iter(range(1, 100))

            async def call(method, params):
                request_id = next(ids)
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": request_id,
                                          "method": method, "params": params}))
                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), 90))
                    if message.get("id") == request_id:
                        if "error" in message:
                            raise RuntimeError(f"{method}: {message['error']}")
                        return message.get("result")
                    pending.append(message)

            pending: list = []

            async def notification(method):
                while True:
                    for message in list(pending):
                        if message.get("method") == method:
                            pending.remove(message)
                            return message["params"]
                    pending.append(json.loads(await asyncio.wait_for(ws.recv(), 90)))

            service = str(FD02_SERVICE).lower()
            await call("discover", {"filters": [{"services": [service]}]})
            found = await notification("didDiscoverPeripheral")
            results["scratch_link_discovered"] = found
            await call("connect", {"peripheralId": found["peripheralId"]})
            await call("startNotifications", {
                "serviceId": service, "characteristicId": str(FD02_TX).lower()})
            await call("write", {
                "serviceId": service, "characteristicId": str(FD02_RX).lower(),
                "message": base64.b64encode(cobs_encode(b"\x00")).decode(),
                "encoding": "base64", "withResponse": False})
            buffer = b""
            while not buffer.endswith(b"\x02"):
                change = await notification("characteristicDidChange")
                buffer += base64.b64decode(change["message"])
            payload = cobs_decode(buffer)
            results["scratch_link_info_response_payload"] = payload.hex()
            assert payload[0] == 0x01, payload.hex()
    finally:
        server.close()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renode", type=Path, required=True)
    parser.add_argument("--air-tools", type=Path,
                        help="renode-spike-prime tools/bw-air (default: under --renode, "
                             "or $BW_AIR_TOOLS)")
    parser.add_argument("--hub-port", type=int, default=7481,
                        help="TCP port of the bw-air/1 hub this test starts")
    parser.add_argument("--microbit", action="store_true",
                        help="also put an emulated micro:bit (SoftDevice HLE, "
                             "tools/nrf-softdevice-hle/fake_app.py) on the same air "
                             "and require the central to see and connect to it")
    parser.add_argument("--sdhle-lib", type=Path,
                        help="libnrf_softdevice_hle.so built from labwired-core "
                             "(crates/nrf-softdevice-hle) for --microbit")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--port", type=int, default=34571)
    parser.add_argument("--classic", action="store_true")
    parser.add_argument("--reconnect", action="store_true",
                        help="after the first LE round trip, require a second one")
    parser.add_argument("--skip-le", action="store_true",
                        help="make no LE connection (Classic only)")
    parser.add_argument("--scratch-link", type=int, metavar="PORT",
                        help="make the LE round trip through the Scratch Link gateway")
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--trace-symbol", action="append", default=[],
                        help="log each entry to this firmware symbol (diagnosis)")
    parser.add_argument("--dump", action="append", default=[],
                        help="HOOK=ADDRESS:WORDS: log memory when HOOK runs (diagnosis)")
    parser.add_argument("--watch", action="append", default=[],
                        help="log every 32-bit write to this address (diagnosis)")
    parser.add_argument("--trace-caller", action="append", default=[],
                        help="log each entry to this symbol with its caller (LR)")
    arguments = parser.parse_args()
    logging.basicConfig(level=os.environ.get("BW_AIR_LOG", "INFO"),
                        format="%(asctime)s %(name)s %(message)s")
    arguments.images = arguments.images.resolve()
    workdir = arguments.workdir or Path(tempfile.mkdtemp(prefix="spike-air-"))
    workdir.mkdir(parents=True, exist_ok=True)

    results: dict = {"images": str(arguments.images), "air_tools": str(AIR_TOOLS)}
    air_hub = subprocess.Popen(
        [sys.executable, str(AIR_TOOLS / "airhub.py"), "--tcp",
         f"127.0.0.1:{arguments.hub_port}", "--ws", "", "--log",
         str(workdir / "air.jsonl")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    microbit = None
    await asyncio.sleep(1)
    if arguments.microbit:
        microbit = subprocess.Popen(
            [sys.executable, str(AIR_TOOLS.parent / "nrf-softdevice-hle" / "fake_app.py"),
             "--air", f"127.0.0.1:{arguments.hub_port}", "--addr", MICROBIT_ADDRESS,
             "--secs", str(int(arguments.timeout) + 120)]
            + (["--lib", str(arguments.sdhle_lib)] if arguments.sdhle_lib else []),
            stdout=open(workdir / "microbit.log", "wb"), stderr=subprocess.STDOUT)
    air = Air(f"127.0.0.1:{arguments.hub_port}")
    hub = None
    renode = await start_renode(arguments.renode, arguments.images,
                                arguments.port, workdir, arguments.trace_symbol,
                                arguments.trace_caller, arguments.watch,
                                arguments.dump)
    try:
        hub = await air.attach_hci_client("spike-hub", "127.0.0.1",
                                          arguments.port, HUB_ADDRESS)
        # One LE connection per run, directly or through the Scratch Link
        # gateway: after the first LE link ends the firmware stops processing
        # HCI events (open; see docs/project/simulated-bluetooth-air.md).
        if arguments.microbit:
            await microbit_check(air, results, arguments.timeout)
        if arguments.scratch_link:
            await scratch_link_round_trip(air, arguments.scratch_link, results)
        elif arguments.skip_le:
            pass
        else:
            central = (await air.add_peer("central", CENTRAL_ADDRESS)).device
            started = time.monotonic()
            advertisement = await find_hub(central, arguments.timeout)
            results["advertisement_after_s"] = round(time.monotonic() - started, 1)
            await le_round_trip(central, advertisement, results)
            if arguments.reconnect:
                # A second central after the first link ended: the hub must
                # advertise again and answer again.
                await air.remove("central")
                again = (await air.add_peer("central-2", "02:B1:0E:5A:17:C3")).device
                started = time.monotonic()
                advertisement = await find_hub(again, arguments.timeout)
                results["readvertised_after_s"] = round(time.monotonic() - started, 1)
                second: dict = {}
                await le_round_trip(again, advertisement, second)
                results["second_info_response_payload"] = second["info_response_payload"]
        if arguments.classic:
            # Page only once the hub has enabled page scan, as a real
            # central would only find it then.
            deadline = time.monotonic() + arguments.timeout
            while 0x0C1A not in hub.controller.commands:
                if time.monotonic() > deadline:
                    raise TimeoutError("hub never enabled page scan")
                await asyncio.sleep(0.5)
            await asyncio.sleep(2)
            peer = (await air.add_peer("classic-central", "02:B1:0E:5A:17:C1")).device
            await asyncio.wait_for(classic_round_trip(peer, results), 120)
        results["status"] = "PASS"
        return_code = 0
    except Exception as error:  # report, then fail
        results["status"] = f"FAIL: {type(error).__name__}: {error}"
        return_code = 1
    finally:
        if hub is not None:
            results["hub_hci_commands"] = [f"0x{op:04x}" for op in hub.controller.commands]
            results["hub_vendor_commands"] = hub.controller.vendor_commands
            results["hub_unknown_commands"] = [f"0x{op:04x}" for op in
                                               hub.controller.unknown_commands]
        for process in (microbit, air_hub):
            if process is not None:
                process.terminate()
        try:
            os.killpg(renode.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await renode.wait()
        print(json.dumps(results, indent=2))
        (workdir / "result.json").write_text(json.dumps(results, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
