#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual peer harness's subscription and silence checks offline."""
import ast
import asyncio
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation/bluetooth-air'))
from spike_codec import cobs_encode, cobs_decode

SOURCE = ROOT / 'simulation/bluetooth-air/test_spike_air.py'
names = {'set_notification_interval', 'collect_battery_notifications',
         'expect_notification_quiet', 'receive_connection_info'}
nodes = [node for node in ast.parse(SOURCE.read_text()).body
         if isinstance(node, ast.AsyncFunctionDef) and node.name in names]
assert {node.name for node in nodes} == names
scope = dict(asyncio=asyncio, time=time, cobs_encode=cobs_encode,
             BATTERY_FIXTURE_PERCENT=62)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)
set_interval = scope['set_notification_interval']
collect = scope['collect_battery_notifications']
quiet = scope['expect_notification_quiet']
connection_info = scope['receive_connection_info']
BATTERY = b'\x3c\x02\x00\x00\x3e'


class Subscription(unittest.IsolatedAsyncioTestCase):
    def inputs(self, *payloads):
        frames = asyncio.Queue()
        for payload in payloads:
            frames.put_nowait(cobs_encode(payload))
        return frames, asyncio.get_running_loop().create_future()

    async def test_unsubscribe_allows_one_in_flight_but_rejects_two(self):
        frames, errors = self.inputs(BATTERY)
        receipt = {}
        await quiet(frames, errors, .02, receipt, allowed=1)
        self.assertTrue(receipt['passed'])
        self.assertEqual(len(receipt['in_flight']), 1)
        frames, errors = self.inputs(BATTERY, BATTERY)
        with self.assertRaisesRegex(AssertionError, 'Unexpected periodic'):
            await quiet(frames, errors, .02, {}, allowed=1)

    async def test_reconnect_requires_zero_inherited_notifications(self):
        frames, errors = self.inputs(BATTERY)
        with self.assertRaisesRegex(AssertionError, 'Unexpected periodic'):
            await quiet(frames, errors, .02, {})
        frames, errors = self.inputs()
        receipt = {}
        await quiet(frames, errors, .02, receipt)
        self.assertTrue(receipt['passed'])
        self.assertFalse(frames._getters)

    async def test_callback_timeout_is_not_reported_as_successful_silence(self):
        frames, errors = self.inputs()
        errors.set_result(TimeoutError('callback failed'))
        with self.assertRaisesRegex(TimeoutError, 'callback failed'):
            await quiet(frames, errors, .02, {})

    async def test_interval_request_checks_ack_and_records_prior_sample(self):
        frames, errors = self.inputs(BATTERY, b'\x29\x00')

        class Peer:
            async def write_value(self, rx, value, with_response):
                self.payload = cobs_decode(value)
                self.with_response = with_response

        peer, receipt = Peer(), {}
        await set_interval(peer, 4, frames, errors, 100, receipt)
        self.assertEqual(peer.payload, b'\x28\x64\x00')
        self.assertFalse(peer.with_response)
        self.assertEqual(receipt['ack_payload'], '2900')
        self.assertEqual(receipt['before_ack'][0]['battery_percent'], 62)
        for invalid in (b'\x29\x01', b'\x29', b'\x01unexpected'):
            frames, errors = self.inputs(invalid)
            with self.assertRaises(ValueError):
                await set_interval(peer, 4, frames, errors, 0, {})

    async def test_observed_emulation_cadence_keeps_four_interval_silence(self):
        from types import SimpleNamespace
        observed = iter((0, 7.7, 15.3, 22.9))
        original_time = scope['time']
        scope['time'] = SimpleNamespace(monotonic=lambda: next(observed))
        try:
            frames, errors = self.inputs(BATTERY, BATTERY, BATTERY)
            receipt = {}
            window = await collect(frames, errors, receipt)
            self.assertAlmostEqual(window, 30.4)
            self.assertGreater(window, 30)
        finally:
            scope['time'] = original_time

    async def test_reconnect_rejects_notification_before_info_response(self):
        import struct
        info = struct.pack('<BBB H BB H HHHH', 1, 1, 0, 0, 0, 1, 0, 20, 1024, 512, 0)
        frames, errors = self.inputs(BATTERY, info)
        with self.assertRaises(ValueError):
            await connection_info(frames, errors, strict=True)
        frames, errors = self.inputs(info)
        self.assertEqual((await connection_info(frames, errors, strict=True))[1], info)

    async def test_collect_requires_three_complete_fixture_records(self):
        frames, errors = self.inputs(BATTERY, BATTERY, BATTERY)
        receipt = {}
        self.assertGreaterEqual(await collect(frames, errors, receipt), 3)
        self.assertEqual(len(receipt['samples']), 3)
        self.assertTrue(all(sample['payload'] == BATTERY.hex()
                            for sample in receipt['samples']))
        frames, errors = self.inputs(BATTERY, b'\x3c\x02\x00\x00\x3f', BATTERY)
        with self.assertRaises(ValueError):
            await collect(frames, errors, {})


if __name__ == '__main__':
    unittest.main()
