/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_CLASSIC_SPP_H
#define BRICKWRIGHT_CLASSIC_SPP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
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
#endif
