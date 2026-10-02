/* SPDX-License-Identifier: Apache-2.0 */
#include "hub_protocol.h"
#include <errno.h>
#include <string.h>
static int receive_ble(const uint8_t *payload, size_t payload_len,
                       bool high_priority, void *context)
{
  struct brickwright_hub_protocol *protocol = context;
  return protocol->callback(BRICKWRIGHT_PROTOCOL_BLE_MESSAGE, payload,
                            payload_len, high_priority, protocol->context);
}
void brickwright_hub_protocol_init(struct brickwright_hub_protocol *protocol,
                                   brickwright_protocol_cb callback,
                                   void *context)
{
  memset(protocol, 0, sizeof(*protocol));
  protocol->callback = callback;
  protocol->context = context;
}
void brickwright_hub_protocol_reset(struct brickwright_hub_protocol *protocol)
{
  protocol->classic_length = 0;
  protocol->classic_drop = false;
  bw_spike_stream_reset(&protocol->ble);
}
int brickwright_hub_protocol_feed_classic(struct brickwright_hub_protocol *protocol,
                                          const uint8_t *data, size_t length)
{
  if (!protocol || !protocol->callback || (!data && length)) return -EINVAL;
  int result = 0;
  for (size_t i = 0; i < length; ++i)
    {
      const uint8_t byte = data[i];
      if (byte == '\r' || byte == '\n')
        {
          if (protocol->classic_drop)
            {
              protocol->classic_drop = false;
              protocol->classic_length = 0;
              result = -EMSGSIZE;
            }
          else if (protocol->classic_length)
            {
              int status = protocol->callback(BRICKWRIGHT_PROTOCOL_CLASSIC_RECORD,
                                              protocol->classic,
                                              protocol->classic_length, false,
                                              protocol->context);
              protocol->classic_length = 0;
              if (status) return status;
            }
          continue;
        }
      if (byte == 3 && protocol->classic_length == 0)
        {
          int status = protocol->callback(BRICKWRIGHT_PROTOCOL_CLASSIC_RECORD,
                                          &data[i], 1, true, protocol->context);
          if (status) return status;
          continue;
        }
      if (!protocol->classic_drop)
        {
          if (protocol->classic_length == sizeof(protocol->classic))
            protocol->classic_drop = true;
          else
            protocol->classic[protocol->classic_length++] = byte;
        }
    }
  return result;
}
int brickwright_hub_protocol_feed_ble(struct brickwright_hub_protocol *protocol,
                                      const uint8_t *data, size_t length)
{
  if (!protocol || !protocol->callback) return -EINVAL;
  return bw_spike_stream_feed(&protocol->ble, data, length, receive_ble, protocol);
}
