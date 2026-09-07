#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import socket
import subprocess
import sys


def receive_exact(connection, length):
    result = b""
    while len(result) < length:
        block = connection.recv(length - len(result))
        if not block:
            raise RuntimeError("bridge closed before returning an HCI event")
        result += block
    return result


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} BRIDGE")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.argv[1], "--trace", "127.0.0.1", str(port)],
        stderr=subprocess.PIPE,
        text=True,
    )
    connection, _ = listener.accept()
    try:
        # Fragmentation exercises the shared H4 stream parser. An opaque TI
        # vendor command is acknowledged but never interpreted by the bridge.
        connection.sendall(bytes.fromhex("0105"))
        connection.sendall(bytes.fromhex("ff01aa"))
        assert receive_exact(connection, 7) == bytes.fromhex("040e040105ff00")

        connection.sendall(bytes.fromhex("01030c00"))
        assert receive_exact(connection, 7) == bytes.fromhex("040e0401030c00")

        connection.sendall(bytes.fromhex("01091000"))
        assert receive_exact(connection, 13) == bytes.fromhex(
            "040e0a01091000060504030201"
        )
    finally:
        connection.close()
        listener.close()
    _, trace = process.communicate(timeout=5)
    if process.returncode != 0:
        raise RuntimeError("bridge failed")
    assert "command=0xff05 params=1" in trace
    assert "opcode=0xff05 status=0x00" in trace
    assert "command=0x0c03 params=0" in trace
    assert "opcode=0x1009 status=0x00" in trace


if __name__ == "__main__":
    main()
