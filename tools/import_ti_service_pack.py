#!/usr/bin/env python3
"""Install an unmodified TI BTS file as separately licensed local firmware.

The tool recognizes only byte-exact files in the reviewed allowlist. It checks
the public BTS container framing but does not decode, alter, disassemble, or
execute controller commands. It can fetch the pinned file and licence directly
from TI. Separately licensed input and output bytes remain outside Git and CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import struct
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "policy" / "ti-service-packs.json"
DEFAULT_OUTPUT = ROOT / ".local" / "ti" / "cc2564c"
BTS_HEADER_SIZE = 32
BTS_MAGIC = b"BTSB"


class ImportFailure(ValueError):
    """A safe, user-facing import rejection."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_bts(data: bytes) -> int:
    """Validate BTS record boundaries and return the action count."""
    if len(data) < BTS_HEADER_SIZE or data[:4] != BTS_MAGIC:
        raise ImportFailure("input is not a BTSB container")

    offset = BTS_HEADER_SIZE
    actions = 0
    while offset < len(data):
        if len(data) - offset < 4:
            raise ImportFailure(f"truncated BTS action header at offset {offset}")
        _action, payload_size = struct.unpack_from("<HH", data, offset)
        offset += 4
        if payload_size > len(data) - offset:
            raise ImportFailure(
                f"truncated BTS action payload at offset {offset}: "
                f"declared {payload_size}, available {len(data) - offset}"
            )
        offset += payload_size
        actions += 1

    if actions == 0:
        raise ImportFailure("BTS container contains no actions")
    return actions


