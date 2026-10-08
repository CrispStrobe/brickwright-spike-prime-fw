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

struct tag_s { uint64_t ticket, ble_identity; uint32_t session; enum brickwright_hub_link link; bool used; };
struct frame_s { uint8_t buf[BTSENSOR_TX_FRAME_MAX_SIZE]; uint16_t len; struct tag_s tag; };
struct response_s { char buf[BTSENSOR_TX_RESPONSE_MAX_LEN]; uint16_t len; struct tag_s tag; };
struct pending_s { uint8_t data[BTSENSOR_TX_FRAME_MAX_SIZE]; size_t len; bool frame; struct tag_s tag; };

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static struct frame_s g_frames[TX_DEPTH];
static struct response_s g_responses[RESP_DEPTH];
static enum brickwright_hub_link g_link;
static bool g_selected, g_pumping, g_repoll, g_online[2];
static uint32_t g_sessions[2], g_lifetime, g_sent, g_dropped_oldest, g_dropped_full;
static uint64_t g_ticket;
static btsensor_tx_drain_cb_t g_drain_cb;
static void *g_drain_ctx, *g_timer_ctx;
static btsensor_tx_timer_start_t g_timer_start;
static btsensor_tx_timer_cancel_t g_timer_cancel;
static uint64_t g_drain_counter, g_drain_id, g_timer_id;
static uint32_t g_drain_timeout;
static bool g_timer_pumping;
static btsensor_tx_timer_cancel_t g_installed_cancel;
static void *g_installed_ctx;

/* A single reconciler serializes external timer operations without holding the
 * queue lock. Reentrant/concurrent changes update the desired registration;
 * the owner reconciles them after its current operation returns. Never reset
 * this ownership flag during init/deinit while an operation is in flight. */
static void reconcile_timer(void)
{
  pthread_mutex_lock(&g_lock);
  if (g_timer_pumping) { pthread_mutex_unlock(&g_lock); return; }
  g_timer_pumping = true;
  for (;;)
    {
      uint64_t desired = g_drain_timeout ? g_drain_id : 0;
      if (g_timer_id == desired)
        {
          g_timer_pumping = false;
          pthread_mutex_unlock(&g_lock);
          return;
        }
      if (g_timer_id)
        {
          uint64_t old = g_timer_id;
          btsensor_tx_timer_cancel_t cancel = g_installed_cancel;
          void *ctx = g_installed_ctx;
          g_timer_id = 0;
          pthread_mutex_unlock(&g_lock);
          cancel(old, ctx);
          pthread_mutex_lock(&g_lock);
          continue;
        }
      uint64_t id = desired;
      uint32_t delay = g_drain_timeout;
      btsensor_tx_timer_start_t start = g_timer_start;
      void *timer_ctx = g_timer_ctx;
      g_timer_id = id;
      g_installed_cancel = g_timer_cancel;
      g_installed_ctx = timer_ctx;
      pthread_mutex_unlock(&g_lock);
      int rc = start(delay, id, timer_ctx);
      pthread_mutex_lock(&g_lock);
      btsensor_tx_drain_cb_t failed = NULL;
      void *failed_ctx = NULL;
      if (rc < 0)
        {
          if (g_timer_id == id) g_timer_id = 0;
          if (g_drain_id == id)
            {
              failed = g_drain_cb; failed_ctx = g_drain_ctx;
              g_drain_id = 0; g_drain_cb = NULL; g_drain_ctx = NULL;
              g_drain_timeout = 0;
            }
        }
      if (failed)
        {
          pthread_mutex_unlock(&g_lock);
          failed(id, rc, failed_ctx);
          pthread_mutex_lock(&g_lock);
        }
    }
}

/* Called with g_lock held. With no installed/desired timer, preserve the
 * transport-only fast path: the application does not currently register drain
 * timers. Any concurrent registration reconciles its own state; an operation
 * already in flight remains responsible for changes made during its callback. */
