/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_modern_notify.h"

#include <assert.h>
#include <errno.h>
#include <string.h>

static uint8_t sent[160];
static size_t sent_length;
static unsigned starts;
static unsigned stops;
static uint32_t period;
static int snapshot_rc;
static struct btsensor_modern_snapshot next_snapshot;

static int send_message(const uint8_t *message, size_t length, bool high,
                        void *context)
{
  (void)high;
  (void)context;
  memcpy(sent, message, length);
  sent_length = length;
  return 0;
}

static int snapshot(struct btsensor_modern_snapshot *out, void *context)
{
  (void)context;
  *out = next_snapshot;
  return snapshot_rc;
}

static int timer_start(uint32_t value, void *context)
{
  (void)context;
  starts++;
  period = value;
  return 0;
}

static void timer_stop(void *context)
{
  (void)context;
  stops++;
}

int main(void)
{
  struct btsensor_modern service;
  struct btsensor_modern_notifier notifier;
  btsensor_modern_init(&service, NULL, send_message, NULL,
                        btsensor_modern_notifier_set_interval, &notifier);
  btsensor_modern_notifier_init(&notifier, &service, snapshot, timer_start,
                                 timer_stop, NULL);

  const uint8_t too_fast[] = {0x28, 19, 0};
  assert(btsensor_modern_receive(&service, too_fast, sizeof(too_fast), false)
         == 0);
  assert(sent_length == 2 && sent[0] == 0x29 && sent[1] == 1);
  assert(starts == 0 && service.notification_interval_ms == 0);

  const uint8_t subscribe[] = {0x28, 100, 0};
  assert(btsensor_modern_receive(&service, subscribe, sizeof(subscribe), false)
         == 0);
  assert(starts == 1 && period == 100 && service.notification_interval_ms == 100);

  /* Exact published distance record: type, port, signed millimetres LE. */
  next_snapshot.battery_percent = 81;
  const uint8_t distance[] = {0x0d, 2, 0xff, 0xff};
  memcpy(next_snapshot.records, distance, sizeof(distance));
  next_snapshot.records_length = sizeof(distance);
  btsensor_modern_notifier_tick(&notifier);
  const uint8_t expected[] = {0x3c, 6, 0, 0x00, 81,
                              0x0d, 2, 0xff, 0xff};
  assert(sent_length == sizeof(expected));
  assert(memcmp(sent, expected, sizeof(expected)) == 0);

  /* Invalid snapshots are atomic: no partial notification is emitted. */
  sent_length = 0;
  next_snapshot.battery_percent = 101;
  btsensor_modern_notifier_tick(&notifier);
  assert(sent_length == 0);
  next_snapshot.battery_percent = 50;
  next_snapshot.records[0] = 0x0d;
  next_snapshot.records_length = 1;
  btsensor_modern_notifier_tick(&notifier);
  assert(sent_length == 0);
  snapshot_rc = -EIO;
  btsensor_modern_notifier_tick(&notifier);
  assert(sent_length == 0);
  snapshot_rc = 0;

  btsensor_modern_notifier_reset(&notifier);
  assert(stops == 1 && service.notification_interval_ms == 0);
  btsensor_modern_notifier_tick(&notifier);
  assert(sent_length == 0);

  const uint8_t disabled[] = {0x28, 0, 0};
  assert(btsensor_modern_receive(&service, disabled, sizeof(disabled), false)
         == 0);
  assert(starts == 1 && stops == 1 && service.notification_interval_ms == 0);
  btsensor_modern_notifier_deinit(&notifier);
  return 0;
}
