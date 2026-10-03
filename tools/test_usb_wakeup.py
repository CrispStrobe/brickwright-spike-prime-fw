#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile patched STM32 USB interrupt paths with register/class mocks."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def function(text, signature):
    match = re.search(r'^' + re.escape(signature) + r'[^;{]*\n\{', text, re.M)
    if not match:
        raise ValueError(f'Implementation missing: {signature}')
    end = match.end()
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


def source(nuttx):
    driver = (nuttx / 'arch/arm/src/stm32/stm32_otgfsdev.c').read_text()
    hardware = (nuttx / 'arch/arm/src/stm32/hardware/stm32fxxxxx_otgfs.h').read_text()
    # Preserve the original Apache-2.0 notices in the temporary compilation.
    result = driver[:driver.index('*/') + 2] + '\n'
    result += hardware[:hardware.index('*/') + 2] + '\n'
    registers = ('GOTGINT', 'GAHBCFG', 'GINTSTS', 'GINTMSK', 'DCTL')
    for line in hardware.splitlines():
        match = re.match(r'#\s*define\s+(\w+)', line)
        if match and (match[1].startswith('OTGFS_GINT') or
                      match[1] in ('OTGFS_DCTL_RWUSIG', 'OTGFS_GAHBCFG_GINTMSK',
                                   'OTGFS_GAHBCFG_TXFELVL') or
                      any(match[1] == 'STM32_OTGFS_' + reg + suffix
                          for reg in registers for suffix in ('', '_OFFSET'))):
            result += line + '\n'
    # F413 uses the non-F446/F469 write-one-to-clear/reserved masks.
    start = driver.index('#if defined(CONFIG_STM32_STM32F446)')
    end = driver.index('/* Debug', start)
    result += driver[start:end]
    result += r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define STM32_OTGFS_BASE 0u
#define OK 0
#define DEBUGASSERT assert
#define usbtrace(...) ((void)0)
struct usbdev_s {int unused;};
struct class_driver {int unused;};
struct stm32_usbdev_s {struct usbdev_s usbdev;struct class_driver *driver;};
static struct stm32_usbdev_s g_otgfsdev;
static uint32_t registers[0x900/4];
static unsigned suspends,resumes,board_suspends,board_resumes,reads;
static char order[16];static unsigned order_count;
static uint32_t stm32_getreg(unsigned address) {
  assert(address/4<sizeof(registers)/sizeof(registers[0]));assert(++reads<100);
  return registers[address/4];
}
static void stm32_putreg(uint32_t value,unsigned address) {
  assert(address/4<sizeof(registers)/sizeof(registers[0]));
  if(address==STM32_OTGFS_GINTSTS) {
    /* Writable IRQ bits clear on writing one; reserved bits stay unchanged. */
    registers[address/4]&=~(value&OTGFS_GINT_RC_W1);
  } else registers[address/4]=value;
}
static void stm32_usbsuspend(struct usbdev_s *dev,bool resume) {
  assert(dev==&g_otgfsdev.usbdev);
  if(resume){board_resumes++;order[order_count++]='p';}
  else {board_suspends++;order[order_count++]='P';}
}
static void class_suspend(struct class_driver *driver,struct usbdev_s *dev) {
  assert(driver&&driver==g_otgfsdev.driver&&dev==&g_otgfsdev.usbdev);
  suspends++;order[order_count++]='s';
}
static void class_resume(struct class_driver *driver,struct usbdev_s *dev) {
  assert(driver&&driver==g_otgfsdev.driver&&dev==&g_otgfsdev.usbdev);
  assert(!(registers[STM32_OTGFS_DCTL/4]&OTGFS_DCTL_RWUSIG));
  resumes++;order[order_count++]='r';
}
#define CLASS_SUSPEND class_suspend
#define CLASS_RESUME class_resume
/* Unexercised endpoint/reset IRQs must not accidentally be dispatched. */
#define stm32_epout_interrupt(priv) assert(0)
#define stm32_epin_interrupt(priv) assert(0)
#define stm32_rxinterrupt(priv) assert(0)
#define stm32_usbreset(priv) assert(0)
#define stm32_enuminterrupt(priv) assert(0)
'''
    result += '\n'.join(function(driver, signature) for signature in (
        'static inline void stm32_resumeinterrupt(',
        'static inline void stm32_suspendinterrupt(',
        'static int stm32_usbinterrupt('))
    initialize = function(driver, 'static void stm32_hwinitialize(')
    start = initialize.index('  /* Disable all interrupts. */')
    end = initialize.rindex('\n}')
    result += '\nstatic void initialize_mask(void) {uint32_t regval;\n' + initialize[start:end] + '\n}\n'
    result += r'''
