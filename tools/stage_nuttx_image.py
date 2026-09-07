#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage a protected NuttX kernel/userspace pair under ignored local storage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct


FILES = ("nuttx", "nuttx_user.elf", "nuttx.bin", "nuttx_user.bin")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=("spike-nx", "brickwright"))
    parser.add_argument("build_directory", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(".local/firmware-images"))
    args = parser.parse_args()
    missing = [name for name in FILES if not (args.build_directory / name).is_file()]
    if missing:
        raise SystemExit("missing build outputs: " + ", ".join(missing))

    kernel = (args.build_directory / "nuttx.bin").read_bytes()
    if len(kernel) < 8:
        raise SystemExit("kernel vector table is truncated")
    initial_sp, reset_pc = struct.unpack_from("<II", kernel)
    if not 0x20000000 <= initial_sp <= 0x20050000:
        raise SystemExit(f"invalid initial SP: 0x{initial_sp:08x}")
    if not 0x08008001 <= reset_pc < 0x08080000 or not reset_pc & 1:
        raise SystemExit(f"invalid Thumb reset vector: 0x{reset_pc:08x}")

    destination = args.output / args.name
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": args.name,
        "load_address_kernel": "0x08008000",
        "load_address_userspace": "0x08080000",
        "initial_sp": f"0x{initial_sp:08x}",
        "reset_pc": f"0x{reset_pc:08x}",
        "files": {},
    }
    for name in FILES:
        source = args.build_directory / name
        target = destination / name
        shutil.copyfile(source, target)
        manifest["files"][name] = {
            "sha256": digest(target),
            "size": target.stat().st_size,
        }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"staged {args.name}: SP={manifest['initial_sp']} PC={manifest['reset_pc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
