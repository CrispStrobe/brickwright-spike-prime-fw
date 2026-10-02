/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_CLASSIC_H
#define BTSENSOR_CLASSIC_H

#include "btsensor_modern.h"
#include "btsensor_modern_notify.h"
#include <brickwright/hub_transport.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef int (*btsensor_classic_operation_t)(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation, void *context);
typedef int (*btsensor_classic_tagged_operation_t)(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation,
    uint32_t *ownership_token, void *context);
typedef int (*btsensor_classic_end_owned_t)(
    enum brickwright_hub_link link, uint8_t port, uint32_t ownership_token,
    uint8_t end_state, void *context);
typedef int (*btsensor_classic_snapshot_t)(
    struct btsensor_modern_snapshot *snapshot, void *context);
typedef int (*btsensor_classic_send_t)(enum brickwright_hub_link link,
                                       const uint8_t *data, size_t length,
                                       void *context);
typedef uint64_t (*btsensor_classic_now_t)(void *context);
typedef int (*btsensor_classic_timer_start_t)(uint32_t delay_ms,
                                              void *context);
typedef void (*btsensor_classic_timer_stop_t)(void *context);

struct btsensor_classic_config
{
  btsensor_classic_operation_t operation;
  btsensor_classic_tagged_operation_t tagged_operation;
  btsensor_classic_end_owned_t end_owned;
  btsensor_classic_snapshot_t snapshot;
  btsensor_classic_send_t send;
  btsensor_classic_now_t now;
  btsensor_classic_timer_start_t timer_start;
  btsensor_classic_timer_stop_t timer_stop;
  void *context;
};

void btsensor_classic_init(const struct btsensor_classic_config *config);
void btsensor_classic_timer_fired(void);
void btsensor_classic_link_state(enum brickwright_hub_link link,
                                 bool connected);

/* Returns true only when line is a syntactically exact request in the
 * supported Classic JSON subset.  Input is never evaluated as Python. */
bool btsensor_classic_receive(enum brickwright_hub_link link,
                              const uint8_t *line, size_t length);

#endif
