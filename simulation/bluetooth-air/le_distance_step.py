# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""External ultrasonic input changes, compared through the real LE guest."""
import asyncio
import json
import time
import uuid

from active_port_notifications import distance_notification
from spike_frames import receive_payload


class DistanceStep:
    def __init__(self, renode, log):
        self.renode, self.log = renode, log
        self.expected_mm = 1000

    def decode(self, payload):
        return distance_notification(payload, expected_mm=self.expected_mm)

    async def change_input(self, millimeters, receipt):
        if type(millimeters) is not int or not 0 <= millimeters <= 32767:
            raise ValueError('External distance must be an integer in 0..32767 mm')
        if self.renode.stdin is None or self.renode.returncode is not None:
            raise ValueError('Owned external-input monitor unavailable')
        tag = 'LE_DISTANCE_' + uuid.uuid4().hex
        offset = self.log.stat().st_size
        # Only the declared external sensor input changes. No guest memory,
        # clock, PWM register or model implementation is replaced.
        code = ("externals['portD'].Device.SetDistance(%d); " % millimeters
                + "monitor.Parse('log \"" + tag + " ' + "
                + "str(int(externals['portD'].Device.DistanceMillimeters)) + '\"')")
        command = 'python ' + json.dumps(code) + '\n'
        receipt.update(requested_mm=millimeters, requested_at_host_s=time.monotonic())
        async with asyncio.timeout(5):
            self.renode.stdin.write(command.encode('ascii'))
            await self.renode.stdin.drain()
            while True:
                if self.renode.returncode is not None:
                    raise ValueError('Renode exited during external input change')
                with self.log.open('rb') as stream:
                    stream.seek(offset)
                    raw = stream.read(65536)
                marker = (tag + ' ').encode('ascii')
                for line in raw.splitlines():
                    if b'[INFO] Script: ' + marker in line:
                        value = int(line.split(marker, 1)[1])
                        if value != millimeters:
                            raise AssertionError('External sensor input readback differs')
                        receipt.update(readback_mm=value, applied_at_host_s=time.monotonic())
                        return
                if len(raw) == 65536:
                    raise ValueError('External input receipt exceeds log bound')
                await asyncio.sleep(.05)

    async def run(self, frames, errors, receipt):
        old = self.expected_mm
        await self.change_input(250, receipt)
        self.expected_mm = 250
        samples = receipt['samples'] = []
        stale = receipt['in_flight_old_samples'] = []
        async with asyncio.timeout(90):
            while len(samples) < 3:
                frame, payload = await receive_payload(frames, errors, timeout=60)
                receipt['last_payload'] = payload.hex()
                # Admit only exact old records until the first new record.
                # A frozen input or later regression cannot satisfy this test.
                if not samples and payload == bytes.fromhex('3c0600003e0d03') + old.to_bytes(2, 'little', signed=True):
                    sample = distance_notification(payload, expected_mm=old)
                    sample.update(frame=frame.hex(), payload=payload.hex())
                    stale.append(sample)
                    if len(stale) > 32:
                        raise AssertionError('Distance change exceeded in-flight bound')
                    continue
                sample = self.decode(payload)
                sample.update(frame=frame.hex(), payload=payload.hex(), received_at_host_s=time.monotonic())
                samples.append(sample)
