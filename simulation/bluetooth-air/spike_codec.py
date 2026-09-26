# SPDX-License-Identifier: Apache-2.0
"""SPIKE App 3 frame codec (COBS with XOR 0x03 and 0x02 terminator).

A Python port of protocol/js/spike-codec.js, checked against the shared
fixtures in protocol/fixtures/spike-cobs-v1.json.
"""

END = 0x02
XOR = 0x03
BLOCK_MAX = 84


def _cobs(payload: bytes) -> bytes:
    output = bytearray([0xFF])
    code_index, block = 0, 1
    for byte in payload:
        if byte <= 2:
            output[code_index] = block + 2 + byte * BLOCK_MAX
            code_index = len(output)
            output.append(0xFF)
            block = 1
        else:
            output.append(byte)
            block += 1
            if block > BLOCK_MAX:
                code_index = len(output)
                output.append(0xFF)
                block = 1
    output[code_index] = block + 2
    return bytes(output)


def _uncobs(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty COBS payload")
    output = bytearray()
    offset = 0
    while offset < len(data):
        code = data[offset]
        offset += 1
        if code <= 2:
            raise ValueError("reserved COBS code")
        if code == 0xFF:
            block, delimiter = BLOCK_MAX, None
        else:
            delimiter, block = divmod(code - 3, BLOCK_MAX)
            if delimiter > 2:
                raise ValueError("invalid COBS delimiter")
        if offset + block > len(data):
            raise ValueError("truncated COBS block")
        output += data[offset:offset + block]
        offset += block
        if delimiter is not None and offset < len(data):
            output.append(delimiter)
    return bytes(output)


def cobs_encode(payload: bytes, high_priority: bool = False) -> bytes:
    body = bytes(b ^ XOR for b in _cobs(payload))
    return (b"\x01" if high_priority else b"") + body + bytes([END])


def cobs_decode(frame: bytes) -> bytes:
    if len(frame) < 2 or frame[-1] != END:
        raise ValueError("unterminated frame")
    start = 1 if frame[0] == 1 else 0
    encoded = frame[start:-1]
    if not encoded:
        raise ValueError("empty encoded frame")
    if any(1 <= b <= 3 for b in encoded):
        raise ValueError("unescaped control byte")
    return _uncobs(bytes(b ^ XOR for b in encoded))
