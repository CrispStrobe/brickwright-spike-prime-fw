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
import hashlib
import struct
import traceback
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
    for index, value in enumerate(argv):
        if value == "--renode" and index + 1 < len(argv):
            candidate = Path(argv[index + 1]).resolve() / "tools" / "bw-air"
            if candidate.is_dir():
                return candidate
    configured = os.environ.get("BW_AIR_TOOLS")
    if configured:
        return Path(configured).resolve()
    raise SystemExit("Specify --air-tools or BW_AIR_TOOLS when --renode has no tools/bw-air")


AIR_TOOLS = air_tools(sys.argv)
if not (AIR_TOOLS / "hci_node.py").is_file():
    raise SystemExit(f"Missing bw-air tools: {AIR_TOOLS}")
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

MILESTONES = ("__start", "bt_enable", "physical_start_host", "settings_load",
              "daemon_wait_for_stop", "btsensor_transport_set_visible",
              "bt_le_adv_start", "bt_br_set_discoverable")

log = logging.getLogger("spike-air-test")


def renode_script(images: Path, port: int, trace=(), callers=(), watches=(),
                  dumps=(), existing_filesystem: Path | None = None) -> str:
    manifest = json.loads((images / "manifest.json").read_text())
    pc = int(manifest["reset_pc"], 16) & ~1
    lines = [
        f"include @{DEVICES}",
        "mach create \"spike\"",
        f"machine LoadPlatformDescription @{PLATFORM}",
    ]
    if existing_filesystem is not None:
        lines.extend([
            f"include @{ROOT / 'tools' / 'renode_load_littlefs_fixture.py'}",
            f"load_littlefs_fixture @{existing_filesystem}",
        ])
    lines.extend([
        f"sysbus LoadELF @{images / 'nuttx'}",
        f"sysbus LoadELF @{images / 'nuttx_user.elf'}",
        "cpu VectorTableOffset 0x08008000",
        f"cpu SP {manifest['initial_sp']}",
        f"cpu PC 0x{pc:08x}",
        f"emulation CreateServerSocketTerminal {port} \"hci\" false",
        "connector Connect sysbus.usart2 hci",
    ])
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
                       trace=(), callers=(), watches=(), dumps=(),
                       existing_filesystem: Path | None = None):
    script = workdir / "spike-air.resc"
    script.write_text(renode_script(images, port, trace, callers, watches, dumps,
                                    existing_filesystem))
    with open(workdir / "renode.log", "wb") as logfile:
        return await asyncio.create_subprocess_exec(
            str(renode_dir / "renode"), "--disable-gui", "--console", "--plain",
            str(script), stdin=asyncio.subprocess.PIPE, stdout=logfile,
            stderr=asyncio.subprocess.STDOUT, start_new_session=True)


async def find_hub(device, timeout: float):
    found: asyncio.Future = asyncio.get_running_loop().create_future()

    def on_advertisement(advertisement):
        if (str(advertisement.address).split("/")[0].upper() == HUB_ADDRESS
                and not found.done()):
            found.set_result(advertisement)

    device.on("advertisement", on_advertisement)
    try:
        async with asyncio.timeout(timeout):
            await device.start_scanning(filter_duplicates=True)
            return await found
    finally:
        device.remove_listener("advertisement", on_advertisement)
        active_error = sys.exc_info()[0] is not None
        try:
            await asyncio.wait_for(device.stop_scanning(), 10)
        except Exception:
            if not active_error:
                raise


async def le_round_trip(central, advertisement, results: dict) -> None:
    from spike_frames import FrameBuffer, receive_info

    connection = None
    try:
        async with asyncio.timeout(180):
            started = time.monotonic()
            connection = await central.connect(advertisement.address,
                                               transport=PhysicalTransport.LE,
                                               timeout=60)
            results["le_connect_s"] = round(time.monotonic() - started, 1)
            peer = Peer(connection)
            await peer.discover_services([FD02_SERVICE])
            services = peer.get_services_by_uuid(FD02_SERVICE)
            assert len(services) == 1, "Expected one FD02 service"
            await services[0].discover_characteristics()
            rx_matches = services[0].get_characteristics_by_uuid(FD02_RX)
            tx_matches = services[0].get_characteristics_by_uuid(FD02_TX)
            assert len(rx_matches) == len(tx_matches) == 1, "Expected FD02 RX and TX"
            rx, tx = rx_matches[0], tx_matches[0]
            results["gatt_fd02"] = {"rx_handle": rx.handle, "tx_handle": tx.handle}
            frames = asyncio.Queue(maxsize=64)
            errors = asyncio.get_running_loop().create_future()
            buffer = FrameBuffer()

            def on_notify(value):
                if errors.done():
                    return
                try:
                    for frame in buffer.feed(value):
                        frames.put_nowait(frame)
                except Exception as error:
                    errors.set_result(error)

            await peer.subscribe(tx, on_notify)
            request = cobs_encode(b"\x00")
            results["info_request_frame"] = request.hex()
            await peer.write_value(rx, request, with_response=False)
            frame, payload, fields = await receive_info(frames, errors)
            results["info_response_frame"] = frame.hex()
            results["info_response_payload"] = payload.hex()
            results["info_response_fields"] = fields
    finally:
        if connection is not None:
            active_error = sys.exc_info()[0] is not None
            try:
                await asyncio.wait_for(connection.disconnect(), 10)
                results["le_disconnected"] = True
            except Exception:
                if not active_error:
                    raise


