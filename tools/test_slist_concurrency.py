#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile real compat list/IRQ-lock primitives and force the lost-TX-node race."""
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


HARNESS = r'''/* Host harness: BSD-3-Clause, Brickwright contributors 2026.
 * Extracted IRQ routines and included list header retain Apache-2.0 notices. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
static void test_pause_get(void *list);
#include <zephyr/sys/slist.h>
static pthread_mutex_t irq_lock_mutex;
static pthread_once_t irq_lock_once = PTHREAD_ONCE_INIT;
'''
TEST = r'''
static sys_slist_t pending=SYS_SLIST_STATIC_INIT(pending);
static sys_snode_t older,newer;
static pthread_mutex_t state_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;
static bool pause_enabled,producer_start,producer_attempt,producer_done;
static void *append_during_get(void *unused) {
  (void)unused;
  pthread_mutex_lock(&state_mutex);
  while(!producer_start)pthread_cond_wait(&changed,&state_mutex);
  producer_attempt=true;pthread_cond_broadcast(&changed);
  pthread_mutex_unlock(&state_mutex);
  sys_slist_append(&pending,&newer);
  pthread_mutex_lock(&state_mutex);producer_done=true;
  pthread_cond_broadcast(&changed);pthread_mutex_unlock(&state_mutex);return NULL;
}
static void test_pause_get(void *list) {
  if(!pause_enabled||list!=&pending)return;
  pause_enabled=false;
  pthread_mutex_lock(&state_mutex);producer_start=true;pthread_cond_broadcast(&changed);
  while(!producer_attempt)pthread_cond_wait(&changed,&state_mutex);
  /* Pause completion after clearing head but before tail. The actual producer
   * must remain excluded until the entire removal is complete. */
  struct timespec deadline;clock_gettime(CLOCK_REALTIME,&deadline);
  deadline.tv_nsec+=100000000;
  if(deadline.tv_nsec>=1000000000){deadline.tv_sec++;deadline.tv_nsec-=1000000000;}
  int rc=0;
  while(!producer_done&&rc!=ETIMEDOUT)rc=pthread_cond_timedwait(&changed,&state_mutex,&deadline);
  assert(!producer_done&&rc==ETIMEDOUT);
  pthread_mutex_unlock(&state_mutex);
}
#define COUNT 30000
struct item {sys_snode_t node;unsigned sequence;};
static struct item items[COUNT];
static sys_slist_t stress=SYS_SLIST_STATIC_INIT(stress);
static void *produce(void *unused) {
  (void)unused;
  for(unsigned i=0;i<COUNT;i++){items[i].sequence=i;sys_slist_append(&stress,&items[i].node);}
  return NULL;
}
int main(void) {
  alarm(10);
  pthread_t producer;
  sys_slist_append(&pending,&older);pause_enabled=true;
  assert(pthread_create(&producer,NULL,append_during_get,NULL)==0);
  assert(sys_slist_get(&pending)==&older);assert(pthread_join(producer,NULL)==0);
  assert(sys_slist_peek_head(&pending)==&newer);assert(sys_slist_peek_tail(&pending)==&newer);
  assert(sys_slist_get(&pending)==&newer);assert(sys_slist_is_empty(&pending));
  /* Exercise recursive insert->prepend locking and find/remove ownership. */
  sys_slist_insert(&pending,NULL,&older);sys_slist_insert(&pending,&older,&newer);
  assert(sys_slist_find(&pending,&newer,NULL));
  assert(sys_slist_find_and_remove(&pending,&newer));
  sys_slist_remove(&pending,NULL,&older);assert(sys_slist_is_empty(&pending));
  assert(pthread_create(&producer,NULL,produce,NULL)==0);
  for(unsigned i=0;i<COUNT;i++) {
    sys_snode_t *node;
    while(!(node=sys_slist_get(&stress)))sched_yield();
    assert(node==&items[i].node&&items[i].sequence==i);
  }
  assert(pthread_join(producer,NULL)==0);assert(sys_slist_is_empty(&stress));
  assert(sys_slist_peek_tail(&stress)==NULL);
  puts("Actual compat list primitives: forced TX-context interleaving and 30000 ordered concurrent nodes passed");
  return 0;
}
'''


def main():
    header = (ROOT / 'bluetooth/zephyr_compat/include/zephyr/sys/slist.h').read_text()
    # Insert a scheduling pause into the actual removal boundary that formerly
    # lost the next TX context; production code has no test hook.
    header = header.replace('    list->head = node->next;',
                            '    list->head = node->next; test_pause_get(list);')
    work = (ROOT / 'bluetooth/zephyr_compat/src/work.c').read_text()
    # Preserve both original Apache notices, and use the actual IRQ mutex.
    locks = work[:work.index('*/') + 2] + '\n' + '\n'.join(
        function(work, signature) for signature in
        ('static void irq_lock_init(', 'unsigned int brickwright_irq_lock(',
         'void brickwright_irq_unlock('))
    with tempfile.TemporaryDirectory(prefix='bw-slist-concurrency-') as temp:
        directory = Path(temp)
        include = directory / 'zephyr/sys'
        include.mkdir(parents=True)
        source = directory / 'test.c'
        source.write_text(HARNESS + locks + TEST)
        binary = directory / 'test'
        for mutant in (False, True):
            tested = header
            if mutant:
                tested = tested.replace('unsigned int key = brickwright_irq_lock();', '')
                tested = tested.replace('brickwright_irq_unlock(key);', '')
            (include / 'slist.h').write_text(tested)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', '-Wno-macro-redefined', '-pthread',
                            '-I' + temp, '-I' + str(ROOT / 'bluetooth/zephyr_compat/include'),
                            str(source), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=12)
            if not mutant:
                if result.returncode:
                    raise RuntimeError(result.stderr)
                print(result.stdout.strip())
            elif result.returncode == 0:
                raise RuntimeError('Missing primitive serialization mutant survived')
            else:
                print('Rejected mutant: concurrent pending-list mutation without IRQ lock')


if __name__ == '__main__':
    main()
