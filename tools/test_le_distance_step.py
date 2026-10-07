#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Dynamic external-input comparisons and monitor admission controls."""
import asyncio
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation/bluetooth-air'))
from le_distance_step import DistanceStep
from spike_codec import cobs_encode

OLD = bytes.fromhex('3c0600003e0d03e803')
NEW = bytes.fromhex('3c0600003e0d03fa00')


class StepControls(unittest.IsolatedAsyncioTestCase):
    def inputs(self, *payloads):
        frames = asyncio.Queue()
        for payload in payloads:
            frames.put_nowait(cobs_encode(payload))
        return frames, asyncio.get_running_loop().create_future()

    def step(self):
        step = DistanceStep(None, None)
        async def applied(value, receipt):
            receipt['readback_mm'] = value
        step.change_input = applied
        return step

    async def test_old_samples_then_exact_new_samples_and_reconnect_decoder(self):
        step, receipt = self.step(), {}
        frames, errors = self.inputs(OLD, OLD, NEW, NEW, NEW)
        await step.run(frames, errors, receipt)
        self.assertEqual(len(receipt['in_flight_old_samples']), 2)
        self.assertEqual(len(receipt['samples']), 3)
        self.assertEqual(step.decode(NEW)['records'][1]['millimeters'], 250)
        with self.assertRaises(ValueError):
            step.decode(OLD)

    async def test_frozen_input_regression_and_malformed_records_cannot_pass(self):
        for payloads in ([OLD] * 33, [NEW, OLD], [NEW, NEW[:-1]], [NEW, bytes.fromhex('3c0200003e')]):
            frames, errors = self.inputs(*payloads)
            with self.assertRaises((ValueError, AssertionError)):
                await self.step().run(frames, errors, {})

    async def test_exact_external_setter_readback_and_integer_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.log'
            path.write_bytes(b'')
            class Input:
                def write(self, raw):
                    code = json.loads(raw.decode().removeprefix('python ').strip())
                    self.code = code
                    self.assertSetter = "externals['portD'].Device.SetDistance(250)" in code
                    tag = re.search(r'LE_DISTANCE_[0-9a-f]+', code).group()
                    with path.open('ab') as stream:
                        stream.write(('[INFO] Script: ' + tag + ' 250\n').encode())
                async def drain(self): pass
            monitor = Input()
            step = DistanceStep(SimpleNamespace(stdin=monitor, returncode=None), path)
            receipt = {}
            await step.change_input(250, receipt)
            self.assertTrue(monitor.assertSetter)
            self.assertNotIn('WriteDoubleWord', monitor.code)
            self.assertNotIn('RunFor', monitor.code)
            self.assertEqual(receipt['readback_mm'], 250)
            for value in (True, -1, 32768, '250'):
                with self.assertRaises(ValueError):
                    await step.change_input(value, {})


if __name__ == '__main__':
    unittest.main()
