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
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air'))
from classic_motor_probe import (MotorPeer, require_move, require_reply, require_disconnect,
                                require_attachment_observation, motor_round_trip, boundary_jobs)


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
            self.assertIn('primeStorageMux.primeStorage', script)
            self.assertNotIn('load_littlefs_fixture @fixture', script)
            candidate = scope['renode_script'](images, 12345,
                motor_runtime=Path('staged'), electrical_qualification=Path('candidate'))
            self.assertIn('include @candidate/models.cs', candidate)
            self.assertIn('emulation CreateQualificationElectricalPorts "spike"', candidate)
            self.assertNotIn('emulation CreatePrimeElectricalPorts', candidate)
            with self.assertRaises(ValueError):
                scope['renode_script'](images, 12345, electrical_qualification=Path('candidate'))

    def test_actual_detach_guard_accepts_compiled_models_with_explicit_layout(self):
        source = Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air/test_spike_air.py'
        main = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == 'main')
        guard = next(n for n in main.body if isinstance(n, ast.If)
                     and "arguments.motor_case == 'detach'" in ast.unparse(n.test))
        class Parser:
            def error(self, message):
                raise ValueError(message)
        for candidate in (None, Path('source-candidate')):
            args = SimpleNamespace(motor_case='detach', motor_port_layout=Path('layout'),
                                   electrical_qualification=candidate)
            exec(compile(ast.Module(body=[guard], type_ignores=[]), str(source), 'exec'),
                 dict(arguments=args, parser=Parser()))
            args.motor_port_layout = None
            with self.assertRaises(ValueError):
                exec(compile(ast.Module(body=[guard], type_ignores=[]), str(source), 'exec'),
                     dict(arguments=args, parser=Parser()))

    def test_compiled_topology_preserves_notices_and_records_source_identity(self):
        from stage_classic_motor_topology import stage, FILES
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'runtime'
            output = Path(directory) / 'output'
            for name in FILES:
                path = runtime / 'platforms' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                body = '// SPDX-License-Identifier: MIT\n'
                if name == 'cpus/stm32f4.repl':
                    body += 'timer12: Timers.STM32_Timer @ sysbus 0x40001800\n    -> nvic@43\n'
                    body += '    ApplySVD @https://example.invalid/device.svd\n'
                if name == 'boards/spike-prime-brick-devices.repl':
                    body += 'timer12:\n    1 -> display@1\n'
                path.write_text(body)
            stage(runtime, output)
            receipt = json.loads((output / 'topology-receipt.json').read_text())
            self.assertEqual(set(receipt['files']), set(FILES))
            for name in FILES:
                source = (output / 'platforms' / name).read_text()
                self.assertIn('SPDX-License-Identifier: MIT', source)
                self.assertNotIn('https://', source)
                self.assertNotIn('BrickwrightSTM32_Timer', source)
            board = (output / 'platforms/boards/spike-prime.repl').read_text()
            self.assertIn('DMARequest -> dma1@7', board)
            self.assertIn('DMATransmit -> dma1@6', board)
            with self.assertRaises(ValueError):
                stage(runtime, output)


