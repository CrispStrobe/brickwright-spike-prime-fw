#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Apply reviewed backports to exact pinned dependencies; refuse source drift."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_record(root, record):
    for component in record["components"]:
        if component["selected_licence"] not in {"Apache-2.0", "Apache-2.0 AND BSD-3-Clause"}:
            raise ValueError("Unreviewed backport licence")
        if digest(root / component["patch"]) != component["patch_sha256"]:
            raise ValueError("Backport patch changed since review")
    for item in record.get("integration_files", []):
        if item["selected_licence"] not in {"MIT", "BSD-3-Clause"} or digest(root / item["path"]) != item["sha256"]:
            raise ValueError(f"{item['path']}: integration source changed since review")
    for name, expected in record["required_notices"].items():
        if digest(root / name) != expected:
            raise ValueError(f"{name}: required notice changed")


def prepare(root, record):
    if record.get("schema") != 1:
        raise ValueError("Unsupported backport manifest schema")
    plans = []
    for component in record['components']:
        checkout = root / component['path']
        revision = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
        if revision != component['base_commit']:
            raise ValueError(f'{checkout}: expected pinned base {component["base_commit"]}')
        patch = root / component['patch']
        if digest(patch) != component['patch_sha256']:
            raise ValueError(f'{patch}: patch hash differs from review')
        actual = [digest(checkout / item['path']) for item in component['files']]
        before = [item['before_sha256'] for item in component['files']]
        after = [item['after_sha256'] for item in component['files']]
        if actual == after:
            plans.append((checkout, patch, False))
        elif actual == before:
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=checkout, check=True)
            plans.append((checkout, patch, True))
        else:
            raise ValueError(f'{checkout}: backport inputs are modified or partially applied')
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-only', action='store_true', help='verify patch and grant records without dependencies')
    parser.add_argument('--check', action='store_true', help='require already applied patches')
    args = parser.parse_args()
    record = json.loads((ROOT / 'policy/nuttx-backports.json').read_text())
    validate_record(ROOT, record)
    if args.record_only:
        print("nuttx-backports: patch and licence records verified")
        return
    plans = prepare(ROOT, record)  # Validate both dependencies before changing either.
    if args.check and any(needed for _, _, needed in plans):
        raise SystemExit('Reviewed dependency patches have not been applied')
    for checkout, patch, needed in plans:
        if needed:
            subprocess.run(['git', 'apply', str(patch)], cwd=checkout, check=True)
    if any(needed for _, _, needed in prepare(ROOT, record)):
        raise SystemExit('Backport verification failed')
    print('nuttx-backports: pinned bases and reviewed patched source hashes verified')


if __name__ == '__main__':
    main()
