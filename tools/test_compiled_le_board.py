#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Direct LE board admission controls; no emulator or guest is launched."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air/test_spike_air.py'
nodes = ast.parse(SOURCE.read_text()).body
node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == 'compiled_le_board')
scope = dict(json=json, hashlib=hashlib, Path=Path)
scope['MILESTONES'] = ast.literal_eval(next(n.value for n in nodes if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == 'MILESTONES' for t in n.targets)))
builder = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == 'renode_script')
exec(compile(ast.Module(body=[node, builder], type_ignores=[]), str(SOURCE), 'exec'), scope)
select = scope['compiled_le_board']


class Parser:
    def error(self, message):
        raise ValueError(message)


class BoardAdmission(unittest.TestCase):
    def test_offline_receipt_and_transport_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ('boards/spike-prime.repl', 'boards/spike-prime-brick-devices.repl',
                     'cpus/stm32f413vg.repl', 'cpus/stm32f4.repl')
            files = {}
            for name in names:
                path = root / 'platforms' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('// synthetic board data\n')
                files[name] = {'stagedSha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            (root / 'topology-receipt.json').write_text(json.dumps({'files': files}))
            args = SimpleNamespace(compiled_board=root, motor_runtime=None, classic=False,
                imu_probe=False, imu_poses=False, imu_readiness=False, imu_calibration=False,
                lite_extension=None, skip_le=False, scratch_link=None, then=None,
                existing_filesystem=root / 'explicit-owned-fixture')
            self.assertEqual(select(args, Parser()), root)
            for field in ('motor_runtime','classic','imu_probe','imu_poses','imu_readiness',
                          'imu_calibration','lite_extension','skip_le','scratch_link','then'):
                original = getattr(args, field)
                setattr(args, field, True)
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'separate direct LE'):
                    select(args, Parser())
                setattr(args, field, original)
            args.existing_filesystem = None
            with self.assertRaisesRegex(ValueError, 'explicit filesystem'):
                select(args, Parser())
            args.existing_filesystem = root / 'explicit-owned-fixture'
            (root / 'platforms' / names[0]).write_text('// modified\n')
            with self.assertRaisesRegex(ValueError, 'differs'):
                select(args, Parser())
            args.compiled_board = None
            self.assertIsNone(select(args, Parser()))

    def test_actual_launcher_uses_selected_board_without_enabling_motor_fixture(self):
        main = next(n for n in nodes if isinstance(n, ast.AsyncFunctionDef) and n.name == 'main')
        call = next(n for n in ast.walk(main) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == 'start_renode')
        self.assertEqual(ast.unparse(call.args[-3]), 'board_runtime')
        self.assertEqual(ast.unparse(call.args[-1]), 'le_board is not None')
        assignment = next(n for n in main.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'board_runtime' for t in n.targets))
        self.assertEqual(ast.unparse(assignment.value), 'arguments.motor_runtime or le_board')
        # Motor scenarios retain their own Classic-only admission guard.
        guards = [n for n in main.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'arguments.motor_runtime']
        self.assertTrue(any('--motor-runtime requires a separate --classic motor scenario' in ast.unparse(n) for n in guards))

    def test_battery_only_fixture_detaches_before_guest_without_state_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({'reset_pc':'0x08008001','initial_sp':'0x20010000'}))
            script = scope['renode_script'](root, 1234, motor_runtime=root, empty_ports=True)
            for port in 'ABCDEF':
                self.assertIn('port' + port + ' Detach\n', script)
                self.assertLess(script.index('port' + port + ' Detach'), script.index('sysbus LoadELF'))
            self.assertNotIn('include @', script)
            self.assertNotIn('WriteDoubleWord', script)
            self.assertNotIn('classic_motor', script)
            self.assertNotIn('Detach', scope['renode_script'](root, 1234, motor_runtime=root))


if __name__ == '__main__':
    unittest.main()
