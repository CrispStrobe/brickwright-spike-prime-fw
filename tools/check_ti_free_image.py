#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail if a simulation image or its build carries TI service-pack material.

Two independent checks:

1. Image scan. The reviewed fingerprint in policy/ti-service-pack-fingerprint.json
   holds SHA-256 digests of the service pack's 256-byte chunks (chunk i covers
   bytes [256*i, 256*i+256); the final chunk is the last 256 bytes). The
   fingerprint is derived data: it stores only digests (a SHA-256 and a 61-bit
   polynomial rolling hash per chunk), contains no TI bytes, and cannot
   reconstruct them. Every 256-byte window of every scanned file is compared
   against it, so an embedded copy is found at any alignment and any offset. The report names
   how many of the service pack's chunks each file contains.

2. Build-reference check. A verbose build log and the build tree's dependency
   files must not name the service pack, its vendored directory, the local
   import directory, or the importer. The configured image must select the
   simulation profile and must not define the embedded payload symbol.

The byte comparison is opaque: nothing here parses, decodes, or interprets the
service pack's contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINGERPRINT = ROOT / "policy" / "ti-service-pack-fingerprint.json"
CHUNK = 256
ROLL_BASE = 257
ROLL_MOD = (1 << 61) - 1
SIM_OPTION = "CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK"
PAYLOAD_SYMBOL = "brickwright_local_ti_bts_image"

# Anything naming the service pack, where it used to be vendored, where the
# hardware build imports it, or the importer itself.
REFERENCE_PATTERNS = (
    re.compile(r"TIInit_[0-9.]+\.bts", re.IGNORECASE),
    re.compile(r"\.bts\b", re.IGNORECASE),
    re.compile(r"third_party/ti-cc2564c"),
    re.compile(r"\.local/ti/"),
    re.compile(r"import_ti_service_pack"),
    re.compile(r"ti_bts_local_payload"),
)
DEPENDENCY_NAMES = (".depend", "Make.dep")
DEPENDENCY_SUFFIXES = (".d",)


def chunks(data: bytes) -> list[bytes]:
    if len(data) < CHUNK:
        raise SystemExit("service pack is shorter than one chunk")
    result = [data[offset:offset + CHUNK]
              for offset in range(0, len(data) - CHUNK + 1, CHUNK)]
    if len(data) % CHUNK:
        result.append(data[-CHUNK:])
    return result


def roll(window: bytes) -> int:
    value = 0
    for byte in window:
        value = (value * ROLL_BASE + byte) % ROLL_MOD
    return value


def fingerprint_of(data: bytes) -> dict[str, object]:
    pieces = chunks(data)
    return {
        "schema": 1,
        "description": (
            "Rolling hash and SHA-256 of each 256-byte chunk of the TI "
            "CC2564C service pack; derived data used only to detect embedded "
            "copies. Contains no service-pack bytes."
        ),
        "service_pack_sha256": hashlib.sha256(data).hexdigest(),
        "service_pack_size": len(data),
        "chunk_size": CHUNK,
        "rolling_hash": {"base": ROLL_BASE, "modulus": ROLL_MOD},
        "chunks": [
            {"rolling": roll(piece),
             "sha256": hashlib.sha256(piece).hexdigest()}
            for piece in pieces
        ],
    }


