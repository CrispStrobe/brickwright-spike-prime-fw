/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_TRANSPORT_H
#define BTSENSOR_TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <brickwright/hub_transport.h>

typedef void (*btsensor_transport_receive_cb)(enum brickwright_hub_link link,
                                               const uint8_t *data,
                                               size_t length, void *context);
typedef brickwright_hub_link_state_cb btsensor_transport_state_cb;

int btsensor_transport_start(btsensor_transport_receive_cb receive,
                             btsensor_transport_state_cb state,
                             void *context);
int btsensor_transport_set_visible(bool visible);
bool btsensor_transport_connected(enum brickwright_hub_link link);
int btsensor_transport_send(enum brickwright_hub_link link,
                            const void *data, size_t length);
int btsensor_transport_stop(void);

#endif
