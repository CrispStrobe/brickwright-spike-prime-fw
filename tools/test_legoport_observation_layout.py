#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Adversaries for private read-only own-kernel diagnostic layout admission."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from collect_legoport_observation_layout import collect, dies, load_layout


class LayoutAdmission(unittest.TestCase):
    def test_exact_hash_and_bounded_six_port_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel, path = root / 'synthetic-own-kernel', root / 'layout'
            kernel.write_bytes(b'synthetic hash binding; not an executable fixture')
            good = {'schema': 1, 'count': 6, 'kernelSha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
                    'address': 0x20000000, 'stride': 112,
                    'offsets': {'confirmed_type': 3, 'flags': 108, 'event_counter': 64}}
            path.write_text(json.dumps(good))
            self.assertEqual(load_layout(path, kernel), good)
            bad = [dict(good, kernelSha256='0' * 64), dict(good, address=0x1FFFFFFF),
                   dict(good, address=0x2000FFF0), dict(good, stride=513),
                   dict(good, stride=True), dict(good, count=7), dict(good, schema=2),
                   dict(good, offsets=[]), []]
            for key, value in [('confirmed_type', -1), ('flags', 112),
                               ('event_counter', 65), ('event_counter', 112),
                               ('event_counter', True), ('extra', 0)]:
                item = copy.deepcopy(good)
                item['offsets'][key] = value
                bad.append(item)
            for item in bad:
                with self.subTest(layout=item):
                    path.write_text(json.dumps(item))
                    with self.assertRaises(ValueError):
                        load_layout(path, kernel)

    def test_invalid_or_truncated_image_refused_before_tools_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic'
            for body in (b'', b'\x7fELF\x01\x01', b'not an ARM ELF' * 3):
                with self.subTest(body=body):
                    path.write_bytes(body)
                    with self.assertRaises(ValueError):
                        collect(path)

    def test_debug_metadata_structure_boundaries(self):
        parsed = list(dies([
            ' <1><10>: Abbrev Number: 3 (DW_TAG_structure_type)\n',
            ' DW_AT_name : (indirect string, offset: 0): legoport_state_s\n',
            ' DW_AT_byte_size : 112\n',
            ' <2><20>: Abbrev Number: 4 (DW_TAG_member)\n',
            ' DW_AT_name : flags\n', ' DW_AT_data_member_location : 108\n',
            ' <2><30>: Abbrev Number: 0\n',
        ]))
        self.assertEqual(parsed[0]['attributes']['name'], 'legoport_state_s')
        self.assertEqual(parsed[0]['attributes']['byte_size'], '112')
        self.assertEqual(parsed[1]['attributes']['data_member_location'], '108')
        self.assertIsNone(parsed[2]['tag'])


if __name__ == '__main__':
    unittest.main()