def load_fingerprint(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if (document.get("schema") != 1 or document.get("chunk_size") != CHUNK or
            document.get("rolling_hash") != {"base": ROLL_BASE,
                                              "modulus": ROLL_MOD} or
            not document.get("chunks")):
        raise SystemExit(f"unsupported fingerprint: {path}")
    return document


def scan(data: bytes, fingerprint: dict[str, object]) -> dict[int, list[int]]:
    """Return {chunk index: [offsets]} for every chunk found in data."""
    by_roll: dict[int, list[tuple[int, str]]] = {}
    for index, entry in enumerate(fingerprint["chunks"]):
        by_roll.setdefault(entry["rolling"], []).append((index, entry["sha256"]))
    found: dict[int, list[int]] = {}
    if len(data) < CHUNK:
        return found
    high = pow(ROLL_BASE, CHUNK - 1, ROLL_MOD)
    value = roll(data[:CHUNK])
    last = len(data) - CHUNK
    start = 0
    while True:
        entries = by_roll.get(value)
        if entries:
            digest = hashlib.sha256(data[start:start + CHUNK]).hexdigest()
            for index, expected in entries:
                if digest == expected:
                    found.setdefault(index, []).append(start)
        if start == last:
            return found
        value = ((value - data[start] * high) * ROLL_BASE +
                 data[start + CHUNK]) % ROLL_MOD
        start += 1


def reference_hits(text: str) -> list[str]:
    return sorted({match.group(0) for pattern in REFERENCE_PATTERNS
                   for match in pattern.finditer(text)})


def dependency_files(build_root: Path) -> list[Path]:
    result = []
    for path in build_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in DEPENDENCY_NAMES or path.suffix in DEPENDENCY_SUFFIXES:
            result.append(path)
    return sorted(result)


def elf_defines(elf: Path, symbol: str) -> bool:
    attempted = []
    for name in ("arm-none-eabi-nm", "llvm-nm", "nm"):
        nm = shutil.which(name)
        if nm is None:
            continue
        attempted.append(name)
        try:
            output = subprocess.run([nm, str(elf)], check=True, text=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL).stdout
        except (OSError, subprocess.CalledProcessError):
            continue
        return any(line.split()[-1] == symbol for line in output.splitlines()
                   if line.strip())
    detail = ", ".join(attempted) if attempted else "no nm implementation found"
    raise SystemExit(f"cannot read symbols from {elf} ({detail})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="*", type=Path,
                        help="image files to scan (bin, hex payload, ELF)")
    parser.add_argument("--fingerprint", type=Path, default=DEFAULT_FINGERPRINT)
    parser.add_argument("--bts", type=Path,
                        help="local service pack: verify the fingerprint matches it")
    parser.add_argument("--write-fingerprint", action="store_true",
                        help="write the fingerprint derived from --bts and exit")
    parser.add_argument("--build-log", type=Path,
                        help="verbose (V=1) build log to check for references")
    parser.add_argument("--build-root", type=Path, action="append", default=[],
                        help="build tree whose dependency files are checked")
    parser.add_argument("--config", type=Path,
                        help="NuttX .config that must select the simulation profile")
    parser.add_argument("--elf", type=Path, action="append", default=[],
                        help="ELF that must not define the payload symbol")
    arguments = parser.parse_args()

    if arguments.write_fingerprint:
        if arguments.bts is None:
            parser.error("--write-fingerprint requires --bts")
        document = fingerprint_of(arguments.bts.read_bytes())
        arguments.fingerprint.write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {arguments.fingerprint}: {len(document['chunks'])} chunks")
        return 0

    fingerprint = load_fingerprint(arguments.fingerprint)
    total = len(fingerprint["chunks"])
    failures: list[str] = []

    if arguments.bts is not None:
        actual = fingerprint_of(arguments.bts.read_bytes())
        if actual["chunks"] != fingerprint["chunks"]:
            failures.append("fingerprint does not match the supplied service pack")
        else:
            print(f"ti-free: fingerprint matches {arguments.bts.name} ({total} chunks)")

    if not arguments.images:
        failures.append("no image supplied")
    for image in arguments.images:
        found = scan(image.read_bytes(), fingerprint)
        print(f"ti-free: {image}: {len(found)}/{total} service-pack chunks present")
        if found:
            first = min(offset for offsets in found.values() for offset in offsets)
            failures.append(
                f"{image} contains {len(found)}/{total} service-pack chunks "
                f"(first at offset 0x{first:x})")

    if arguments.build_log is not None:
        hits = reference_hits(arguments.build_log.read_text(errors="replace"))
        print(f"ti-free: build log references: {len(hits)}")
        if hits:
            failures.append("build log references the service pack: " +
                            ", ".join(hits))
    for build_root in arguments.build_root:
        referencing = []
        files = dependency_files(build_root)
        for path in files:
            hits = reference_hits(path.read_text(errors="replace"))
            if hits:
                referencing.append(f"{path}: {', '.join(hits)}")
        print(f"ti-free: {build_root}: {len(files)} dependency files, "
              f"{len(referencing)} referencing the service pack")
        failures.extend(referencing)

    if arguments.config is not None:
        config = arguments.config.read_text()
        if f"{SIM_OPTION}=y" not in config.splitlines():
            failures.append(f"{arguments.config} does not select {SIM_OPTION}")
        else:
            print(f"ti-free: {arguments.config.name} selects {SIM_OPTION}")
    for elf in arguments.elf:
        if elf_defines(elf, PAYLOAD_SYMBOL):
            failures.append(f"{elf} defines {PAYLOAD_SYMBOL}")
        else:
            print(f"ti-free: {elf.name} does not define {PAYLOAD_SYMBOL}")

    if failures:
        for failure in failures:
            print(f"ti-free: FAIL: {failure}", file=sys.stderr)
        return 1
    print("ti-free: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
