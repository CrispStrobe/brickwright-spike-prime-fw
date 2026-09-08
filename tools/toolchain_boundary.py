#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the pinned compiler boundary and linked-runtime declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

SCHEMA = "brickwright/arm-toolchain-lock/v1"
EVIDENCE_SCHEMA = "brickwright/linked-runtime-evidence/v1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def fail(message: str) -> None:
    raise SystemExit(f"toolchain-boundary: ERROR: {message}")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            value.update(chunk)
    return value.hexdigest()


def load_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != SCHEMA:
        fail("invalid toolchain lock schema")
    archive = lock.get("archive", {})
    if not archive.get("url", "").startswith("https://") or not SHA256.fullmatch(archive.get("sha256", "")):
        fail("archive requires an HTTPS URL and SHA-256")
    if PurePosixPath(archive.get("directory", "")).name != archive.get("directory"):
        fail("archive directory must be one relative component")
    if not lock.get("tools") or len(set(lock["tools"])) != len(lock["tools"]):
        fail("tool list must be nonempty and unique")
    for component, policy in lock.get("runtime_policy", {}).items():
        for field in ("license_expression", "source_repository", "source_commit", "license_url", "license_file", "license_sha256"):
            if not policy.get(field):
                fail(f"runtime policy {component} missing {field}")
        if not re.fullmatch(r"[0-9a-f]{40}", policy["source_commit"]):
            fail(f"runtime policy {component} has a mutable source revision")
        if not policy["license_url"].startswith("https://") or not SHA256.fullmatch(policy["license_sha256"]):
            fail(f"runtime policy {component} lacks immutable licence provenance")
    return lock


def verify_licenses(lock: dict, directory: Path) -> None:
    for component, policy in lock["runtime_policy"].items():
        path = directory / policy["license_file"]
        if not path.is_file() or digest(path) != policy["license_sha256"]:
            fail(f"licence evidence SHA-256 mismatch: {component}")


def verify_install(lock: dict, root: Path) -> None:
    root = root.resolve()
    for name in lock["tools"]:
        tool = root / "bin" / name
        if not tool.is_file() or not os.access(tool, os.X_OK):
            fail(f"missing executable: {tool}")
    compiler = root / "bin" / "arm-none-eabi-gcc"
    result = subprocess.run([compiler, "-dumpfullversion"], text=True, capture_output=True, check=True)
    if result.stdout.strip() != "13.2.1":
        fail(f"unexpected compiler version: {result.stdout.strip()}")


def verify_archive(lock: dict, archive: Path) -> None:
    if not archive.is_file() or digest(archive) != lock["archive"]["sha256"]:
        fail("toolchain archive SHA-256 mismatch")


def verify_evidence(lock: dict, root: Path, path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != EVIDENCE_SCHEMA or not isinstance(document.get("artifacts"), list):
        fail("invalid linked-runtime evidence schema")
    root = root.resolve()
    seen: set[str] = set()
    for artifact in document["artifacts"]:
        relative = PurePosixPath(artifact.get("path", ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            fail("runtime artifact path escapes the toolchain")
        name = relative.as_posix()
        if name in seen:
            fail(f"duplicate runtime artifact: {name}")
        seen.add(name)
        component = artifact.get("component")
        if component not in lock["runtime_policy"]:
            fail(f"undeclared runtime component: {component}")
        actual = (root / name).resolve()
        try:
            actual.relative_to(root)
        except ValueError:
            fail(f"runtime artifact symlink escapes the toolchain: {name}")
        if not actual.is_file() or not SHA256.fullmatch(artifact.get("sha256", "")):
            fail(f"runtime artifact lacks exact file evidence: {name}")
        if digest(actual) != artifact["sha256"]:
            fail(f"runtime artifact SHA-256 mismatch: {name}")
        policy = lock["runtime_policy"][component]
        if artifact.get("license_expression") != policy["license_expression"]:
            fail(f"runtime licence does not match reviewed policy: {name}")
    if not seen:
        fail("linked-runtime evidence is empty")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("policy/arm-toolchain.lock.json"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--toolchain-root", type=Path)
    parser.add_argument("--linked-runtime", type=Path)
    parser.add_argument("--license-dir", type=Path)
    arguments = parser.parse_args()
    lock = load_lock(arguments.lock)
    if arguments.archive:
        verify_archive(lock, arguments.archive)
    if arguments.toolchain_root:
        verify_install(lock, arguments.toolchain_root)
    if arguments.linked_runtime:
        if not arguments.toolchain_root:
            fail("--linked-runtime requires --toolchain-root")
        verify_evidence(lock, arguments.toolchain_root, arguments.linked_runtime)
    if arguments.license_dir:
        verify_licenses(lock, arguments.license_dir)
    if not any((arguments.archive, arguments.toolchain_root, arguments.linked_runtime, arguments.license_dir)):
        fail("nothing to verify")


if __name__ == "__main__":
    main()
