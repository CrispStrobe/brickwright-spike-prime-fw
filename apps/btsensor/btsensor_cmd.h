/****************************************************************************
 * apps/btsensor/btsensor_cmd.h
 *
 * PC -> Hub ASCII command parser for btsensor (Issue #56 Commit D).
 *
 * Commands are one line per request, terminated by '\n' (CR ignored).
 * Replies (`OK\n` / `ERR <reason>\n`) go through the btsensor_tx
 * arbiter so they always make it through ahead of telemetry.  Lines
 * longer than BTSENSOR_CMD_MAX_LINE bytes are dropped with
 * `ERR overflow\n`.
 *
 *   IMU ON | OFF            -> toggle IMU streaming (BUNDLE wire)
 *   SENSOR ON | OFF         -> toggle LEGO sensor TLV streaming
 *   SET ODR <hz>            -> set ODR live or idle (backend caps at 833 Hz)
 *   SET ACCEL_FSR <g>       -> set accel FSR live or idle
 *   SET GYRO_FSR <dps>      -> set gyro FSR live or idle
 ****************************************************************************/

#ifndef __APPS_BTSENSOR_BTSENSOR_CMD_H
#define __APPS_BTSENSOR_BTSENSOR_CMD_H

#include <stddef.h>
#include <stdint.h>
#include <brickwright/hub_transport.h>

#if defined __cplusplus
extern "C" {
#endif

#define BTSENSOR_CMD_MAX_LINE   128

/* Initialise the line buffer.  Idempotent. */

void btsensor_cmd_init(void);

/* Discard the pending line buffer.  Used by shell-mode transitions to
 * make sure no half-line bytes leak across mode changes.
 */

void btsensor_cmd_reset_rx_buffer(void);

/* Feed bytes received over the selected transport.  Splits on '\n',
 * dispatches each line, and queues a reply on the same tagged link.  Must run
 * from the serialized host receive context. It is not safe for concurrent
 * callers; simulator transports must provide the same serialization.
 */

void btsensor_cmd_feed(const uint8_t *data, uint16_t len);
void btsensor_cmd_feed_link(enum brickwright_hub_link link,
                            const uint8_t *data, size_t len);

#if defined __cplusplus
}
#endif

#endif /* __APPS_BTSENSOR_BTSENSOR_CMD_H */
