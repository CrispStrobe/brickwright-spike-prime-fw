#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise patch application drift checks using small synthetic repositories."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from apply_nuttx_backports import prepare


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Backports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.record = {'schema': 1, 'components': []}
        for name in ('nuttx', 'nuttx-apps'):
            path = self.root / name
            path.mkdir()
            subprocess.run(['git', 'init', '-q', str(path)], check=True)
            (path / 'source.c').write_text('before\n')
            subprocess.run(['git', 'add', '.'], cwd=path, check=True)
            subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit', '-qm', 'Synthetic base'], cwd=path, check=True)
            base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()
            (path / 'source.c').write_text('after\n')
            patch = subprocess.check_output(['git', 'diff', '--binary'], cwd=path)
            (path / 'source.c').write_text('before\n')
            rel = name + '.patch'
            (self.root / rel).write_bytes(patch)
            self.record['components'].append({'path': name, 'base_commit': base,
                'patch': rel, 'patch_sha256': sha(patch), 'files': [{'path': 'source.c',
                'before_sha256': sha(b'before\n'), 'after_sha256': sha(b'after\n')}]})

    def test_apply_and_repeat(self):
        for path, patch, needed in prepare(self.root, self.record):
            self.assertTrue(needed)
            subprocess.run(['git', 'apply', str(patch)], cwd=path, check=True)
        self.assertFalse(any(plan[2] for plan in prepare(self.root, self.record)))

    def test_second_component_drift_does_not_change_first(self):
        (self.root / 'nuttx-apps/source.c').write_text('unexpected\n')
        with self.assertRaises(ValueError):
            prepare(self.root, self.record)
        self.assertEqual((self.root / 'nuttx/source.c').read_text(), 'before\n')

    def test_tampered_patch(self):
        (self.root / 'nuttx.patch').write_text('tampered\n')
        with self.assertRaises(ValueError):
            prepare(self.root, self.record)

    def test_wrong_base(self):
        self.record['components'][0]['base_commit'] = '0' * 40
        with self.assertRaises(ValueError):
            prepare(self.root, self.record)


if __name__ == '__main__':
    unittest.main()
