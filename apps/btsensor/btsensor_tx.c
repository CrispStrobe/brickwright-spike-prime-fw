/* SPDX-License-Identifier: Apache-2.0 */
/* Thread-safe, transport-neutral command response and telemetry arbiter. */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <brickwright/hub_transport.h>
#include "btsensor_tx.h"
#include "btsensor_wire.h"

#ifndef CONFIG_APP_BTSENSOR_RING_DEPTH
#  define CONFIG_APP_BTSENSOR_RING_DEPTH 8
#endif
#define TX_DEPTH CONFIG_APP_BTSENSOR_RING_DEPTH
#define RESP_DEPTH 4
_Static_assert(BTSENSOR_BUNDLE_FRAME_MAX <= BTSENSOR_TX_FRAME_MAX_SIZE,
               "BTSENSOR_TX_FRAME_MAX_SIZE too small");

struct frame_s { uint8_t buf[BTSENSOR_TX_FRAME_MAX_SIZE]; uint16_t len; };
struct response_s { char buf[BTSENSOR_TX_RESPONSE_MAX_LEN]; uint16_t len; };
struct pending_s { uint8_t data[BTSENSOR_TX_FRAME_MAX_SIZE]; size_t len; bool frame; };

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static struct frame_s g_frames[TX_DEPTH];
static struct response_s g_responses[RESP_DEPTH];
static uint8_t g_frame_head, g_frame_tail, g_response_head, g_response_tail;
static enum brickwright_hub_link g_link;
static bool g_selected, g_pumping;
static uint32_t g_generation, g_sent, g_dropped_oldest, g_dropped_full;
static btsensor_tx_drain_cb_t g_drain_cb, g_timeout_cb;
static void *g_drain_ctx, *g_timer_ctx;
static btsensor_tx_timer_start_t g_timer_start;
static btsensor_tx_timer_cancel_t g_timer_cancel;
static bool g_timer_armed;

static bool frames_empty(void) { return g_frame_head == g_frame_tail; }
static bool responses_empty(void) { return g_response_head == g_response_tail; }
static bool frames_full(void) { return (g_frame_head + 1) % TX_DEPTH == g_frame_tail; }

static void cancel_outside_lock(bool cancel, btsensor_tx_timer_cancel_t fn,
                                void *ctx)
{
  if (cancel && fn) fn(ctx);
}

int btsensor_tx_init(void)
{
  pthread_mutex_lock(&g_lock);
  memset(g_frames, 0, sizeof(g_frames));
  memset(g_responses, 0, sizeof(g_responses));
  g_frame_head = g_frame_tail = g_response_head = g_response_tail = 0;
  g_link = BRICKWRIGHT_HUB_LINK_CLASSIC;
  g_selected = g_pumping = false;
  g_generation++;
  g_sent = g_dropped_oldest = g_dropped_full = 0;
  g_drain_cb = g_timeout_cb = NULL;
  g_drain_ctx = NULL;
  g_timer_armed = false;
  pthread_mutex_unlock(&g_lock);
  return 0;
}

void btsensor_tx_deinit(void)
{
  pthread_mutex_lock(&g_lock);
  bool cancel = g_timer_armed;
  btsensor_tx_timer_cancel_t timer_cancel = g_timer_cancel;
  void *timer_ctx = g_timer_ctx;
  g_frame_head = g_frame_tail = g_response_head = g_response_tail = 0;
  g_selected = false;
  g_generation++;
  g_drain_cb = g_timeout_cb = NULL;
  g_drain_ctx = NULL;
  g_timer_armed = false;
  pthread_mutex_unlock(&g_lock);
  cancel_outside_lock(cancel, timer_cancel, timer_ctx);
}

void btsensor_tx_set_link(enum brickwright_hub_link link, bool selected)
{
  if (link != BRICKWRIGHT_HUB_LINK_CLASSIC && link != BRICKWRIGHT_HUB_LINK_BLE) return;
  bool pump = false;
  pthread_mutex_lock(&g_lock);
  if (!selected && g_selected && g_link == link)
    {
      g_selected = false;
      g_frame_head = g_frame_tail;
      g_response_head = g_response_tail;
      g_generation++;
    }
  else if (selected)
    {
      if (!g_selected || g_link != link) g_generation++;
      g_link = link;
      g_selected = true;
      pump = true;
    }
  pthread_mutex_unlock(&g_lock);
  if (pump) btsensor_tx_on_can_send_now();
}

void btsensor_tx_set_rfcomm_cid(uint16_t cid)
{
  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_CLASSIC, cid != 0);
}

