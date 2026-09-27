/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_CLASSIC_SPP_H
#define BRICKWRIGHT_CLASSIC_SPP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* RFCOMM server channel of the SPP record. Channel 1 matches the LEGO hub:
 * tools written against official SPIKE/Robot Inventor firmware open channel
 * 1 directly (BlueZ `rfcomm connect` default; SPIKE-RI-Rfcomm), as do
 * Scratch Link's macOS and Linux backends, and the BTstack-based spike-nx
 * baseline served SPP on channel 1 on real hubs. Zephyr's pre-allocated
 * BT_RFCOMM_CHAN_SPP (5) would only be found by SDP-aware clients. */
#define BRICKWRIGHT_SPP_RFCOMM_CHANNEL 1

typedef void (*brickwright_classic_spp_receive_cb)(const uint8_t *data,
                                                    size_t length,
                                                    void *context);
typedef void (*brickwright_classic_spp_state_cb)(bool connected,
                                                 void *context);
int brickwright_classic_spp_register(brickwright_classic_spp_receive_cb receive,
                                     brickwright_classic_spp_state_cb state,
                                     void *context);
int brickwright_classic_spp_send(const void *data, size_t length);
bool brickwright_classic_spp_is_connected(void);
uint8_t brickwright_classic_spp_channel(void);
/* Called whenever a sent SPP frame completes, so a sender that stopped on a
 * busy link (-ENOMEM: the transmit pool is empty) can resume. */
void brickwright_classic_spp_set_sent_hook(void (*sent)(void));
#endif
