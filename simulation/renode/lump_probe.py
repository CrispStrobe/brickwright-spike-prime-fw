# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Observe the one-shot real userspace probe; never write guest memory/state."""
import time


def validate_probe(words, readonly):
    if len(words) != 8:
        raise AssertionError('Wrong probe publication length')
    magic, version, state, checks, failure, result, error, address = words
    if (magic != 0x42574c50 or version != 1 or state != 2 or checks != 511
            or failure or result or error):
        raise AssertionError('Guest refusal probe failed: %r' % (words,))
    if address != readonly or not 0x08060000 <= address <= 0x08100000 - 48:
        raise AssertionError('Probe read-only output is not the ELF user-flash object')
    return True


def mc_check_lump_probe(base, readonly):
    from Antmicro.Renode.Core import EmulationManager
    from Antmicro.Renode.Time import TimeInterval
    from System import UInt64
    base, readonly = int(str(base), 0), int(str(readonly), 0)
    if base % 4 or not 0x20020000 <= base <= 0x20040000 - 32:
        raise AssertionError('ELF probe result is outside userspace static RAM')
    if not 0x08060000 <= readonly <= 0x08100000 - 48:
        raise AssertionError('ELF probe output object is outside user flash')
    machine = monitor.Machine
    if not machine.IsPaused:
        raise AssertionError('Probe observation must start paused')
    started = time.time()
    for elapsed in range(0, 110001, 20):
        if time.time() - started > 575:
            raise AssertionError('Probe exceeded 575 host seconds')
        bus = machine.SystemBus
        first = int(bus.ReadDoubleWord(UInt64(base + 8)))
        if first in (2, 3):
            words = tuple(int(bus.ReadDoubleWord(UInt64(base + i * 4)))
                          for i in range(8))
            if first == int(bus.ReadDoubleWord(UInt64(base + 8))):
                validate_probe(words, readonly)
                print('LUMP protected refusal probe passed: checks=511 guest_ms=%d' % elapsed)
                return
        elif first not in (0, 1):
            raise AssertionError('Invalid probe state: %d' % first)
        if elapsed == 110000:
            raise AssertionError('Probe exceeded 110 guest seconds / 575 host seconds')
        EmulationManager.Instance.CurrentEmulation.RunFor(
            TimeInterval.FromMilliseconds(UInt64(20)))
        if not machine.IsPaused:
            raise AssertionError('RunFor did not leave the guest paused')
