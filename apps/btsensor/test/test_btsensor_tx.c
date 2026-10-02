/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <brickwright/hub_transport.h>
#include "btsensor_tx.h"

#ifndef CONFIG_APP_BTSENSOR_RING_DEPTH
#  define CONFIG_APP_BTSENSOR_RING_DEPTH 8
#endif

struct sent_s { enum brickwright_hub_link link; uint8_t data[80]; size_t len; };
static struct sent_s sent[16];
static size_t sent_count;
static bool connected[2];
static int send_result;
static unsigned timer_started, timer_cancelled, drained, timed_out;

int brickwright_hub_transport_send(enum brickwright_hub_link link,
                                   const void *data, size_t length)
{
  if (send_result) return send_result;
  assert(sent_count < 16 && length <= sizeof(sent[0].data));
  sent[sent_count].link = link;
  sent[sent_count].len = length;
  memcpy(sent[sent_count].data, data, length);
  sent_count++;
  return 0;
}
bool brickwright_hub_transport_connected(enum brickwright_hub_link link)
{
  return connected[link];
}
static int timer_start(uint32_t milliseconds, void *ctx)
{
  assert(milliseconds == 500 && ctx == &timer_started);
  timer_started++;
  return 0;
}
static void timer_cancel(void *ctx)
{
  assert(ctx == &timer_started);
  timer_cancelled++;
}
static void drain(void *ctx) { assert(ctx == &drained); drained++; }
static void timeout(void *ctx) { assert(ctx == &drained); timed_out++; }

static void *produce(void *argument)
{
  uintptr_t producer = (uintptr_t)argument;
  for (uint32_t sequence = 0; sequence < 1000; sequence++)
    {
      uint8_t frame[8];
      memcpy(frame, &producer, sizeof(uint32_t));
      memcpy(frame + 4, &sequence, sizeof(sequence));
      int rc = btsensor_tx_try_enqueue_frame(frame, sizeof(frame));
      assert(rc == 0 || rc == -ENOSPC);
    }
  return NULL;
}

static void *reselect(void *argument)
{
  (void)argument;
  for (size_t i = 0; i < 1000; i++)
    {
      btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_CLASSIC, false);
      btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_CLASSIC, true);
    }
  return NULL;
}

int main(void)
{
  assert(btsensor_tx_init() == 0);
  assert(btsensor_tx_try_enqueue_frame(NULL, 1) == -E2BIG);
  assert(btsensor_tx_try_enqueue_frame((const uint8_t *)"x", 0) == -E2BIG);
  assert(btsensor_tx_enqueue_response(NULL) == -EINVAL);

  /* A blocked transport retains queue order.  The fixed-depth frame ring
   * drops exactly the oldest item on overflow and immediately recovers once
   * the transport accepts sends again. */
  connected[BRICKWRIGHT_HUB_LINK_BLE] = true;
  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_BLE, true);
  send_result = -EAGAIN;
  for (uint8_t i = 0; i < CONFIG_APP_BTSENSOR_RING_DEPTH; i++)
    {
      uint8_t frame[] = {0xa0, i};
      assert(btsensor_tx_try_enqueue_frame(frame, sizeof(frame)) ==
             (i == CONFIG_APP_BTSENSOR_RING_DEPTH - 1 ? -ENOSPC : 0));
    }
  uint32_t dropped = 0;
  btsensor_tx_get_stats(NULL, &dropped, NULL);
  assert(dropped == 1 && btsensor_tx_frame_ring_full());
  send_result = 0;
  btsensor_tx_on_can_send_now();
  assert(sent_count == CONFIG_APP_BTSENSOR_RING_DEPTH - 1 &&
         btsensor_tx_frame_ring_empty());
  for (uint8_t i = 0; i < CONFIG_APP_BTSENSOR_RING_DEPTH - 1; i++)
    assert(sent[i].len == 2 && sent[i].data[0] == 0xa0 &&
           sent[i].data[1] == i + 1);

  btsensor_tx_deinit();
  sent_count = 0;
  assert(btsensor_tx_init() == 0);
  const uint8_t telemetry[] = {0xb6, 0x6b, 2};
  assert(btsensor_tx_try_enqueue_frame(telemetry, sizeof(telemetry)) == 0);
  assert(btsensor_tx_enqueue_response("OK\n") == 0);
  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_BLE, true);
  assert(sent_count == 2);
  assert(sent[0].link == BRICKWRIGHT_HUB_LINK_BLE);
  assert(sent[0].len == 3 && !memcmp(sent[0].data, "OK\n", 3));
  assert(sent[1].len == sizeof(telemetry));
  assert(btsensor_tx_has_consumer());
  assert(btsensor_tx_get_rfcomm_cid() == 0);

  uint32_t frames = 0;
  btsensor_tx_get_stats(&frames, NULL, NULL);
  assert(frames == 1);

  send_result = -ENOMEM;
  assert(btsensor_tx_enqueue_response("WAIT\n") == 0);
  btsensor_tx_set_timer_ops(timer_start, timer_cancel, &timer_started);
  assert(btsensor_tx_arm_post_drain_callback(drain, timeout, &drained, 500) == 0);
  assert(timer_started == 1 && drained == 0);
  btsensor_tx_on_drain_timeout();
  assert(timed_out == 1 && drained == 0);

  send_result = 0;
  btsensor_tx_on_can_send_now();
  assert(sent_count == 3 && !memcmp(sent[2].data, "WAIT\n", 5));
  assert(btsensor_tx_arm_post_drain_callback(drain, timeout, &drained, 500) == 0);
  assert(drained == 1);
  assert(timer_started == 1 && timer_cancelled == 0);

  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_BLE, false);
  assert(!btsensor_tx_has_consumer());
  connected[BRICKWRIGHT_HUB_LINK_CLASSIC] = true;
  btsensor_tx_set_rfcomm_cid(42);
  assert(btsensor_tx_get_rfcomm_cid() == 1);
  assert(btsensor_tx_enqueue_response("CLASSIC\n") == 0);
  assert(sent[3].link == BRICKWRIGHT_HUB_LINK_CLASSIC);

  /* Multiple scheduler/RX-side producers can fill and overwrite the frame
   * ring concurrently while disconnected without corrupting indices/data. */
  connected[BRICKWRIGHT_HUB_LINK_CLASSIC] = false;
  pthread_t producers[4];
  pthread_t selector;
  assert(pthread_create(&selector, NULL, reselect, NULL) == 0);
  for (uintptr_t i = 0; i < 4; i++)
    assert(pthread_create(&producers[i], NULL, produce, (void *)i) == 0);
  for (size_t i = 0; i < 4; i++) assert(pthread_join(producers[i], NULL) == 0);
  assert(pthread_join(selector, NULL) == 0);
  for (uintptr_t i = 0; i < 3; i++)
    {
      uint8_t final_frame[8] = {0};
      memcpy(final_frame, &i, sizeof(uint32_t));
      (void)btsensor_tx_try_enqueue_frame(final_frame, sizeof(final_frame));
    }
  assert(btsensor_tx_frame_ring_full());
  connected[BRICKWRIGHT_HUB_LINK_CLASSIC] = true;
  btsensor_tx_on_can_send_now();
  assert(btsensor_tx_frame_ring_empty());
  for (size_t i = 4; i < sent_count; i++) assert(sent[i].len == 8);
  btsensor_tx_deinit();
  puts("btsensor transport-neutral TX tests passed");
  return 0;
}