async def serve_and_run(air, arguments, results: dict) -> None:
    """Serve Scratch Link on the air and run an outside client against it.

    Used to put a real browser (Brickwright lite under Playwright) on the air:
    the command is started once the hub advertises, and its exit status
    decides the run. Its stdout is kept in the results."""
    import scratch_link_node

    server = await scratch_link_node.serve(air, port=arguments.serve_scratch_link)
    process = None
    try:
        process = await asyncio.create_subprocess_shell(
            arguments.then, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        output, _ = await asyncio.wait_for(process.communicate(), arguments.timeout + 600)
        results["then_exit"] = process.returncode
        results["then_output"] = output.decode(errors="replace")[-4000:]
        assert process.returncode == 0, f"client failed ({process.returncode})"
    finally:
        await stop_owned_process(process)
        server.close()
        await asyncio.wait_for(server.wait_closed(), 10)


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


async def classic_round_trip(central, results: dict,
                             legacy_extension: Path | None = None) -> None:
    from bumble.rfcomm import Client, find_rfcomm_channel_with_uuid
    from bumble.sdp import Client as SdpClient  # noqa: F401

    connection = await central.connect(HUB_ADDRESS,
                                       transport=PhysicalTransport.BR_EDR,
                                       timeout=60)
    results["classic_connected"] = True
    try:
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
        if legacy_extension is not None:
            await legacy_round_trips(dlc, received, legacy_extension, results)
    finally:
        active_error = sys.exc_info()[0] is not None
        try:
            await asyncio.wait_for(connection.disconnect(), 10)
            results["classic_disconnected"] = True
        except Exception:
            if not active_error:
                raise


async def legacy_round_trips(dlc, received, extension: Path, results: dict) -> None:
    """Every legacy JSON request lite's extension sends, one at a time."""
    import lite_legacy_messages as legacy

    emitted = legacy.methods_in_extension(extension)
    covered = set(legacy.REQUESTS)
    results["legacy_methods_in_lite"] = sorted(emitted)
    assert emitted == covered, (
        f"lite emits {sorted(emitted - covered)} not covered; "
        f"covered but not emitted {sorted(covered - emitted)}")
    replies = {}
    pending = b""
    for index, method in enumerate(sorted(emitted)):
        request_id = f"l{index:03d}"
        dlc.write(legacy.request_line(method, request_id))
        lines = []
        deadline = time.monotonic() + 20
        reply = None
        while reply is None and time.monotonic() < deadline:
            try:
                pending += await asyncio.wait_for(received.get(), 2)
            except asyncio.TimeoutError:
                continue
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                lines.append(line.decode(errors="replace"))
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if message.get("i") == request_id:
                    reply = message
        assert reply is not None, f"{method}: no reply carrying {request_id}"
        entry = {"reply": reply}
        if method == "trigger_current_state":
            unsolicited = [json.loads(l) for l in lines if l.startswith("{\"m\"")]
            entry["state"] = [m for m in unsolicited if m.get("m") in (0, 2)]
            assert {m["m"] for m in entry["state"]} == {0, 2}, lines
        replies[method] = entry
    results["legacy_replies"] = replies


async def scratch_link_round_trip(air, port: int, results: dict) -> None:
    """Bounded complete InfoRequest through the actual Scratch Link gateway."""
    import base64
    import websockets
    import scratch_link_node
    from spike_frames import FrameBuffer, info_response

    server = await scratch_link_node.serve(air, port=port)
    try:
        async with asyncio.timeout(180):
            async with websockets.connect(f"ws://127.0.0.1:{port}/scratch/ble") as ws:
                ids = iter(range(1, 100))
                pending = []

                def remember(message):
                    if len(pending) >= 64:
                        raise ValueError('Scratch Link pending-message bound exceeded')
                    pending.append(message)

                async def call(method, params):
                    request_id = next(ids)
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": request_id,
                                              "method": method, "params": params}))
                    while True:
                        message = json.loads(await ws.recv())
                        if message.get("id") == request_id:
                            if "error" in message:
                                raise RuntimeError(f"{method}: {message['error']}")
                            return message.get("result")
                        remember(message)

                async def notification(method):
                    while True:
                        for message in list(pending):
                            if message.get("method") == method:
                                pending.remove(message)
                                return message["params"]
                        remember(json.loads(await ws.recv()))

                service = str(FD02_SERVICE).lower()
                await call("discover", {"filters": [{"services": [service]}]})
                while True:
                    found = await notification("didDiscoverPeripheral")
                    if str(found["peripheralId"]).split("/")[0].upper() == HUB_ADDRESS:
                        break
                results["scratch_link_discovered"] = found
                await call("connect", {"peripheralId": found["peripheralId"]})
                await call("startNotifications", {
                    "serviceId": service, "characteristicId": str(FD02_TX).lower()})
                await call("write", {
                    "serviceId": service, "characteristicId": str(FD02_RX).lower(),
                    "message": base64.b64encode(cobs_encode(b"\x00")).decode(),
                    "encoding": "base64", "withResponse": False})
                buffer = FrameBuffer()
                while True:
                    change = await notification("characteristicDidChange")
                    for frame in buffer.feed(base64.b64decode(change["message"], validate=True)):
                        payload = cobs_decode(frame)
                        if not payload:
                            raise ValueError('Empty SPIKE notification payload')
                        if payload[0] == 1:
                            fields = info_response(payload)
                            results["scratch_link_info_response_payload"] = payload.hex()
                            results["scratch_link_info_response_fields"] = fields
                            await ws.close()
                            results["scratch_link_websocket_closed"] = True
                            return
    finally:
        server.close()
        await asyncio.wait_for(server.wait_closed(), 10)


