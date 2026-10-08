# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Observe guest-owned request results; never write guest state or queues."""
import time


def validate_requests(words):
    """Validate the inactive six-call batch, not active DATA or console transport."""
    if len(words) != 100:
        raise AssertionError('Wrong request publication length')
    magic, version, state, sequence, selector, calls, opened, error, closed, close_error = words[:10]
    if (magic != 0x42575251 or version != 1 or state != 2 or sequence != 1
            or selector != 7 or calls != 6 or opened > 0x7fffffff
            or error or closed or close_error):
        raise AssertionError('Guest request header failed: %r' % (words[:10],))
    for i in range(6):
        record = words[10 + 15 * i:25 + 15 * i]
        expected_error = 22 if i == 0 else 14 if i < 5 else 11
        expected_length = 0 if i < 5 else 48
        expected_bytes = [0] * 12 if i < 5 else [0xa5a5a5a5] * 12
        if record != [0xffffffff, expected_error, expected_length] + expected_bytes:
            raise AssertionError('Guest request %d failed: %r' % (i + 1, record))
    return True


def mc_check_lump_requests(base):
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64
    base = int(str(base), 0)
    if base % 4 or not 0x20020000 <= base <= 0x20040000 - 400:
        raise AssertionError('Request publication outside userspace static RAM')
    machine = monitor.Machine
    if not machine.IsPaused:
        raise AssertionError('Request observation must start paused')
    started = time.time()
    for elapsed in range(0, 110001, 20):
        if time.time() - started > 575:
            raise AssertionError('Request observation exceeded 575 host seconds')
        bus = machine.SystemBus
        state = int(bus.ReadDoubleWord(UInt64(base + 8)))
        sequence = int(bus.ReadDoubleWord(UInt64(base + 12)))
        if state in (2, 3):
            words = tuple(int(bus.ReadDoubleWord(UInt64(base + i * 4)))
                          for i in range(100))
            if (state == int(bus.ReadDoubleWord(UInt64(base + 8)))
                    and sequence == int(bus.ReadDoubleWord(UInt64(base + 12)))
                    and state == words[2] and sequence == words[3]):
                validate_requests(list(words))
                print('LUMP protected fixed request batch passed: requests=6 guest_ms=%d' % elapsed)
                return
        elif state not in (0, 1):
            raise AssertionError('Invalid request publication state: %d' % state)
        if elapsed == 110000:
            raise AssertionError('Requests exceeded 110 guest seconds / 575 host seconds')
        EmulationManager.Instance.CurrentEmulation.RunFor(
            TimeInterval.FromMilliseconds(UInt64(20)))
        if not machine.IsPaused:
            raise AssertionError('RunFor did not leave the guest paused')
