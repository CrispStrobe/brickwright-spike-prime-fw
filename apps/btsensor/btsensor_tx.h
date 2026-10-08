/****************************************************************************
 * apps/btsensor/btsensor_tx.h
 *
 * Single RFCOMM send arbiter for btsensor.  Holds two queues — a small
 * response queue (Commit D ASCII command replies, must always make it
 * through) and a frame ringbuf (IMU telemetry, may be dropped under
 * back-pressure).  It is owned by the daemon thread and sends through
 * the transport-neutral Classic/BLE hub interface.
 ****************************************************************************/

#ifndef __APPS_BTSENSOR_BTSENSOR_TX_H
#define __APPS_BTSENSOR_BTSENSOR_TX_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <brickwright/hub_transport.h>

#if defined __cplusplus
extern "C" {
#endif

/* Maximum size of a single RFCOMM payload buffered in the frame ring.
 * Sized to cover the post-#88 BUNDLE frame layout (envelope + bundle
 * header + 8 IMU samples + 6 TLVs of full 32 B payload = 401 bytes;
 * see btsensor_wire.h::BTSENSOR_BUNDLE_FRAME_MAX) with headroom.  Each
 * ring slot allocates this many bytes statically.
 */

#define BTSENSOR_TX_FRAME_MAX_SIZE   1408

/* Maximum size of a single response line (ASCII), including the bounded
 * coherent fusion diagnostic snapshot.
 */

#define BTSENSOR_TX_RESPONSE_MAX_LEN 256

int  btsensor_tx_init(void);
void btsensor_tx_deinit(void);

/* Legacy Classic binding shim.  Non-zero selects Classic and zero closes the
 * active Classic session.  New daemon code should call set_link().
 */

void btsensor_tx_set_rfcomm_cid(uint16_t cid);

/* Select the tagged link which supplied the current command/session. */

void btsensor_tx_set_link(enum brickwright_hub_link link, bool selected);

/* Connection-state notifications invalidate queued work for that link only.
 * Receive-side selection changes the legacy default, never existing entries.
 */
void btsensor_tx_link_state(enum brickwright_hub_link link, bool connected,
                            uint32_t generation);
int btsensor_tx_enqueue_response_for_link(enum brickwright_hub_link link,
                                          const char *line);
int btsensor_tx_try_enqueue_frame_for_link(enum brickwright_hub_link link,
                                           const uint8_t *buf, size_t len);

/* Enqueue an ASCII response line.  Trailing newline is the caller's
 * responsibility.  Returns -ENOSPC if the response queue is full,
 * -E2BIG if the payload exceeds BTSENSOR_TX_RESPONSE_MAX_LEN.
 */

int  btsensor_tx_enqueue_response(const char *line);

/* Enqueue a telemetry frame.  If the ring is full, the oldest entry
 * is dropped to favour newer data and -ENOSPC is returned (the call
 * still succeeds in storing the new frame).  The caller's `buf` is
 * memcpy'd into the ring before this function returns, so the buffer
 * may be reused (or stack-resident) immediately after the call.
 */

int  btsensor_tx_try_enqueue_frame(const uint8_t *buf, size_t len);

/* Retry/pump hook.  Drains responses first and then telemetry until the
 * neutral transport reports back-pressure.  The legacy function name keeps
 * existing callers source compatible.
 */

void btsensor_tx_on_can_send_now(void);

/* True when an RFCOMM channel is bound (cid != 0).  Lets producers
 * (e.g. imu_sampler) short-circuit frame encoding when there's no
 * consumer.
 */

bool btsensor_tx_has_consumer(void);

/* Legacy compatibility value: 1 when Classic is selected, otherwise 0.
 */

uint16_t btsensor_tx_get_rfcomm_cid(void);

/* True iff the response queue currently holds zero pending entries.
 * Used by the shell-mode post-drain callback machinery to detect when
 * `OK\n` has physically been sent before flipping into MODE_SHELL.
 */

bool btsensor_tx_response_queue_empty(void);

/* True iff the telemetry frame ring currently holds zero pending entries. */

bool btsensor_tx_frame_ring_empty(void);

/* True iff the telemetry frame ring has no slot available for a new
 * frame.  Used by the lossless capture forwarder to decide whether to
 * read the next chunk from /dev/btcap or back-pressure the producer
 * (Issue #122 follow-up): if the ring is full, on_read returns without
 * touching the chardev, the chardev write side blocks naturally, and
 * the kernel chardev's pipe-style back-pressure propagates all the way
 * up to the apps/sensor writer.
 */

bool btsensor_tx_frame_ring_full(void);

/* Identity-bearing, single-shot drain registration. Success reports empty
 * local queues, not remote receipt or physical delivery. The callback receives
 * 0 on drain, -ETIMEDOUT on expiry, or the negative timer-start error. Admission
 * returns 0 even if a synchronous terminal callback has already run; negative
 * returns mean no registration was admitted. *registration is set before any
 * callback. Identities never reset/reuse; exhaustion fails with -EOVERFLOW.
 *
 * Backend start/cancel calls are serialized outside the queue mutex and may
 * reenter this API. A failed start must not leave a timer armed. Cancellation
 * may leave a queued expiry, which must carry its original registration id.
 * Clear, init/deinit and disconnect discard cancel without a terminal callback.
 * A stale clear/expiry cannot affect a replacement registration. Backend/context
 * ownership must remain valid until its start/cancel operation returns.
 */
typedef void (*btsensor_tx_drain_cb_t)(uint64_t registration, int result, void *ctx);
typedef int (*btsensor_tx_timer_start_t)(uint32_t timeout_ms,
                                        uint64_t registration, void *ctx);
typedef void (*btsensor_tx_timer_cancel_t)(uint64_t registration, void *ctx);

/* Returns -EBUSY while a registration or timer operation owns the provider.
 * Non-null start and cancel must be supplied together. */
int btsensor_tx_set_timer_ops(btsensor_tx_timer_start_t start,
                               btsensor_tx_timer_cancel_t cancel, void *ctx);
int btsensor_tx_arm_post_drain_callback(btsensor_tx_drain_cb_t cb, void *ctx,
                                        uint32_t timeout_ms,
                                        uint64_t *registration);
/* True means cancellation won and no callback can claim this registration.
 * False includes an already claimed callback; this is not a callback join.
 * Keep callback context alive until cancellation wins or its callback returns.
 * Init/deinit likewise do not join previously claimed callbacks. */
bool btsensor_tx_clear_post_drain_callback(uint64_t registration);
void btsensor_tx_on_drain_timeout(uint64_t registration);

/* Telemetry counters.  Pass NULL for any counter you don't need.
 * - frames_sent:          successful neutral-transport sends
 * - frames_dropped_oldest: ring was full at enqueue time; oldest slot
 *                          was overwritten to make room (the new frame
 *                          is preserved)
 * - frames_dropped_full:   reserved for future paths that fail to
 *                          enqueue at all (currently always 0; the
 *                          drop-oldest path always succeeds)
 */

void btsensor_tx_get_stats(uint32_t *frames_sent,
                           uint32_t *frames_dropped_oldest,
                           uint32_t *frames_dropped_full);

#if defined __cplusplus
}
#endif

#endif /* __APPS_BTSENSOR_BTSENSOR_TX_H */
