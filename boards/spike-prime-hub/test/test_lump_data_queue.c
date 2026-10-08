/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include <assert.h>
#include <stddef.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include "lump_data_queue.h"

_Static_assert(sizeof(struct lump_data_frame_s) == 36, "legacy ABI");
_Static_assert(sizeof(struct lump_data_session_frame_s) == 48, "session ABI");
_Static_assert(offsetof(struct lump_data_session_frame_s, frame) == 8, "frame offset");
_Static_assert(offsetof(struct lump_data_session_frame_s, reserved) == 44, "tail offset");

static struct lump_data_frame_s sample(uint64_t value)
{
  struct lump_data_frame_s f = {.mode = 2, .len = 8};
  memcpy(f.data, &value, sizeof(value));
  return f;
}

static void expect_frame(struct lump_data_queue_s *q, uint64_t session,
                         uint64_t value)
{
  struct lump_data_session_frame_s out;
  memset(&out, 0xa5, sizeof(out));
  assert(lump_data_queue_pop(q, &out) == 0);
  assert(out.session == session && out.reserved == 0);
  struct lump_data_frame_s expected = sample(value);
  assert(memcmp(&out.frame, &expected, sizeof(expected)) == 0);
}

static void expect_empty(struct lump_data_queue_s *q)
{
  struct lump_data_session_frame_s out, before;
  memset(&out, 0xa5, sizeof(out)); before = out;
  assert(lump_data_queue_pop(q, &out) == -EAGAIN);
  assert(memcmp(&out, &before, sizeof(out)) == 0);
}

static void lifecycle(void)
{
  struct lump_data_queue_s q = {0};
  struct lump_data_frame_s f = sample(10);
  expect_empty(&q);
  assert(lump_data_queue_push(&q, &f) == -EAGAIN);
  assert(lump_data_queue_begin(&q) == 0);
  assert(lump_data_queue_push(&q, &f) == 0);
  expect_frame(&q, 1, 10);
  assert(lump_data_queue_push(&q, &f) == 0);
  lump_data_queue_invalidate(&q);
  expect_empty(&q); /* Error/backoff cannot expose the old UART frame. */
  assert(lump_data_queue_push(&q, &f) == -EAGAIN);
  assert(lump_data_queue_begin(&q) == 0);
  expect_empty(&q);
  f = sample(20);
  assert(lump_data_queue_push(&q, &f) == 0);
  expect_frame(&q, 2, 20);
  assert(lump_data_queue_push(&q, &f) == 0);
  assert(lump_data_queue_begin(&q) == 0); /* Reset without explicit end. */
  expect_empty(&q);
  assert(lump_data_queue_push(&q, &f) == 0);
  expect_frame(&q, 3, 20);

  struct lump_data_queue_s other = {0};
  assert(lump_data_queue_begin(&other) == 0);
  assert(lump_data_queue_push(&other, &f) == 0);
  lump_data_queue_invalidate(&q);
  expect_frame(&other, 1, 20); /* Per-port isolation. */

  q.session = UINT64_MAX - 1;
  assert(lump_data_queue_begin(&q) == 0);
  assert(lump_data_queue_push(&q, &f) == 0);
  expect_frame(&q, UINT64_MAX, 20);
  assert(lump_data_queue_push(&q, &f) == 0);
  assert(lump_data_queue_begin(&q) == -EOVERFLOW);
  expect_empty(&q);
  assert(lump_data_queue_push(&q, &f) == -EAGAIN);
  lump_data_queue_invalidate(&q);
  assert(lump_data_queue_begin(&q) == -EOVERFLOW);
}

