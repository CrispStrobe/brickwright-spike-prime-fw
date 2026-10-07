# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Bounded read-only guest clock diagnostics; no timer or radio accuracy claim."""
import asyncio
import json
import re
import time
import uuid


class GuestClockProbe:
    def __init__(self, renode, log, receipt):
        self.renode, self.log, self.receipt = renode, log, receipt
        self.samples = receipt['samples'] = []
        receipt['scope'] = 'read-only guest clock with host observation windows; instrumented run'
        self.task = None
        self.progress_at = None

    def accept(self, guest_us, before, after):
        if (type(guest_us) is not int or not 0 <= guest_us < 1 << 64
                or not 0 <= before <= after):
            raise ValueError('Malformed guest-clock observation')
        if len(self.samples) >= 256:
            raise ValueError('Guest-clock diagnostic sample bound exceeded')
        if self.samples:
            prior = self.samples[-1]
            if before < prior['host_after_s'] or guest_us < prior['guest_us']:
                raise ValueError('Guest-clock observation regressed')
            if guest_us > prior['guest_us']:
                self.progress_at = after
        else:
            self.progress_at = after
        self.samples.append({'guest_us': guest_us, 'host_before_s': before, 'host_after_s': after})
        if after - self.progress_at >= 15:
            raise TimeoutError('No observed guest-clock progress for 15 host seconds')

    async def sample(self):
        if self.renode.stdin is None or self.renode.returncode is not None:
            raise ValueError('Owned Renode clock monitor unavailable')
        tag = 'LE_CLOCK_' + uuid.uuid4().hex
        marker = (tag + ' ').encode('ascii')
        offset = self.log.stat().st_size
        before = time.monotonic()
        # Read only. Do not pause, RunFor, write registers or force guest time.
        command = ('python "monitor.Parse(\'log \\\"' + tag + ' \' + '
                   'str(int(monitor.Machine.ElapsedVirtualTime.TimeElapsed.TotalMicroseconds)) + \'\\\"\')"\n')
        async with asyncio.timeout(3):
            self.renode.stdin.write(command.encode('ascii'))
            await self.renode.stdin.drain()
            while True:
                if self.renode.returncode is not None:
                    raise ValueError('Renode exited during guest-clock observation')
                with self.log.open('rb') as stream:
                    stream.seek(offset)
                    raw = stream.read(65536)
                for tail in raw.split(marker)[1:]:
                    if b'\n' in tail and re.fullmatch(rb'-?[0-9]+\r?', tail.split(b'\n', 1)[0]):
                        value = tail.splitlines()[0]
                        self.accept(json.loads(value), before, time.monotonic())
                        return
                if len(raw) == 65536:
                    raise ValueError('Guest-clock receipt exceeds log bound')
                await asyncio.sleep(.05)

    async def loop(self):
        try:
            while True:
                await self.sample()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.receipt['error'] = type(error).__name__ + ': ' + str(error)

    def start(self):
        if self.task is not None:
            raise ValueError('Guest-clock probe already started')
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.receipt['stopped'] = True

    def require_complete(self):
        if self.receipt.get('error') or len(self.samples) < 2:
            raise ValueError('Guest-clock diagnostics failed: ' + self.receipt.get('error', 'fewer than two samples'))
