#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Copy a verified source-closure manifest into an otherwise empty tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


def fail(message: str) -> None:
    raise SystemExit(f"materialize-source-closure: ERROR: {message}")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_relative(value: str, label: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        fail(f"{label} is not a safe relative path")
    return Path(*path.parts)


def load_roots(declaration: Path, repository: Path) -> dict[str, tuple[Path, Path]]:
    document = json.loads(declaration.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(document.get("roots"), list):
        fail("invalid roots declaration")
    result: dict[str, tuple[Path, Path]] = {}
    for item in document["roots"]:
        name = item.get("name")
        if not isinstance(name, str) or not name or name in result:
            fail("invalid or duplicate source root")
        relative = Path() if item.get("path") == "." else safe_relative(item.get("path", ""), "root path")
        source = (repository / relative).resolve()
        try:
            source.relative_to(repository)
        except ValueError:
            fail(f"source root escapes repository: {name}")
        result[name] = (source, relative)
    return result


def copy_checked(source: Path, destination: Path, expected: str) -> None:
    if not source.is_file() or digest(source) != expected:
        fail("source input is missing or changed")
    if destination.exists():
        if not destination.is_file() or digest(destination) != expected:
            fail("conflicting closure destination")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=True)
    if digest(destination) != expected:
        fail("copied input failed hash verification")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    arguments = parser.parse_args()

    repository = arguments.repository.resolve()
    destination = arguments.destination.resolve()
    if destination == repository or repository in destination.parents:
        fail("destination must be outside the source repository")
    if destination.exists() and any(destination.iterdir()):
        fail("destination is not empty")
    destination.mkdir(parents=True, exist_ok=True)

    roots = load_roots(arguments.roots, repository)
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), list):
        fail("invalid source-closure manifest")

    copied: dict[Path, str] = {}
    for item in manifest["files"]:
        root_name = item.get("source_root")
        if root_name not in roots:
            fail("manifest names an undeclared source root")
        source_root, destination_root = roots[root_name]
        relative = safe_relative(item.get("path", ""), "manifest path")
        target = destination_root / relative
        expected = item.get("sha256")
        if not isinstance(expected, str):
            fail("manifest input lacks SHA-256")
        if target in copied and copied[target] != expected:
            fail("manifest inputs collide at destination")
        copy_checked(source_root / relative, destination / target, expected)
        copied[target] = expected

    for item in manifest.get("generated_inputs", []):
        relative = safe_relative(item.get("path", ""), "generated input path")
        expected = item.get("sha256")
        if not isinstance(expected, str):
            fail("generated input lacks SHA-256")
        if relative in copied and copied[relative] != expected:
            fail("generated input collides at destination")
        copy_checked(repository / relative, destination / relative, expected)
        copied[relative] = expected

    print(f"materialize-source-closure: copied {len(copied)} files")


if __name__ == "__main__":
    main()
