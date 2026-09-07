/****************************************************************************
 * apps/btsensor/btsensor_scheduler.c
 *
 * SPDX-License-Identifier: Apache-2.0
 ****************************************************************************/

#include <nuttx/config.h>

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "btsensor_scheduler.h"

#define BTSENSOR_SCHED_MAX_WATCHES  8
#define BTSENSOR_SCHED_MAX_TIMERS   4
#define BTSENSOR_SCHED_IDLE_MS      1000

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  g_idle;
static pthread_t       g_thread;
static unsigned int    g_refs;
static bool            g_running;
static bool            g_stop;
static int             g_wake_rfd = -1;
static int             g_wake_wfd = -1;
static struct btsensor_watch_s *g_watches[BTSENSOR_SCHED_MAX_WATCHES];
static struct btsensor_timer_s *g_timers[BTSENSOR_SCHED_MAX_TIMERS];

static uint64_t scheduler_now_ms(void)
{
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000ULL + (uint64_t)ts.tv_nsec / 1000000ULL;
}

static void scheduler_wake(void)
{
  uint8_t byte = 1;
  if (g_wake_wfd >= 0)
    {
      (void)write(g_wake_wfd, &byte, sizeof(byte));
    }
}

static void scheduler_drain_wake(void)
{
  uint8_t bytes[16];
  while (read(g_wake_rfd, bytes, sizeof(bytes)) > 0)
    {
    }
}

static void *scheduler_worker(void *unused)
{
  (void)unused;

  for (;;)
    {
      struct pollfd pfds[BTSENSOR_SCHED_MAX_WATCHES + 1];
      struct btsensor_watch_s *map[BTSENSOR_SCHED_MAX_WATCHES];
      int nfds = 1;
      int timeout = BTSENSOR_SCHED_IDLE_MS;

      pfds[0].fd = g_wake_rfd;
      pfds[0].events = POLLIN;
      pfds[0].revents = 0;

      pthread_mutex_lock(&g_lock);
      if (g_stop)
        {
          pthread_mutex_unlock(&g_lock);
          break;
        }

      for (int i = 0; i < BTSENSOR_SCHED_MAX_WATCHES; i++)
        {
          struct btsensor_watch_s *watch = g_watches[i];
          if (watch != NULL && watch->active)
            {
              pfds[nfds].fd = watch->fd;
              pfds[nfds].events = POLLIN;
              pfds[nfds].revents = 0;
              map[nfds - 1] = watch;
              nfds++;
            }
        }

      uint64_t now = scheduler_now_ms();
      for (int i = 0; i < BTSENSOR_SCHED_MAX_TIMERS; i++)
        {
          struct btsensor_timer_s *timer = g_timers[i];
          if (timer != NULL && timer->active)
            {
              uint64_t delta = timer->deadline_ms > now
                                 ? timer->deadline_ms - now : 0;
              if (delta < (uint64_t)timeout)
                {
                  timeout = (int)delta;
                }
            }
        }

      pthread_mutex_unlock(&g_lock);

      int ret = poll(pfds, nfds, timeout);
      if (ret < 0 && errno != EINTR)
        {
          break;
        }

      if ((pfds[0].revents & POLLIN) != 0)
        {
          scheduler_drain_wake();
        }

      for (int i = 1; i < nfds; i++)
        {
          if ((pfds[i].revents & POLLIN) == 0)
            {
              continue;
            }

          struct btsensor_watch_s *watch = map[i - 1];
          pthread_mutex_lock(&g_lock);
          if (watch->active)
            {
              watch->dispatching = true;
              btsensor_watch_cb_t callback = watch->callback;
              void *arg = watch->arg;
              int fd = watch->fd;
              pthread_mutex_unlock(&g_lock);
              callback(fd, arg);
              pthread_mutex_lock(&g_lock);
              watch->dispatching = false;
              pthread_cond_broadcast(&g_idle);
            }

          pthread_mutex_unlock(&g_lock);
        }

      now = scheduler_now_ms();
      for (int i = 0; i < BTSENSOR_SCHED_MAX_TIMERS; i++)
        {
          pthread_mutex_lock(&g_lock);
          struct btsensor_timer_s *timer = g_timers[i];
          if (timer != NULL && timer->active && timer->deadline_ms <= now)
            {
              /* Advance from the previous deadline to avoid drift. */
              if (timer->one_shot)
                {
                  timer->active = false;
                  g_timers[i] = NULL;
                }
              else
                {
                  do
                    {
                      timer->deadline_ms += timer->period_ms;
                    }
                  while (timer->deadline_ms <= now);
                }

              timer->dispatching = true;
              btsensor_timer_cb_t callback = timer->callback;
              void *arg = timer->arg;
              pthread_mutex_unlock(&g_lock);
              callback(arg);
              pthread_mutex_lock(&g_lock);
              timer->dispatching = false;
              pthread_cond_broadcast(&g_idle);
            }

          pthread_mutex_unlock(&g_lock);
        }
    }

  return NULL;
}

