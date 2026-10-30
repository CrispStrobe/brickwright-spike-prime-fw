#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic controls for the instruction ABI marker: no compiler, emulator or firmware inputs."""
import struct
import unittest
import check_addressed_sensor_marker as addressed
from check_instruction_abi_marker import SYMBOL, validate
from test_addressed_sensor_marker import fixture as addressed_fixture


def fixture(value=2):
    raw, symbols = addressed_fixture()
    names = b'\0' + SYMBOL.encode('ascii') + b'\0'
    raw[500:600] = bytes(100)
    raw[500:500 + len(names)] = names
    struct.pack_into('<I', raw, 740, len(names))
    struct.pack_into('<I', raw, 256, value)
    return raw, symbols.replace(addressed.SYMBOL, SYMBOL)


class Marker(unittest.TestCase):
    def test_supported(self):
        raw, symbols = fixture()
        result = validate(raw, symbols)
        self.assertEqual((result['abi'], result['address']), (2, addressed.FLASH_START))

    def test_other_versions_refused(self):
        for value in (0, 1, 3):
            raw, symbols = fixture(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(raw, symbols)

    def test_other_markers_do_not_establish_it(self):
        raw, symbols = addressed_fixture()
        struct.pack_into('<I', raw, 256, 2)
        with self.assertRaises(ValueError):
            validate(raw, symbols)
        raw, symbols = fixture()
        with self.assertRaises(ValueError):
            validate(raw, symbols.replace(SYMBOL, addressed.SYMBOL))

    def test_shared_layout_refusals(self):
        raw, symbols = fixture()
        for offset, fmt, value in [(428, 'B', 0x12), (648, 'I', 3), (420, 'I', addressed.FLASH_START + 4),
                                   (76, 'I', 0), (64, 'I', addressed.FLASH_START + 4)]:
            broken = bytearray(raw)
            struct.pack_into('<' + fmt, broken, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                validate(broken, symbols)
        for variant in ['', symbols * 2, symbols.replace(' R ', ' D '), symbols.replace('00000004', '00000008')]:
            with self.subTest(symbol=variant), self.assertRaises(ValueError):
                validate(raw, variant)


if __name__ == '__main__':
    unittest.main()
