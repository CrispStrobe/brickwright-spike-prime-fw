/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_modern_notify.h"

#include <errno.h>
#include <string.h>

void btsensor_modern_notifier_init(
    struct btsensor_modern_notifier *notifier,
    struct btsensor_modern *service,
    btsensor_modern_snapshot_t snapshot,
    btsensor_modern_timer_start_t timer_start,
    btsensor_modern_timer_stop_t timer_stop,
    void *context)
{
  memset(notifier, 0, sizeof(*notifier));
  notifier->service = service;
  notifier->snapshot = snapshot;
  notifier->timer_start = timer_start;
  notifier->timer_stop = timer_stop;
  notifier->context = context;
  (void)pthread_mutex_init(&notifier->lock, NULL);
  (void)pthread_mutex_init(&notifier->control_lock, NULL);
}

int btsensor_modern_notifier_set_interval(uint16_t interval_ms, void *context)
{
  struct btsensor_modern_notifier *notifier = context;
  int rc;
  bool was_active;
  if (!notifier || !notifier->service || !notifier->timer_start ||
      !notifier->timer_stop) return -EINVAL;
  if (interval_ms != 0 &&
      (interval_ms < BTSENSOR_MODERN_NOTIFY_MIN_INTERVAL_MS ||
       interval_ms > BTSENSOR_MODERN_NOTIFY_MAX_INTERVAL_MS)) return -ERANGE;

  pthread_mutex_lock(&notifier->control_lock);
  pthread_mutex_lock(&notifier->lock);
  was_active = notifier->interval_ms != 0;
  notifier->interval_ms = 0;
  __atomic_store_n(&notifier->service->notification_interval_ms, 0,
                   __ATOMIC_RELEASE);
  pthread_mutex_unlock(&notifier->lock);
  if (was_active) notifier->timer_stop(notifier->context);
  if (interval_ms == 0)
    {
      pthread_mutex_unlock(&notifier->control_lock);
      return 0;
    }

  rc = notifier->timer_start(interval_ms, notifier->context);
  if (rc < 0)
    {
      pthread_mutex_unlock(&notifier->control_lock);
      return rc;
    }
  pthread_mutex_lock(&notifier->lock);
  notifier->interval_ms = interval_ms;
  pthread_mutex_unlock(&notifier->lock);
  pthread_mutex_unlock(&notifier->control_lock);
  return 0;
}

void btsensor_modern_notifier_tick(struct btsensor_modern_notifier *notifier)
{
  struct btsensor_modern_snapshot snapshot;
  if (!notifier || !notifier->snapshot) return;
  pthread_mutex_lock(&notifier->lock);
  if (notifier->interval_ms == 0)
    {
      pthread_mutex_unlock(&notifier->lock);
      return;
    }
  memset(&snapshot, 0, sizeof(snapshot));
  if (notifier->snapshot(&snapshot, notifier->context) < 0 ||
      snapshot.battery_percent > 100 ||
      snapshot.records_length > sizeof(snapshot.records))
    {
      pthread_mutex_unlock(&notifier->lock);
      return;
    }

  notifier->records[0] = 0x00;
  notifier->records[1] = snapshot.battery_percent;
  memcpy(notifier->records + 2, snapshot.records, snapshot.records_length);
  (void)btsensor_modern_notify(notifier->service, notifier->records,
                               snapshot.records_length + 2, false);
  pthread_mutex_unlock(&notifier->lock);
}

void btsensor_modern_notifier_reset(struct btsensor_modern_notifier *notifier)
{
  bool was_active;
  if (!notifier) return;
  pthread_mutex_lock(&notifier->control_lock);
  pthread_mutex_lock(&notifier->lock);
  was_active = notifier->interval_ms != 0;
  notifier->interval_ms = 0;
  if (notifier->service)
    __atomic_store_n(&notifier->service->notification_interval_ms, 0,
                     __ATOMIC_RELEASE);
  memset(notifier->records, 0, sizeof(notifier->records));
  pthread_mutex_unlock(&notifier->lock);
  if (was_active && notifier->timer_stop)
    notifier->timer_stop(notifier->context);
  pthread_mutex_unlock(&notifier->control_lock);
}

void btsensor_modern_notifier_deinit(struct btsensor_modern_notifier *notifier)
{
  if (!notifier) return;
  btsensor_modern_notifier_reset(notifier);
  (void)pthread_mutex_destroy(&notifier->control_lock);
  (void)pthread_mutex_destroy(&notifier->lock);
}
