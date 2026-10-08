/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 *
 * Engine-owned DATA ring. Every operation requires the same external port
 * mutex. Begin/invalidate and pop therefore share one linearization boundary.
 * The counter is zero-initialized once at boot, never by session reset.
 */
#ifndef BRICKWRIGHT_LUMP_DATA_QUEUE_H
#define BRICKWRIGHT_LUMP_DATA_QUEUE_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <arch/board/board_lump.h>

_Static_assert(sizeof(struct lump_data_frame_s) == 36, "legacy DATA ABI");
_Static_assert(sizeof(struct lump_data_session_frame_s) == 48, "session DATA ABI");

struct lump_data_queue_s
{
  struct lump_data_frame_s frames[LUMP_DATA_QUEUE];
  uint64_t session;
  uint32_t dropped;
  uint8_t head;
  uint8_t tail;
  uint8_t count;
  bool active;
};

static inline void lump_data_queue_invalidate(struct lump_data_queue_s *q)
{
  q->active = false;
  q->head = q->tail = q->count = 0;
}

static inline int lump_data_queue_begin(struct lump_data_queue_s *q)
{
  lump_data_queue_invalidate(q);
  q->dropped = 0;
  if (q->session == UINT64_MAX)
    {
      return -EOVERFLOW;
    }
  q->session++;
  q->active = true;
  return 0;
}

static inline int lump_data_queue_push(struct lump_data_queue_s *q,
                                      const struct lump_data_frame_s *frame)
{
  if (!frame || !frame->len || frame->len > LUMP_MAX_PAYLOAD ||
      frame->mode >= LUMP_MAX_MODES)
    {
      return -EINVAL;
    }
  if (!q->active)
    {
      return -EAGAIN;
    }
  if (q->count == LUMP_DATA_QUEUE)
    {
      q->tail = (uint8_t)((q->tail + 1) % LUMP_DATA_QUEUE);
      q->count--;
      q->dropped++;
    }
  q->frames[q->head] = *frame;
  q->head = (uint8_t)((q->head + 1) % LUMP_DATA_QUEUE);
  q->count++;
  return 0;
}

static inline int lump_data_queue_pop(struct lump_data_queue_s *q,
                                     struct lump_data_session_frame_s *out)
{
  if (!out)
    {
      return -EINVAL;
    }
  if (!q->active || !q->count)
    {
      return -EAGAIN;
    }
  /* Both values are copied under the engine's queue mutex. */
  out->session = q->session;
  out->frame = q->frames[q->tail];
  out->reserved = 0;
  q->tail = (uint8_t)((q->tail + 1) % LUMP_DATA_QUEUE);
  q->count--;
  return 0;
}
#endif
