#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The air carries traffic between an HCI host that dials in and a peer.

No emulator is needed: a bumble host stands in for an emulated device (for
example a micro:bit whose SoftDevice emulation speaks HCI), connects to the
air's HCI port over TCP, and serves a GATT service. A second station, the
in-process central, finds it by advertisement, connects, writes, and receives
a notification. A third station attaches over the same HCI port to show that
several dial-in devices share one air and see each other's advertisements.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bw_air import Air  # noqa: E402

from bumble.core import UUID, PhysicalTransport  # noqa: E402
from bumble.device import Device, Peer  # noqa: E402
from bumble.gatt import Characteristic, CharacteristicValue, Service  # noqa: E402
from bumble.hci import Address  # noqa: E402
from bumble.transport import open_transport  # noqa: E402

SERVICE = UUID("6e400001-b5a3-f393-e0a9-e50e24dcca9e")  # Nordic UART, as micro:bit
RX = UUID("6e400002-b5a3-f393-e0a9-e50e24dcca9e")
TX = UUID("6e400003-b5a3-f393-e0a9-e50e24dcca9e")
PORT = 20129


async def dial_in_peripheral(name: str, index: int):
    transport = await open_transport(f"tcp-client:127.0.0.1:{PORT}")
    device = Device.with_hci(name, Address(f"C1:B1:0E:00:00:{index:02X}"),
                             transport.source, transport.sink)
    tx = Characteristic(TX, Characteristic.Properties.NOTIFY,
                        Characteristic.READABLE, b"")

    def on_write(connection, value):
        asyncio.ensure_future(device.notify_subscribers(tx, b"echo:" + value))

    rx = Characteristic(RX, Characteristic.Properties.WRITE_WITHOUT_RESPONSE |
                        Characteristic.Properties.WRITE,
                        Characteristic.WRITEABLE, CharacteristicValue(write=on_write))
    device.add_service(Service(SERVICE, [rx, tx]))
    await device.power_on()
    await device.start_advertising(auto_restart=True)
    return device, transport


async def main() -> int:
    air = Air()
    await air.serve_hci(PORT, lambda n: f"02:B1:0E:00:00:{n:02X}")
    peripheral, transport = await dial_in_peripheral("microbit-stand-in", 1)
    other, other_transport = await dial_in_peripheral("second-device", 2)
    central = (await air.add_peer("central", "02:B1:0E:00:00:C0")).device

    seen: dict[str, asyncio.Future] = {}
    loop = asyncio.get_running_loop()
    wanted = {"C1:B1:0E:00:00:01", "C1:B1:0E:00:00:02"}
    for address in wanted:
        seen[address] = loop.create_future()

    def on_advertisement(advertisement):
        key = str(advertisement.address).split("/")[0]
        if key in seen and not seen[key].done():
            seen[key].set_result(advertisement)

    central.on("advertisement", on_advertisement)
    await central.start_scanning()
    advertisements = await asyncio.wait_for(asyncio.gather(*seen.values()), 20)
    await central.stop_scanning()
    print(f"air: central saw {len(advertisements)} dial-in advertisers: "
          + ", ".join(sorted(wanted)))

    connection = await central.connect(advertisements[0].address,
                                       transport=PhysicalTransport.LE, timeout=20)
    peer = Peer(connection)
    await peer.discover_services([SERVICE])
    service = peer.get_services_by_uuid(SERVICE)[0]
    await service.discover_characteristics()
    rx = service.get_characteristics_by_uuid(RX)[0]
    tx = service.get_characteristics_by_uuid(TX)[0]
    received: asyncio.Queue = asyncio.Queue()
    await peer.subscribe(tx, received.put_nowait)
    await peer.write_value(rx, b"hello", with_response=True)
    value = await asyncio.wait_for(received.get(), 10)
    print(f"air: GATT write/notify round trip -> {bytes(value)!r}")
    assert bytes(value) == b"echo:hello"
    await connection.disconnect()
    await transport.close()
    await other_transport.close()
    print("air: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
