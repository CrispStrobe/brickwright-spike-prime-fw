# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Qualify real platform TIM2 -> ADC scan -> circular DMA, without a guest."""

from Antmicro.Renode.Time import TimeInterval
from System import UInt64


def mc_check_adc_dma():
    machine = monitor.Machine
    if not machine.IsPaused:
        raise ValueError('ADC DMA check requires a paused machine')
    bus = machine.SystemBus
    adc = machine['sysbus.adc1']
    dma = machine['sysbus.dma2']
    timer = machine['sysbus.timer2']
    # This test has loaded no guest or ELF. Use ordinary mapped SRAM solely
    # as model-test DMA destination; never patch a firmware-owned ADC buffer.
    address = 0x2003f004
    expected = [123, 3100, 2048, 456, 4095, 4095]
    for channel, value in zip([10, 11, 8, 3, 14, 1], expected):
        adc.SetChannelValue(channel, value)
    bus.WriteDoubleWord(address - 4, 0x12345678)
    bus.WriteDoubleWord(address + 12, 0x87654321)
    for index in range(6):
        bus.WriteWord(address + 2 * index, 0xa55a)

    def advance(steps):
        # Drive the real clock while the CPU stays paused. Short steps retain
        # individual 100us ADC completions between 1ms timer update events.
        for unused in range(steps):
            machine.ClockSource.Advance(TimeInterval.FromNanoseconds(UInt64(100000)), True)

    def buffer_is(values):
        actual = [int(bus.ReadWord(address + 2 * index)) for index in range(6)]
        if actual != values:
            raise AssertionError('ADC DMA rank order/data differs: %r != %r' % (actual, values))
        if bus.ReadDoubleWord(address - 4) != 0x12345678 or bus.ReadDoubleWord(address + 12) != 0x87654321:
            raise AssertionError('ADC DMA wrote outside its six halfword destination')

    # Mirror the board driver's order, notably ADON BEFORE the sequence writes.
    adc.WriteDoubleWord(0x04, 1 << 8)  # CR1 SCAN, 12-bit
    adc.WriteDoubleWord(0x08, 1 | (1 << 8) | (1 << 9) | (6 << 24) | (1 << 28))
    adc.WriteDoubleWord(0x2c, 5 << 20)
    adc.WriteDoubleWord(0x34, 10 | (11 << 5) | (8 << 10) | (3 << 15) | (14 << 20) | (1 << 25))
    dma.WriteDoubleWord(0x10, 0)
    dma.WriteDoubleWord(0x14, 6)
    dma.WriteDoubleWord(0x18, 0x4001204c)
    dma.WriteDoubleWord(0x1c, address)
    dma.WriteDoubleWord(0x10, 1 | (1 << 4) | (1 << 8) | (1 << 10) | (1 << 11) | (1 << 13))
    timer.WriteDoubleWord(0x28, 0)  # PSC=0, board input96MHz
    timer.WriteDoubleWord(0x2c, 95999)  # ARR, real32-bit TIM2
    timer.WriteDoubleWord(0x04, 2 << 4)  # MMS update TRGO
    advance(18)
    buffer_is([0xa55a] * 6)  # No SWSTART/direct ADC trigger or free-running scan.
    timer.WriteDoubleWord(0x00, 1)
    advance(18)
    buffer_is(expected)

    def completed():
        if not (dma.ReadDoubleWord(0x00) & (1 << 5)):
            raise AssertionError('ADC DMA stream0 did not latch transfer completion')
        if not (dma.ReadDoubleWord(0x10) & 1) or dma.ReadDoubleWord(0x14) != 6:
            raise AssertionError('ADC circular DMA did not retain EN and reload NDTR')
        dma.WriteDoubleWord(0x08, 1 << 5)
        if dma.ReadDoubleWord(0x00) & (1 << 5):
            raise AssertionError('ADC DMA completion W1C did not clear')

    completed()
    # Change the modeled physical voltage, then observe subsequent real DMA
    # writes. 3000 is center-button pressed;4095 is the released ladder.
    adc.SetChannelValue(14, 3000)
    expected[4] = 3000
    advance(10)
    buffer_is(expected)
    completed()
    adc.SetChannelValue(14, 4095)
    expected[4] = 4095
    advance(10)
    buffer_is(expected)
    completed()
    timer.WriteDoubleWord(0x00, 0)
    adc.SetChannelValue(14, 3000)
    advance(20)
    buffer_is(expected)
    print('ADC DMA passed: TIM2 TRGO, six halfword ranks, circular repeats, physical press/release, W1C')
