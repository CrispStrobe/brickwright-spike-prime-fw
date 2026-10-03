#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise actual fixture formatting and provenance/corruption rejection."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from make_littlefs_fixture import (SOURCES, COMPILE_DEFINITIONS, compile_harness,
                                   generate, verify_fixture, verify_sources)

SOURCE = None


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='bw-lfs-fixture-tests-')
        cls.root = Path(cls.temp.name)
        cls.valid = cls.root / 'valid'
        generate(SOURCE, cls.valid)
        cls.receipt = (cls.valid / 'receipt.json').read_bytes()
        cls.payload = (cls.valid / 'flash-blocks.bin').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def copy_fixture(self):
        target = self.root / self.id().split('.')[-1]
        shutil.copytree(self.valid, target)
        return target

    def test_actual_format_mount_and_reproducibility(self):
        second = self.root / 'independent'
        generate(SOURCE, second)
        self.assertEqual((second / 'flash-blocks.bin').read_bytes(), self.payload)
        self.assertEqual((second / 'receipt.json').read_bytes(), self.receipt)
        receipt = verify_fixture(second)
        self.assertEqual(len(self.payload), 8192)
        self.assertEqual([block['chip_offset'] for block in receipt['blocks']],
                         [0x100000, 0x101000])
        self.assertFalse(receipt['covers_erased_first_boot'])
        self.assertEqual(receipt['geometry']['block_count'] * 4096, 31 * 1024 * 1024)

    def test_guest_limits_reject_old_format_and_accept_corrected_format(self):
        # Compile actual pinned LittleFS twice, reproducing the prior host/guest
        # discrepancy. The guest build rejects the old name_max255 superblock.
        legacy_dir = self.root / 'legacy-build'
        guest_dir = self.root / 'guest-build'
        legacy_dir.mkdir()
        guest_dir.mkdir()
        legacy = compile_harness(SOURCE, legacy_dir,
                                 [item.replace('NAME_MAX=32', 'NAME_MAX=255')
                                  for item in COMPILE_DEFINITIONS])
        guest = compile_harness(SOURCE, guest_dir)
        old_records = self.root / 'old-records.bin'
        old_records.write_bytes(subprocess.check_output([str(legacy)]))
        subprocess.run([str(guest), str(old_records), '-22'], check=True)
        new_records = self.root / 'new-records.bin'
        new_records.write_bytes(subprocess.check_output([str(guest)]))
        subprocess.run([str(guest), str(new_records), '0'], check=True)
        receipt = json.loads(self.receipt)
        self.assertEqual(receipt['compile_definitions'], COMPILE_DEFINITIONS)
        self.assertEqual(receipt['geometry']['name_max'], 32)
        for field in ('name_max', 'file_max', 'attr_max'):
            target = self.root / ('bad-' + field)
            shutil.copytree(self.valid, target)
            changed = json.loads(self.receipt)
            changed['geometry'][field] += 1
            (target / 'receipt.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'geometry'):
                verify_fixture(target)
        target = self.root / 'bad-definitions'
        shutil.copytree(self.valid, target)
        receipt['compile_definitions'][0] = 'LFS_NAME_MAX=255'
        (target / 'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            verify_fixture(target)

    def test_source_and_licence_drift_rejected(self):
        source = self.root / 'modified-inputs'
        source.mkdir()
        for filename in SOURCES:
            shutil.copyfile(SOURCE / filename, source / filename)
        for name in ('lfs.c', 'LICENSE.md'):
            original = (source / name).read_bytes()
            (source / name).write_bytes(original + b'\n')
            with self.assertRaisesRegex(ValueError, name.replace('.', r'\.')):
                verify_sources(source)
            (source / name).write_bytes(original)
        verify_sources(source)

    def test_existing_output_preserved(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            generate(SOURCE, self.valid)
        self.assertEqual((self.valid / 'flash-blocks.bin').read_bytes(), self.payload)
        self.assertEqual((self.valid / 'receipt.json').read_bytes(), self.receipt)

    def test_payload_corruption_and_truncation_rejected(self):
        target = self.copy_fixture()
        payload = bytearray(self.payload)
        for index in (0, 4095, 4096, 8191):
            payload[index] ^= 1
            (target / 'flash-blocks.bin').write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'hash'):
                verify_fixture(target)
            payload[index] ^= 1
        (target / 'flash-blocks.bin').write_bytes(payload[:-1])
        with self.assertRaisesRegex(ValueError, 'size/hash'):
            verify_fixture(target)

    def test_reserved_region_bounds_geometry_and_provenance_rejected(self):
        target = self.copy_fixture()
        original = json.loads(self.receipt)
        for offset in (0, 0xfffff, 0x2000000, 0x100001):
            receipt = json.loads(self.receipt)
            receipt['blocks'][0]['chip_offset'] = offset
            (target / 'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'offsets'):
                verify_fixture(target)
        for field, value in (('geometry', {}), ('source_sha256', {}),
                             ('littlefs_version', 'wrong'), ('covers_erased_first_boot', True)):
            receipt = dict(original)
            receipt[field] = value
            (target / 'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                verify_fixture(target)

    def test_payload_path_and_order_rejected(self):
        target = self.copy_fixture()
        for mutate in ('path', 'order', 'length'):
            receipt = json.loads(self.receipt)
            if mutate == 'path':
                receipt['payload_file'] = '../other.bin'
            elif mutate == 'order':
                receipt['blocks'].reverse()
            else:
                receipt['blocks'][0]['length'] += 1
            (target / 'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                verify_fixture(target)


def main():
    global SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--littlefs', type=Path, required=True)
    args = parser.parse_args()
    SOURCE = args.littlefs.resolve()
    verify_sources(SOURCE)
    unittest.main(argv=['test_littlefs_fixture.py'])


if __name__ == '__main__':
    main()
