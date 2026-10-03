# SPDX-License-Identifier: Apache-2.0
"""Bounded SPIKE frames and selected Info/periodic-battery contracts."""
import asyncio
import struct
from spike_codec import cobs_decode


class FrameBuffer:
    def __init__(self, maximum=1200, maximum_frames=64):
        self.pending = bytearray()
        self.maximum = maximum
        self.maximum_frames = maximum_frames

    def feed(self, chunk):
        frames = []
        for value in chunk:
            self.pending.append(value)
            if len(self.pending) > self.maximum:
                raise ValueError('SPIKE notification exceeds frame bound')
            if value == 2:
                frames.append(bytes(self.pending))
                self.pending.clear()
                if len(frames) > self.maximum_frames:
                    raise ValueError('Too many SPIKE notification frames')
        return frames


def info_response(payload):
    # apps/btsensor/btsensor_modern.c send_info and btsensor_main.c's
    # selected modern_config: type, RPC/firmware versions, limits, product ID.
    if len(payload) != 17 or payload[0] != 1:
        raise ValueError('InfoResponse must contain exactly 17 bytes')
    values = struct.unpack('<BBB H BB H HHHH', payload)
    expected = (1, 1, 0, 0, 0, 1, 0, 20, 1024, 512, 0)
    if values != expected:
        raise ValueError('InfoResponse differs from selected firmware contract: %r' % (values,))
    return dict(rpc_version=list(values[1:4]), firmware_version=list(values[4:7]),
                max_packet=values[7], max_message=values[8], max_chunk=values[9],
                product_group_device=values[10])


def notification_ack(payload):
    # modern.c MSG_DEVICE_NOTIFICATION_REQUEST emits [0x29, status].
    # This qualification requires successful subscribe/unsubscribe, not a
    # rejected interval. The requested interval is not echoed on the wire.
    if payload != b"\x29\x00":
        raise ValueError('Notification acknowledgement must be exactly 0x29,0x00')
    return dict(message_type=0x29, status=0)


def battery_notification(payload, expected_percent=None):
    # modern_notify.c prepends type0/percentage to the coherent snapshot;
    # modern.c prefixes type0x3c and the little-endian record byte count.
    # The no-attached-sensor fixture must contain exactly this one record.
    if len(payload) != 5 or payload[0] != 0x3c:
        raise ValueError('Battery-only DeviceNotification must contain exactly 5 bytes')
    declared = int.from_bytes(payload[1:3], 'little')
    if declared != 2 or payload[3] != 0:
        raise ValueError('Expected one complete type-0 battery record')
    percent = payload[4]
    if percent > 100:
        raise ValueError('Battery percentage exceeds 100')
    if expected_percent is not None:
        if type(expected_percent) is not int or not 0 <= expected_percent <= 100:
            raise ValueError('Expected battery percentage must be an integer in 0..100')
        if percent != expected_percent:
            raise ValueError('Battery percentage differs from selected fixture')
    return dict(message_type=0x3c, record_bytes=declared, battery_percent=percent,
                records=[dict(type=0, percent=percent)])


async def receive_payload(frames, errors, timeout=10, message_type=None):
    if timeout <= 0:
        raise ValueError('Notification timeout must be positive')
    async with asyncio.timeout(timeout):
        while True:
            pending = asyncio.create_task(frames.get())
            try:
                done, _ = await asyncio.wait((pending, errors), return_when=asyncio.FIRST_COMPLETED)
                if errors in done:
                    raise errors.result()
                frame = pending.result()
                payload = cobs_decode(frame)
                if not payload or len(payload) > 1024:
                    raise ValueError('SPIKE notification payload length is outside 1..1024')
                if message_type is None or payload[0] == message_type:
                    return frame, payload
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def receive_info(frames, errors):
    frame, payload = await receive_payload(frames, errors, timeout=60, message_type=1)
    return frame, payload, info_response(payload)
