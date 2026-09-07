#!/usr/bin/env python3
"""Import the reviewed Zephyr host subset from an exact local Git checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "third_party" / "zephyr-host" / "manifest.json"
DEST = ROOT / "third_party" / "zephyr-host" / "upstream"
LOCK = ROOT / "third_party" / "zephyr-host" / "files.sha256"


def git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def selected_paths(manifest: dict) -> list[str]:
    paths: list[str] = []
    for group in manifest["source_groups"].values():
        paths.extend(group)
    paths.extend(manifest["required_public_headers"])
    paths.extend(manifest["required_internal_headers"])
    paths.append("LICENSE")
    if len(paths) != len(set(paths)):
        raise SystemExit("manifest contains duplicate import paths")
    return sorted(paths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["upstream"]["commit"]
    actual = git(args.source, "rev-parse", "HEAD")
    if actual != expected:
        raise SystemExit(f"wrong Zephyr commit: expected {expected}, got {actual}")
    if git(args.source, "status", "--porcelain"):
        raise SystemExit("Zephyr source checkout is dirty")

    paths = selected_paths(manifest)
    missing = [path for path in paths if not (args.source / path).is_file()]
    if missing:
        raise SystemExit("missing selected files:\n  " + "\n  ".join(missing))

    stage = DEST.with_name("upstream.new")
    if stage.exists():
        shutil.rmtree(stage)
    for relative in paths:
        source = args.source / relative
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if relative != "LICENSE" and b"SPDX-License-Identifier: Apache-2.0" not in target.read_bytes():
            raise SystemExit(f"selected file is not declared Apache-2.0: {relative}")

    for patch in manifest.get("local_patches", []):
        patch_path = ROOT / "third_party" / "zephyr-host" / patch["path"]
        if patch["license"] != "Apache-2.0" or not patch_path.is_file():
            raise SystemExit(f"invalid local patch declaration: {patch}")
        subprocess.run(
            ["patch", "--batch", "--forward", "-p1", "-i", str(patch_path)],
            cwd=stage,
            check=True,
        )

    if DEST.exists():
        shutil.rmtree(DEST)
    stage.rename(DEST)

    entries = []
    for relative in paths:
        digest = hashlib.sha256((DEST / relative).read_bytes()).hexdigest()
        entries.append(f"{digest}  upstream/{relative}")
    LOCK.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(f"imported {len(paths)} files from Zephyr {expected}")


if __name__ == "__main__":
    main()
