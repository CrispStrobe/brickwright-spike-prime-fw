#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one simulated Bluetooth air.

Examples:
  # SPIKE hub in Renode (USART2 exported on 34571), a micro:bit HCI host
  # dialling in on 20120, and a Scratch Link gateway for lite on 20111:
  bw_air_server.py --renode-hci spike=127.0.0.1:34571@02:B1:0E:5A:17:01 \
      --hci-listen 20120 --scratch-link 20111
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bw_air import Air  # noqa: E402
import scratch_link_gateway  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--renode-hci", action="append", default=[],
                        metavar="NAME=HOST:PORT@ADDRESS",
                        help="attach an emulated UART exported as a TCP server")
    parser.add_argument("--hci-listen", type=int, action="append", default=[],
                        metavar="PORT",
                        help="accept HCI hosts (H4 over TCP); one controller each")
    parser.add_argument("--scratch-link", type=int, metavar="PORT",
                        help="serve the Scratch Link protocol on this port")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")

    air = Air()
    for spec in arguments.renode_hci:
        name, rest = spec.split("=", 1)
        endpoint, address = rest.split("@", 1)
        host, port = endpoint.rsplit(":", 1)
        await air.attach_hci_client(name, host, int(port), address)
    for port in arguments.hci_listen:
        await air.serve_hci(port, lambda n, p=port: f"02:B1:0E:{p >> 8:02X}:{p & 0xFF:02X}:{n:02X}")
    if arguments.scratch_link:
        await scratch_link_gateway.serve(air, port=arguments.scratch_link)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
