/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Host-only service fault injection around the actual registration function.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#define BOARD_LEGOPORT_COUNT 6
#define LUMP_KTHREAD_PRIO 123
#define LUMP_KTHREAD_STACK 1024
#define LOG_ERR 3
#define LOG_INFO 6
#define OK 0

/* Only fields referenced by registration, plus a live-session sentinel.
 * No scheduler, queue, mutex or handoff behavior is emulated here.
 */
struct lump_engine_s
{
  uint8_t port;
  int wakeup, info_lock, tx_lock, dq_lock, cb_lock;
  int kthread;
  bool dcm_cb_registered;
  uint64_t live_session;
};

static struct lump_engine_s g_lump[BOARD_LEGOPORT_COUNT];
static bool g_lump_registration_started;
static int g_fault, g_threads, g_handoffs, g_semaphores, g_mutexes;

static void nxsem_init(int *semaphore, int shared, unsigned value)
{
  assert(shared == 0 && value == 0);
  *semaphore = ++g_semaphores;
}

static void nxmutex_init(int *mutex)
{
  *mutex = ++g_mutexes;
}

static int lump_kthread_entry(int argc, char **argv)
{
  (void)argc;
  (void)argv;
  assert(!"host control must never execute a thread entry");
  return 0;
}

static int kthread_create(const char *name, int priority, int stack,
                          int (*entry)(int, char **), char **argv)
{
  int port = g_threads++;
  char expected[16];
  snprintf(expected, sizeof(expected), "lump-%c", 'A' + port);
  assert(strcmp(name, expected) == 0);
  assert(priority == LUMP_KTHREAD_PRIO && stack == LUMP_KTHREAD_STACK);
  assert(entry == lump_kthread_entry && argv[1] == NULL);
  assert(atoi(argv[0]) == port);
  return g_fault == port ? -ENOMEM : 100 + port;
}

static void lump_handoff_cb(void) {}

static int stm32_legoport_register_uart_handoff(int port,
                                               void (*callback)(void),
                                               struct lump_engine_s *engine)
{
  assert(port == g_handoffs++);
  assert(callback == lump_handoff_cb && engine == &g_lump[port]);
  return g_fault == port + 6 ? -EIO : 0;
}

static void test_syslog(int level, const char *format, ...)
{
  (void)level;
  (void)format;
}
#define syslog test_syslog
#include "registration.inc"

int main(int argc, char **argv)
{
  assert(argc == 2);
  g_fault = atoi(argv[1]);
  assert(g_fault >= -1 && g_fault < 12);
  int port = g_fault < 0 ? 5 : g_fault % 6;
  int result = stm32_legoport_lump_register();
  assert(result == (g_fault < 0 ? 0 : g_fault < 6 ? -ENOMEM : -EIO));
  assert(g_threads == port + 1);
  assert(g_handoffs == port + (g_fault >= 0 && g_fault < 6 ? 0 : 1));
  assert(g_semaphores == port + 1 && g_mutexes == 4 * (port + 1));
  assert(g_lump_registration_started);
  for (int i = 0; i <= port; i++)
    {
      assert(g_lump[i].port == i);
      assert(g_lump[i].dcm_cb_registered ==
             (g_fault < 0 || i < port));
      g_lump[i].live_session = UINT64_C(0x100000000) + i;
    }

  struct lump_engine_s before[BOARD_LEGOPORT_COUNT];
  memcpy(before, g_lump, sizeof(before));
  int threads = g_threads, handoffs = g_handoffs;
  int semaphores = g_semaphores, mutexes = g_mutexes;
  g_fault = -1; /* A retry would now succeed if it were incorrectly allowed. */
  for (int retry = 0; retry < 3; retry++)
    {
      assert(stm32_legoport_lump_register() == -EALREADY);
      assert(memcmp(before, g_lump, sizeof(before)) == 0);
      assert(g_threads == threads && g_handoffs == handoffs);
      assert(g_semaphores == semaphores && g_mutexes == mutexes);
    }
  return 0;
}
