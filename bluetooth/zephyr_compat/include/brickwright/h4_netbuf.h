/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_H4_NETBUF_H
#define BRICKWRIGHT_H4_NETBUF_H
#include <stddef.h>
#include <stdint.h>
struct net_buf;
typedef int (*brickwright_netbuf_receive_cb)(struct net_buf *buffer,
                                             void *context);
struct brickwright_h4_netbuf {
  brickwright_netbuf_receive_cb receive;
  void *context;
  int64_t allocation_timeout;
};
int brickwright_h4_netbuf_receive(uint8_t type, const uint8_t *packet,
                                  size_t length, void *context);
#endif
