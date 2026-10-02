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

/* Maximum size of a single response line (ASCII).  Plenty for the
 * `OK` / `ERR <reason>` style replies introduced in Commit D.
 */

#define BTSENSOR_TX_RESPONSE_MAX_LEN 64

int  btsensor_tx_init(void);
void btsensor_tx_deinit(void);

/* Legacy Classic binding shim.  Non-zero selects Classic and zero closes the
 * active Classic session.  New daemon code should call set_link().
 */

void btsensor_tx_set_rfcomm_cid(uint16_t cid);

/* Select the tagged link which supplied the current command/session. */

void btsensor_tx_set_link(enum brickwright_hub_link link, bool selected);

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

/* Post-drain single-shot callback.
 *
 * Stores `cb(ctx)` to fire once both the response queue and the frame
 * ring are empty AND no can-send-now request is pending.  The hook is
 * checked at the end of every btsensor_tx_on_can_send_now() invocation;
 * if the conditions are satisfied the registered callback is cleared
 * and invoked exactly once.
 *
 * An optional daemon timer fires `timeout_cb(ctx)` if the drain has not
 * completed.  Timer operations are injected so this module has no Bluetooth
 * stack or scheduler dependency.
 *
 * `btsensor_tx_clear_post_drain_callback()` cancels both the drain hook
 * and the timer (e.g. on RFCOMM CHANNEL_CLOSED, shell exit, deinit).
 *
 * All functions must run on the daemon owner thread.  Returns 0 on success
 * or -EBUSY if a callback is already armed.
 */

typedef void (*btsensor_tx_drain_cb_t)(void *ctx);
typedef int (*btsensor_tx_timer_start_t)(uint32_t timeout_ms, void *ctx);
typedef void (*btsensor_tx_timer_cancel_t)(void *ctx);

void btsensor_tx_set_timer_ops(btsensor_tx_timer_start_t start,
                               btsensor_tx_timer_cancel_t cancel,
                               void *ctx);

int  btsensor_tx_arm_post_drain_callback(btsensor_tx_drain_cb_t cb,
                                         btsensor_tx_drain_cb_t timeout_cb,
                                         void *ctx,
                                         uint32_t timeout_ms);

void btsensor_tx_clear_post_drain_callback(void);
void btsensor_tx_on_drain_timeout(void);

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