class AdmissionChecks(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_compiled_model_is_refused_before_motor_requests(self):
        packets = []
        dlc = SimpleNamespace(write=packets.append)
        initial = {'bridge_drive': None, 'bridge_braking': None, 'attached': True,
                   'guest': {'confirmed_type': 0, 'flags': 0, 'event_counter': 0}}
        with patch.object(MotorPeer, 'model', AsyncMock(return_value=initial)), \
             patch.object(MotorPeer, 'establish_encoder', AsyncMock()) as establish:
            with self.assertRaisesRegex(AssertionError, 'bridge observers'):
                await motor_round_trip(dlc, asyncio.Queue(), None, {}, renode_log=Path('unused'), case='detach')
            establish.assert_not_called()
        self.assertFalse(packets)


class ObservationChecks(unittest.TestCase):
    def test_disconnect_requires_real_guest_edge_and_bridge_release(self):
        before = {'attached': True, 'bridge_drive': 5000, 'bridge_braking': False,
                  'guest': {'event_counter': 7, 'confirmed_type': 14, 'flags': 1}}
        detached = {'virtual_us': 100}
        after = {'virtual_us': 1000100, 'bridge_drive': 0, 'bridge_braking': False, 'attached': False,
                 'guest': {'event_counter': 8, 'confirmed_type': 0, 'flags': 0}}
        self.assertEqual(require_disconnect(before, detached, after), 1000000)
        for mutation in ({'bridge_drive': 3000}, {'attached': True}, {'virtual_us': 100}, {'virtual_us': 3000100},
                         {'guest': dict(after['guest'], event_counter=7)},
                         {'guest': dict(after['guest'], confirmed_type=14)},
                         {'guest': dict(after['guest'], flags=1)}):
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                require_disconnect(before, detached, dict(after, **mutation))
        for guest in (dict(before['guest'], confirmed_type=0), dict(before['guest'], flags=0)):
            with self.subTest(prior=guest), self.assertRaises(AssertionError):
                require_disconnect(dict(before, guest=guest), detached, after)

    def test_missing_or_malformed_observers_are_not_supported_bridge_state(self):
        good = {'attached': True, 'bridge_drive': 0, 'bridge_braking': True,
                'guest': {'confirmed_type': 0, 'flags': 0, 'event_counter': 0}}
        require_attachment_observation(good)
        for mutation in ({'bridge_drive': None}, {'bridge_drive': False}, {'bridge_drive': 10001},
                         {'bridge_braking': None}, {'attached': 1}, {'guest': None},
                         {'guest': dict(good['guest'], event_counter=-1)},
                         {'guest': dict(good['guest'], event_counter=0x100000000)},
                         {'guest': dict(good['guest'], flags=256)}):
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                require_attachment_observation(dict(good, **mutation))

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


class BoundaryChecks(unittest.IsolatedAsyncioTestCase):
    async def test_guest_errno_abi_and_rejected_power(self):
        class Peer:
            def __init__(self, unsupported=-138, power=0):
                self.unsupported, self.power = unsupported, power
            def send(self, ident, method, params):
                self.ident, self.params = ident, params
            async def collect(self, ident, error):
                actual = -22 if self.params['speed'] == 0 else self.unsupported
                require_reply({'i': self.ident, 'e': {'code': actual}}, ident, error)
            async def model(self, port):
                return {'power': self.power}
            async def quiet(self, duration):
                pass
        record = {'cases': []}
        await boundary_jobs(Peer(), record)
        self.assertEqual([c['error'] for c in record['cases']], [-138, -22, -138])
        for broken in (Peer(unsupported=-95), Peer(power=30)):
            with self.assertRaises(AssertionError):
                await boundary_jobs(broken, {'cases': []})


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

    async def test_preparation_retries_only_unpowered_not_ready_responses(self):
        for codes, power, fails in [([-19, -11, 0], 0, False),
                                    ([-11], 30, True), ([-16], 0, True)]:
            peer = self.peer()
            peer.record.update(cases=[])
            clock, position = 0, 0
            responses = iter(codes)

            async def model(port):
                nonlocal clock
                clock += 1000
                return {'port': port, 'position': position, 'power': power,
                        'virtual_us': clock}

            async def collect(ident, error):
                nonlocal position
                self.assertIsNone(error)
                code = next(responses)
                if code == 0:
                    position += 30
                    return {'i': ident, 'r': None}
                return {'i': ident, 'e': {'code': code}}

            async def wait(*unused):
                pass

            peer.model, peer.collect = model, collect
            peer.wait_virtual, peer.quiet = wait, wait
            with self.subTest(codes=codes, power=power):
                if fails:
                    with self.assertRaises(AssertionError):
                        await peer.establish_encoder('A')
                    self.assertEqual(len(self.packets), 1)
                else:
                    await peer.establish_encoder('A')
                    self.assertEqual(len(self.packets), 3)
                    self.assertEqual(len(peer.sent), 3)
                    self.assertEqual(peer.record['cases'][0]['delta'], 30)


if __name__ == '__main__':
    unittest.main()
