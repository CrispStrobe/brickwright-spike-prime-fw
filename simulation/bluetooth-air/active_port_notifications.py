# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exact own-firmware battery plus one coherent ultrasonic snapshot contract."""


def distance_notification(payload, expected_percent=62, expected_port=3, expected_mm=1000):
    for name, value, lower, upper in (
        ('battery', expected_percent, 0, 100), ('port', expected_port, 0, 5),
        ('distance', expected_mm, -32768, 32767)):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError('Invalid expected ' + name)
    # Exactly two records: type0 battery, then type0x0d signed millimetres.
    # Reject missing, unknown, duplicate, reordered and trailing records.
    if len(payload) != 9 or payload[:4] != b'\x3c\x06\x00\x00' or payload[5] != 0x0d:
        raise ValueError('Expected exactly battery then one distance record')
    percent, port = payload[4], payload[6]
    millimeters = int.from_bytes(payload[7:9], 'little', signed=True)
    if percent != expected_percent or port != expected_port or millimeters != expected_mm:
        raise ValueError('Notification differs from selected external input fixture')
    return dict(message_type=0x3c, record_bytes=6, battery_percent=percent,
                records=[dict(type=0, percent=percent),
                         dict(type=0x0d, port=port, millimeters=millimeters)])
