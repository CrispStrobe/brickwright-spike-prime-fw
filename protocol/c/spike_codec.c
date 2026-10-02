/* SPDX-License-Identifier: Apache-2.0 */
#include "spike_codec.h"

#define BW_DELIMITER_END 2u
#define BW_XOR 3u
#define BW_BLOCK_MAX 84u

static int bw_cobs_encode(const uint8_t *src, size_t src_len, uint8_t *dst,
                          size_t capacity, size_t *dst_len)
{
  size_t code_index = 0;
  size_t out = 1;
  size_t block = 1;

  if (capacity < 1 || (src_len > 0 && src == NULL))
    {
      return BW_CODEC_NO_SPACE;
    }

  dst[0] = 0xff;
  for (size_t i = 0; i < src_len; i++)
    {
      uint8_t byte = src[i];
      if (byte <= 2)
        {
          dst[code_index] = (uint8_t)(block + 2u + byte * BW_BLOCK_MAX);
          if (out >= capacity)
            {
              return BW_CODEC_NO_SPACE;
            }
          code_index = out++;
          dst[code_index] = 0xff;
          block = 1;
        }
      else
        {
          if (out >= capacity)
            {
              return BW_CODEC_NO_SPACE;
            }
          dst[out++] = byte;
          block++;
          if (block > BW_BLOCK_MAX)
            {
              if (out >= capacity)
                {
                  return BW_CODEC_NO_SPACE;
                }
              code_index = out++;
              dst[code_index] = 0xff;
              block = 1;
            }
        }
    }

  dst[code_index] = (uint8_t)(block + 2u);
  *dst_len = out;
  return BW_CODEC_OK;
}

static int bw_cobs_decode(const uint8_t *src, size_t src_len, uint8_t *dst,
                          size_t capacity, size_t *dst_len)
{
  size_t in = 0;
  size_t out = 0;

  if (src_len == 0)
    {
      return BW_CODEC_INVALID;
    }

  while (in < src_len)
    {
      uint8_t code = src[in++];
      size_t block;
      int delimiter = -1;

      if (code <= 2)
        {
          return BW_CODEC_INVALID;
        }
      if (code == 0xff)
        {
          block = BW_BLOCK_MAX;
        }
      else
        {
          unsigned adjusted = (unsigned)code - 3u;
          delimiter = (int)(adjusted / BW_BLOCK_MAX);
          block = adjusted % BW_BLOCK_MAX;
          if (delimiter > 2)
            {
              return BW_CODEC_INVALID;
            }
        }

      if (in + block > src_len)
        {
          return BW_CODEC_INVALID;
        }
      if (out + block + ((delimiter >= 0 && in + block < src_len) ? 1u : 0u) > capacity)
        {
          return BW_CODEC_NO_SPACE;
        }
      for (size_t j = 0; j < block; j++)
        {
          dst[out++] = src[in++];
        }
      if (delimiter >= 0 && in < src_len)
        {
          dst[out++] = (uint8_t)delimiter;
        }
    }

  *dst_len = out;
  return BW_CODEC_OK;
}

int bw_spike_pack(const uint8_t *payload, size_t payload_len, bool high_priority,
                  uint8_t *frame, size_t frame_capacity, size_t *frame_len)
{
  size_t encoded_len;
  size_t start = high_priority ? 1u : 0u;
  int status;

  if (frame == NULL || frame_len == NULL || frame_capacity < start + 2u)
    {
      return BW_CODEC_NO_SPACE;
    }
  if (high_priority)
    {
      frame[0] = 1;
    }
  status = bw_cobs_encode(payload, payload_len, frame + start,
                          frame_capacity - start - 1u, &encoded_len);
  if (status != BW_CODEC_OK)
    {
      return status;
    }
  for (size_t i = 0; i < encoded_len; i++)
    {
      frame[start + i] ^= BW_XOR;
    }
  frame[start + encoded_len] = BW_DELIMITER_END;
  *frame_len = start + encoded_len + 1u;
  return BW_CODEC_OK;
}

int bw_spike_unpack(const uint8_t *frame, size_t frame_len, uint8_t *payload,
                    size_t payload_capacity, size_t *payload_len)
{
  uint8_t scratch[1024];
  size_t start;
  size_t encoded_len;

  if (frame == NULL || payload == NULL || payload_len == NULL || frame_len < 2 ||
      frame[frame_len - 1] != BW_DELIMITER_END)
    {
      return BW_CODEC_INVALID;
    }
  start = frame[0] == 1 ? 1u : 0u;
  encoded_len = frame_len - start - 1u;
  if (encoded_len == 0 || encoded_len > sizeof(scratch))
    {
      return BW_CODEC_INVALID;
    }
  for (size_t i = 0; i < encoded_len; i++)
    {
      if (frame[start + i] == 1 || frame[start + i] == 2 || frame[start + i] == 3)
        {
          return BW_CODEC_INVALID;
        }
      scratch[i] = frame[start + i] ^ BW_XOR;
    }
  return bw_cobs_decode(scratch, encoded_len, payload, payload_capacity, payload_len);
}

void bw_spike_stream_reset(struct bw_spike_stream *stream)
{
  if (stream)
    {
      stream->low_len = 0;
      stream->high_len = 0;
      stream->high_active = false;
    }
}

int bw_spike_stream_feed(struct bw_spike_stream *stream, const uint8_t *data,
                         size_t data_len, bw_spike_message_cb callback,
                         void *context)
{
  uint8_t payload[BW_SPIKE_STREAM_MAX_FRAME];
  if (!stream || (!data && data_len) || !callback)
    {
      return BW_CODEC_INVALID;
    }
  for (size_t i = 0; i < data_len; ++i)
    {
      const uint8_t byte = data[i];
      if (byte == 1)
        {
          stream->high_len = 0;
          stream->high_active = true;
          continue;
        }
      size_t *length = stream->high_active ? &stream->high_len : &stream->low_len;
      uint8_t *frame = stream->high_active ? stream->high : stream->low;
      if (byte == BW_DELIMITER_END)
        {
          if (*length)
            {
              size_t payload_len = 0;
              frame[(*length)++] = BW_DELIMITER_END;
              int status = bw_spike_unpack(frame, *length, payload,
                                           sizeof(payload), &payload_len);
              *length = 0;
              if (stream->high_active)
                {
                  stream->high_active = false;
                }
              if (status != BW_CODEC_OK)
                {
                  bw_spike_stream_reset(stream);
                  return status;
                }
              status = callback(payload, payload_len, frame == stream->high,
                                context);
              if (status)
                {
                  return status;
                }
            }
          else if (stream->high_active)
            {
              stream->high_active = false;
            }
          continue;
        }
      if (byte == BW_XOR || *length >= BW_SPIKE_STREAM_MAX_FRAME - 1)
        {
          bw_spike_stream_reset(stream);
          return byte == BW_XOR ? BW_CODEC_INVALID : BW_CODEC_NO_SPACE;
        }
      frame[(*length)++] = byte;
    }
  return BW_CODEC_OK;
}