static void unlock_and_reconcile_timer(void)
{
  bool needed = !g_timer_pumping &&
                (g_timer_id || (g_drain_id && g_drain_timeout));
  pthread_mutex_unlock(&g_lock);
  if (needed) reconcile_timer();
}

static void clear_drain_locked(void)
{
  g_drain_id = 0; g_drain_cb = NULL; g_drain_ctx = NULL;
  g_drain_timeout = 0;
}

static bool valid_link(enum brickwright_hub_link link)
{ return link == BRICKWRIGHT_HUB_LINK_CLASSIC || link == BRICKWRIGHT_HUB_LINK_BLE; }
static unsigned frame_count(void)
{ unsigned n = 0; for (unsigned i = 0; i < TX_DEPTH; i++) n += g_frames[i].tag.used; return n; }
static bool frames_empty(void) { return frame_count() == 0; }
static bool responses_empty(void)
{ for (unsigned i = 0; i < RESP_DEPTH; i++) if (g_responses[i].tag.used) return false; return true; }
static bool frames_full(void) { return frame_count() == TX_DEPTH - 1; }
static void discard_link(enum brickwright_hub_link link)
{
  bool discarded = false;
  for (unsigned i = 0; i < TX_DEPTH; i++)
    discarded |= g_frames[i].tag.used && g_frames[i].tag.link == link;
  for (unsigned i = 0; i < RESP_DEPTH; i++)
    discarded |= g_responses[i].tag.used && g_responses[i].tag.link == link;
  if (discarded) clear_drain_locked();
  for (unsigned i = 0; i < TX_DEPTH; i++) if (g_frames[i].tag.link == link) g_frames[i].tag.used = false;
  for (unsigned i = 0; i < RESP_DEPTH; i++) if (g_responses[i].tag.link == link) g_responses[i].tag.used = false;
}
static int admission(enum brickwright_hub_link link, struct tag_s *tag)
{
  if (!valid_link(link)) return -EINVAL;
  if (!g_online[link]) return -ENOTCONN;
  if (g_ticket == UINT64_MAX) return -EOVERFLOW;
  uint64_t identity = 0;
  if (link == BRICKWRIGHT_HUB_LINK_BLE)
    {
      int rc = brickwright_hub_transport_capture_ble(&identity);
      if (rc) return rc;
    }
  *tag = (struct tag_s){ .ticket = ++g_ticket, .ble_identity = identity,
    .session = g_sessions[link], .link = link, .used = true };
  return 0;
}

int btsensor_tx_init(void)
{
  pthread_mutex_lock(&g_lock);
  memset(g_frames, 0, sizeof(g_frames));
  memset(g_responses, 0, sizeof(g_responses));
  for (unsigned i = 0; i < TX_DEPTH; i++) g_frames[i].tag.used = false;
  for (unsigned i = 0; i < RESP_DEPTH; i++) g_responses[i].tag.used = false;
  g_link = BRICKWRIGHT_HUB_LINK_CLASSIC;
  g_selected = g_pumping = false;
  g_lifetime++;
  g_online[0] = g_online[1] = false;
  g_sent = g_dropped_oldest = g_dropped_full = 0;
  clear_drain_locked();
  unlock_and_reconcile_timer();
  return 0;
}

void btsensor_tx_deinit(void)
{
  pthread_mutex_lock(&g_lock);
  for (unsigned i = 0; i < TX_DEPTH; i++) g_frames[i].tag.used = false;
  for (unsigned i = 0; i < RESP_DEPTH; i++) g_responses[i].tag.used = false;
  g_selected = false;
  g_lifetime++;
  g_online[0] = g_online[1] = false;
  clear_drain_locked();
  unlock_and_reconcile_timer();
}

void btsensor_tx_link_state(enum brickwright_hub_link link, bool connected, uint32_t generation)
{
  if (!valid_link(link)) return;
  pthread_mutex_lock(&g_lock);
  if (!connected || !g_online[link] || g_sessions[link] != generation)
    discard_link(link);
  g_sessions[link] = generation;
  g_online[link] = connected;
  if (!connected && g_selected && g_link == link) g_selected = false;
  pthread_mutex_unlock(&g_lock);
  btsensor_tx_on_can_send_now();
}

