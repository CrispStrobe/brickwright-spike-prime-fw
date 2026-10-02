/* SPDX-License-Identifier: Apache-2.0 */

#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <unistd.h>

#include "btsensor_scheduler.h"

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_changed = PTHREAD_COND_INITIALIZER;
static unsigned int g_reads;
static unsigned int g_ticks;
static struct btsensor_timer_s g_once;
static unsigned int g_once_ticks;

static void on_read(int fd, void *arg)
{
  (void)arg;
  uint8_t byte;
  assert(read(fd, &byte, 1) == 1);
  pthread_mutex_lock(&g_lock);
  g_reads++;
  pthread_cond_broadcast(&g_changed);
  pthread_mutex_unlock(&g_lock);
}

static void on_once(void *arg)
{
  (void)arg;
  pthread_mutex_lock(&g_lock);
  g_once_ticks++;
  unsigned int count = g_once_ticks;
  pthread_cond_broadcast(&g_changed);
  pthread_mutex_unlock(&g_lock);
  /* The Classic deadline queue re-arms its single timer from the callback. */
  if (count == 1)
    assert(btsensor_scheduler_timer_start_once(&g_once, 5, on_once, NULL) == 0);
}

static void on_tick(void *arg)
{
  (void)arg;
  pthread_mutex_lock(&g_lock);
  g_ticks++;
  pthread_cond_broadcast(&g_changed);
  pthread_mutex_unlock(&g_lock);
}

static void wait_for(unsigned int *value, unsigned int minimum)
{
  pthread_mutex_lock(&g_lock);
  while (*value < minimum)
    {
      pthread_cond_wait(&g_changed, &g_lock);
    }

  pthread_mutex_unlock(&g_lock);
}

int main(void)
{
  struct btsensor_watch_s watch = {0};
  struct btsensor_timer_s timer = {0};
  int pipefd[2];

  assert(btsensor_scheduler_acquire() == 0);
  assert(btsensor_scheduler_acquire() == 0);

  /* Capacity failures must be bounded and a released slot reusable.  Use
   * long deadlines so this check is independent of host scheduling. */
  struct btsensor_timer_s capacity[5] = {{0}};
  for (unsigned int i = 0; i < 4; i++)
    assert(btsensor_scheduler_timer_start(&capacity[i], 60000, on_tick,
                                           NULL) == 0);
  assert(btsensor_scheduler_timer_start(&capacity[4], 60000, on_tick,
                                         NULL) == -ENOSPC);
  btsensor_scheduler_timer_stop(&capacity[1]);
  assert(btsensor_scheduler_timer_start_once(&capacity[4], 60000, on_tick,
                                              NULL) == 0);
  for (unsigned int i = 0; i < 5; i++)
    btsensor_scheduler_timer_stop(&capacity[i]);

  assert(pipe(pipefd) == 0);
  assert(btsensor_scheduler_watch_start(&watch, pipefd[0], on_read, NULL) == 0);
  assert(btsensor_scheduler_timer_start(&timer, 5, on_tick, NULL) == 0);
  assert(btsensor_scheduler_timer_start_once(&g_once, 5, on_once, NULL) == 0);

  uint8_t byte = 42;
  assert(write(pipefd[1], &byte, 1) == 1);
  wait_for(&g_reads, 1);
  wait_for(&g_ticks, 2);
  wait_for(&g_once_ticks, 2);
  usleep(15000);
  assert(g_once_ticks == 2);

  btsensor_scheduler_watch_stop(&watch);
  btsensor_scheduler_timer_stop(&timer);
  btsensor_scheduler_timer_stop(&g_once);
  unsigned int stopped_ticks = g_ticks;
  usleep(20000);
  assert(g_ticks == stopped_ticks);

  close(pipefd[0]);
  close(pipefd[1]);
  btsensor_scheduler_release();
  btsensor_scheduler_release();
  return 0;
}
