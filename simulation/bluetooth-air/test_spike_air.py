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
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bw_air import Air  # noqa: E402
from spike_codec import cobs_decode, cobs_encode  # noqa: E402

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
DISPLAY_STUBS = ("tlc5955_initialize", "tlc5955_update_sync", "tlc5955_set_duty")

MILESTONES = ("__start", "bt_enable", "physical_start_host", "settings_load",
              "daemon_wait_for_stop", "btsensor_transport_set_visible",
              "bt_le_adv_start", "bt_br_set_discoverable")

log = logging.getLogger("spike-air-test")


def renode_script(images: Path, port: int, trace=()) -> str:
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
    lines.append("start")
    return "\n".join(lines) + "\n"


async def start_renode(renode_dir: Path, images: Path, port: int, workdir: Path,
                       trace=()):
    script = workdir / "spike-air.resc"
    script.write_text(renode_script(images, port, trace))
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
    multiplexer = await Client(connection).start()
    dlc = await multiplexer.open_dlc(channel)
    received: asyncio.Queue = asyncio.Queue()
    dlc.sink = received.put_nowait
    results["rfcomm_open"] = True
    await connection.disconnect()


async def scratch_link_round_trip(air, port: int, results: dict) -> None:
    """The same InfoRequest, sent the way a browser would via Scratch Link."""
    import base64
    import websockets
    import scratch_link_gateway

    server = await scratch_link_gateway.serve(air, port=port)
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
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--port", type=int, default=34571)
    parser.add_argument("--classic", action="store_true")
    parser.add_argument("--scratch-link", type=int, metavar="PORT",
                        help="make the LE round trip through the Scratch Link gateway")
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--trace-symbol", action="append", default=[],
                        help="log each entry to this firmware symbol (diagnosis)")
    arguments = parser.parse_args()
    logging.basicConfig(level=os.environ.get("BW_AIR_LOG", "INFO"),
                        format="%(asctime)s %(name)s %(message)s")
    arguments.images = arguments.images.resolve()
    workdir = arguments.workdir or Path(tempfile.mkdtemp(prefix="spike-air-"))
    workdir.mkdir(parents=True, exist_ok=True)

    results: dict = {"images": str(arguments.images)}
    air = Air()
    hub = None
    renode = await start_renode(arguments.renode, arguments.images,
                                arguments.port, workdir, arguments.trace_symbol)
    try:
        hub = await air.attach_hci_client("spike-hub", "127.0.0.1",
                                          arguments.port, HUB_ADDRESS)
        # The hub advertises once: after a peripheral connection Zephyr stops
        # legacy advertising and the firmware does not restart it, so each run
        # makes exactly one LE connection, either directly or through the
        # Scratch Link gateway.
        if arguments.scratch_link:
            await scratch_link_round_trip(air, arguments.scratch_link, results)
        else:
            central = (await air.add_peer("central", CENTRAL_ADDRESS)).device
            started = time.monotonic()
            advertisement = await find_hub(central, arguments.timeout)
            results["advertisement_after_s"] = round(time.monotonic() - started, 1)
            await le_round_trip(central, advertisement, results)
        if arguments.classic:
            peer = (await air.add_peer("classic-central", "02:B1:0E:5A:17:C1")).device
            await classic_round_trip(peer, results)
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
