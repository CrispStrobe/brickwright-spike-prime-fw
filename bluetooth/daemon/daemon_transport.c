/* SPDX-License-Identifier: Apache-2.0 */
#include "daemon_transport.h"
#include <brickwright/hub_transport.h>
#include <errno.h>
#include <string.h>
static struct brickwright_hub_protocol protocol;
static void receive_bytes(enum brickwright_hub_link link, const uint8_t *data,
                          size_t length, void *context)
{
  (void)context;
  if (link == BRICKWRIGHT_HUB_LINK_CLASSIC)
    (void)brickwright_hub_protocol_feed_classic(&protocol, data, length);
  else
    (void)brickwright_hub_protocol_feed_ble(&protocol, data, length);
}
int brickwright_daemon_transport_init(brickwright_protocol_cb callback,
                                      void *context)
{
  if (!callback) return -EINVAL;
  brickwright_hub_protocol_init(&protocol, callback, context);
  return brickwright_hub_transport_register(receive_bytes, NULL, NULL);
}
void brickwright_daemon_transport_reset(void)
{
  brickwright_hub_protocol_reset(&protocol);
}
int brickwright_daemon_transport_send(enum brickwright_protocol_kind kind,
                                      const void *data, size_t length,
                                      bool high_priority)
{
  if ((!data && length) || length > BW_SPIKE_STREAM_MAX_FRAME) return -EINVAL;
  if (kind == BRICKWRIGHT_PROTOCOL_BLE_MESSAGE)
    {
      uint8_t frame[BW_SPIKE_STREAM_MAX_FRAME + 3];
      size_t frame_length = 0;
      int status = bw_spike_pack(data, length, high_priority, frame,
                                 sizeof(frame), &frame_length);
      return status == BW_CODEC_OK ?
        brickwright_hub_transport_send(BRICKWRIGHT_HUB_LINK_BLE, frame,
                                       frame_length) : -EMSGSIZE;
    }
  if (kind == BRICKWRIGHT_PROTOCOL_CLASSIC_RECORD)
    {
      uint8_t record[BRICKWRIGHT_CLASSIC_RECORD_MAX + 2];
      if (length > BRICKWRIGHT_CLASSIC_RECORD_MAX) return -EMSGSIZE;
      memcpy(record, data, length);
      record[length] = '\r';
      record[length + 1] = '\n';
      return brickwright_hub_transport_send(BRICKWRIGHT_HUB_LINK_CLASSIC,
                                            record, length + 2);
    }
  return -EINVAL;
}
