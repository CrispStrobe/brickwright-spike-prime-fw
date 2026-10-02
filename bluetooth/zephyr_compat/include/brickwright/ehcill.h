/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_EHCILL_H
#define BRICKWRIGHT_EHCILL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <brickwright/h4.h>

#define BRICKWRIGHT_EHCILL_SLEEP_IND 0x30
#define BRICKWRIGHT_EHCILL_SLEEP_ACK 0x31
#define BRICKWRIGHT_EHCILL_WAKE_IND  0x32
#define BRICKWRIGHT_EHCILL_WAKE_ACK  0x33
#define BRICKWRIGHT_EHCILL_PENDING_MAX 4096

typedef int (*brickwright_ehcill_write_cb)(const uint8_t *data, size_t length,
                                            void *context);

enum brickwright_ehcill_state {
  BRICKWRIGHT_EHCILL_AWAKE,
  BRICKWRIGHT_EHCILL_ASLEEP,
  BRICKWRIGHT_EHCILL_WAKING
};

struct brickwright_ehcill {
  enum brickwright_ehcill_state state;
  struct brickwright_h4 *h4;
  brickwright_ehcill_write_cb write;
  void *context;
  uint8_t pending[BRICKWRIGHT_EHCILL_PENDING_MAX];
  size_t pending_length;
};

void brickwright_ehcill_init(struct brickwright_ehcill *ehcill,
                             struct brickwright_h4 *h4,
                             brickwright_ehcill_write_cb write,
                             void *context);
int brickwright_ehcill_feed(struct brickwright_ehcill *ehcill,
                            const void *data, size_t length);
int brickwright_ehcill_send(struct brickwright_ehcill *ehcill,
                            const void *frame, size_t length);
bool brickwright_ehcill_awake(const struct brickwright_ehcill *ehcill);
void brickwright_ehcill_abort(struct brickwright_ehcill *ehcill);

#endif
