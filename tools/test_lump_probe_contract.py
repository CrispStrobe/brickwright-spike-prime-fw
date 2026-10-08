#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Publication validator controls, not guest execution or kernel mutations."""
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

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


class Observer(unittest.TestCase):
    """Execute the real observer against a read-only simulated host API.

    These controls test observer refusals and boundedness, not ARM execution.
    Deliberately provide no bus write method or guest-state setter.
    """

    def setUp(self):
        self.base = 0x20020000
        self.readonly = 0x08070000
        self.words = [0x42574c50, 1, 2, 511, 0, 0, 0, self.readonly]
        self.calls = []
        self.reads = []
        self.machine = SimpleNamespace(IsPaused=True)
        self.machine.SystemBus = SimpleNamespace(ReadDoubleWord=self.read)
        self.modules = {}
        for name, members in {
            'Antmicro.Renode.Core': {
                'EmulationManager': SimpleNamespace(Instance=SimpleNamespace(
                    CurrentEmulation=SimpleNamespace(RunFor=self.advance)))},
            'Antmicro.Renode.Time': {
                'TimeInterval': SimpleNamespace(FromMilliseconds=int)},
            'System': {'UInt64': int},
        }.items():
            self.modules[name] = ModuleType(name)
            self.modules[name].__dict__.update(members)

    def read(self, address):
        self.reads.append(address)
        self.assertGreaterEqual(address, self.base)
        self.assertLess(address, self.base + 32)
        self.assertEqual((address - self.base) % 4, 0)
        return self.words[(address - self.base) // 4]

    def advance(self, milliseconds):
        self.assertEqual(milliseconds, 20)
        self.calls.append(milliseconds)

    def observe(self, base=None, readonly=None, times=None):
        clock = {'side_effect': times} if times is not None else {'return_value': 0}
        with patch.dict(sys.modules, self.modules), \
                patch.object(module, 'monitor', SimpleNamespace(Machine=self.machine), create=True), \
                patch.object(module.time, 'time', **clock), redirect_stdout(io.StringIO()):
            module.mc_check_lump_probe(hex(self.base if base is None else base),
                                       hex(self.readonly if readonly is None else readonly))

    def test_terminal_success_needs_no_execution_or_write(self):
        self.observe()
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.reads), 10)

    def test_real_boot_progress_is_required(self):
        self.words[2] = 0
        original_run = self.advance

        def boot(milliseconds):
            original_run(milliseconds)
            self.words[2] = 1 if len(self.calls) == 1 else 2

        self.modules['Antmicro.Renode.Core'].EmulationManager.Instance.CurrentEmulation.RunFor = boot
        self.observe()
        self.assertEqual(self.calls, [20, 20])

    def test_guest_failure_and_invalid_state_refuse(self):
        for state in (3, 4, 0xffffffff):
            with self.subTest(state=state):
                self.words[2] = state
                with self.assertRaises(AssertionError):
                    self.observe()
                self.assertEqual(self.calls, [])

    def test_stalled_probe_hits_guest_bound(self):
        self.words[2] = 1
        with self.assertRaisesRegex(AssertionError, '110 guest seconds'):
            self.observe()
        self.assertEqual(sum(self.calls), 110000)

    def test_host_bound_refuses_before_advancing(self):
        self.words[2] = 1
        with self.assertRaisesRegex(AssertionError, '575 host seconds'):
            self.observe(times=[0, 576])
        self.assertEqual(self.calls, [])

    def test_unpaused_entry_and_unpaused_return_refuse(self):
        self.machine.IsPaused = False
        with self.assertRaisesRegex(AssertionError, 'start paused'):
            self.observe()
        self.assertEqual(self.reads, [])
        self.machine.IsPaused = True
        self.words[2] = 1

        def leave_running(milliseconds):
            self.advance(milliseconds)
            self.machine.IsPaused = False

        self.modules['Antmicro.Renode.Core'].EmulationManager.Instance.CurrentEmulation.RunFor = leave_running
        with self.assertRaisesRegex(AssertionError, 'leave the guest paused'):
            self.observe()
        self.assertEqual(self.calls, [20])

    def test_invalid_symbol_ranges_refuse_before_reading(self):
        for base in (self.base - 4, self.base + 1, 0x20040000 - 28):
            with self.subTest(base=base), self.assertRaises(AssertionError):
                self.observe(base=base)
        for readonly in (0x08060000 - 1, 0x08100000 - 47):
            with self.subTest(readonly=readonly), self.assertRaises(AssertionError):
                self.observe(readonly=readonly)
        self.assertEqual(self.reads, [])
        self.assertEqual(self.calls, [])


class ObserverMutations(unittest.TestCase):
    def test_broken_observers_fail_assertions(self):
        global module
        original = module
        source = (ROOT / 'simulation/renode/lump_probe.py').read_text()
        mutations = [
            ('ignore terminal validation', '                validate_probe(words, readonly)',
             '                pass'),
            ('omit host bound', '        if time.time() - started > 575:',
             '        if False:'),
            ('omit guest bound', '        if elapsed == 110000:',
             '        if False:'),
        ]
        try:
            for name, old, new in mutations:
                with self.subTest(mutation=name):
                    self.assertEqual(source.count(old), 1)
                    mutant = ModuleType('lump_probe_mutant')
                    exec(compile(source.replace(old, new), name, 'exec'), mutant.__dict__)
                    module = mutant
                    output = io.StringIO()
                    result = unittest.TextTestRunner(stream=output).run(
                        unittest.defaultTestLoader.loadTestsFromTestCase(Observer))
                    self.assertEqual(result.testsRun, 7, output.getvalue())
                    self.assertEqual(result.errors, [], output.getvalue())
                    self.assertTrue(result.failures, output.getvalue())
        finally:
            module = original


if __name__ == '__main__':
    unittest.main()
