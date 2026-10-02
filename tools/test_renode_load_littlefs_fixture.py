#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Host protocol tests; generate the exact fixture from qualified external sources."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import make_littlefs_fixture as generator
import renode_load_littlefs_fixture as loader


class NorProtocol:
    def __init__(self):
        self.memory = bytearray(b'\xff') * (32*1024*1024)
        self.packet = []
        self.commands = []
        self.programs = []
        self.write_enabled = False

    def Transmit(self, value):
        self.packet.append(value)
        if self.packet[0] == 0x0C and len(self.packet) > 6:
            address = int.from_bytes(bytes(self.packet[1:5]), 'big')
            return self.memory[address + len(self.packet) - 7]
        return 0

    def FinishTransmission(self):
        command = self.packet[0]
        self.commands.append(command)
        if command == 0x06:
            self.write_enabled = True
        elif command == 0x12:
            assert self.write_enabled
            address = int.from_bytes(bytes(self.packet[1:5]), 'big')
            data = bytes(self.packet[5:])
            assert len(data) == 256 and address % 256 == 0
            for i, value in enumerate(data):
                self.memory[address+i] &= value
            self.programs.append((address, data))
            self.write_enabled = False
        elif command != 0x0C:
            raise AssertionError('Unexpected NOR command: %s' % command)
        self.packet = []


class LoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.original = cls.root / 'original'
        generator.generate(SOURCE, cls.original)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.directory = self.root / 'test'
        if self.directory.exists():
            shutil.rmtree(self.directory)
        shutil.copytree(self.original, self.directory)
        self.flash = NorProtocol()

    def change_receipt(self, change):
        path = self.directory / 'receipt.json'
        receipt = json.loads(path.read_text())
        change(receipt)
        path.write_text(json.dumps(receipt))

    def test_real_fixture_programs_exact_pages_and_preserves_all_other_bytes(self):
        # Mark the reserved prefix and every byte outside the two intended
        # blocks. Loading must retain these existing bytes, including the last
        # byte of the full 32 MiB chip (never wrap an address).
        self.flash.memory[:1048576] = b'\xa5' * 1048576
        self.flash.memory[1056768:] = b'\x5a' * (32*1024*1024-1056768)
        before = bytes(self.flash.memory)
        proof = loader.load_fixture(self.flash, str(self.directory))
        payload = (self.directory / 'flash-blocks.bin').read_bytes()
        self.assertEqual(payload, self.flash.memory[1048576:1056768])
        self.assertEqual(before[:1048576], self.flash.memory[:1048576])
        self.assertEqual(before[1056768:], self.flash.memory[1056768:])
        self.assertEqual([1048576+i*256 for i in range(32)],
                         [address for address, _ in self.flash.programs])
        self.assertEqual(32, proof['pages_programmed'])
        self.assertFalse(proof['covers_erased_first_boot'])
        self.assertEqual(generator.SOURCES, loader.SOURCES)
        self.assertEqual(generator.GEOMETRY, loader.GEOMETRY)
        self.assertEqual(generator.BLOCK_HASHES, loader.BLOCK_HASHES)

    def test_invalid_metadata_is_rejected_before_any_spi_command(self):
        changes = [
            lambda r: r['source_sha256'].__setitem__('lfs.c', '0'*64),
            lambda r: r['geometry'].__setitem__('partition_size', 4096),
            lambda r: r['blocks'][0].__setitem__('chip_offset', 0),
            lambda r: r['blocks'][1].__setitem__('chip_offset', 32*1024*1024),
            lambda r: r.__setitem__('covers_erased_first_boot', True),
            lambda r: r.__setitem__('payload_file', '../flash-blocks.bin'),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                self.change_receipt(change)
                with self.assertRaises(ValueError):
                    loader.load_fixture(self.flash, str(self.directory))
                self.assertEqual([], self.flash.commands)

    def test_payload_tampering_is_rejected_before_any_spi_command(self):
        path = self.directory / 'flash-blocks.bin'
        data = bytearray(path.read_bytes())
        data[8191] ^= 1
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            loader.load_fixture(self.flash, str(self.directory))
        self.assertEqual([], self.flash.commands)

    def test_non_erased_destination_is_not_programmed(self):
        self.flash.memory[1052672] = 0
        with self.assertRaises(ValueError):
            loader.load_fixture(self.flash, str(self.directory))
        self.assertEqual([], self.flash.programs)
        self.assertNotIn(0x06, self.flash.commands)
        self.assertNotIn(0x12, self.flash.commands)

    def test_programming_readback_failure_is_reported(self):
        transmit = self.flash.Transmit
        def corrupted(value):
            result = transmit(value)
            if len(self.flash.programs) == 32 and self.flash.packet[0] == 0x0C:
                return result ^ 1
            return result
        self.flash.Transmit = corrupted
        with self.assertRaisesRegex(ValueError, 'readback'):
            loader.load_fixture(self.flash, str(self.directory))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--littlefs', required=True, type=Path)
    args, remaining = parser.parse_known_args()
    SOURCE = args.littlefs.resolve()
    unittest.main(argv=[__file__] + remaining)
