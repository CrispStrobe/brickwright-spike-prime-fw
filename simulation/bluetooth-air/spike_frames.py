# SPDX-License-Identifier: Apache-2.0
"""Bounded SPIKE notification framing and the selected firmware's Info contract."""
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


async def receive_info(frames, errors):
    while True:
        pending = asyncio.create_task(frames.get())
        try:
            done, _ = await asyncio.wait((pending, errors), return_when=asyncio.FIRST_COMPLETED)
            if errors in done:
                raise errors.result()
            frame = pending.result()
            payload = cobs_decode(frame)
            if not payload:
                raise ValueError('Empty SPIKE notification payload')
            if payload[0] == 1:
                return frame, payload, info_response(payload)
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
