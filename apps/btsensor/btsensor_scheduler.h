/****************************************************************************
 * apps/btsensor/btsensor_scheduler.h
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Small transport-neutral scheduler for btsensor background work.
 ****************************************************************************/

#ifndef __APPS_BTSENSOR_BTSENSOR_SCHEDULER_H
#define __APPS_BTSENSOR_BTSENSOR_SCHEDULER_H

#include <stdbool.h>
#include <stdint.h>

struct btsensor_watch_s;
struct btsensor_timer_s;

typedef void (*btsensor_watch_cb_t)(int fd, void *arg);
typedef void (*btsensor_timer_cb_t)(void *arg);

struct btsensor_watch_s
{
  int                    fd;
  btsensor_watch_cb_t    callback;
  void                  *arg;
  bool                   active;
  bool                   dispatching;
};

struct btsensor_timer_s
{
  uint32_t               period_ms;
  uint64_t               deadline_ms;
  btsensor_timer_cb_t     callback;
  void                  *arg;
  bool                   active;
  bool                   one_shot;
  bool                   dispatching;
};

/* Acquire/release one reference to the process-wide scheduler worker. */

int  btsensor_scheduler_acquire(void);
void btsensor_scheduler_release(void);

int  btsensor_scheduler_watch_start(struct btsensor_watch_s *watch, int fd,
                                    btsensor_watch_cb_t callback, void *arg);
void btsensor_scheduler_watch_stop(struct btsensor_watch_s *watch);

int  btsensor_scheduler_timer_start(struct btsensor_timer_s *timer,
                                    uint32_t period_ms,
                                    btsensor_timer_cb_t callback, void *arg);
int  btsensor_scheduler_timer_start_once(struct btsensor_timer_s *timer,
                                         uint32_t delay_ms,
                                         btsensor_timer_cb_t callback,
                                         void *arg);
void btsensor_scheduler_timer_stop(struct btsensor_timer_s *timer);

#endif /* __APPS_BTSENSOR_BTSENSOR_SCHEDULER_H */
