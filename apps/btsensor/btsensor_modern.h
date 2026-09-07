/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_MODERN_H
#define BTSENSOR_MODERN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BTSENSOR_MODERN_MAX_MESSAGE 1024u
/* Safe before ATT MTU exchange: one complete packet fits the mandatory
 * 23-byte ATT MTU (20-byte characteristic value). */
#define BTSENSOR_MODERN_MAX_PACKET  20u
#define BTSENSOR_MODERN_MAX_CHUNK   512u
#define BTSENSOR_MODERN_MAX_NOTIFICATION_RECORDS 128u

enum btsensor_modern_operation_kind
{
  BTSENSOR_MODERN_OP_MOTOR,
  BTSENSOR_MODERN_OP_MATRIX3,
  BTSENSOR_MODERN_OP_MATRIX5_PIXEL,
  BTSENSOR_MODERN_OP_MATRIX5_CLEAR,
  BTSENSOR_MODERN_OP_SOUND_BEEP,
  BTSENSOR_MODERN_OP_SOUND_STOP,
  BTSENSOR_MODERN_OP_TUNNEL_OPAQUE,
};

struct btsensor_modern_operation
{
  enum btsensor_modern_operation_kind kind;
  const uint8_t *opaque;
  size_t opaque_length;
  uint8_t port;
  int8_t speed;
  uint8_t end_state;
  bool has_end_state;
  uint8_t pixels[9];
  uint8_t x;
  uint8_t y;
  uint8_t brightness;
  uint16_t frequency_hz;
  uint16_t duration_ms;
};

typedef int (*btsensor_modern_send_t)(const uint8_t *message, size_t length,
                                      bool high_priority, void *context);
typedef int (*btsensor_modern_operation_t)(
    const struct btsensor_modern_operation *operation, void *context);
typedef int (*btsensor_modern_interval_t)(uint16_t interval_ms,
                                          void *context);

struct btsensor_modern_config
{
  uint8_t rpc_major;
  uint8_t rpc_minor;
  uint16_t rpc_build;
  uint8_t firmware_major;
  uint8_t firmware_minor;
  uint16_t firmware_build;
  uint16_t product_group_device;
};

struct btsensor_modern
{
  struct btsensor_modern_config config;
  btsensor_modern_send_t send;
  btsensor_modern_operation_t operation;
  btsensor_modern_interval_t set_interval;
  void *context;
  uint16_t notification_interval_ms;
  /* Avoid placing a maximum-size notification on a scheduler worker stack. */
  uint8_t notification_message[BTSENSOR_MODERN_MAX_NOTIFICATION_RECORDS + 3u];
};

void btsensor_modern_init(struct btsensor_modern *service,
                          const struct btsensor_modern_config *config,
                          btsensor_modern_send_t send,
                          btsensor_modern_operation_t operation,
                          btsensor_modern_interval_t set_interval,
                          void *context);
int btsensor_modern_receive(struct btsensor_modern *service,
                            const uint8_t *message, size_t length,
                            bool high_priority);
int btsensor_modern_notify(struct btsensor_modern *service,
                           const uint8_t *device_records, size_t length,
                           bool high_priority);

#endif
