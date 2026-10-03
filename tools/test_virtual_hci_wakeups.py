#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Exercise actual virtual HCI slot transitions with adversarial condition waiters."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
typedef int pthread_mutex_t;
typedef int pthread_cond_t;
struct driver_state {
  int backend; bool stopping; pthread_mutex_t virtual_mutex, physical_mutex;
  pthread_cond_t virtual_changed; size_t virtual_length;
  uint8_t virtual_frame[71]; unsigned virtual_enqueued_generation;
  unsigned virtual_received_generation; int transport, controller;
};
#define BRICKWRIGHT_HCI_BACKEND_VIRTUAL 1
static struct driver_state *active;
static bool producer_waiting, receiver_waiting, completion_waiting;
static unsigned broadcasts, signals, feeds, waits;
static int wait_action;
static uint8_t expected[3] = {4, 14, 0};
static int pthread_mutex_lock(pthread_mutex_t *m) {(void)m; return 0;}
static int pthread_mutex_unlock(pthread_mutex_t *m) {(void)m; return 0;}
/* POSIX permits signal to pick any waiter. Choose the completion waiter,
 * which cannot satisfy the slot producer/receiver's different predicate. */
static int pthread_cond_signal(pthread_cond_t *c) {
  (void)c;signals++;completion_waiting=false;return 0;
}
static int pthread_cond_broadcast(pthread_cond_t *c) {
  (void)c;broadcasts++;producer_waiting=false;receiver_waiting=false;
  completion_waiting=false;return 0;
}
static int pthread_cond_wait(pthread_cond_t *c,pthread_mutex_t *m) {
  (void)c;(void)m;assert(++waits<3);
  if(wait_action==1)active->virtual_length=0;
  else if(wait_action==2)active->stopping=true;
  else assert(false);
  return 0;
}
static int brickwright_h4_feed(void *h4,const void *frame,size_t length) {
  (void)h4;assert(!producer_waiting);assert(length==sizeof(expected));
  assert(!memcmp(frame,expected,length));feeds++;active->stopping=true;return 0;
}
static int brickwright_h4_transport_receive(void *p,int timeout) {(void)p;(void)timeout;return 0;}
static int brickwright_h4_transport_fault(void *p) {(void)p;return 0;}
static int brickwright_controller_recover(void *p) {(void)p;return 0;}
'''
# receive_main references its embedded H4 adapter even in the virtual branch.
HARNESS = HARNESS.replace('int transport, controller;',
                          'struct {int h4;} transport; int controller;')
MAIN = r'''
static void reset(struct driver_state *driver) {
  memset(driver,0,sizeof(*driver));driver->backend=BRICKWRIGHT_HCI_BACKEND_VIRTUAL;
  active=driver;producer_waiting=receiver_waiting=completion_waiting=false;
  broadcasts=signals=feeds=waits=0;wait_action=0;
}
int main(void) {
  struct driver_state driver;
  reset(&driver);receiver_waiting=completion_waiting=true;
  assert(virtual_send(expected,sizeof(expected),&driver)==0);
  assert(!receiver_waiting);assert(driver.virtual_length==sizeof(expected));
  assert(!memcmp(driver.virtual_frame,expected,sizeof(expected)));
  assert(driver.virtual_enqueued_generation==1);
  /* The producer must also wake immediately when the receiver frees the slot,
   * before H4 delivery and completion-generation processing. */
  producer_waiting=completion_waiting=true;
  assert(receive_main(&driver)==NULL);assert(feeds==1);
  assert(driver.virtual_length==0);assert(driver.virtual_received_generation==1);
  assert(broadcasts==3&&signals==0);
  reset(&driver);driver.virtual_length=sizeof(expected);wait_action=1;
  receiver_waiting=completion_waiting=true;
  assert(virtual_send(expected,sizeof(expected),&driver)==0);
  assert(waits==1&&!receiver_waiting&&driver.virtual_enqueued_generation==1);
  reset(&driver);driver.virtual_length=sizeof(expected);wait_action=2;
  assert(virtual_send(expected,sizeof(expected),&driver)==-ESHUTDOWN);
  assert(driver.virtual_enqueued_generation==0);
  reset(&driver);driver.stopping=true;
  assert(virtual_send(expected,sizeof(expected),&driver)==-ESHUTDOWN);
  assert(virtual_send(expected,72,&driver)==-EMSGSIZE);
  assert(driver.virtual_enqueued_generation==0);
  puts("Actual virtual HCI slot wakeups: heterogeneous waiters, backpressure and shutdown passed");
  return 0;
}
'''


def main():
    driver = (ROOT / 'bluetooth/zephyr_compat/src/hci_driver.c').read_text()
    # Retain the original Apache-2.0 notice on the extracted implementation.
    bodies = driver[:driver.index('*/') + 2] + '\n' + '\n'.join(
        function(driver, signature) for signature in
        ('static int virtual_send(', 'static void *receive_main('))
    with tempfile.TemporaryDirectory(prefix='bw-virtual-hci-wakeups-') as temp:
        source = Path(temp) / 'wakeups.c'
        binary = Path(temp) / 'wakeups'
        for name, implementation in (
                ('actual', bodies),
                ('wrong waiter on fill', bodies.replace(
                    'pthread_cond_broadcast(&driver->virtual_changed);',
                    'pthread_cond_signal(&driver->virtual_changed);', 1)),
                ('wrong waiter on drain', bodies.replace(
                    '          pthread_cond_broadcast(&driver->virtual_changed);',
                    '          pthread_cond_signal(&driver->virtual_changed);', 1))):
            source.write_text(HARNESS + implementation + MAIN)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', str(source), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            if name == 'actual':
                if result.returncode:
                    raise RuntimeError(result.stderr)
                print(result.stdout.strip())
            elif not result.returncode:
                raise RuntimeError('Regression did not reject ' + name)
            else:
                print('Rejected mutant: ' + name)


if __name__ == '__main__':
    main()
