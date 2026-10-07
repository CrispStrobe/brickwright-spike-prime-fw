/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026 Brickwright contributors */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include "../btsensor_tx.c"

static int send_result = -EAGAIN;
static unsigned calls[8], starts, cancels, depth;
static int terminal[8];
static uint64_t observed[8], backend_id, replacement;
static int start_error;
static uint32_t expected_delay = 500;
static enum { NONE, REPLACE_START, EXPIRE_START, RESET_START, DRAIN_START,
              REPLACE_CANCEL, BLOCK_START } hook;
static bool rearm;
static pthread_mutex_t test_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t test_cond = PTHREAD_COND_INITIALIZER;
static bool entered, released;

int brickwright_hub_transport_send(enum brickwright_hub_link link,
                                   const void *data, size_t len)
{ (void)link; (void)data; (void)len; return send_result; }
bool brickwright_hub_transport_connected(enum brickwright_hub_link link)
{ (void)link; return true; }
int brickwright_hub_transport_capture_ble(uint64_t *id) { *id = 1; return 0; }
int brickwright_hub_transport_send_ble(uint64_t id, const void *data, size_t len)
{ assert(id == 1); return brickwright_hub_transport_send(BRICKWRIGHT_HUB_LINK_BLE, data, len); }

static void completion(uint64_t id, int result, void *ctx);
static void arm_replacement(void)
{
  assert(btsensor_tx_arm_post_drain_callback(completion, (void *)1, 500,
                                            &replacement) == 0);
}
static void completion(uint64_t id, int result, void *ctx)
{
  unsigned slot = (unsigned)(uintptr_t)ctx;
  assert(slot < 8 && id);
  assert(!btsensor_tx_clear_post_drain_callback(id)); /* callback already claimed */
  calls[slot]++; terminal[slot] = result; observed[slot] = id;
  assert(calls[slot] == 1);
  if (rearm)
    {
      rearm = false;
      send_result = -EAGAIN;
      if (btsensor_tx_response_queue_empty())
        assert(btsensor_tx_enqueue_response_for_link(BRICKWRIGHT_HUB_LINK_CLASSIC, "next") == 0);
      arm_replacement();
    }
}
static int start(uint32_t delay, uint64_t id, void *ctx)
{
  (void)ctx;
  assert(delay == expected_delay && id && ++depth == 1 && backend_id == 0);
  backend_id = id; starts++;
  int result = start_error;
  start_error = 0;
  int action = hook;
  if (action != REPLACE_CANCEL) hook = NONE;
  if (action == REPLACE_START)
    {
      btsensor_tx_clear_post_drain_callback(id);
      arm_replacement();
      assert(starts == 1 && backend_id == id);
    }
  else if (action == EXPIRE_START)
    {
      backend_id = 0;
      btsensor_tx_on_drain_timeout(id);
      assert(starts == 1);
    }
  else if (action == RESET_START)
    {
      btsensor_tx_deinit();
      assert(btsensor_tx_init() == 0);
      btsensor_tx_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, true, 2);
      assert(btsensor_tx_enqueue_response_for_link(BRICKWRIGHT_HUB_LINK_CLASSIC, "reset") == 0);
      arm_replacement();
      assert(starts == 1);
    }
  else if (action == DRAIN_START)
    {
      send_result = 0;
      btsensor_tx_on_can_send_now();
      assert(starts == 1);
    }
  else if (action == BLOCK_START)
    {
      pthread_mutex_lock(&test_lock);
      entered = true; pthread_cond_broadcast(&test_cond);
      while (!released) pthread_cond_wait(&test_cond, &test_lock);
      pthread_mutex_unlock(&test_lock);
    }
  if (result < 0 && backend_id == id) backend_id = 0;
  depth--;
  return result;
}
static void cancel(uint64_t id, void *ctx)
{
  (void)ctx;
  assert(id && ++depth == 1 && backend_id == id);
  backend_id = 0; cancels++;
  if (hook == REPLACE_CANCEL)
    {
      hook = NONE;
      arm_replacement();
      btsensor_tx_on_drain_timeout(id);
      assert(backend_id == 0);
    }
  depth--;
}
static void fresh(void)
{
  hook = NONE; rearm = false; start_error = 0;
  btsensor_tx_deinit();
  assert(backend_id == 0);
  assert(btsensor_tx_init() == 0);
  assert(btsensor_tx_set_timer_ops(start, cancel, NULL) == 0);
  memset(calls, 0, sizeof(calls)); memset(terminal, 0, sizeof(terminal));
  memset(observed, 0, sizeof(observed));
  starts = cancels = depth = 0; replacement = 0; send_result = -EAGAIN;
  expected_delay = 500;
  btsensor_tx_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, true, 1);
  assert(btsensor_tx_enqueue_response_for_link(BRICKWRIGHT_HUB_LINK_CLASSIC, "blocked") == 0);
}
static uint64_t arm(void)
{
  uint64_t id;
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 500, &id) == 0);
  assert(id);
  return id;
}
static void expire(uint64_t id)
{
  assert(backend_id == id);
  backend_id = 0;
  btsensor_tx_on_drain_timeout(id);
}
static void *thread_arm(void *ctx)
{ *(uint64_t *)ctx = arm(); return NULL; }

