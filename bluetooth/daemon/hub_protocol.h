/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_HUB_PROTOCOL_H
#define BRICKWRIGHT_HUB_PROTOCOL_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "../../protocol/c/spike_codec.h"
#define BRICKWRIGHT_CLASSIC_RECORD_MAX 1024u
enum brickwright_protocol_kind
{
  BRICKWRIGHT_PROTOCOL_CLASSIC_RECORD,
  BRICKWRIGHT_PROTOCOL_BLE_MESSAGE,
};
typedef int (*brickwright_protocol_cb)(enum brickwright_protocol_kind kind,
                                      const uint8_t *data, size_t length,
                                      bool high_priority, void *context);
struct brickwright_hub_protocol
{
  struct bw_spike_stream ble;
  uint8_t classic[BRICKWRIGHT_CLASSIC_RECORD_MAX];
  size_t classic_length;
  bool classic_drop;
  brickwright_protocol_cb callback;
  void *context;
};
void brickwright_hub_protocol_init(struct brickwright_hub_protocol *protocol,
                                   brickwright_protocol_cb callback,
                                   void *context);
void brickwright_hub_protocol_reset(struct brickwright_hub_protocol *protocol);
int brickwright_hub_protocol_feed_classic(struct brickwright_hub_protocol *protocol,
                                          const uint8_t *data, size_t length);
int brickwright_hub_protocol_feed_ble(struct brickwright_hub_protocol *protocol,
                                      const uint8_t *data, size_t length);
#endif
