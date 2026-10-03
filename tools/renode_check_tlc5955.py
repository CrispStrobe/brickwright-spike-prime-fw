# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Check actual SPI1 bytes and GPIO LAT against the selected digital model."""


def mc_check_tlc5955():
    if not monitor.Machine.IsPaused:
        raise ValueError('Display check requires a paused machine')
    bus = monitor.Machine['sysbus']
    display = monitor.Machine['sysbus.spi1.display']
    port = monitor.Machine['sysbus.gpioPortA']
    spi = monitor.Machine['sysbus.spi1']
    # Use the real STM32 output port and SPI data register; no guest executes.
    port.WriteDoubleWord(0x00, 1 << 30)
    port.WriteDoubleWord(0x18, 1 << 31)
    display.Reset()
    spi.WriteDoubleWord(0x00, 0x344)  # SPE, master, software NSS high.

    def send(packed, prefix=()):
        for value in list(prefix) + [(packed >> (8 * i)) & 255 for i in range(96, -1, -1)]:
            bus.WriteByte(0x4001300c, value)
            if bus.ReadByte(0x4001300c) != 0:
                raise AssertionError('Unexpected modeled SPI response')

    def latch():
        port.WriteDoubleWord(0x18, 1 << 31)
        port.WriteDoubleWord(0x18, 1 << 15)

    words = [(i * 1237 + 0x1234) & 0xffff for i in range(48)]
    packed = sum(value << (16 * i) for i, value in enumerate(words))
    send(packed, [0x7f, 0xa5, 0xff])
    display.FinishTransmission()
    if display.Frames != 0 or display.GetGrayscale(0) != 0:
        raise AssertionError('SPI bytes/transaction end committed a latch')
    latch()
    for i, value in enumerate(words):
        if display.GetGrayscale(i) != value or display.GetWireWord(47 - i) != value:
            raise AssertionError('Grayscale shift or wire/chip order differs')
    frames = display.Frames
    port.WriteDoubleWord(0x18, 1 << 15)
    port.WriteDoubleWord(0x18, 1 << 31)
    if display.Frames != frames:
        raise AssertionError('Repeated high or falling LAT committed a latch')

    dc = [(i * 3 + 5) & 127 for i in range(48)]
    bc, mc = [13, 72, 126], [2, 5, 7]
    control = (1 << 768) | (0x96 << 760) | (9 << 366)
    control |= sum(value << (7 * i) for i, value in enumerate(dc))
    control |= sum(value << (345 + 7 * i) for i, value in enumerate(bc))
    control |= sum(value << (336 + 3 * i) for i, value in enumerate(mc))
    send(control)
    latch()
    if display.ControlLatches != 1 or display.ControlFunction != 9:
        raise AssertionError('Control command/fields not latched')
    for i in range(48):
        if display.GetControlDotCorrection(i) != dc[i] or display.GetGrayscale(i) != words[i]:
            raise AssertionError('Control write changed grayscale or lost DC data')
    for i in range(3):
        if display.GetControlBrightness(i) != bc[i] or display.GetMaximumCurrent(i) != 0:
            raise AssertionError('Brightness or first MC write differs')
    send(control)
    latch()
    if display.ControlLatches != 2 or any(display.GetMaximumCurrent(i) != mc[i] for i in range(3)):
        raise AssertionError('Matching second MC write was not confirmed')
    # A rejected command carries different fields, exposing unwanted copies.
    invalid = (1 << 768) | (0x95 << 760) | (22 << 366)
    invalid |= sum((127 - value) << (7 * i) for i, value in enumerate(dc))
    invalid |= sum((127 - value) << (345 + 7 * i) for i, value in enumerate(bc))
    invalid |= sum((7 - value) << (336 + 3 * i) for i, value in enumerate(mc))
    send(invalid)
    latch()
    if display.ControlLatches != 2 or display.InvalidControlLatches != 1:
        raise AssertionError('Invalid control command accepted')
    if (any(display.GetMaximumCurrent(i) != mc[i] or display.GetControlBrightness(i) != bc[i] for i in range(3))
            or display.ControlFunction != 9
            or any(display.GetControlDotCorrection(i) != dc[i] for i in range(48))):
        raise AssertionError('Invalid command changed retained control data')

    # Confirmed A must survive the first B; only a matching second B commits.
    next_mc = [6, 1, 3]
    next_control = control & ~(((1 << 9) - 1) << 336)
    next_control |= sum(value << (336 + 3 * i) for i, value in enumerate(next_mc))
    send(next_control)
    latch()
    if any(display.GetMaximumCurrent(i) != mc[i] for i in range(3)):
        raise AssertionError('Mismatching first MC write changed confirmed current')
    send(next_control)
    latch()
    if display.ControlLatches != 4 or any(display.GetMaximumCurrent(i) != next_mc[i] for i in range(3)):
        raise AssertionError('Matching replacement MC write was not confirmed')

    # Chip registers shift continuously across SPI transaction boundaries.
    next_words = [value ^ 0xffff for value in words]
    next_packed = sum(value << (16 * i) for i, value in enumerate(next_words))
    data = [(next_packed >> (8 * i)) & 255 for i in range(96, -1, -1)]
    for index, value in enumerate(data):
        bus.WriteByte(0x4001300c, value)
        bus.ReadByte(0x4001300c)
        if index == 40:
            display.FinishTransmission()
    if display.GetGrayscale(47) != words[47]:
        raise AssertionError('Unlatched shift changed grayscale output')
    latch()
    if display.GrayscaleLatches != 2 or any(display.GetGrayscale(i) != next_words[i] for i in range(48)):
        raise AssertionError('Split transfer lost shift state')

    display.Reset()
    if (display.TotalBytes != 0 or display.Frames != 0 or display.InvalidControlLatches != 0
            or display.ControlLatches != 0 or display.GrayscaleLatches != 0):
        raise AssertionError('Reset retained counters')
    if any(display.GetGrayscale(i) != 0 or display.GetControlDotCorrection(i) != 0 for i in range(48)):
        raise AssertionError('Reset retained deterministic register state')
    if (display.ControlFunction != 0
            or any(display.GetMaximumCurrent(i) != 0 or display.GetControlBrightness(i) != 0 for i in range(3))):
        raise AssertionError('Reset retained control/current fields')
    print('TLC5955 passed: real SPI1/PA15, shift retention, rising LAT, word order, control/MC confirmation/replacement, invalid commands and reset')


def mc_check_tlc5955_guest():
    """Read-only assertions after the unchanged guest reaches daemon readiness."""
    if not monitor.Machine.IsPaused:
        raise ValueError('Guest display check requires a paused machine')
    display = monitor.Machine['sysbus.spi1.display']
    if (display.ControlLatches != 2 or display.GrayscaleLatches < 1
            or display.InvalidControlLatches != 0
            or display.TotalBytes < 291 or display.TotalBytes % 97 != 0):
        raise AssertionError('Guest did not complete expected valid display transfers')
    if (display.ControlFunction != 0x19
            or any(display.GetControlDotCorrection(i) != 127 for i in range(48))
            or any(display.GetControlBrightness(i) != 127 or display.GetMaximumCurrent(i) != 0 for i in range(3))):
        raise AssertionError('Guest display control values differ from board initialization')
    print('TLC5955 guest passed: bytes=%d control=%d grayscale=%d invalid=%d FC=0x%02x wire=%s' % (
        display.TotalBytes, display.ControlLatches, display.GrayscaleLatches,
        display.InvalidControlLatches, display.ControlFunction,
        ','.join(str(display.GetWireWord(i)) for i in range(21))))
