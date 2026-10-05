#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Record actual linked temporary-file member hashes without publishing bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

MEMBERS = {"lib_mkstemp.o", "lib_mktemp.o"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_map", type=Path, nargs="+")
    args = parser.parse_args()
    evidence = {}
    for path in args.link_map:
        text = path.read_text().split("Allocating common symbols")[0].split("Discarded input sections")[0]
        for archive, member in re.findall(r"^(\S+\.a)\(([^)]+)\)", text, re.M):
            if member not in MEMBERS:
                continue
            data = subprocess.check_output(["ar", "p", archive, member])
            if not data:
                raise ValueError("selected archive member is empty: " + member)
            key = str(path) + ":" + member
            evidence[key] = {"archive": archive, "member": member,
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if {item["member"] for item in evidence.values()} != MEMBERS:
        raise ValueError("both reviewed temporary-file members must appear in actual link maps")
    print("tempfile-link-evidence: " + json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
