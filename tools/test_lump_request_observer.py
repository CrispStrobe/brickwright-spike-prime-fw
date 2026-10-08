#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Controls for the read-only request observer; not ARM or kernel qualification."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('requests', ROOT/'simulation/renode/lump_requests.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Contract(unittest.TestCase):
    def setUp(self):
        self.words = [0x42575251, 1, 2, 1, 7, 6, 3, 0, 0, 0]
        for i in range(6):
            self.words += [0xffffffff, 22 if i == 0 else 14 if i < 5 else 11,
                           0 if i < 5 else 48] + ([0]*12 if i < 5 else [0xa5a5a5a5]*12)

    def test_valid_and_all_wrong_fields(self):
        self.assertTrue(module.validate_requests(self.words))
        for field in range(100):
            bad = self.words[:]; bad[field] ^= 1
            # Any nonnegative descriptor is valid; all other fields are exact.
            if field == 6: bad[field] = 0xffffffff
            with self.subTest(field=field), self.assertRaises(AssertionError):
                module.validate_requests(bad)
        for bad in [self.words[:-1], self.words+[0]]:
            with self.assertRaises(AssertionError): module.validate_requests(bad)

    def test_read_only_observer_progress_and_bounds(self):
        base = 0x20020000
        reads, advances = [], []
        machine = SimpleNamespace(IsPaused=True)
        state = [0]
        def read(address):
            self.assertTrue(base <= address < base+400 and (address-base)%4 == 0)
            reads.append(address)
            index = (address-base)//4
            return state[0] if index == 2 else self.words[index]
        def run(milliseconds):
            self.assertEqual(milliseconds, 20)
            advances.append(milliseconds)
            state[0] = 2
        machine.SystemBus = SimpleNamespace(ReadDoubleWord=read)
        modules = {}
        for name, members in {
            'Antmicro.Renode.Core': {'EmulationManager': SimpleNamespace(Instance=SimpleNamespace(CurrentEmulation=SimpleNamespace(RunFor=run)))},
            'Antmicro.Renode.Time': {'TimeInterval': SimpleNamespace(FromMilliseconds=int)},
            'System': {'UInt64': int},
        }.items():
            modules[name] = ModuleType(name); modules[name].__dict__.update(members)
        with patch.dict(sys.modules, modules), patch.object(module,'monitor',SimpleNamespace(Machine=machine),create=True), patch.object(module.time,'time',return_value=0):
            module.mc_check_lump_requests(hex(base))
            self.assertEqual(advances,[20])
            for wrong in [0,base+1,0x20040000-396]:
                with self.assertRaises(AssertionError): module.mc_check_lump_requests(hex(wrong))
            state[0] = 3
            with self.assertRaises(AssertionError): module.mc_check_lump_requests(hex(base))
            state[0] = 7
            with self.assertRaises(AssertionError): module.mc_check_lump_requests(hex(base))
            machine.IsPaused = False
            with self.assertRaises(AssertionError): module.mc_check_lump_requests(hex(base))
        # A stalled guest and an expired wall limit must both refuse.
        machine.IsPaused=True; state[0]=1
        modules['Antmicro.Renode.Core'].EmulationManager.Instance.CurrentEmulation.RunFor=lambda ms: None
        with patch.dict(sys.modules,modules), patch.object(module,'monitor',SimpleNamespace(Machine=machine),create=True):
            with patch.object(module.time,'time',return_value=0), self.assertRaisesRegex(AssertionError,'110 guest'):
                module.mc_check_lump_requests(hex(base))
            with patch.object(module.time,'time',side_effect=[0,576]), self.assertRaisesRegex(AssertionError,'575 host'):
                module.mc_check_lump_requests(hex(base))

if __name__=='__main__': unittest.main()
