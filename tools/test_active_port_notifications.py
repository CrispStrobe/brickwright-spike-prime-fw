#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Strict external notification comparisons and actual collector controls."""
import ast
import asyncio
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation/bluetooth-air'))
from active_port_notifications import distance_notification
from spike_codec import cobs_encode
from spike_frames import battery_notification

ACTIVE = bytes.fromhex('3c0600003e0d03e803')
BATTERY = bytes.fromhex('3c0200003e')
SOURCE = ROOT / 'simulation/bluetooth-air/test_spike_air.py'
names = {'set_notification_interval', 'collect_battery_notifications', 'expect_notification_quiet'}
nodes = [n for n in ast.parse(SOURCE.read_text()).body
         if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
scope = dict(asyncio=asyncio, time=time, cobs_encode=cobs_encode, BATTERY_FIXTURE_PERCENT=62)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)


class Records(unittest.TestCase):
    def test_exact_distance_and_signed_unit_boundary(self):
        self.assertEqual(distance_notification(ACTIVE)['records'][1],
                         dict(type=13, port=3, millimeters=1000))
        negative = ACTIVE[:7] + (-32768).to_bytes(2, 'little', signed=True)
        self.assertEqual(distance_notification(negative, expected_mm=-32768)['records'][1]['millimeters'], -32768)
        with self.assertRaises(ValueError):
            battery_notification(ACTIVE, 62)
        with self.assertRaises(ValueError):
            distance_notification(BATTERY)

    def test_malformed_duplicate_unknown_and_wrong_fixture_fail_closed(self):
        bad = [ACTIVE[:i] for i in range(len(ACTIVE))]
        bad += [ACTIVE + ACTIVE[5:], ACTIVE[:5] + b'\x00' + ACTIVE[6:],
                ACTIVE[:6] + b'\x06' + ACTIVE[7:], ACTIVE[:7] + b'\xe9\x03',
                ACTIVE[:4] + b'\x65' + ACTIVE[5:], b'\x3c\x05\x00' + ACTIVE[3:],
                b'\x3c\x06\x00' + ACTIVE[5:] + ACTIVE[3:5]]
        for value in bad:
            with self.subTest(payload=value.hex()), self.assertRaises(ValueError):
                distance_notification(value)
        for kw in ({'expected_port':True}, {'expected_port':6}, {'expected_mm':32768}, {'expected_percent':101}):
            with self.assertRaises(ValueError):
                distance_notification(ACTIVE, **kw)

    def test_mutations_are_detected_by_external_fixture(self):
        # Mutate fixture comparisons, not the test expectation. Both otherwise
        # well-formed wrong-port and wrong-distance records must be rejected.
        path = ROOT / 'simulation/bluetooth-air/active_port_notifications.py'
        source = path.read_text()
        for old, new, payload in (
            ('port != expected_port', 'False', ACTIVE[:6] + b'\x04' + ACTIVE[7:]),
            ('millimeters != expected_mm', 'False', ACTIVE[:7] + b'\xe9\x03')):
            mutated = {}
            exec(compile(source.replace(old, new), str(path), 'exec'), mutated)
            with self.assertRaises(ValueError):
                distance_notification(payload)
            # The broken implementation admits the adverse observable input.
            mutated['distance_notification'](payload)


class Collector(unittest.IsolatedAsyncioTestCase):
    def inputs(self, *payloads):
        frames = asyncio.Queue()
        for payload in payloads:
            frames.put_nowait(cobs_encode(payload))
        return frames, asyncio.get_running_loop().create_future()

    async def test_actual_subscribe_collect_and_quiet_validate_active_records(self):
        frames, errors = self.inputs(ACTIVE, b'\x29\x00')
        class Peer:
            async def write_value(self, *args, **kwargs): pass
        receipt = {}
        await scope['set_notification_interval'](Peer(), None, frames, errors, 100,
                                                  receipt, decoder=distance_notification)
        self.assertEqual(receipt['before_ack'][0]['records'][1]['millimeters'], 1000)
        frames, errors = self.inputs(ACTIVE, ACTIVE, ACTIVE)
        receipt = {}
        await scope['collect_battery_notifications'](frames, errors, receipt, decoder=distance_notification)
        self.assertEqual(len(receipt['samples']), 3)
        frames, errors = self.inputs(BATTERY, ACTIVE, ACTIVE, ACTIVE)
        startup = {}
        await scope['collect_battery_notifications'](frames, errors, startup,
            decoder=distance_notification, allow_initial_battery=True)
        self.assertEqual(len(startup['initial_battery']), 1)
        self.assertEqual(len(startup['samples']), 3)
        frames, errors = self.inputs(*([BATTERY] * 33))
        with self.assertRaisesRegex(AssertionError, 'startup record bound'):
            await scope['collect_battery_notifications'](frames, errors, {},
                decoder=distance_notification, allow_initial_battery=True)
        frames, errors = self.inputs(ACTIVE)
        await scope['expect_notification_quiet'](frames, errors, .01, {}, allowed=1, decoder=distance_notification)
        frames, errors = self.inputs(ACTIVE)
        with self.assertRaises(AssertionError):
            await scope['expect_notification_quiet'](frames, errors, .01, {}, decoder=distance_notification)
        frames, errors = self.inputs(BATTERY)
        with self.assertRaises(ValueError):
            await scope['collect_battery_notifications'](frames, errors, {}, decoder=distance_notification)


if __name__ == '__main__':
    unittest.main()
