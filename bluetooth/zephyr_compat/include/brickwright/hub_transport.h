/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_HUB_TRANSPORT_H
#define BRICKWRIGHT_HUB_TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum brickwright_hub_link
{
  BRICKWRIGHT_HUB_LINK_CLASSIC,
  BRICKWRIGHT_HUB_LINK_BLE,
};

typedef void (*brickwright_hub_receive_cb)(enum brickwright_hub_link link,
                                            const uint8_t *data,
                                            size_t length, void *context);
typedef void (*brickwright_hub_link_state_cb)(enum brickwright_hub_link link,
                                               bool connected,
                                               uint32_t generation,
                                               void *context);

int brickwright_hub_transport_register(brickwright_hub_receive_cb receive,
                                       brickwright_hub_link_state_cb state,
                                       void *context);
void brickwright_hub_transport_unregister(void);
int brickwright_hub_transport_send(enum brickwright_hub_link link,
                                   const void *data, size_t length);
bool brickwright_hub_transport_connected(enum brickwright_hub_link link);

/* A controller stops legacy advertising when a central connects, and the
 * host does not resume it. The transport reports both moments so the owner
 * of advertising can track it and restart it: advertising_stopped runs when
 * an LE peripheral link is established, advertising_restart runs on the
 * system work queue once a finished connection's object is recycled. */
/* Called when a link can take more data after a send was refused for lack of
 * transmit buffers (Classic: an SPP frame completed). */
void brickwright_hub_transport_set_writable_hook(
  void (*writable)(enum brickwright_hub_link link));

void brickwright_hub_transport_set_advertising_hooks(
  void (*advertising_stopped)(void), void (*advertising_restart)(void));

#endif