def image_receipt(images):
    manifest = json.loads((images / "manifest.json").read_text())
    if manifest.get("name") != "brickwright-simulation":
        raise ValueError("Use the staged TI-free simulation-hci pair")
    expected = {"nuttx", "nuttx_user.elf", "nuttx.bin", "nuttx_user.bin"}
    if set(manifest.get("files", {})) != expected:
        raise ValueError("Protected pair manifest has unexpected files")
    for name in sorted(expected):
        data = (images / name).read_bytes()
        recorded = manifest["files"][name]
        if len(data) != recorded["size"] or hashlib.sha256(data).hexdigest() != recorded["sha256"]:
            raise ValueError(f"Protected image differs from manifest: {name}")
    sp, pc = struct.unpack_from("<II", (images / "nuttx.bin").read_bytes())
    if (sp != int(manifest["initial_sp"], 16) or pc != int(manifest["reset_pc"], 16)
            or not 0x20000000 <= sp <= 0x20050000
            or not 0x08008001 <= pc < 0x08060000 or not pc & 1):
        raise ValueError("Protected image vector table differs")
    return manifest


async def stop_owned_process(process):
    if process is None:
        return
    asynchronous = isinstance(process, asyncio.subprocess.Process)
    # The leader may have exited while its children still own this group.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        if asynchronous:
            await asyncio.wait_for(process.wait(), 5)
        else:
            await asyncio.to_thread(process.wait, timeout=5)
    except (asyncio.TimeoutError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if asynchronous:
            await asyncio.wait_for(process.wait(), 5)
        else:
            await asyncio.to_thread(process.wait, timeout=5)
    # Give descendants a short opportunity to exit/reap after SIGTERM.
    await asyncio.sleep(0.1)
    # An exited leader cannot wait for a child that ignores SIGTERM.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


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
    parser.add_argument("--existing-filesystem", type=Path,
                        help="explicit validated synthetic LittleFS fixture directory; default is erased flash")
    parser.add_argument("--port", type=int, default=34571)
    parser.add_argument("--classic", action="store_true")
    parser.add_argument("--serve-scratch-link", type=int, default=20111,
                        metavar="PORT", help="Scratch Link port for --then")
    parser.add_argument("--then", metavar="COMMAND",
                        help="serve Scratch Link on the air and run COMMAND "
                             "(e.g. a browser test of lite); its exit decides")
    parser.add_argument("--lite-extension", type=Path,
                        help="lite's spikeprime extension index.js: with --classic, "
                             "send every legacy JSON request it emits over SPP")
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
    if sys.version_info < (3, 11):
        parser.error("Bluetooth-air tests require Python 3.11 or later")
    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    if arguments.reconnect and (arguments.skip_le or arguments.scratch_link or arguments.then):
        parser.error("--reconnect requires the direct LE path")
    arguments.images = arguments.images.resolve()
    workdir = arguments.workdir or Path(tempfile.mkdtemp(prefix="spike-air-"))
    workdir.mkdir(parents=True, exist_ok=True)

    results: dict = {"images": str(arguments.images), "air_tools": str(AIR_TOOLS),
                     "status": "RUNNING", "storage": "initially-erased"}
    air_hub = microbit = renode = hub = None
    air = Air(f"127.0.0.1:{arguments.hub_port}")
    return_code = 1
    try:
        results["image_manifest"] = image_receipt(arguments.images)
        if arguments.existing_filesystem is not None:
            arguments.existing_filesystem = arguments.existing_filesystem.resolve()
            sys.path.insert(0, str(ROOT / "tools"))
            from renode_load_littlefs_fixture import validate_fixture
            _, results["fixture_receipt"] = validate_fixture(str(arguments.existing_filesystem))
            results["storage"] = "explicit-existing-filesystem"
        async with asyncio.timeout(arguments.timeout + 600):
            air_hub = subprocess.Popen(
                [sys.executable, str(AIR_TOOLS / "airhub.py"), "--tcp",
                 f"127.0.0.1:{arguments.hub_port}", "--ws", "", "--log",
                 str(workdir / "air.jsonl")],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            await asyncio.sleep(1)
            if arguments.microbit:
                microbit = subprocess.Popen(
                    [sys.executable, str(AIR_TOOLS.parent / "nrf-softdevice-hle" / "fake_app.py"),
                     "--air", f"127.0.0.1:{arguments.hub_port}", "--addr", MICROBIT_ADDRESS,
                     "--secs", str(int(arguments.timeout) + 120)]
                    + (["--lib", str(arguments.sdhle_lib)] if arguments.sdhle_lib else []),
                    stdout=open(workdir / "microbit.log", "wb"), stderr=subprocess.STDOUT, start_new_session=True)
            renode = await start_renode(arguments.renode, arguments.images,
                                        arguments.port, workdir, arguments.trace_symbol,
                                        arguments.trace_caller, arguments.watch,
                                        arguments.dump, arguments.existing_filesystem)
            hub = await air.attach_hci_client("spike-hub", "127.0.0.1",
                                              arguments.port, HUB_ADDRESS)
            # Reconnection is a separate full discovery and request on a new peer.
            if arguments.then:
                await serve_and_run(air, arguments, results)
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
                    results["second_le_round_trip"] = second
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
                await asyncio.wait_for(
                    classic_round_trip(peer, results, arguments.lite_extension), 240)
            assert 0x0C03 in hub.controller.commands, "Controller never received HCI Reset"
            assert not hub.controller.vendor_commands, "Unexpected vendor HCI commands"
            assert not hub.controller.unknown_commands, "Unsupported HCI commands"
            if "MILESTONE daemon_wait_for_stop" not in (workdir / "renode.log").read_text(errors="replace"):
                raise AssertionError("Firmware did not reach daemon readiness")
            results["script_sha256"] = hashlib.sha256((workdir / "spike-air.resc").read_bytes()).hexdigest()
            results["status"] = "PASS"
            return_code = 0
    except Exception as error:  # report, then fail
        results["status"] = f"FAIL: {type(error).__name__}: {error}"
        results["traceback"] = traceback.format_exc()
        return_code = 1
    except asyncio.CancelledError:
        results["status"] = "FAIL: cancelled"
        raise
    finally:
        if hub is not None:
            results["hub_hci_commands"] = [f"0x{op:04x}" for op in hub.controller.commands]
            results["hub_vendor_commands"] = hub.controller.vendor_commands
            results["hub_unknown_commands"] = [f"0x{op:04x}" for op in
                                               hub.controller.unknown_commands]
        cleanup_errors = []
        pumps = [station.extra["pump"] for station in list(air.stations.values())
                 if "pump" in station.extra]
        for name in list(air.stations):
            try:
                await asyncio.wait_for(air.remove(name), 5)
            except Exception as error:
                cleanup_errors.append(str(error))
        for process in (renode, microbit, air_hub):
            try:
                await stop_owned_process(process)
            except Exception as error:
                cleanup_errors.append(str(error))
        for pump in pumps:
            pump.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)
        if cleanup_errors:
            results["cleanup_errors"] = cleanup_errors
            if results["status"] == "PASS":
                results["status"] = "FAIL: process cleanup"
                return_code = 1
        print(json.dumps(results, indent=2))
        (workdir / "result.json").write_text(json.dumps(results, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
