/* SPDX-License-Identifier: Apache-2.0 */
#include "hub_protocol.h"
#include <assert.h>
#include <errno.h>
#include <string.h>
struct capture { enum brickwright_protocol_kind kind[4]; uint8_t data[4][32]; size_t length[4]; bool high[4]; size_t count; };
static int collect(enum brickwright_protocol_kind kind, const uint8_t *data,
                   size_t length, bool high, void *context)
{
  struct capture *capture = context;
  assert(capture->count < 4 && length <= sizeof(capture->data[0]));
  capture->kind[capture->count] = kind;
  memcpy(capture->data[capture->count], data, length);
  capture->length[capture->count] = length;
  capture->high[capture->count] = high;
  ++capture->count;
  return 0;
}
int main(void)
{
  struct brickwright_hub_protocol protocol;
  struct capture capture = {0};
  brickwright_hub_protocol_init(&protocol, collect, &capture);
  const uint8_t a[] = {3, '{', '"', 'm'};
  const uint8_t b[] = {'"', ':', 'x', '}', '\r', '\n'};
  assert(brickwright_hub_protocol_feed_classic(&protocol, a, sizeof(a)) == 0);
  assert(brickwright_hub_protocol_feed_classic(&protocol, b, sizeof(b)) == 0);
  assert(capture.count == 2 && capture.high[0] && capture.length[0] == 1);
  assert(capture.kind[1] == BRICKWRIGHT_PROTOCOL_CLASSIC_RECORD);
  assert(capture.length[1] == 7 && !memcmp(capture.data[1], "{\"m\":x}", 7));
  const uint8_t message[] = {0x28, 0x64, 0};
  uint8_t frame[32]; size_t frame_length = 0;
  assert(bw_spike_pack(message, sizeof(message), true, frame, sizeof(frame),
                       &frame_length) == BW_CODEC_OK);
  assert(brickwright_hub_protocol_feed_ble(&protocol, frame, 2) == 0);
  assert(brickwright_hub_protocol_feed_ble(&protocol, frame + 2,
                                            frame_length - 2) == 0);
  assert(capture.count == 3 && capture.kind[2] == BRICKWRIGHT_PROTOCOL_BLE_MESSAGE);
  assert(capture.high[2] && capture.length[2] == sizeof(message));
  assert(!memcmp(capture.data[2], message, sizeof(message)));
  uint8_t overlong[BRICKWRIGHT_CLASSIC_RECORD_MAX + 2];
  memset(overlong, 'a', sizeof(overlong)); overlong[sizeof(overlong) - 1] = '\r';
  assert(brickwright_hub_protocol_feed_classic(&protocol, overlong,
                                                sizeof(overlong)) == -EMSGSIZE);
  assert(capture.count == 3);
  return 0;
}