void btsensor_tx_set_link(enum brickwright_hub_link link, bool selected)
{
  if (!valid_link(link)) return;
  pthread_mutex_lock(&g_lock);
  if (!selected)
    {
      discard_link(link);
      g_online[link] = false;
      g_sessions[link]++;
      if (g_selected && g_link == link) g_selected = false;
    }
  else
    {
      g_link = link;
      g_selected = true;
      g_online[link] = true;
    }
  pthread_mutex_unlock(&g_lock);
  if (selected) btsensor_tx_on_can_send_now();
  else reconcile_timer();
}

void btsensor_tx_set_rfcomm_cid(uint16_t cid)
{
  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_CLASSIC, cid != 0);
}

int btsensor_tx_enqueue_response_for_link(enum brickwright_hub_link link, const char *line)
{
  if (!line || !valid_link(link)) return -EINVAL;
  size_t len = strnlen(line, BTSENSOR_TX_RESPONSE_MAX_LEN + 1);
  if (len > BTSENSOR_TX_RESPONSE_MAX_LEN) return -E2BIG;
  pthread_mutex_lock(&g_lock);
  unsigned count = 0, slot = RESP_DEPTH;
  for (unsigned i = 0; i < RESP_DEPTH; i++)
    { if (g_responses[i].tag.used) count++; else slot = i; }
  if (count == RESP_DEPTH - 1) { pthread_mutex_unlock(&g_lock); return -ENOSPC; }
  struct tag_s tag;
  int rc = admission(link, &tag);
  if (rc) { pthread_mutex_unlock(&g_lock); return rc; }
  memcpy(g_responses[slot].buf, line, len);
  g_responses[slot].len = (uint16_t)len;
  g_responses[slot].tag = tag;
  pthread_mutex_unlock(&g_lock);
  btsensor_tx_on_can_send_now();
  return 0;
}

int btsensor_tx_enqueue_response(const char *line)
{
  if (!line) return -EINVAL;
  pthread_mutex_lock(&g_lock);
  enum brickwright_hub_link link = g_link;
  bool selected = g_selected;
  pthread_mutex_unlock(&g_lock);
  return selected ? btsensor_tx_enqueue_response_for_link(link, line) : -ENOTCONN;
}

int btsensor_tx_try_enqueue_frame_for_link(enum brickwright_hub_link link, const uint8_t *buf, size_t len)
{
  if (!buf || !len || len > BTSENSOR_TX_FRAME_MAX_SIZE) return -E2BIG;
  int result = 0;
  pthread_mutex_lock(&g_lock);
  struct tag_s tag;
  int rc = admission(link, &tag);
  if (rc) { pthread_mutex_unlock(&g_lock); return rc; }
  unsigned slot = TX_DEPTH;
  uint64_t oldest = UINT64_MAX;
  if (frames_full())
    {
      for (unsigned i = 0; i < TX_DEPTH; i++)
        if (g_frames[i].tag.used && g_frames[i].tag.ticket < oldest)
          { oldest = g_frames[i].tag.ticket; slot = i; }
      g_dropped_oldest++;
      result = -ENOSPC;
    }
  else
    for (unsigned i = 0; i < TX_DEPTH; i++) if (!g_frames[i].tag.used) { slot = i; break; }
  memcpy(g_frames[slot].buf, buf, len);
  g_frames[slot].len = (uint16_t)len;
  g_frames[slot].tag = tag;
  pthread_mutex_unlock(&g_lock);
  btsensor_tx_on_can_send_now();
  return result;
}

int btsensor_tx_try_enqueue_frame(const uint8_t *buf, size_t len)
{
  if (!buf || !len || len > BTSENSOR_TX_FRAME_MAX_SIZE) return -E2BIG;
  pthread_mutex_lock(&g_lock);
  enum brickwright_hub_link link = g_link;
  bool selected = g_selected;
  pthread_mutex_unlock(&g_lock);
  return selected ? btsensor_tx_try_enqueue_frame_for_link(link, buf, len) : -ENOTCONN;
}