int btsensor_tx_enqueue_response(const char *line)
{
  if (!line) return -EINVAL;
  size_t len = strnlen(line, BTSENSOR_TX_RESPONSE_MAX_LEN + 1);
  if (len > BTSENSOR_TX_RESPONSE_MAX_LEN) return -E2BIG;
  pthread_mutex_lock(&g_lock);
  uint8_t next = (g_response_head + 1) % RESP_DEPTH;
  if (next == g_response_tail) { pthread_mutex_unlock(&g_lock); return -ENOSPC; }
  memcpy(g_responses[g_response_head].buf, line, len);
  g_responses[g_response_head].len = (uint16_t)len;
  g_response_head = next;
  pthread_mutex_unlock(&g_lock);
  btsensor_tx_on_can_send_now();
  return 0;
}

int btsensor_tx_try_enqueue_frame(const uint8_t *buf, size_t len)
{
  if (!buf || !len || len > BTSENSOR_TX_FRAME_MAX_SIZE) return -E2BIG;
  int rc = 0;
  pthread_mutex_lock(&g_lock);
  uint8_t next = (g_frame_head + 1) % TX_DEPTH;
  if (next == g_frame_tail)
    {
      g_frame_tail = (g_frame_tail + 1) % TX_DEPTH;
      g_dropped_oldest++;
      rc = -ENOSPC;
    }
  memcpy(g_frames[g_frame_head].buf, buf, len);
  g_frames[g_frame_head].len = (uint16_t)len;
  g_frame_head = next;
  pthread_mutex_unlock(&g_lock);
  btsensor_tx_on_can_send_now();
  return rc;
}

void btsensor_tx_on_can_send_now(void)
{
  enum brickwright_hub_link link;
  uint32_t generation;
  pthread_mutex_lock(&g_lock);
  if (g_pumping || !g_selected) { pthread_mutex_unlock(&g_lock); return; }
  g_pumping = true;
  link = g_link;
  generation = g_generation;
  pthread_mutex_unlock(&g_lock);

  if (!brickwright_hub_transport_connected(link))
    {
      pthread_mutex_lock(&g_lock);
      g_pumping = false;
      pthread_mutex_unlock(&g_lock);
      return;
    }

  for (;;)
    {
      struct pending_s pending;
      uint8_t tail;
      pthread_mutex_lock(&g_lock);
      if (generation != g_generation || !g_selected || g_link != link)
        { g_pumping = false; pthread_mutex_unlock(&g_lock); return; }
      if (!responses_empty())
        {
          struct response_s *r = &g_responses[g_response_tail];
          pending.len = r->len; pending.frame = false; tail = g_response_tail;
          memcpy(pending.data, r->buf, pending.len);
        }
      else if (!frames_empty())
        {
          struct frame_s *f = &g_frames[g_frame_tail];
          pending.len = f->len; pending.frame = true; tail = g_frame_tail;
          memcpy(pending.data, f->buf, pending.len);
        }
      else
        { g_pumping = false; pthread_mutex_unlock(&g_lock); break; }
      pthread_mutex_unlock(&g_lock);

      int rc = brickwright_hub_transport_send(link, pending.data, pending.len);
      pthread_mutex_lock(&g_lock);
      bool same = generation == g_generation && g_selected && g_link == link;
      if (!rc && same)
        {
          if (pending.frame && g_frame_tail == tail)
            { g_frame_tail = (g_frame_tail + 1) % TX_DEPTH; g_sent++; }
          else if (!pending.frame && g_response_tail == tail)
            g_response_tail = (g_response_tail + 1) % RESP_DEPTH;
        }
      if (rc || !same) { g_pumping = false; pthread_mutex_unlock(&g_lock); return; }
      pthread_mutex_unlock(&g_lock);
    }

  btsensor_tx_drain_cb_t cb = NULL;
  btsensor_tx_timer_cancel_t timer_cancel = NULL;
  void *ctx = NULL, *timer_ctx = NULL;
  bool cancel = false;
  pthread_mutex_lock(&g_lock);
  if (g_drain_cb && responses_empty() && frames_empty())
    {
      cb = g_drain_cb; ctx = g_drain_ctx; cancel = g_timer_armed;
      timer_cancel = g_timer_cancel; timer_ctx = g_timer_ctx;
      g_drain_cb = g_timeout_cb = NULL; g_drain_ctx = NULL; g_timer_armed = false;
    }
  pthread_mutex_unlock(&g_lock);
  cancel_outside_lock(cancel, timer_cancel, timer_ctx);
  if (cb) cb(ctx);
}

