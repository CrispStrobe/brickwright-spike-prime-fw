#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare two isolated closure builds and emit host-path-free evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            value.update(chunk)
    return value.hexdigest()


def relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise SystemExit("compare-offline-builds: ERROR: artifact path escapes run tree")
    return Path(*path.parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-a", type=Path, required=True)
    parser.add_argument("--run-b", type=Path, required=True)
    parser.add_argument("--artifact", action="append", required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    if re.fullmatch(r"sha256:[0-9a-f]{64}", arguments.container_image) is None:
        raise SystemExit("compare-offline-builds: ERROR: container image must be an immutable ID")
    artifacts = []
    identical = True
    for raw in sorted(set(arguments.artifact)):
        relative = relative_path(raw)
        first = arguments.run_a / relative
        second = arguments.run_b / relative
        for run, artifact in ((arguments.run_a, first), (arguments.run_b, second)):
            try:
                artifact.resolve().relative_to(run.resolve())
            except ValueError:
                raise SystemExit("compare-offline-builds: ERROR: artifact symlink escapes run tree")
        if not first.is_file() or not second.is_file():
            raise SystemExit(f"compare-offline-builds: ERROR: missing artifact: {relative.as_posix()}")
        first_hash = digest(first)
        second_hash = digest(second)
        same = first_hash == second_hash
        identical &= same
        artifacts.append({
            "path": relative.as_posix(),
            "run_a_sha256": first_hash,
            "run_b_sha256": second_hash,
            "identical": same,
        })

    document = {
        "schema": "brickwright/offline-fixed-point/v1",
        "status": "identical" if identical else "different",
        "network": "none",
        "container_image": arguments.container_image,
        "source_manifest_sha256": digest(arguments.source_manifest),
        "runs": 2,
        "artifacts": artifacts,
    }
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"compare-offline-builds: {document['status']}")
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