def load_policy(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    source = document.get("source")
    if (document.get("schema") != 1 or
            not isinstance(document.get("files"), dict) or
            not isinstance(source, dict)):
        raise ImportFailure("unsupported or malformed allowlist")
    for key in ("repository", "commit", "bts_path", "license_path",
                "license_sha256"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise ImportFailure(f"allowlist source is missing {key}")
    return document


def run_git(*arguments: str, cwd: Path) -> None:
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        raise ImportFailure(
            f"official TI fetch failed: {detail[-1] if detail else 'git failed'}"
        )


def fetch_from_ti(policy: dict[str, object], destination: Path) -> tuple[Path, Path]:
    source = policy["source"]
    assert isinstance(source, dict)
    run_git("init", "--quiet", cwd=destination)
    run_git("remote", "add", "origin", str(source["repository"]), cwd=destination)
    run_git("fetch", "--quiet", "--depth=1", "origin", str(source["commit"]),
            cwd=destination)
    run_git("checkout", "--quiet", "FETCH_HEAD", "--",
            str(source["bts_path"]), str(source["license_path"]),
            cwd=destination)
    return destination / str(source["bts_path"]), destination / str(source["license_path"])


def find_license(source: Path, explicit: Path | None) -> tuple[str, bytes]:
    if explicit is not None:
        if not explicit.is_file():
            raise ImportFailure(f"licence file does not exist: {explicit}")
        return explicit.name, explicit.read_bytes()
    if source.is_file() and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            matches = [info for info in archive.infolist()
                       if not info.is_dir() and PurePosixPath(info.filename).name == "LICENSE"]
            if len(matches) == 1:
                return matches[0].filename, archive.read(matches[0])
    roots = [source] if source.is_dir() else [source.parent, source.parent.parent]
    for root in roots:
        candidate = root / "LICENSE"
        if candidate.is_file():
            return str(candidate), candidate.read_bytes()
    raise ImportFailure("the accompanying TI LICENSE was not found; use --license")


def candidates(source: Path) -> list[tuple[str, bytes]]:
    if source.is_file() and zipfile.is_zipfile(source):
        found: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                member = PurePosixPath(info.filename)
                if not info.is_dir() and member.suffix.lower() == ".bts":
                    found.append((info.filename, archive.read(info)))
        return found
    if source.is_file():
        return [(source.name, source.read_bytes())]
    if source.is_dir():
        return [
            (str(path.relative_to(source)), path.read_bytes())
            for path in sorted(source.rglob("*"))
            if path.is_file() and path.suffix.lower() == ".bts"
        ]
    raise ImportFailure(f"input does not exist: {source}")


def select_allowed(
    source: Path, allowlist: dict[str, dict[str, object]]
) -> tuple[str, bytes, str, dict[str, object]]:
    examined = candidates(source)
    if not examined:
        raise ImportFailure("input contains no .bts files")
    matches = []
    for name, data in examined:
        sha256 = digest(data)
        if sha256 in allowlist:
            matches.append((name, data, sha256, allowlist[sha256]))
    if not matches:
        hashes = ", ".join(f"{name}={digest(data)}" for name, data in examined)
        raise ImportFailure(f"no allowlisted BTS file found; examined: {hashes}")
    if len(matches) != 1:
        names = ", ".join(match[0] for match in matches)
        raise ImportFailure(f"input contains multiple allowlisted BTS files: {names}")
    return matches[0]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == data:
            return
        raise ImportFailure(f"refusing to overwrite different local file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def c_header(data: bytes, sha256: str) -> bytes:
    """Create an ignored, build-local byte container without transforming it."""
    rows = []
    for offset in range(0, len(data), 12):
        values = ", ".join(f"0x{value:02x}" for value in data[offset : offset + 12])
        rows.append(f"  {values},")
    text = "\n".join(
        [
            "/* Generated locally from an allowlisted TI firmware file.",
            " * Separately TI-licensed: use only with TI Devices and preserve",
            " * the accompanying LICENSE in any permitted redistribution. */",
            "#ifndef BRICKWRIGHT_LOCAL_TI_BTS_PAYLOAD_H",
            "#define BRICKWRIGHT_LOCAL_TI_BTS_PAYLOAD_H",
            "#include <stddef.h>",
            "#include <stdint.h>",
            f"/* SHA-256: {sha256} */",
            "static const uint8_t brickwright_local_ti_bts_image[] = {",
            *rows,
            "};",
            "static const size_t brickwright_local_ti_bts_image_size =",
            "  sizeof(brickwright_local_ti_bts_image);",
            "#endif",
            "",
        ]
    )
    return text.encode("ascii")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path,
                        help="official BTS file, directory, or ZIP")
    parser.add_argument("--from-ti", action="store_true",
                        help="fetch the pinned file and licence from TI")
    parser.add_argument("--license", type=Path,
                        help="accompanying TI LICENSE for a supplied source")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.from_ti == (arguments.source is not None):
        raise ImportFailure("choose exactly one of SOURCE or --from-ti")
    if arguments.from_ti and arguments.license is not None:
        raise ImportFailure("--license cannot be combined with --from-ti")
    policy = load_policy(arguments.allowlist)
    with tempfile.TemporaryDirectory(prefix="brickwright-ti-fetch-") as temporary:
        if arguments.from_ti:
            source, license_path = fetch_from_ti(policy, Path(temporary))
            license_name, license_data = license_path.name, license_path.read_bytes()
        else:
            assert arguments.source is not None
            source = arguments.source
            license_name, license_data = find_license(source, arguments.license)
        expected_license = str(policy["source"]["license_sha256"])
        license_sha256 = digest(license_data)
        if license_sha256 != expected_license:
            raise ImportFailure(
                f"TI licence hash is not allowlisted: {license_sha256}"
            )
        source_name, data, sha256, metadata = select_allowed(
            source, policy["files"]
        )
    if len(data) != metadata["size"]:
        raise ImportFailure("allowlisted metadata size does not match input")
    actions = validate_bts(data)

    filename = str(metadata["filename"])
    output = arguments.output_dir / filename
    atomic_write(output, data)
    atomic_write(arguments.output_dir / "LICENSE.ti", license_data)
    atomic_write(
        arguments.output_dir / "ti_bts_local_payload.h", c_header(data, sha256)
    )
    manifest = {
        "schema": 1,
        "source_name": source_name,
        "sha256": sha256,
        "size": len(data),
        "actions": actions,
        "metadata": metadata,
        "source": policy["source"],
        "licence": {
            "name": license_name,
            "sha256": license_sha256,
            "scope": "TI-licensed firmware; not MIT/Apache-2.0",
        },
    }
    atomic_write(
        arguments.output_dir / "import-manifest.json",
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    print(f"installed {output}")
    print(f"installed {arguments.output_dir / 'LICENSE.ti'}")
    print(f"sha256 {sha256}; {len(data)} bytes; {actions} BTS actions")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportFailure, OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        print(f"import-ti-service-pack: ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
