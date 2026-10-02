/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_FD02_SERVICE_H
#define BRICKWRIGHT_FD02_SERVICE_H
#include <stddef.h>
#include <stdint.h>
struct bt_conn;
typedef void (*brickwright_fd02_receive_cb)(const uint8_t *data, size_t length,
                                            void *context);
void brickwright_fd02_set_receive(brickwright_fd02_receive_cb callback,
                                  void *context);
int brickwright_fd02_notify(struct bt_conn *connection, const void *data,
                            uint16_t length);
uint16_t brickwright_fd02_rx_handle(void);
uint16_t brickwright_fd02_tx_handle(void);
uint16_t brickwright_fd02_ccc_handle(void);
#endif
