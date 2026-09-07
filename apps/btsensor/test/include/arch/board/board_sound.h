/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_BOARD_SOUND_H
#define TEST_BOARD_SOUND_H
#include <stdint.h>
#define TONEIOC_STOP 0x6042
#define PCM_WRITE_MAGIC 0x304d4350u
#define PCM_WRITE_VERSION 1u
struct pcm_write_hdr_s {
  uint32_t magic;
  uint16_t version;
  uint16_t hdr_size;
  uint32_t flags;
  uint32_t sample_rate;
  uint32_t sample_count;
};
#endif