int main(void)
{
  fresh();
  uint64_t old = arm();
  assert(btsensor_tx_set_timer_ops(NULL, NULL, NULL) == -EBUSY);
  uint64_t rejected = 123;
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 500, &rejected) == -EBUSY && rejected == 0);
  assert(btsensor_tx_clear_post_drain_callback(old));
  arm_replacement();
  assert(replacement > old && backend_id == replacement);
  btsensor_tx_on_drain_timeout(old);
  assert(!btsensor_tx_clear_post_drain_callback(old));
  assert(calls[1] == 0 && backend_id == replacement);
  expire(replacement);
  btsensor_tx_on_drain_timeout(replacement);
  assert(calls[1] == 1 && terminal[1] == -ETIMEDOUT);

  fresh(); hook = REPLACE_START; old = arm();
  assert(!calls[0] && replacement > old && starts == 2 && cancels == 1);
  expire(replacement); assert(calls[1] == 1);

  fresh(); hook = REPLACE_CANCEL; old = arm();
  btsensor_tx_clear_post_drain_callback(old);
  assert(replacement > old && starts == 2 && backend_id == replacement && !calls[1]);
  expire(replacement); assert(calls[1] == 1);

  fresh(); hook = EXPIRE_START; rearm = true; start_error = -EIO; old = arm();
  assert(calls[0] == 1 && terminal[0] == -ETIMEDOUT && observed[0] == old);
  assert(replacement > old && backend_id == replacement && calls[1] == 0);
  expire(replacement); assert(calls[1] == 1);

  fresh(); hook = RESET_START; old = arm();
  assert(!calls[0] && replacement > old && starts == 2 && cancels == 1);
  btsensor_tx_on_drain_timeout(old); assert(!calls[1]);
  expire(replacement);

  fresh(); hook = DRAIN_START; rearm = true; old = arm();
  assert(calls[0] == 1 && terminal[0] == 0 && starts == 2 && cancels == 1);
  btsensor_tx_on_drain_timeout(old); assert(!calls[1]);
  expire(replacement);

  fresh(); start_error = -ENOSPC; rearm = true; old = arm();
  assert(calls[0] == 1 && terminal[0] == -ENOSPC && observed[0] == old);
  assert(backend_id == replacement && replacement > old);
  expire(replacement);

  fresh(); old = arm();
  btsensor_tx_link_state(BRICKWRIGHT_HUB_LINK_BLE, false, 1);
  assert(backend_id == old); /* unrelated empty link cannot cancel */
  btsensor_tx_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, false, 1);
  assert(backend_id == 0 && cancels == 1 && !calls[0]);
  btsensor_tx_on_drain_timeout(old); assert(!calls[0]);

  fresh(); old = arm(); btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_CLASSIC, false);
  assert(!backend_id && !calls[0]);

  fresh();
  assert(btsensor_tx_set_timer_ops(NULL, cancel, NULL) == -EINVAL);
  assert(btsensor_tx_set_timer_ops(NULL, NULL, NULL) == 0);
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 500, &old) == -ENOTSUP && old == 0);
  assert(btsensor_tx_arm_post_drain_callback(NULL, NULL, 0, &old) == -EINVAL);
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 0, NULL) == -EINVAL);
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 0, &old) == 0);
  btsensor_tx_on_drain_timeout(old); assert(!calls[0]);
  send_result = 0; btsensor_tx_on_can_send_now();
  assert(calls[0] == 1 && terminal[0] == 0);
  assert(btsensor_tx_arm_post_drain_callback(completion, (void *)1, 500, &replacement) == 0);
  assert(calls[1] == 1 && terminal[1] == 0);

  fresh(); hook = BLOCK_START; entered = released = false;
  pthread_t thread; uint64_t threaded_id = 0;
  assert(pthread_create(&thread, NULL, thread_arm, &threaded_id) == 0);
  pthread_mutex_lock(&test_lock);
  while (!entered) pthread_cond_wait(&test_cond, &test_lock);
  old = g_drain_id; /* start cannot complete until this test releases it */
  pthread_mutex_unlock(&test_lock);
  btsensor_tx_clear_post_drain_callback(old); arm_replacement();
  assert(starts == 1 && !calls[0] && !calls[1]);
  pthread_mutex_lock(&test_lock); released = true;
  pthread_cond_broadcast(&test_cond); pthread_mutex_unlock(&test_lock);
  assert(pthread_join(thread, NULL) == 0 && threaded_id == old);
  assert(starts == 2 && cancels == 1 && backend_id == replacement);
  btsensor_tx_on_drain_timeout(old); assert(!calls[1]); expire(replacement);

  fresh(); expected_delay = UINT32_MAX;
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, UINT32_MAX, &old) == 0);
  assert(backend_id == old); expire(old);
  assert(calls[0] == 1 && terminal[0] == -ETIMEDOUT);

  fresh(); g_drain_counter = UINT64_MAX - 1; old = arm();
  assert(old == UINT64_MAX); btsensor_tx_clear_post_drain_callback(old);
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 500, &old) == -EOVERFLOW && old == 0);
  assert(btsensor_tx_init() == 0 && g_drain_counter == UINT64_MAX);
  assert(btsensor_tx_arm_post_drain_callback(completion, NULL, 0, &old) == -EOVERFLOW);
  puts("drain identities, serialized reentry, stale expiry/cancel, lifecycle, errors and concurrent arm passed");
  return 0;
}
