/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_H4_H
#define BRICKWRIGHT_H4_H
#include <stddef.h>
#include <stdint.h>
#define BRICKWRIGHT_H4_MAX_PACKET 2048
typedef int (*brickwright_h4_packet_cb)(uint8_t type, const uint8_t *packet,
                                        size_t length, void *context);
struct brickwright_h4 {
  uint8_t type;
  uint8_t header_length;
  size_t used;
  size_t expected;
  uint8_t packet[BRICKWRIGHT_H4_MAX_PACKET];
  brickwright_h4_packet_cb receive;
  void *context;
};
void brickwright_h4_init(struct brickwright_h4 *h4,
                         brickwright_h4_packet_cb receive, void *context);
int brickwright_h4_feed(struct brickwright_h4 *h4, const void *data, size_t length);
#endif
