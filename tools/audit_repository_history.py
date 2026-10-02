#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Read-only reachable-blob review against the source policy, including deletions.

Does not examine unreachable server objects, cached PR refs, release assets or
Git LFS objects. Fetch the intended refs before running. Paths from rev-list
are representative names; content hashes detect the same bytes under aliases.
No payload contents are exported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True)


def audit(root, policy):
    records = git(root, 'rev-list', '--objects', '--all').splitlines()
    refs = [line.split() for line in git(root, 'for-each-ref',
            '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes', 'refs/tags').splitlines()
            if not line.split()[0].endswith('/HEAD')]
    findings, blob_count = [], 0
    process = subprocess.Popen(['git', '-C', str(root), 'cat-file', '--batch'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for record in records:
            object_id, _, path = record.partition(' ')
            process.stdin.write((object_id + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3:
                raise RuntimeError(f'unreadable object: {object_id}')
            _, kind, size = header
            size = int(size)
            digest = hashlib.sha256()
            remaining = size
            while remaining:
                chunk = process.stdout.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise RuntimeError(f'truncated object: {object_id}')
                digest.update(chunk)
                remaining -= len(chunk)
            if process.stdout.read(1) != b'\n':
                raise RuntimeError(f'invalid object framing: {object_id}')
            if kind != 'blob':
                continue
            blob_count += 1
            sha = digest.hexdigest()
            reason = policy['forbidden_sha256'].get(sha)
            if (reason or path in policy['forbidden_tracked_paths'] or
                    path.lower().endswith(tuple(policy['forbidden_tracked_suffixes']))):
                findings.append({'object': object_id, 'path': path, 'sha256': sha,
                                 'finding': reason or 'Historical artifact/path requiring review',
                                 'reachable_from': []})
    finally:
        process.stdin.close()
        process.wait()
    for ref, tip in refs:
        reachable = {line.split()[0] for line in git(root, 'rev-list', '--objects', tip).splitlines()}
        for finding in findings:
            if finding['object'] in reachable:
                finding['reachable_from'].append(ref)
    return {'schema': 1, 'revision': git(root, 'rev-parse', 'HEAD').strip(),
            'commit_count': int(git(root, 'rev-list', '--all', '--count')),
            'blob_count': blob_count,
            'refs': [{'ref': ref, 'commit': tip} for ref, tip in refs],
            'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-clean', action='store_true',
                        help='Fail if a reviewed forbidden blob/path is reachable')
    args = parser.parse_args()
    policy_path = args.policy or args.repo / 'policy/source-policy.json'
    report = audit(args.repo, json.loads(policy_path.read_text()))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'history: {report["commit_count"]} commits, {report["blob_count"]} blobs, '
          f'{len(report["findings"])} findings; no history or refs changed')
    if args.require_clean and report['findings']:
        raise SystemExit('history: reviewed forbidden material remains reachable')


if __name__ == '__main__':
    main()
