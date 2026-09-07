/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_MODERN_BACKEND_H
#define BTSENSOR_MODERN_BACKEND_H

#include "btsensor_modern.h"
#include <brickwright/hub_transport.h>

/* Narrow system boundary. Production uses the NuttX implementations; tests
 * replace these callbacks with an in-memory model. Callbacks return either a
 * non-negative result or a negated errno. */
struct btsensor_modern_backend_io
{
  int (*open)(const char *path, int flags, void *context);
  int (*ioctl)(int fd, int command, unsigned long argument, void *context);
  int (*close)(int fd, void *context);
  void *context;
};

int btsensor_modern_backend_operation(
    const struct btsensor_modern_operation *operation);
int btsensor_modern_backend_operation_for_link(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation);
int btsensor_modern_backend_operation_for_link_tagged(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation,
    uint32_t *ownership_token);
int btsensor_modern_backend_end_motor_if_owned(
    enum brickwright_hub_link link, uint8_t port, uint32_t ownership_token,
    uint8_t end_state);
void btsensor_modern_backend_link_state(enum brickwright_hub_link link,
                                        bool connected, uint32_t generation);
void btsensor_modern_backend_set_motor_owner(enum brickwright_hub_link link,
                                              uint8_t port, bool running);
void btsensor_modern_backend_shutdown(void);

int btsensor_modern_backend_operation_with_io(
    const struct btsensor_modern_operation *operation,
    const struct btsensor_modern_backend_io *io);

/* Test/support seam: coast and close descriptors retained by the supplied
 * port-indexed I/O backend.  Production shutdown performs this automatically.
 */
void btsensor_modern_backend_reset_with_io(
    const struct btsensor_modern_backend_io *io);

#endif