void btsensor_tx_on_can_send_now(void)
{
  bool blocked[2] = { false, false };
  bool retry_available = true;
  pthread_mutex_lock(&g_lock);
  if (g_pumping) { g_repoll = true; pthread_mutex_unlock(&g_lock); return; }
  g_pumping = true;
  g_repoll = false;
  uint32_t lifetime = g_lifetime;
  pthread_mutex_unlock(&g_lock);

  for (;;)
    {
      struct pending_s pending;
      int slot = -1;
      pthread_mutex_lock(&g_lock);
      if (lifetime != g_lifetime) { pthread_mutex_unlock(&g_lock); return; }
      /* Response priority, FIFO per queue, independent blocked destinations. */
      uint64_t oldest = UINT64_MAX;
      for (unsigned i = 0; i < RESP_DEPTH; i++)
        if (g_responses[i].tag.used && !blocked[g_responses[i].tag.link] &&
            g_responses[i].tag.ticket < oldest)
          { oldest = g_responses[i].tag.ticket; slot = i; }
      pending.frame = slot < 0;
      if (slot >= 0)
        {
          pending.tag = g_responses[slot].tag;
          pending.len = g_responses[slot].len;
          memcpy(pending.data, g_responses[slot].buf, pending.len);
        }
      else
        {
          oldest = UINT64_MAX;
          for (unsigned i = 0; i < TX_DEPTH; i++)
            if (g_frames[i].tag.used && !blocked[g_frames[i].tag.link] &&
                g_frames[i].tag.ticket < oldest)
              { oldest = g_frames[i].tag.ticket; slot = i; }
          if (slot >= 0)
            {
              pending.tag = g_frames[slot].tag;
              pending.len = g_frames[slot].len;
              memcpy(pending.data, g_frames[slot].buf, pending.len);
            }
        }
      if (slot < 0)
        {
          if (g_repoll && retry_available)
            {
              g_repoll = false; retry_available = false;
              blocked[0] = blocked[1] = false;
              pthread_mutex_unlock(&g_lock); continue;
            }
          g_pumping = false; pthread_mutex_unlock(&g_lock); break;
        }
      enum brickwright_hub_link link = pending.tag.link;
      pthread_mutex_unlock(&g_lock);
      int rc = link == BRICKWRIGHT_HUB_LINK_BLE ?
               brickwright_hub_transport_send_ble(pending.tag.ble_identity, pending.data, pending.len) :
               brickwright_hub_transport_connected(link) ?
               brickwright_hub_transport_send(link, pending.data, pending.len) : -ENOTCONN;
      bool stale_ble = link == BRICKWRIGHT_HUB_LINK_BLE && rc == -ESTALE;
      pthread_mutex_lock(&g_lock);
      if (lifetime != g_lifetime) { pthread_mutex_unlock(&g_lock); return; }
      struct tag_s *tag = pending.frame ? &g_frames[slot].tag : &g_responses[slot].tag;
      bool same = tag->used && tag->ticket == pending.tag.ticket &&
                  tag->session == pending.tag.session && g_online[link] &&
                  g_sessions[link] == pending.tag.session;
      /* A refused stale BLE token cannot become writable again. Drop only its
       * exact ticket; preserve a replacement enqueued during the send call. */
      if ((!rc || stale_ble) && same)
        {
          tag->used = false;
          if (pending.frame && !rc) g_sent++;
        }
      if (rc && !stale_ble) blocked[link] = true;
      pthread_mutex_unlock(&g_lock);
    }

  btsensor_tx_drain_cb_t cb = NULL;
  void *ctx = NULL;
  uint64_t id = 0;
  pthread_mutex_lock(&g_lock);
  if (g_drain_cb && responses_empty() && frames_empty())
    {
      cb = g_drain_cb; ctx = g_drain_ctx; id = g_drain_id;
      clear_drain_locked();
    }
  unlock_and_reconcile_timer();
  if (cb) cb(id, 0, ctx);
}

