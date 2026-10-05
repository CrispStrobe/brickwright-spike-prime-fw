# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise our actual ARM service through its published debug packet mailbox.

The only guest writes are request fields in ELF-resolved g_bw_program_debug.
No program state, device feedback, CPU registers or function returns are patched.
Single-machine RunFor calls execute the real guest scheduler and worker.
"""
import struct
import time
from Antmicro.Renode.Core import EmulationManager
from Antmicro.Renode.Time import TimeInterval
from System import UInt32, UInt64


class ProgramWorkflow(object):
    def __init__(self, machine, base, advance):
        self.bus = machine.SystemBus
        self.base = int(str(base), 0)
        if self.base % 4 or not 0x20020000 <= self.base <= 0x20040000 - 112:
            raise AssertionError('ELF mailbox is outside bounded userspace SRAM')
        self.advance = advance
        self.submissions = 0

    def word(self, offset):
        return int(self.bus.ReadDoubleWord(UInt64(self.base + offset)))

    def bytes(self, offset, length):
        return [int(self.bus.ReadByte(UInt64(self.base + offset + i))) for i in range(length)]

    def write(self, offset, value):
        self.bus.WriteDoubleWord(UInt64(self.base + offset), UInt32(value & 0xffffffff))

    def snapshot(self):
        if self.word(0) != 0x42574e50 or self.word(4) != 1:
            return None  # Boot may not have initialized userspace data yet.
        before = self.word(60)
        if not before or before & 1:
            return None
        state = self.word(68)
        result = dict(clock=self.word(64), state=state, id=self.word(72),
                      pc=self.word(76), error=signed(self.word(80)))
        if self.word(60) != before:
            return None
        if state > 5 or result['pc'] > 256:
            raise AssertionError('Malformed guest program publication: %r' % result)
        return result

    def wait(self, predicate, limit_ms=2000, description='program state'):
        for unused in range(limit_ms // 20 + 1):
            result = self.snapshot()
            if result is not None and predicate(result):
                return result
            self.advance()
        raise AssertionError('Timed out waiting for %s; last=%r' % (description, self.snapshot()))

    def exchange(self, operation, ident, extra=None, allow_busy=False):
        packet = [0x70, 1, operation, 0] + le32(ident) + list(extra or [])
        if not 8 <= len(packet) <= 20:
            raise AssertionError('Test packet exceeds public mailbox ABI')
        before = self.word(8)
        if before & 1 or before != self.word(36):
            raise AssertionError('Previous request is still pending')
        sequence = (before + 2) & 0xffffffff
        if not sequence:
            sequence = 2
        self.write(8, sequence - 1)
        self.write(12, len(packet))
        padded = packet + [0] * (20 - len(packet))
        for i in range(5):
            self.write(16 + 4*i, sum(padded[4*i+j] << (8*j) for j in range(4)))
        self.write(8, sequence)
        self.submissions += 1
        for unused in range(101):
            if self.word(36) == sequence:
                reply = self.bytes(40, 20)
                if self.word(36) != sequence:
                    continue
                if reply[:3] != [0x71, 1, operation] or unsigned(reply[4:8]) != ident:
                    raise AssertionError('Uncorrelated guest reply: %r' % reply)
                rc = signed(unsigned(reply[8:12]))
                if rc and not (allow_busy and rc == -16):
                    raise AssertionError('Guest request %d failed: %d' % (operation, rc))
                return reply, rc
            self.advance()
        raise AssertionError('Actual worker did not acknowledge operation %d' % operation)

    def upload(self, ident, payload, python=False):
        count = len(payload) if python else len(payload) // 16
        self.exchange(7 if python else 0, ident, le32(count) + le32(crc32(payload)))
        for offset in range(0, len(payload), 10):
            self.exchange(1, ident, [offset & 255, (offset >> 8) & 255] + payload[offset:offset+10])
        reply, unused = self.exchange(2, ident)
        if reply[3] != 1:
            raise AssertionError('Committed program is not READY')
        self.wait(lambda s: s['state'] == 1 and s['id'] == ident, description='committed READY')

    def start(self, ident, allow_unwind=False):
        for unused in range(51):
            reply, rc = self.exchange(3, ident, allow_busy=allow_unwind)
            if rc == 0:
                if reply[3] != 2 or unsigned(reply[12:14]) != 0 or unsigned(reply[18:20]) != 0:
                    raise AssertionError('START did not reset RUNNING/pc/error: %r' % reply)
                return
            self.advance()
        raise AssertionError('Python execution did not unwind for retained START')


def unsigned(values):
    return sum(value << (8*i) for i, value in enumerate(values))


def signed(value):
    return value if value < 0x80000000 else value - 0x100000000


def signed16(value):
    return value if value < 0x8000 else value - 0x10000


def le32(value):
    return [(value >> shift) & 255 for shift in (0, 8, 16, 24)]


def crc32(values):
    crc = 0xffffffff
    for value in values:
        crc ^= value
        for unused in range(8):
            crc = (crc >> 1) ^ (0xedb88320 if crc & 1 else 0)
    return crc ^ 0xffffffff


def payload_bytes(raw):
    return [v if isinstance(v, int) else ord(v) for v in raw]


def mc_check_program_workflow(base):
    machine = monitor.Machine
    if not machine.IsPaused:
        raise AssertionError('Workflow must begin with a paused loaded machine')
    elapsed = [0]
    started = time.time()

    def advance():
        if elapsed[0] + 20 > 120000 or time.time() - started > 575:
            raise AssertionError('Workflow exceeded 120 guest seconds / 575 host seconds')
        EmulationManager.Instance.CurrentEmulation.RunFor(TimeInterval.FromMilliseconds(UInt64(20)))
        elapsed[0] += 20
        if not machine.IsPaused:
            raise AssertionError('RunFor did not leave the guest paused')

    client = ProgramWorkflow(machine, base, advance)
    client.wait(lambda s: True, 110000, 'real program worker publication after full board boot')
    ident = 0x1357
    native = payload_bytes(struct.pack('<8i', 2, 150, 0, 0, 0, 0, 0, 0))
    client.upload(ident, native)
    native_upload_submissions = client.submissions
    completions = []
    for cycle in range(3):
        client.start(ident)
        running = client.wait(lambda s: s['state'] == 2 and s['id'] == ident and s['pc'] == 1,
                              description='native WAIT execution')
        if cycle == 2:
            reply, unused = client.exchange(4, ident)
            if reply[3] != 4:
                raise AssertionError('STOP did not publish STOPPED')
            client.wait(lambda s: s['state'] == 4 and s['id'] == ident, description='STOPPED')
            client.start(ident)
            running = client.wait(lambda s: s['state'] == 2 and s['id'] == ident and s['pc'] == 1,
                                  description='WAIT after STOP/START without upload')
        complete = client.wait(lambda s: s['state'] == 3 and s['id'] == ident,
                               description='native COMPLETE without reload')
        if complete['error'] != 0 or complete['pc'] != 1 or complete['clock'] - running['clock'] < 100:
            raise AssertionError('Retained WAIT/END completed incorrectly: %r -> %r' % (running, complete))
        status_reply, unused = client.exchange(5, ident)
        if status_reply[3] != 3 or unsigned(status_reply[12:14]) != 1 or unsigned(status_reply[18:20]) != 0:
            raise AssertionError('Actual STATUS did not confirm COMPLETE')
        completions.append(complete['clock'])
    # Exactly one upload plus START, START, START, STOP, START and three STATUS
    # packets: restarts must
    # not be smuggled in as an implicit replacement of the retained program.
    if client.submissions != native_upload_submissions + 8:
        raise AssertionError('Unexpected transaction during retained native restarts')

    python_id = 0x2468
    client.upload(python_id, payload_bytes(b'raise OSError(5)\n'), python=True)
    python_upload_submissions = client.submissions
    faults = []
    for unused in range(2):
        client.start(python_id, allow_unwind=True)
        fault = client.wait(lambda s: s['state'] == 5 and s['id'] == python_id,
                            description='real MicroPython OSError fault')
        if fault['error'] != -5:
            raise AssertionError('Python OSError errno was lost: %r' % fault)
        status_reply, unused = client.exchange(5, python_id)
        if status_reply[3] != 5 or signed16(unsigned(status_reply[18:20])) != -5:
            raise AssertionError('Actual STATUS did not preserve Python errno')
        faults.append(fault['error'])
    print('Program workflow passed: ARM worker native COMPLETE/START and STOP/START '
          'without reload; Python FAULT/START retained OSError; completions=%r '
          'faults=%r requests=%d python_followup_requests=%d guest_ms=%d' %
          (completions, faults, client.submissions,
           client.submissions - python_upload_submissions, elapsed[0]))