static void bounds_and_overflow(void)
{
  struct lump_data_queue_s q = {0};
  assert(lump_data_queue_begin(&q) == 0);
  struct lump_data_frame_s f = sample(0);
  assert(lump_data_queue_push(&q, NULL) == -EINVAL);
  assert(lump_data_queue_pop(&q, NULL) == -EINVAL);
  f.len = 0; assert(lump_data_queue_push(&q, &f) == -EINVAL);
  f.len = LUMP_MAX_PAYLOAD + 1; assert(lump_data_queue_push(&q, &f) == -EINVAL);
  f = sample(0); f.mode = LUMP_MAX_MODES;
  assert(lump_data_queue_push(&q, &f) == -EINVAL);
  expect_empty(&q);
  for (unsigned i = 0; i < LUMP_DATA_QUEUE + 3; i++)
    {
      f = sample(i); assert(lump_data_queue_push(&q, &f) == 0);
    }
  assert(q.dropped == 3);
  for (unsigned i = 3; i < LUMP_DATA_QUEUE + 3; i++) expect_frame(&q, 1, i);
  expect_empty(&q);
  lump_data_queue_invalidate(&q);
  assert(q.dropped == 3); /* Preserve error/backoff diagnostics. */
  assert(lump_data_queue_begin(&q) == 0);
  assert(q.dropped == 0);
}

static struct lump_data_queue_s shared;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static unsigned phase;
static atomic_bool done;

static void *replacement(void *unused)
{
  (void)unused;
  pthread_mutex_lock(&lock);
  while (phase != 1) pthread_cond_wait(&changed, &lock);
  lump_data_queue_invalidate(&shared);
  assert(lump_data_queue_begin(&shared) == 0);
  struct lump_data_frame_s f = sample(22);
  assert(lump_data_queue_push(&shared, &f) == 0);
  phase = 2; pthread_cond_broadcast(&changed);
  pthread_mutex_unlock(&lock);
  return NULL;
}

static void concurrent_replacement(void)
{
  pthread_t thread;
  assert(lump_data_queue_begin(&shared) == 0);
  struct lump_data_frame_s f = sample(11);
  assert(lump_data_queue_push(&shared, &f) == 0);
  /* A completed snapshot survives replacement as an OLD identity. */
  struct lump_data_session_frame_s before;
  assert(lump_data_queue_pop(&shared, &before) == 0);
  assert(lump_data_queue_push(&shared, &f) == 0);
  assert(pthread_create(&thread, NULL, replacement, NULL) == 0);
  pthread_mutex_lock(&lock);
  phase = 1; pthread_cond_broadcast(&changed);
  while (phase != 2) pthread_cond_wait(&changed, &lock);
  expect_frame(&shared, 2, 22);
  expect_empty(&shared);
  pthread_mutex_unlock(&lock);
  assert(pthread_join(thread, NULL) == 0);
  assert(before.session == 1 && memcmp(before.frame.data, f.data, 8) == 0);
}

static void *producer(void *unused)
{
  (void)unused;
  for (uint64_t i = 3; i < 20003; i++)
    {
      pthread_mutex_lock(&lock);
      lump_data_queue_invalidate(&shared);
      assert(lump_data_queue_begin(&shared) == 0);
      struct lump_data_frame_s f = sample(i);
      assert(lump_data_queue_push(&shared, &f) == 0);
      pthread_mutex_unlock(&lock);
    }
  atomic_store(&done, true);
  return NULL;
}

static void threaded_snapshots(void)
{
  pthread_t thread;
  pthread_mutex_lock(&lock); lump_data_queue_invalidate(&shared);
  pthread_mutex_unlock(&lock);
  assert(pthread_create(&thread, NULL, producer, NULL) == 0);
  do
    {
      struct lump_data_session_frame_s out;
      pthread_mutex_lock(&lock);
      int rc = lump_data_queue_pop(&shared, &out);
      pthread_mutex_unlock(&lock);
      assert(rc == 0 || rc == -EAGAIN);
      if (rc == 0)
        {
          uint64_t payload; memcpy(&payload, out.frame.data, 8);
          assert(out.session == payload && out.reserved == 0);
        }
    }
  while (!atomic_load(&done));
  assert(pthread_join(thread, NULL) == 0);
}

int main(void)
{
  lifecycle(); bounds_and_overflow(); concurrent_replacement(); threaded_snapshots();
  puts("LUMP session queue: PASS");
}
