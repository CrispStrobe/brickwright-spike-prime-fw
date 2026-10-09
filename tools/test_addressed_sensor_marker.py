#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic refusal controls: no compiler, emulator or firmware inputs."""
import struct
import unittest
from check_addressed_sensor_marker import FLASH_START, SYMBOL, validate


def fixture():
    data = bytearray(800)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HHI', data, 16, 2, 40, 1)
    struct.pack_into('<I', data, 28, 52)
    struct.pack_into('<HHH', data, 40, 52, 32, 1)
    struct.pack_into('<8I', data, 52, 1, 256, FLASH_START, FLASH_START, 4, 4, 4, 4)
    struct.pack_into('<I', data, 256, 1)
    struct.pack_into('<I', data, 32, 600)
    struct.pack_into('<HH', data, 46, 40, 4)
    struct.pack_into('<10I', data, 640, 0, 1, 2, FLASH_START, 256, 4, 0, 0, 4, 0)
    struct.pack_into('<10I', data, 680, 0, 2, 0, 0, 400, 32, 3, 0, 4, 16)
    names = b'\0' + SYMBOL.encode('ascii') + b'\0'
    data[500:500 + len(names)] = names
    struct.pack_into('<10I', data, 720, 0, 3, 0, 0, 500, len(names), 0, 0, 1, 0)
    struct.pack_into('<IIIBBH', data, 416, 1, FLASH_START, 4, 0x11, 0, 1)
    return data, '%08x 00000004 R %s\n' % (FLASH_START, SYMBOL)


class Marker(unittest.TestCase):
    def test_supported(self):
        raw, symbols = fixture()
        result = validate(raw, symbols)
        self.assertEqual((result['abi'], result['address']), (1, FLASH_START))
        self.assertEqual(len(result['userspaceSha256']), 64)
        raw[256] = 2
        with self.assertRaises(ValueError):
            validate(raw, symbols)

    def test_merged_text(self):
        raw, symbols = fixture()
        struct.pack_into('<I', raw, 76, 7)
        struct.pack_into('<I', raw, 648, 6)
        self.assertEqual(validate(raw, symbols.replace(' R ', ' T '))['abi'], 1)

    def test_object_and_section_refusals(self):
        raw, symbols = fixture()
        for offset, fmt, value in [(32, 'I', 800), (46, 'H', 0), (48, 'H', 0),
                (424, 'I', 8), (420, 'I', FLASH_START + 4), (428, 'B', 0x12),
                (428, 'B', 0x01), (430, 'H', 0), (430, 'H', 4),
                (644, 'I', 8), (648, 'I', 3), (648, 'I', 0), (656, 'I', 257),
                (696, 'I', 799), (704, 'I', 4), (716, 'I', 8),
                (416, 'I', 799), (736, 'I', 799)]:
            broken = bytearray(raw)
            struct.pack_into('<' + fmt, broken, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                validate(broken, symbols)

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
                     (52, 'I', 0), (56, 'I', 799), (60, 'I', FLASH_START + 1),
                     (64, 'I', FLASH_START + 4), (68, 'I', 3), (72, 'I', 3),
                     (76, 'I', 0), (256, 'I', 0), (256, 'I', 2)]
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
