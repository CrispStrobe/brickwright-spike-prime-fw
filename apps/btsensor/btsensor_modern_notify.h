/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_MODERN_NOTIFY_H
#define BTSENSOR_MODERN_NOTIFY_H

#include <stddef.h>
#include <stdint.h>
#include <pthread.h>

#include "btsensor_modern.h"

#define BTSENSOR_MODERN_NOTIFY_MIN_INTERVAL_MS 20u
#define BTSENSOR_MODERN_NOTIFY_MAX_INTERVAL_MS 60000u
#define BTSENSOR_MODERN_NOTIFY_RECORDS_MAX \
  BTSENSOR_MODERN_MAX_NOTIFICATION_RECORDS

struct btsensor_modern_snapshot
{
  uint8_t battery_percent;
  uint8_t records[BTSENSOR_MODERN_NOTIFY_RECORDS_MAX - 2u];
  size_t records_length;
};

/* Platform snapshot seam. A board adapter may override the weak daemon
 * implementation once it can obtain a coherent, non-destructive snapshot.
 * records must contain complete published DeviceNotification records; the
 * notifier prepends and encodes the battery record and validates all records
 * atomically before enqueueing. */
int btsensor_hub_snapshot(struct btsensor_modern_snapshot *snapshot);

typedef int (*btsensor_modern_snapshot_t)(
    struct btsensor_modern_snapshot *snapshot, void *context);
typedef int (*btsensor_modern_timer_start_t)(uint32_t period_ms,
                                             void *context);
typedef void (*btsensor_modern_timer_stop_t)(void *context);

struct btsensor_modern_notifier
{
  struct btsensor_modern *service;
  btsensor_modern_snapshot_t snapshot;
  btsensor_modern_timer_start_t timer_start;
  btsensor_modern_timer_stop_t timer_stop;
  void *context;
  uint16_t interval_ms;
  uint8_t records[BTSENSOR_MODERN_NOTIFY_RECORDS_MAX];
  pthread_mutex_t lock;
  pthread_mutex_t control_lock;
};

void btsensor_modern_notifier_init(
    struct btsensor_modern_notifier *notifier,
    struct btsensor_modern *service,
    btsensor_modern_snapshot_t snapshot,
    btsensor_modern_timer_start_t timer_start,
    btsensor_modern_timer_stop_t timer_stop,
    void *context);
int btsensor_modern_notifier_set_interval(uint16_t interval_ms,
                                          void *context);
void btsensor_modern_notifier_tick(struct btsensor_modern_notifier *notifier);
void btsensor_modern_notifier_reset(struct btsensor_modern_notifier *notifier);
void btsensor_modern_notifier_deinit(struct btsensor_modern_notifier *notifier);

#endif