bool btsensor_tx_response_queue_empty(void)
{ pthread_mutex_lock(&g_lock); bool v = responses_empty(); pthread_mutex_unlock(&g_lock); return v; }
bool btsensor_tx_frame_ring_empty(void)
{ pthread_mutex_lock(&g_lock); bool v = frames_empty(); pthread_mutex_unlock(&g_lock); return v; }
bool btsensor_tx_frame_ring_full(void)
{ pthread_mutex_lock(&g_lock); bool v = frames_full(); pthread_mutex_unlock(&g_lock); return v; }

void btsensor_tx_set_timer_ops(btsensor_tx_timer_start_t start,
                               btsensor_tx_timer_cancel_t cancel, void *ctx)
{
  pthread_mutex_lock(&g_lock);
  bool do_cancel = g_timer_armed;
  btsensor_tx_timer_cancel_t old_cancel = g_timer_cancel;
  void *old_ctx = g_timer_ctx;
  g_timer_armed = false; g_timer_start = start; g_timer_cancel = cancel; g_timer_ctx = ctx;
  pthread_mutex_unlock(&g_lock);
  cancel_outside_lock(do_cancel, old_cancel, old_ctx);
}

int btsensor_tx_arm_post_drain_callback(btsensor_tx_drain_cb_t cb,
                                        btsensor_tx_drain_cb_t timeout_cb,
                                        void *ctx, uint32_t timeout_ms)
{
  if (!cb) return -EINVAL;
  pthread_mutex_lock(&g_lock);
  if (g_drain_cb) { pthread_mutex_unlock(&g_lock); return -EBUSY; }
  g_drain_cb = cb; g_timeout_cb = timeout_cb; g_drain_ctx = ctx;
  btsensor_tx_timer_start_t start = g_timer_start;
  void *timer_ctx = g_timer_ctx;
  bool drained = responses_empty() && frames_empty();
  if (drained)
    {
      g_drain_cb = g_timeout_cb = NULL;
      g_drain_ctx = NULL;
    }
  pthread_mutex_unlock(&g_lock);
  if (drained) { cb(ctx); return 0; }
  if (timeout_ms && timeout_cb && start)
    {
      int rc = start(timeout_ms, timer_ctx);
      pthread_mutex_lock(&g_lock);
      if (rc < 0 && g_drain_cb == cb) { g_drain_cb = g_timeout_cb = NULL; g_drain_ctx = NULL; }
      else if (!rc && g_drain_cb == cb) g_timer_armed = true;
      pthread_mutex_unlock(&g_lock);
      if (rc < 0) return rc;
    }
  return 0;
}

void btsensor_tx_on_drain_timeout(void)
{
  pthread_mutex_lock(&g_lock);
  btsensor_tx_drain_cb_t cb = g_timeout_cb;
  void *ctx = g_drain_ctx;
  g_timer_armed = false; g_drain_cb = g_timeout_cb = NULL; g_drain_ctx = NULL;
  pthread_mutex_unlock(&g_lock);
  if (cb) cb(ctx);
}

void btsensor_tx_clear_post_drain_callback(void)
{
  pthread_mutex_lock(&g_lock);
  bool cancel = g_timer_armed;
  btsensor_tx_timer_cancel_t fn = g_timer_cancel;
  void *ctx = g_timer_ctx;
  g_timer_armed = false; g_drain_cb = g_timeout_cb = NULL; g_drain_ctx = NULL;
  pthread_mutex_unlock(&g_lock);
  cancel_outside_lock(cancel, fn, ctx);
}

bool btsensor_tx_has_consumer(void)
{
  pthread_mutex_lock(&g_lock); bool selected = g_selected; enum brickwright_hub_link link = g_link; pthread_mutex_unlock(&g_lock);
  return selected && brickwright_hub_transport_connected(link);
}
uint16_t btsensor_tx_get_rfcomm_cid(void)
{
  pthread_mutex_lock(&g_lock); bool classic = g_selected && g_link == BRICKWRIGHT_HUB_LINK_CLASSIC; pthread_mutex_unlock(&g_lock); return classic ? 1 : 0;
}
void btsensor_tx_get_stats(uint32_t *sent, uint32_t *oldest, uint32_t *full)
{
  pthread_mutex_lock(&g_lock);
  if (sent) *sent = g_sent;
  if (oldest) *oldest = g_dropped_oldest;
  if (full) *full = g_dropped_full;
  pthread_mutex_unlock(&g_lock);
}
