#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Validate the origin review; optionally refuse open distribution findings."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def clearance_errors(review):
    return [f'{item["id"]}: {item["required_action"]}' for item in review['findings']
            if item['status'] != 'resolved' and item['blocks_redistribution_clearance']]


def check_record(root, review):
    errors = []
    if review.get('schema') != 1:
        errors.append('Unsupported source-origin review schema')
    history = review['pybricks_history']
    reuse = json.loads((root / 'policy/pybricks-reuse.json').read_text())
    if history['reference_commit'] != reuse['reference_commit']:
        errors.append('Source-origin review and reuse reference disagree')
    expected = {item['path'] for item in reuse['files']}
    actual = {item['path'] for item in history['first_current_path_history']}
    if expected != actual:
        errors.append('Per-path history coverage differs from the reuse inventory')
    for item in history['first_current_path_history']:
        if item['pybricks_gitlink_at_first_path_commit'] != history['reference_commit']:
            errors.append(f'{item["path"]}: historical gitlink conclusion needs review')
    ids = set()
    for item in review['findings']:
        if item['id'] in ids:
            errors.append(f'Duplicate finding: {item["id"]}')
        ids.add(item['id'])
        if item['status'] not in {'unresolved', 'outside-configured-profile', 'resolved'}:
            errors.append(f'{item["id"]}: unknown status')
        if item['status'] == 'resolved' and not item.get('resolution_evidence'):
            errors.append(f'{item["id"]}: resolved finding has no evidence')
        for source in item['affected_files']:
            path = root / source['path']
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
                errors.append(f'{source["path"]}: changed affected source; update origin finding/evidence')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, default=ROOT / 'policy/source-origin-review.json')
    parser.add_argument('--require-clearance', action='store_true')
    args = parser.parse_args()
    review = json.loads(args.review.read_text())
    errors = check_record(ROOT, review)
    if args.require_clearance:
        errors += clearance_errors(review)
    if errors:
        raise SystemExit('\n'.join(errors))
    print('source-origin: review record and affected source hashes verified')
    if clearance_errors(review):
        print('source-origin: OPEN provenance/history findings; redistribution clearance refused')
    else:
        print('source-origin: no recorded blocking findings; scope/limits still apply')


if __name__ == '__main__':
    main()
