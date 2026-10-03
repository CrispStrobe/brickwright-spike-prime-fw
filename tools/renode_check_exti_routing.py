# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Brickwright contributors
"""Exercise the platform's real GPIO/SYSCFG/EXTI path before guest execution."""


def mc_check_exti_routing():
    if not monitor.Machine.IsPaused:
        raise ValueError('External interrupt routing check requires a paused machine')
    port_a = monitor.Machine['sysbus.gpioPortA']
    port_c = monitor.Machine['sysbus.gpioPortC']
    syscfg = monitor.Machine['sysbus.syscfg']
    exti = monitor.Machine['sysbus.exti']
    bit = 1 << 9
    exti.WriteDoubleWord(0x00, bit)
    exti.WriteDoubleWord(0x08, bit)
    exti.WriteDoubleWord(0x0c, bit)
    exti.WriteDoubleWord(0x14, bit)

    def pending(expected):
        actual = bool(exti.ReadDoubleWord(0x14) & bit)
        if actual != expected or exti.Connections[9].IsSet != expected:
            raise AssertionError('EXTI9 pending/output differs from selected GPIO edge')

    pending(False)
    for unused in range(8):
        port_c.OnGPIO(9, True)
        port_c.OnGPIO(9, False)
        pending(False)
    port_a.OnGPIO(9, True)
    pending(True)
    exti.WriteDoubleWord(0x14, bit)
    pending(False)
    port_a.OnGPIO(9, False)
    pending(True)
    exti.WriteDoubleWord(0x14, bit)
    pending(False)

    # Select port C for line 9 through its real EXTICR3 field.
    syscfg.WriteDoubleWord(0x10, 2 << 4)
    exti.WriteDoubleWord(0x14, bit)
    for unused in range(8):
        port_a.OnGPIO(9, True)
        port_a.OnGPIO(9, False)
        pending(False)
    port_c.OnGPIO(9, True)
    pending(True)
    exti.WriteDoubleWord(0x14, bit)
    pending(False)
    port_c.OnGPIO(9, False)
    pending(True)
    exti.WriteDoubleWord(0x14, bit)
    pending(False)
    print('SYSCFG routing passed: selected PA9/PC9 edges, rejected other port, W1C output clear')
