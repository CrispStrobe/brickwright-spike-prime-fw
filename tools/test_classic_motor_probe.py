#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Synthetic adversaries for the actual Classic motor peer's observations."""
import asyncio
import ast
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air'))
from classic_motor_probe import MotorPeer, require_move, require_reply


class ScriptSelection(unittest.TestCase):
    def test_motor_topology_is_explicit_and_default_board_is_preserved(self):
        root = Path(__file__).resolve().parents[1]
        source = root / 'simulation/bluetooth-air/test_spike_air.py'
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'renode_script')
        scope = dict(Path=Path, json=json, ROOT=root, DEVICES=Path('default.cs'),
                     PLATFORM=Path('default.repl'), MILESTONES=())
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory:
            images = Path(directory)
            (images / 'manifest.json').write_text(json.dumps({'reset_pc': '0x08008001',
                                                             'initial_sp': '0x20008000'}))
            default = scope['renode_script'](images, 12345)
            self.assertIn('include @default.cs', default)
            self.assertNotIn('CreatePrimeElectricalPorts', default)
            script = scope['renode_script'](images, 12345,
                        existing_filesystem=Path('fixture'), motor_runtime=Path('staged'))
            self.assertNotIn('include @', script.split('mach create')[0])
            self.assertIn('LoadPlatformDescription @staged/platforms/boards/spike-prime.repl', script)
            self.assertIn('emulation CreatePrimeElectricalPorts "spike"', script)
            self.assertIn('DMARequest -> dma1@7', script)
            self.assertIn('DMATransmit -> dma1@6', script)
            self.assertIn('primeStorageMux.primeStorage', script)
            self.assertNotIn('load_littlefs_fixture @fixture', script)


class ObservationChecks(unittest.TestCase):
    def test_signed_motion_and_terminal_drive(self):
        before = {'position': 15, 'virtual_us': 100}
        for angle in (90, -90):
            after = {'position': 15 + angle, 'virtual_us': 1000100, 'power': 0}
            self.assertEqual(require_move(before, after, angle), angle)
            for mutation in ({'position': 15}, {'position': 15 - angle},
                             {'position': float('nan')}, {'position': 15 + angle * 2},
                             {'power': 30}, {'virtual_us': 100}):
                with self.subTest(angle=angle, mutation=mutation):
                    with self.assertRaises(AssertionError):
                        require_move(before, dict(after, **mutation), angle)

    def test_timeout_must_be_error_and_id_must_match(self):
        require_reply({'i': 'p001', 'e': {'code': -110}}, 'p001', -110)
        for broken in ({'i': 'p001', 'r': None}, {'i': 'p002', 'e': {'code': -110}},
                       {'i': 'p001', 'e': {'code': -95}}):
            with self.assertRaises(AssertionError):
                require_reply(broken, 'p001', -110)


class ReplyChecks(unittest.IsolatedAsyncioTestCase):
    def peer(self):
        self.packets = []
        self.queue = asyncio.Queue()
        return MotorPeer(SimpleNamespace(write=self.packets.append), self.queue,
                         None, None, {'requests': [], 'replies': []})

    async def test_coalesced_reordered_replies_keep_identity(self):
        peer = self.peer()
        peer.degrees('p001', 'A', 90); peer.degrees('p002', 'B', -90)
        self.queue.put_nowait(b'{"i":"p002","r":null}\r\n{"i":"p001",')
        self.queue.put_nowait(b'"r":null}\r\n')
        await peer.collect('p001'); await peer.collect('p002')
        self.assertEqual(len(peer.record['replies']), 2)
        self.assertIn(b'"stall":false', self.packets[0])

    async def test_duplicate_and_unsolicited_results_are_rejected(self):
        for data in (b'{"i":"p001","r":null}\r\n' * 2,
                     b'{"i":"p999","r":null}\r\n'):
            peer = self.peer(); peer.degrees('p001', 'A', 90)
            self.queue.put_nowait(data)
            with self.assertRaises(AssertionError):
                await peer.collect('p001')

    async def test_wrong_error_and_reused_id_are_rejected(self):
        peer = self.peer(); peer.degrees('p001', 'A', 90)
        self.queue.put_nowait(b'{"i":"p001","r":null}\r\n')
        with self.assertRaises(AssertionError):
            await peer.collect('p001', -110)
        with self.assertRaises(ValueError):
            peer.degrees('p001', 'B', 90)


if __name__ == '__main__':
    unittest.main()
