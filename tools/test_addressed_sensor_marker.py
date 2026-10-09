#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic refusal controls: no compiler, emulator or firmware inputs."""
import struct
import unittest
from check_addressed_sensor_marker import FLASH_START, SYMBOL, validate


def fixture():
    data = bytearray(260)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHI', data, 16, 2, 40, 1)
    struct.pack_into('<I', data, 28, 52)
    struct.pack_into('<HHH', data, 40, 52, 32, 1)
    struct.pack_into('<8I', data, 52, 1, 256, FLASH_START, FLASH_START, 4, 4, 4, 4)
    struct.pack_into('<I', data, 256, 1)
    return data, '%08x 00000004 R %s\n' % (FLASH_START, SYMBOL)


class Marker(unittest.TestCase):
    def test_supported(self):
        raw, symbols = fixture()
        result = validate(raw, symbols)
        self.assertEqual((result['abi'], result['address']), (1, FLASH_START))
        self.assertEqual(len(result['userspaceSha256']), 64)
        raw[-1] = 1
        with self.assertRaises(ValueError):
            validate(raw, symbols)

    def test_symbol_refusals(self):
        raw, symbols = fixture()
        variants = ['', symbols * 2, symbols.replace(' R ', ' D '),
                    symbols.replace(' R ', ' r '), symbols.replace('00000004', '00000008'),
                    symbols.replace('%08x' % FLASH_START, '%08x' % (FLASH_START + 1)),
                    symbols.replace('%08x' % FLASH_START, '20000000'),
                    symbols.replace('%08x' % FLASH_START, '08100000')]
        for variant in variants:
            with self.subTest(symbol=variant), self.assertRaises(ValueError):
                validate(raw, variant)

    def test_elf_refusals(self):
        raw, symbols = fixture()
        mutations = [(4, 'B', 2), (5, 'B', 2), (6, 'B', 0), (16, 'H', 3),
                     (18, 'H', 3), (20, 'I', 0), (28, 'I', 260),
                     (40, 'H', 0), (42, 'H', 0), (44, 'H', 0),
                     (52, 'I', 0), (56, 'I', 259), (60, 'I', FLASH_START + 1),
                     (64, 'I', FLASH_START + 4), (68, 'I', 3), (72, 'I', 3),
                     (76, 'I', 6), (76, 'I', 0), (256, 'I', 0), (256, 'I', 2)]
        for offset, fmt, value in mutations:
            broken = bytearray(raw)
            struct.pack_into('<' + fmt, broken, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                validate(broken, symbols)
        for length in (0, 20, 51, 83, 259):
            with self.subTest(length=length), self.assertRaises(ValueError):
                validate(raw[:length], symbols)

    def test_physical_alias(self):
        for physical in (FLASH_START, FLASH_START + 1, FLASH_START - 1):
            raw, symbols = fixture()
            struct.pack_into('<H', raw, 44, 2)
            struct.pack_into('<8I', raw, 84, 1, 256, 0x20000000, physical, 4, 4, 6, 4)
            with self.subTest(physical=physical), self.assertRaises(ValueError):
                validate(raw, symbols)

    def test_overlapping_load(self):
        raw, symbols = fixture()
        struct.pack_into('<H', raw, 44, 2)
        raw[84:116] = raw[52:84]
        with self.assertRaises(ValueError):
            validate(raw, symbols)


if __name__ == '__main__':
    unittest.main()
