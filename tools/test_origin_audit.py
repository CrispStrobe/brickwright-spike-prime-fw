#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise renamed-code discovery and deleted-payload history coverage."""
import hashlib
from pathlib import Path
import subprocess
import tempfile

from audit_repository_history import audit
from audit_source_similarity import scan, tracked_text
from check_source_origin_review import clearance_errors


def run(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def check():
    open_review = {'findings': [{'id': 'fixture', 'status': 'unresolved',
                                 'blocks_redistribution_clearance': True,
                                 'required_action': 'Establish fixture origin'}]}
    assert clearance_errors(open_review)
    open_review['findings'][0]['status'] = 'resolved'
    assert not clearance_errors(open_review)
    code = 'int calculate(int value) {\n' + ''.join(
        f'value = value * {i} + {i + 11};\n' for i in range(1, 22)) + 'return value;\n}\n'
    reference = [('original.c', code)]
    copied = [('local.c', '/* A different notice. */\n' + code.replace(' ', '  '))]
    assert scan(copied, reference, 'exact', 32)
    renamed = [('local.c', code.replace('calculate', 'adjust').replace('value', 'sample'))]
    assert scan(renamed, reference, 'renamed', 65)
    unrelated = [('local.c', 'int separate(void) { return 44; }')]
    assert not scan(unrelated, reference, 'exact', 32)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        run(root, 'init', '-q')
        run(root, 'config', 'user.name', 'Synthetic audit fixture')
        run(root, 'config', 'user.email', 'fixture@example.invalid')
        payload = b'Only synthetic test data, no third-party payload.\n'
        (root / 'removed.bts').write_bytes(payload)
        run(root, 'add', '.')
        run(root, 'commit', '-qm', 'Add synthetic payload')
        run(root, 'tag', 'old-fixture')
        run(root, 'rm', 'removed.bts')
        (root / 'plain.c').write_text(code)
        (root / 'not-utf8.c').write_bytes(b'/* \xff */ int readable(void) { return 3; }\n')
        (root / 'binary.dat').write_bytes(b'\x00\xff')
        run(root, 'add', '.')
        run(root, 'commit', '-qm', 'Delete synthetic payload')
        policy = {'forbidden_sha256': {hashlib.sha256(payload).hexdigest(): 'Synthetic restricted fixture'},
                  'forbidden_tracked_paths': [], 'forbidden_tracked_suffixes': []}
        report = audit(root, policy)
        assert len(report['findings']) == 1
        assert 'refs/tags/old-fixture' in report['findings'][0]['reachable_from']
        assert report['commit_count'] == 2
        texts, inventory = tracked_text(root)
        assert any(name == 'not-utf8.c' for name, _ in texts)
        assert any(x['path'] == 'binary.dat' and x['kind'] == 'binary-not-token-scanned' for x in inventory)
    print('origin audit: discovery, negative control, deleted history and clearance refusal verified')


if __name__ == '__main__':
    check()
