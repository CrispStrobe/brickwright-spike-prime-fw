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
from spike_frames import (FrameBuffer, info_response, receive_info,
                          notification_ack, battery_notification, receive_payload)

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


class PeriodicContract(unittest.TestCase):
    def test_exact_success_ack_and_reject_failure_or_truncation(self):
        self.assertEqual(notification_ack(b'\x29\0'), dict(message_type=0x29, status=0))
        for payload in (b'', b'\x29', b'\x29\1', b'\x29\0\0', b'\x28\0'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                notification_ack(payload)

    def test_battery_boundaries_and_optional_fixture_receipt(self):
        for percent in (0, 42, 100):
            payload = bytes([0x3c, 2, 0, 0, percent])
            receipt = battery_notification(payload, expected_percent=percent)
            self.assertEqual(receipt['records'], [dict(type=0, percent=percent)])
            self.assertEqual(receipt['record_bytes'], 2)
        with self.assertRaises(ValueError):
            battery_notification(b'\x3c\2\0\0\x2a', expected_percent=43)
        for expected in (-1, 101, 1.5, False):
            with self.assertRaises(ValueError):
                battery_notification(b'\x3c\2\0\0\x2a', expected_percent=expected)

    def test_complete_length_type_and_range_are_required(self):
        valid = b'\x3c\2\0\0\x2a'
        invalid = [valid[:length] for length in range(5)] + [valid + b'\0',
                   b'\x3c\1\0\0\x2a', b'\x3c\3\0\0\x2a',
                   b'\x3c\0\2\0\x2a', b'\x3c\2\0\1\x2a',
                   b'\x29\2\0\0\x2a', b'\x3c\2\0\0\x65',
                   b'\x3c\2\0\0\xff']
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                battery_notification(payload)

    def test_ack_and_periodic_records_coalesce_with_trailing_partial(self):
        payloads = [b'\x29\0', b'\x3c\2\0\0\x2a', b'\x3c\2\0\0\x64']
        encoded = [cobs_encode(payload) for payload in payloads]
        for split in range(len(encoded[-1])):
            buffer = FrameBuffer()
            frames = buffer.feed(encoded[0] + encoded[1] + encoded[2][:split])
            frames += buffer.feed(encoded[2][split:])
            self.assertEqual(frames, encoded)


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

    async def test_periodic_receipts_in_order_after_fragmented_delivery(self):
        queue = asyncio.Queue(maxsize=64)
        error = asyncio.get_running_loop().create_future()
        buffer = FrameBuffer()
        data = cobs_encode(b'\x29\0') + cobs_encode(b'\x3c\2\0\0\x2a')
        for byte in data:
            for frame in buffer.feed(bytes([byte])):
                queue.put_nowait(frame)
        _, ack = await receive_payload(queue, error)
        self.assertEqual(notification_ack(ack)['status'], 0)
        _, payload = await receive_payload(queue, error)
        self.assertEqual(battery_notification(payload, 42)['battery_percent'], 42)

    async def test_generic_timeout_includes_unrelated_traffic(self):
        queue = asyncio.Queue()
        error = asyncio.get_running_loop().create_future()
        for _ in range(20):
            queue.put_nowait(cobs_encode(b'\x01'))
        with self.assertRaises(TimeoutError):
            await receive_payload(queue, error, timeout=.01, message_type=0x3c)
        self.assertFalse(error.cancelled())
        self.assertFalse(queue._getters)

    async def test_generic_error_and_oversize_are_not_hidden_by_type_filter(self):
        queue = asyncio.Queue()
        error = asyncio.get_running_loop().create_future()
        queue.put_nowait(cobs_encode(b'x' * 1025))
        with self.assertRaises(ValueError):
            await receive_payload(queue, error, message_type=0x3c)
        error.set_result(ValueError('callback failed'))
        with self.assertRaisesRegex(ValueError, 'callback failed'):
            await receive_payload(queue, error)


if __name__ == '__main__':
    unittest.main()
