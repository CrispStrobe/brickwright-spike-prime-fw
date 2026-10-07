#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Clock diagnostic controls, not guest/radio qualification."""
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air'))
from le_clock_probe import GuestClockProbe


class ClockChecks(unittest.IsolatedAsyncioTestCase):
    def probe(self):
        return GuestClockProbe(None, None, {})

    def test_progress_regression_stall_and_malformed_samples(self):
        p = self.probe()
        p.accept(100, 0, 1)
        p.accept(200, 5, 6)
        for guest, before, after in ((True, 7, 8), (-1, 7, 8), (1 << 64, 7, 8),
                                     ('200', 7, 8), (199, 7, 8), (200, 4, 8), (200, 9, 8)):
            with self.subTest(guest=guest, before=before), self.assertRaises(ValueError):
                p.accept(guest, before, after)
        with self.assertRaisesRegex(TimeoutError, 'No observed guest-clock progress'):
            p.accept(200, 20, 21)

    async def test_actual_read_command_and_marker_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'log'
            log.write_bytes(b'')
            commands = []
            class Stdin:
                def write(self, command):
                    commands.append(command.decode())
                    log.write_bytes(command + b'[INFO] machine: LE_CLOCK_fixed 12345\n')
                async def drain(self):
                    pass
            p = GuestClockProbe(SimpleNamespace(stdin=Stdin(), returncode=None), log, {})
            with patch('le_clock_probe.uuid.uuid4', return_value=SimpleNamespace(hex='fixed')):
                await p.sample()
            self.assertEqual(p.samples[0]['guest_us'], 12345)
            command = commands[0]
            self.assertIn('ElapsedVirtualTime.TimeElapsed.TotalMicroseconds', command)
            # The monitor command contains exactly a Python read plus a log.
            expression = command.removeprefix('python "').removesuffix('"\n').replace('\\"', '"')
            emitted = []
            env = {'monitor': SimpleNamespace(Parse=emitted.append,
                   Machine=SimpleNamespace(ElapsedVirtualTime=SimpleNamespace(
                       TimeElapsed=SimpleNamespace(TotalMicroseconds=12345))))}
            exec(expression, env)
            self.assertEqual(emitted, ['log "LE_CLOCK_fixed 12345"'])

    async def test_failed_probe_and_cancelled_loop_are_joined(self):
        p = self.probe()
        p.start()
        await asyncio.sleep(0)
        await p.stop()
        self.assertTrue(p.task.done())
        self.assertTrue(p.receipt['stopped'])
        with self.assertRaisesRegex(ValueError, 'Guest-clock diagnostics failed'):
            p.require_complete()
        p = self.probe()
        async def waiting():
            await asyncio.Event().wait()
        p.sample = waiting
        p.start()
        await asyncio.sleep(0)
        await p.stop()
        self.assertTrue(p.task.done())
        self.assertNotIn('error', p.receipt)


if __name__ == '__main__':
    unittest.main()