static void interrupt(uint32_t pending) {
  registers[STM32_OTGFS_GINTSTS/4]|=pending;reads=0;
  assert(stm32_usbinterrupt(0,NULL,NULL)==OK);
}
static void reset(struct class_driver *driver) {
  memset(registers,0,sizeof(registers));g_otgfsdev.driver=driver;
  suspends=resumes=board_suspends=board_resumes=order_count=reads=0;
  memset(order,0,sizeof(order));initialize_mask();
}
int main(void) {
  struct class_driver driver={0};uint32_t retained=1u<<2;
  reset(&driver);
  assert(registers[STM32_OTGFS_GINTMSK/4]&OTGFS_GINT_WKUP);
  assert(registers[STM32_OTGFS_GAHBCFG/4]&OTGFS_GAHBCFG_GINTMSK);
  /* Actual IRQ masking defers wakeup until it is enabled again. */
  registers[STM32_OTGFS_GINTMSK/4]&=~OTGFS_GINT_WKUP;
  interrupt(OTGFS_GINT_WKUP);assert(!resumes&&!board_resumes);
  assert(registers[STM32_OTGFS_GINTSTS/4]&OTGFS_GINT_WKUP);
  registers[STM32_OTGFS_GINTMSK/4]|=OTGFS_GINT_WKUP;
  interrupt(0);assert(resumes==1&&board_resumes==1);interrupt(0);assert(resumes==1);
  reset(&driver);
  /* Suspend followed by wake must acknowledge each event exactly once. */
  registers[STM32_OTGFS_GINTSTS/4]=OTGFS_GINT_RES89;
  interrupt(OTGFS_GINT_USBSUSP);assert(suspends==1&&board_suspends==1&&!resumes);
  registers[STM32_OTGFS_DCTL/4]=OTGFS_DCTL_RWUSIG|retained;
  interrupt(OTGFS_GINT_WKUP);assert(resumes==1&&board_resumes==1);
  assert(registers[STM32_OTGFS_DCTL/4]==retained);
  assert(registers[STM32_OTGFS_GINTSTS/4]==OTGFS_GINT_RES89);
  assert(!memcmp(order,"sPpr",4));interrupt(0);assert(resumes==1&&suspends==1);
  /* Unbound class driver remains safe; board still receives power events. */
  reset(NULL);interrupt(OTGFS_GINT_USBSUSP);
  registers[STM32_OTGFS_DCTL/4]=OTGFS_DCTL_RWUSIG|retained;
  interrupt(OTGFS_GINT_WKUP);assert(!suspends&&!resumes);
  assert(board_suspends==1&&board_resumes==1&&registers[STM32_OTGFS_DCTL/4]==retained);
  interrupt(0);assert(board_resumes==1);
  puts("USB: initialized WKUP mask, suspend/resume dispatch, RWUSIG clearing, acknowledgement and unbound driver passed");
  return 0;
}
'''
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nuttx', type=Path, required=True)
    args = parser.parse_args()
    original = source(args.nuttx)
    with tempfile.TemporaryDirectory(prefix='bw-usb-wakeup-') as temp:
        c = Path(temp) / 'regression.c'
        binary = Path(temp) / 'regression'
        for mutant in (False, True):
            text = original
            if mutant:
                old = 'OTGFS_GINT_RXFLVL | OTGFS_GINT_USBSUSP | OTGFS_GINT_WKUP |'
                if text.count(old) != 1:
                    raise ValueError('Initialization mask changed; update mutation check')
                text = text.replace(old, 'OTGFS_GINT_RXFLVL | OTGFS_GINT_USBSUSP |')
            c.write_text(text)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-parameter', str(c), '-o', str(binary)], check=True)
            if mutant:
                result = subprocess.run([str(binary)], capture_output=True, text=True)
                if result.returncode == 0 or 'OTGFS_GINT_WKUP' not in result.stderr:
                    raise RuntimeError('WKUP mask-removal mutation was not detected')
                print('USB: initialization WKUP mask-removal mutation detected')
            else:
                subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
