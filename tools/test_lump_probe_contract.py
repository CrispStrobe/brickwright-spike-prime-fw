#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Publication validator controls, not guest execution or kernel mutations."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lump_probe', ROOT / 'simulation/renode/lump_probe.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Contract(unittest.TestCase):
    def setUp(self):
        self.words = [0x42574c50, 1, 2, 511, 0, 0, 0, 0x08070000]

    def test_valid(self):
        self.assertTrue(module.validate_probe(self.words, 0x08070000))

    def test_each_corrupted_field(self):
        for field in range(8):
            with self.subTest(field=field):
                words = self.words[:]; words[field] ^= 1
                with self.assertRaises(AssertionError):
                    module.validate_probe(words, 0x08070000)

    def test_missing_result_and_guest_failure(self):
        for words in [[], self.words[:-1], self.words+[0],
                      [0x42574c50, 1, 3, 255, 10, 0xffffffff, 5, 0x08070000]]:
            with self.assertRaises(AssertionError):
                module.validate_probe(words, 0x08070000)

    def test_wrong_or_nonflash_elf_address(self):
        for address in [0, 0x20020000, 0x08060000 - 1, 0x08100000 - 47]:
            words = self.words[:]; words[-1] = address
            with self.assertRaises(AssertionError):
                module.validate_probe(words, address)
        for address in [0x08060000, 0x08100000 - 48]:
            words = self.words[:]; words[-1] = address
            self.assertTrue(module.validate_probe(words, address))

    def test_actual_makefile_requires_all_simulation_guards(self):
        with tempfile.TemporaryDirectory(prefix='lump-probe-make-') as directory:
            root = Path(directory)
            (root / 'Make.defs').write_text('')
            (root / 'Application.mk').write_text('$(info PROBE_SOURCES:$(CSRCS))\nall:;@true\n')
            names = ['CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK',
                     'CONFIG_BUILD_PROTECTED', 'CONFIG_LEGO_LUMP']
            for flags in range(8):
                output = subprocess.check_output(
                    ['make', '--no-print-directory', '-f', str(ROOT / 'apps/port/Makefile'),
                     'APPDIR='+str(root),
                     *[name+'='+('y' if flags & (1 << index) else 'n')
                       for index, name in enumerate(names)]], text=True)
                self.assertEqual('lumpprobe.c' in output, flags == 7, output)


if __name__ == '__main__':
    unittest.main()
