/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_SPIKE_CODEC_H
#define BRICKWRIGHT_SPIKE_CODEC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum bw_codec_status
{
  BW_CODEC_OK = 0,
  BW_CODEC_INVALID = -1,
  BW_CODEC_NO_SPACE = -2
};

#define BW_SPIKE_STREAM_MAX_FRAME 1026u

struct bw_spike_stream
{
  uint8_t low[BW_SPIKE_STREAM_MAX_FRAME];
  uint8_t high[BW_SPIKE_STREAM_MAX_FRAME];
  size_t low_len;
  size_t high_len;
  bool high_active;
};

typedef int (*bw_spike_message_cb)(const uint8_t *payload, size_t payload_len,
                                   bool high_priority, void *context);

int bw_spike_pack(const uint8_t *payload, size_t payload_len, bool high_priority,
                  uint8_t *frame, size_t frame_capacity, size_t *frame_len);
int bw_spike_unpack(const uint8_t *frame, size_t frame_len, uint8_t *payload,
                    size_t payload_capacity, size_t *payload_len);
void bw_spike_stream_reset(struct bw_spike_stream *stream);
int bw_spike_stream_feed(struct bw_spike_stream *stream, const uint8_t *data,
                         size_t data_len, bw_spike_message_cb callback,
                         void *context);

#endif