int btsensor_scheduler_acquire(void)
{
  pthread_mutex_lock(&g_lock);
  if (g_refs++ > 0)
    {
      pthread_mutex_unlock(&g_lock);
      return 0;
    }

  int pipefd[2];
  int rc = pthread_cond_init(&g_idle, NULL);
  if (rc != 0)
    {
      g_refs = 0;
      pthread_mutex_unlock(&g_lock);
      return -rc;
    }

  if (pipe(pipefd) < 0)
    {
      g_refs = 0;
      rc = -errno;
      pthread_cond_destroy(&g_idle);
      pthread_mutex_unlock(&g_lock);
      return rc;
    }

  g_wake_rfd = pipefd[0];
  g_wake_wfd = pipefd[1];
  (void)fcntl(g_wake_rfd, F_SETFL, O_NONBLOCK);
  (void)fcntl(g_wake_wfd, F_SETFL, O_NONBLOCK);
  g_stop = false;
  rc = pthread_create(&g_thread, NULL, scheduler_worker, NULL);
  if (rc != 0)
    {
      close(g_wake_rfd);
      close(g_wake_wfd);
      g_wake_rfd = -1;
      g_wake_wfd = -1;
      g_refs = 0;
      pthread_cond_destroy(&g_idle);
      pthread_mutex_unlock(&g_lock);
      return -rc;
    }

  g_running = true;
  pthread_mutex_unlock(&g_lock);
  return 0;
}

void btsensor_scheduler_release(void)
{
  pthread_mutex_lock(&g_lock);
  if (g_refs == 0 || --g_refs > 0)
    {
      pthread_mutex_unlock(&g_lock);
      return;
    }

  g_stop = true;
  scheduler_wake();
  pthread_mutex_unlock(&g_lock);
  pthread_join(g_thread, NULL);

  pthread_mutex_lock(&g_lock);
  close(g_wake_rfd);
  close(g_wake_wfd);
  g_wake_rfd = -1;
  g_wake_wfd = -1;
  g_running = false;
  memset(g_watches, 0, sizeof(g_watches));
  memset(g_timers, 0, sizeof(g_timers));
  pthread_cond_destroy(&g_idle);
  pthread_mutex_unlock(&g_lock);
}

int btsensor_scheduler_watch_start(struct btsensor_watch_s *watch, int fd,
                                   btsensor_watch_cb_t callback, void *arg)
{
  if (watch == NULL || fd < 0 || callback == NULL)
    {
      return -EINVAL;
    }

  pthread_mutex_lock(&g_lock);
  for (int i = 0; i < BTSENSOR_SCHED_MAX_WATCHES; i++)
    {
      if (g_watches[i] == NULL)
        {
          watch->fd = fd;
          watch->callback = callback;
          watch->arg = arg;
          watch->dispatching = false;
          watch->active = true;
          g_watches[i] = watch;
          scheduler_wake();
          pthread_mutex_unlock(&g_lock);
          return 0;
        }
    }

  pthread_mutex_unlock(&g_lock);
  return -ENOSPC;
}

void btsensor_scheduler_watch_stop(struct btsensor_watch_s *watch)
{
  if (watch == NULL)
    {
      return;
    }

  pthread_mutex_lock(&g_lock);
  watch->active = false;
  scheduler_wake();
  while (watch->dispatching)
    {
      pthread_cond_wait(&g_idle, &g_lock);
    }

  for (int i = 0; i < BTSENSOR_SCHED_MAX_WATCHES; i++)
    {
      if (g_watches[i] == watch)
        {
          g_watches[i] = NULL;
          break;
        }
    }

  pthread_mutex_unlock(&g_lock);
}

static int timer_start(struct btsensor_timer_s *timer, uint32_t period_ms,
                       btsensor_timer_cb_t callback, void *arg,
                       bool one_shot)
{
  if (timer == NULL || period_ms == 0 || callback == NULL)
    {
      return -EINVAL;
    }

  pthread_mutex_lock(&g_lock);
  for (int i = 0; i < BTSENSOR_SCHED_MAX_TIMERS; i++)
    {
      if (g_timers[i] == NULL || g_timers[i] == timer)
        {
          timer->period_ms = period_ms;
          timer->deadline_ms = scheduler_now_ms() + period_ms;
          timer->callback = callback;
          timer->arg = arg;
          timer->active = true;
          timer->one_shot = one_shot;
          g_timers[i] = timer;
          scheduler_wake();
          pthread_mutex_unlock(&g_lock);
          return 0;
        }
    }

  pthread_mutex_unlock(&g_lock);
  return -ENOSPC;
}

int btsensor_scheduler_timer_start(struct btsensor_timer_s *timer,
                                   uint32_t period_ms,
                                   btsensor_timer_cb_t callback, void *arg)
{
  return timer_start(timer, period_ms, callback, arg, false);
}

int btsensor_scheduler_timer_start_once(struct btsensor_timer_s *timer,
                                        uint32_t delay_ms,
                                        btsensor_timer_cb_t callback,
                                        void *arg)
{
  return timer_start(timer, delay_ms, callback, arg, true);
}

void btsensor_scheduler_timer_stop(struct btsensor_timer_s *timer)
{
  if (timer == NULL)
    {
      return;
    }

  pthread_mutex_lock(&g_lock);
  timer->active = false;
  scheduler_wake();
  while (timer->dispatching)
    {
      pthread_cond_wait(&g_idle, &g_lock);
    }

  for (int i = 0; i < BTSENSOR_SCHED_MAX_TIMERS; i++)
    {
      if (g_timers[i] == timer)
        {
          g_timers[i] = NULL;
          break;
        }
    }

  pthread_mutex_unlock(&g_lock);
}
