#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify an isolated native NuttX Apps registry regeneration."""
import argparse, hashlib, json, re
from pathlib import Path, PurePosixPath

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fail(message: str) -> None:
    raise SystemExit(f"builtin-registry-proof: ERROR: {message}")

def safe_relative(value: str, label: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        fail(f"{label} path escapes root")
    return relative

def valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    evidence = json.loads(Path(args.evidence).read_text())
    if evidence.get("schema") != "brickwright/generated-input-proof/v1":
        fail("invalid schema")
    if evidence.get("status") != "exact-output-match": fail("proof status is not exact")
    isolation = evidence.get("isolation", {})
    if isolation.get("network_namespace") != "none" or isolation.get("successful_connects") != 0:
        fail("proof is not network isolated")
    argv = evidence.get("generator_argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        fail("generator argv is missing")
    if not valid_hash(evidence.get("trace_sha256")): fail("trace hash is invalid")
    repository = Path(args.repository).resolve()
    output_root = Path(args.output_root).resolve()
    for item in evidence.get("generator_inputs", []):
        relative = safe_relative(item.get("path", ""), "generator input")
        path = repository / relative
        if path.is_symlink() or not path.is_file() or not valid_hash(item.get("sha256")) or digest(path) != item["sha256"]:
            fail(f"generator input missing or changed: {item['path']}")
    expected = {}
    for item in evidence.get("outputs", []):
        relative = safe_relative(item.get("path", ""), "output")
        if not valid_hash(item.get("sha256")): fail(f"invalid output hash: {relative}")
        if item.get("disposition") not in {"consumed-generated-input", "metadata-only"}:
            fail(f"invalid output disposition: {relative}")
        if relative.as_posix() in expected:
            fail(f"duplicate output: {relative}")
        expected[relative.as_posix()] = item
    paths = list(output_root.rglob("*"))
    if any(path.is_symlink() for path in paths): fail("output tree contains a symlink")
    actual = {path.relative_to(output_root).as_posix() for path in paths if path.is_file()}
    if actual != set(expected):
        fail("generated output set differs")
    for relative, item in expected.items():
        if digest(output_root / relative) != item["sha256"]:
            fail(f"generated output hash mismatch: {relative}")
    admitted = {}
    for item in evidence.get("files", []):
        relative = safe_relative(item.get("path", ""), "admitted input").as_posix()
        if relative in admitted or not valid_hash(item.get("sha256")):
            fail(f"invalid or duplicate admitted input: {relative}")
        admitted[relative] = item["sha256"]
    concluded = {
        path: item["sha256"] for path, item in expected.items()
        if item["disposition"] == "consumed-generated-input"
    }
    if admitted != concluded:
        fail("admitted generated inputs differ from consumed outputs")
    counts = evidence.get("output_set", {})
    if counts.get("consumed_data_file_count") != len(concluded) or counts.get("metadata_output_count") != len(expected) - len(concluded):
        fail("output disposition counts differ")
    print(f"builtin-registry-proof: verified {len(expected)} outputs")

if __name__ == "__main__":
    main()
