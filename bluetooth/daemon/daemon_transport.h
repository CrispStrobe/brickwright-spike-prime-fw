/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_DAEMON_TRANSPORT_H
#define BRICKWRIGHT_DAEMON_TRANSPORT_H
#include "hub_protocol.h"
int brickwright_daemon_transport_init(brickwright_protocol_cb callback,
                                      void *context);
void brickwright_daemon_transport_reset(void);
int brickwright_daemon_transport_send(enum brickwright_protocol_kind kind,
                                      const void *data, size_t length,
                                      bool high_priority);
#endif
