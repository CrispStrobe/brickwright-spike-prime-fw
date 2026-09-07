/* SPDX-License-Identifier: Apache-2.0 */
#include "spike_codec.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct vector
{
  const uint8_t *payload;
  size_t payload_len;
  const uint8_t *frame;
  size_t frame_len;
};

static void check(const struct vector *v)
{
  uint8_t encoded[256];
  uint8_t decoded[256];
  size_t encoded_len = 0;
  size_t decoded_len = 0;
  assert(bw_spike_pack(v->payload, v->payload_len, false, encoded,
                       sizeof(encoded), &encoded_len) == BW_CODEC_OK);
  assert(encoded_len == v->frame_len);
  assert(memcmp(encoded, v->frame, encoded_len) == 0);
  assert(bw_spike_unpack(v->frame, v->frame_len, decoded, sizeof(decoded),
                         &decoded_len) == BW_CODEC_OK);
  assert(decoded_len == v->payload_len);
  assert(memcmp(decoded, v->payload, decoded_len) == 0);
}

struct messages
{
  uint8_t payload[3][16];
  size_t length[3];
  bool high[3];
  size_t count;
};

static int collect(const uint8_t *payload, size_t payload_len,
                   bool high_priority, void *context)
{
  struct messages *messages = context;
  assert(messages->count < 3 && payload_len <= 16);
  memcpy(messages->payload[messages->count], payload, payload_len);
  messages->length[messages->count] = payload_len;
  messages->high[messages->count] = high_priority;
  ++messages->count;
  return 0;
}

int main(void)
{
  static const uint8_t p0[] = {0};
  static const uint8_t p1[] = {1};
  static const uint8_t p2[] = {2};
  static const uint8_t p3[] = {3};
  static const uint8_t pall[] = {0, 1, 2, 3};
  static const uint8_t pn[] = {0x28, 0x64, 0};
  static const uint8_t fempty[] = {0, 2};
  static const uint8_t f0[] = {0, 0, 2};
  static const uint8_t f1[] = {0x54, 0, 2};
  static const uint8_t f2[] = {0xa8, 0, 2};
  static const uint8_t f3[] = {7, 0, 2};
  static const uint8_t fall[] = {0, 0x54, 0xa8, 7, 0, 2};
  static const uint8_t fn[] = {6, 0x2b, 0x67, 0, 2};
  static const struct vector vectors[] = {
    {NULL, 0, fempty, sizeof(fempty)}, {p0, sizeof(p0), f0, sizeof(f0)},
    {p1, sizeof(p1), f1, sizeof(f1)}, {p2, sizeof(p2), f2, sizeof(f2)},
    {p3, sizeof(p3), f3, sizeof(f3)}, {pall, sizeof(pall), fall, sizeof(fall)},
    {pn, sizeof(pn), fn, sizeof(fn)}
  };
  uint8_t out[8];
  size_t out_len;
  static const uint8_t bad1[] = {2};
  static const uint8_t bad2[] = {0, 0};
  static const uint8_t bad3[] = {3, 2};

  for (size_t i = 0; i < sizeof(vectors) / sizeof(vectors[0]); i++)
    {
      check(&vectors[i]);
    }
  assert(bw_spike_unpack(bad1, sizeof(bad1), out, sizeof(out), &out_len) == BW_CODEC_INVALID);
  assert(bw_spike_unpack(bad2, sizeof(bad2), out, sizeof(out), &out_len) == BW_CODEC_INVALID);
  assert(bw_spike_unpack(bad3, sizeof(bad3), out, sizeof(out), &out_len) == BW_CODEC_INVALID);
  struct bw_spike_stream stream = {0};
  struct messages messages = {0};
  uint8_t normal[32];
  uint8_t urgent[32];
  size_t normal_len = 0;
  size_t urgent_len = 0;
  assert(bw_spike_pack(pall, sizeof(pall), false, normal, sizeof(normal),
                       &normal_len) == BW_CODEC_OK);
  assert(bw_spike_pack(pn, sizeof(pn), true, urgent, sizeof(urgent),
                       &urgent_len) == BW_CODEC_OK);
  assert(bw_spike_stream_feed(&stream, normal, 2, collect, &messages) == BW_CODEC_OK);
  assert(bw_spike_stream_feed(&stream, urgent, urgent_len, collect, &messages) == BW_CODEC_OK);
  assert(bw_spike_stream_feed(&stream, normal + 2, normal_len - 2, collect,
                              &messages) == BW_CODEC_OK);
  assert(messages.count == 2);
  assert(messages.high[0] && !messages.high[1]);
  assert(messages.length[0] == sizeof(pn) && !memcmp(messages.payload[0], pn, sizeof(pn)));
  assert(messages.length[1] == sizeof(pall) && !memcmp(messages.payload[1], pall, sizeof(pall)));
  static const uint8_t malformed_stream[] = {3};
  assert(bw_spike_stream_feed(&stream, malformed_stream,
                              sizeof(malformed_stream), collect,
                              &messages) == BW_CODEC_INVALID);
  puts("native spike codec: all vectors passed");
  return 0;
}
