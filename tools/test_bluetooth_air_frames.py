#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic framing/contract regressions; no Bluetooth runtime required."""
import asyncio
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'simulation/bluetooth-air'))
from spike_codec import cobs_encode
from spike_frames import FrameBuffer, info_response, receive_info

PAYLOAD = struct.pack('<BBB H BB H HHHH', 1, 1, 0, 0, 0, 1, 0, 20, 1024, 512, 0)


class Framing(unittest.TestCase):
    def test_every_split_and_coalesced_partial(self):
        first, second = cobs_encode(PAYLOAD), cobs_encode(b'\x29hello')
        for split in range(len(first) + 1):
            buffer = FrameBuffer()
            output = buffer.feed(first[:split]) + buffer.feed(first[split:] + second[:-1])
            self.assertEqual(output, [first])
            self.assertEqual(buffer.feed(second[-1:]), [second])
        self.assertEqual(FrameBuffer().feed(first + second + first), [first, second, first])

    def test_unterminated_and_burst_bounds(self):
        with self.assertRaises(ValueError):
            FrameBuffer(maximum=4).feed(b'12345')
        with self.assertRaises(ValueError):
            FrameBuffer(maximum_frames=2).feed(b'\x02\x02\x02')

    def test_real_contract_and_truncated_or_wrong_content(self):
        self.assertEqual(info_response(PAYLOAD)['max_chunk'], 512)
        for payload in (b'', b'\x01', PAYLOAD[:-1], PAYLOAD + b'\0', b'\x29' + PAYLOAD[1:],
                        PAYLOAD[:9] + b'\x15' + PAYLOAD[10:]):
            with self.assertRaises(ValueError):
                info_response(payload)


class AsyncFrames(unittest.IsolatedAsyncioTestCase):
    async def test_unrelated_frame_then_actual_response(self):
        queue = asyncio.Queue()
        error = asyncio.get_running_loop().create_future()
        for frame in FrameBuffer().feed(cobs_encode(b'\x29event') + cobs_encode(PAYLOAD)):
            queue.put_nowait(frame)
        frame, payload, fields = await receive_info(queue, error)
        self.assertEqual(payload, PAYLOAD)
        self.assertEqual(fields['rpc_version'], [1, 0, 0])

    async def test_malformed_and_callback_error_propagate(self):
        queue = asyncio.Queue()
        error = asyncio.get_running_loop().create_future()
        queue.put_nowait(b'\x02')
        with self.assertRaises(ValueError):
            await receive_info(queue, error)
        error.set_result(ValueError('queue overflow'))
        with self.assertRaisesRegex(ValueError, 'queue overflow'):
            await receive_info(queue, error)

    async def test_no_response_has_bounded_cancellation(self):
        queue = asyncio.Queue()
        error = asyncio.get_running_loop().create_future()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(0.01):
                await receive_info(queue, error)
        self.assertFalse(error.cancelled())
        self.assertFalse(queue._getters)


if __name__ == '__main__':
    unittest.main()