bool btsensor_tx_response_queue_empty(void)
{ pthread_mutex_lock(&g_lock); bool v = responses_empty(); pthread_mutex_unlock(&g_lock); return v; }
bool btsensor_tx_frame_ring_empty(void)
{ pthread_mutex_lock(&g_lock); bool v = frames_empty(); pthread_mutex_unlock(&g_lock); return v; }
bool btsensor_tx_frame_ring_full(void)
{ pthread_mutex_lock(&g_lock); bool v = frames_full(); pthread_mutex_unlock(&g_lock); return v; }

int btsensor_tx_set_timer_ops(btsensor_tx_timer_start_t start,
                               btsensor_tx_timer_cancel_t cancel, void *ctx)
{
  if ((!start) != (!cancel)) return -EINVAL;
  pthread_mutex_lock(&g_lock);
  if (g_drain_id || g_timer_id || g_timer_pumping)
    { pthread_mutex_unlock(&g_lock); return -EBUSY; }
  g_timer_start = start; g_timer_cancel = cancel; g_timer_ctx = ctx;
  pthread_mutex_unlock(&g_lock);
  return 0;
}

int btsensor_tx_arm_post_drain_callback(btsensor_tx_drain_cb_t cb, void *ctx,
                                        uint32_t timeout_ms,
                                        uint64_t *registration)
{
  if (!registration) return -EINVAL;
  *registration = 0;
  if (!cb) return -EINVAL;
  pthread_mutex_lock(&g_lock);
  if (g_drain_id) { pthread_mutex_unlock(&g_lock); return -EBUSY; }
  bool drained = responses_empty() && frames_empty();
  if (!drained && timeout_ms && !g_timer_start)
    { pthread_mutex_unlock(&g_lock); return -ENOTSUP; }
  if (g_drain_counter == UINT64_MAX)
    { pthread_mutex_unlock(&g_lock); return -EOVERFLOW; }
  uint64_t id = ++g_drain_counter;
  *registration = id;
  if (!drained)
    {
      g_drain_id = id; g_drain_cb = cb; g_drain_ctx = ctx;
      g_drain_timeout = timeout_ms;
    }
  unlock_and_reconcile_timer();
  if (drained) cb(id, 0, ctx);
  return 0;
}

void btsensor_tx_on_drain_timeout(uint64_t registration)
{
  pthread_mutex_lock(&g_lock);
  btsensor_tx_drain_cb_t cb = NULL;
  void *ctx = NULL;
  if (registration && g_drain_id == registration && g_timer_id == registration)
    {
      cb = g_drain_cb; ctx = g_drain_ctx;
      g_timer_id = 0;
      clear_drain_locked();
    }
  pthread_mutex_unlock(&g_lock);
  if (cb) cb(registration, -ETIMEDOUT, ctx);
  reconcile_timer();
}

bool btsensor_tx_clear_post_drain_callback(uint64_t registration)
{
  pthread_mutex_lock(&g_lock);
  bool canceled = registration && g_drain_id == registration;
  if (canceled) clear_drain_locked();
  unlock_and_reconcile_timer();
  return canceled;
}

bool btsensor_tx_has_consumer(void)
{
  pthread_mutex_lock(&g_lock); bool selected = g_selected; enum brickwright_hub_link link = g_link; pthread_mutex_unlock(&g_lock);
  return selected && brickwright_hub_transport_connected(link);
}
uint16_t btsensor_tx_get_rfcomm_cid(void)
{
  pthread_mutex_lock(&g_lock); bool classic = g_online[BRICKWRIGHT_HUB_LINK_CLASSIC]; pthread_mutex_unlock(&g_lock); return classic ? 1 : 0;
}
void btsensor_tx_get_stats(uint32_t *sent, uint32_t *oldest, uint32_t *full)
{
  pthread_mutex_lock(&g_lock);
  if (sent) *sent = g_sent;
  if (oldest) *oldest = g_dropped_oldest;
  if (full) *full = g_dropped_full;
  pthread_mutex_unlock(&g_lock);
}
