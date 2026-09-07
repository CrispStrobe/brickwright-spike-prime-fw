/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_SOUND_H
#define BTSENSOR_SOUND_H

#include "btsensor_modern.h"
#include <brickwright/hub_transport.h>
#include <stddef.h>
#include <stdint.h>

typedef void (*btsensor_sound_timer_cb_t)(void *arg);

struct btsensor_sound_io
{
  int (*open)(const char *path, int flags, void *context);
  int (*write)(int fd, const void *data, size_t length, void *context);
  int (*ioctl)(int fd, int command, unsigned long argument, void *context);
  int (*close)(int fd, void *context);
  int (*timer_start)(uint32_t delay_ms, btsensor_sound_timer_cb_t callback,
                     void *arg, void *context);
  void (*timer_stop)(void *context);
  void *context;
};

int btsensor_sound_operation(enum brickwright_hub_link link,
                             const struct btsensor_modern_operation *operation);
int btsensor_sound_operation_with_io(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation,
    const struct btsensor_sound_io *io);
void btsensor_sound_link_state(enum brickwright_hub_link link, bool connected);
void btsensor_sound_shutdown(void);
void btsensor_sound_reset_with_io(const struct btsensor_sound_io *io);

#endif
