#!/usr/bin/env python3
"""Fail closed on restricted payloads, build artifacts, and dependency drift."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policy" / "source-policy.json"
TI_POLICY_PATH = ROOT / "policy" / "ti-service-packs.json"


def fail(message: str) -> None:
    print(f"source-policy: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_entries() -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for record in git("ls-files", "-s", "-z").split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        mode, object_id, _stage = metadata.split()
        entries[path] = (mode, object_id)
    return entries


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("schema") != 1:
        fail("unsupported policy schema")

    entries = tracked_entries()
    expected_submodules = policy["pinned_submodules"]
    actual_submodules = {
        path: object_id
        for path, (mode, object_id) in entries.items()
        if mode == "160000"
    }
    if actual_submodules != expected_submodules:
        fail(
            "submodule pins differ from the reviewed baseline:\n"
            f"  expected={expected_submodules}\n  actual={actual_submodules}"
        )

    quarantine = policy["private_baseline_quarantine"]
    allowed_restricted_paths = set(policy.get("allowed_restricted_paths", []))
    if allowed_restricted_paths != set(quarantine):
        fail("allowed restricted paths must exactly match the reviewed quarantine")
    for path, metadata in quarantine.items():
        if path not in entries:
            fail(f"quarantine entry is stale or missing from Git: {path}")
        mode, object_id = entries[path]
        expected_gitlink = metadata.get("gitlink")
        if expected_gitlink is not None:
            if mode != "160000" or object_id != expected_gitlink:
                fail(f"quarantined gitlink changed without review: {path}")
            continue
        expected_hash = metadata.get("sha256")
        actual_hash = sha256(ROOT / path)
        if actual_hash != expected_hash:
            fail(
                f"quarantined file changed without review: {path}\n"
                f"  expected={expected_hash}\n  actual={actual_hash}"
            )

    forbidden_paths = sorted(
        set(policy["forbidden_tracked_paths"]).intersection(entries)
    )
    if forbidden_paths:
        fail("forbidden tracked paths:\n  " + "\n  ".join(forbidden_paths))

    forbidden_hashes = policy["forbidden_sha256"]
    ti_policy = json.loads(TI_POLICY_PATH.read_text(encoding="utf-8"))
    required_ti_hashes = set(ti_policy.get("files", {}))
    ti_source = ti_policy.get("source", {})
    if isinstance(ti_source, dict) and isinstance(ti_source.get("license_sha256"), str):
        required_ti_hashes.add(ti_source["license_sha256"])
    allowed_restricted_hashes = {
        metadata["sha256"] for metadata in quarantine.values()
        if "sha256" in metadata
    }
    missing_ti_hashes = sorted(
        required_ti_hashes.difference(forbidden_hashes).difference(
            allowed_restricted_hashes
        )
    )
    if missing_ti_hashes:
        fail("allowlisted TI material is not forbidden from Git: " +
             ", ".join(missing_ti_hashes))
    for path, (mode, _object_id) in entries.items():
        if mode == "160000":
            continue
        digest = sha256(ROOT / path)
        if path in allowed_restricted_paths:
            continue
        if digest in forbidden_hashes:
            fail(
                f"forbidden content at {path}: {forbidden_hashes[digest]} "
                f"({digest})"
            )

    forbidden_suffixes = tuple(policy["forbidden_tracked_suffixes"])
    forbidden_artifacts = sorted(
        path
        for path, (mode, _object_id) in entries.items()
        if mode != "160000" and path not in allowed_restricted_paths
        and path.lower().endswith(forbidden_suffixes)
    )
    if forbidden_artifacts:
        fail("tracked build artifacts:\n  " + "\n  ".join(forbidden_artifacts))

    forbidden_references = [
        value.lower() for value in policy.get("forbidden_public_references", [])
    ]
    reference_hits = []
    for path, (mode, _object_id) in entries.items():
        if (mode == "160000" or path in allowed_restricted_paths or
                path == str(POLICY_PATH.relative_to(ROOT))):
            continue
        try:
            content = (ROOT / path).read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        for forbidden in forbidden_references:
            if forbidden in path.lower() or forbidden in content:
                reference_hits.append(f"{path}: {forbidden}")
    if reference_hits:
        fail("forbidden public repository references:\n  " +
             "\n  ".join(sorted(reference_hits)))

    print("source-policy: dependency pins and restricted-file policy are intact")
    print(
        "source-policy: allowed target licences: "
        + ", ".join(policy["allowed_project_licenses"])
    )
    if allowed_restricted_paths:
        print(
            "source-policy: exact separately licensed hardware files: "
            + ", ".join(sorted(allowed_restricted_paths))
        )


if __name__ == "__main__":
    main()
