#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify an isolated native NuttX Apps registry regeneration."""
import argparse, hashlib, json
from pathlib import Path, PurePosixPath

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fail(message: str) -> None:
    raise SystemExit(f"builtin-registry-proof: ERROR: {message}")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    evidence = json.loads(Path(args.evidence).read_text())
    if evidence.get("schema") != "brickwright/generated-input-proof/v1":
        fail("invalid schema")
    repository = Path(args.repository).resolve()
    output_root = Path(args.output_root).resolve()
    for item in evidence.get("generator_inputs", []):
        path = repository / item["path"]
        if not path.is_file() or digest(path) != item["sha256"]:
            fail(f"generator input missing or changed: {item['path']}")
    expected = {}
    for item in evidence.get("outputs", []):
        relative = PurePosixPath(item.get("path", ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            fail("output path escapes root")
        if item.get("disposition") not in {"consumed-generated-input", "metadata-only"}:
            fail(f"invalid output disposition: {relative}")
        if relative.as_posix() in expected:
            fail(f"duplicate output: {relative}")
        expected[relative.as_posix()] = item
    actual = {
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*") if path.is_file()
    }
    if actual != set(expected):
        fail("generated output set differs")
    for relative, item in expected.items():
        if digest(output_root / relative) != item["sha256"]:
            fail(f"generated output hash mismatch: {relative}")
    admitted = {item["path"]: item["sha256"] for item in evidence.get("files", [])}
    concluded = {
        path: item["sha256"] for path, item in expected.items()
        if item["disposition"] == "consumed-generated-input"
    }
    if admitted != concluded:
        fail("admitted generated inputs differ from consumed outputs")
    print(f"builtin-registry-proof: verified {len(expected)} outputs")

if __name__ == "__main__":
    main()
