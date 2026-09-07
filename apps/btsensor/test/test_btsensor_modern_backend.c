/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_modern_backend.h"
#include <arch/board/board_legoport.h>
#include <arch/board/board_rgbled.h>
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

struct fake_port {
  uint8_t device_type, flags, lump_type;
  bool pinned;
  int16_t duty;
  int coast_count, brake_count;
  struct legoport_lump_send_arg_s matrix;
};
struct fake {
  struct fake_port ports[BOARD_LEGOPORT_COUNT];
  int opens[BOARD_LEGOPORT_COUNT], closes[BOARD_LEGOPORT_COUNT];
  struct rgbled_duty_s led;
  unsigned led_writes;
  int rgb_opens, rgb_closes;
};

static int fd_port(int fd) {
  int port = fd - 20;
  return port >= 0 && port < BOARD_LEGOPORT_COUNT ? port : -1;
}
static int fake_open(const char *path, int flags, void *context) {
  struct fake *f = context;
  int port = -1;
  (void)flags;
  if (!strcmp(path, "/dev/rgbled0")) {
    f->rgb_opens++;
    return 30;
  }
  if (sscanf(path, "/dev/legoport%d", &port) != 1 || port < 0 ||
      port >= BOARD_LEGOPORT_COUNT)
    return -ENOENT;
  f->opens[port]++;
  return 20 + port;
}
static int fake_ioctl(int fd, int command, unsigned long argument,
                      void *context) {
  struct fake *f = context;
  int port = fd_port(fd);
  if (fd == 30 && command == RGBLEDIOC_SETDUTY) {
    f->led = *(const struct rgbled_duty_s *)argument;
    f->led_writes++;
    return 0;
  }
  if (port < 0)
    return -EBADF;
  struct fake_port *p = &f->ports[port];
  if (command == LEGOPORT_GET_DEVICE_INFO) {
    struct legoport_info_s *i = (void *)argument;
    memset(i, 0, sizeof(*i));
    i->device_type = p->device_type;
    i->flags = p->flags;
    return 0;
  }
  if (command == LEGOPORT_LUMP_GET_INFO) {
    struct lump_device_info_s *i = (void *)argument;
    if (!(p->flags & LEGOPORT_FLAG_IS_UART))
      return -EAGAIN;
    memset(i, 0, sizeof(*i));
    i->type_id = p->lump_type;
    i->num_modes = 4;
    i->modes[2].writable = 1;
    i->modes[2].num_values = 9;
    i->modes[2].data_type = LUMP_DATA_INT8;
    return 0;
  }
  if (command == LEGOPORT_PWM_GET_STATUS) {
    struct legoport_pwm_status_s *s = (void *)argument;
    memset(s, 0, sizeof(*s));
    s->flags = p->pinned ? LEGOPORT_PWM_FLAG_PINNED : 0;
    return 0;
  }
  if (command == LEGOPORT_PWM_SET_DUTY) {
    p->duty = (int16_t)argument;
    return p->pinned ? -EBUSY : 0;
  }
  if (command == LEGOPORT_PWM_COAST) {
    p->coast_count++;
    return 0;
  }
  if (command == LEGOPORT_PWM_BRAKE) {
    p->brake_count++;
    return 0;
  }
  if (command == LEGOPORT_LUMP_SEND) {
    p->matrix = *(const struct legoport_lump_send_arg_s *)argument;
    return 0;
  }
  return -ENOTTY;
}
static int fake_close(int fd, void *context) {
  struct fake *f = context;
  if (fd == 30) {
    f->rgb_closes++;
    return 0;
  }
  int port = fd_port(fd);
  if (port < 0)
    return -EBADF;
  f->closes[port]++;
  return 0;
}
static struct btsensor_modern_backend_io fake_io(struct fake *f) {
  struct btsensor_modern_backend_io io = {fake_open, fake_ioctl, fake_close, f};
  return io;
}
static void uart_device(struct fake *f, int port, uint8_t type) {
  f->ports[port].device_type = LEGOPORT_TYPE_LPF2_UNKNOWN_UART;
  f->ports[port].flags = LEGOPORT_FLAG_CONNECTED | LEGOPORT_FLAG_IS_UART;
  f->ports[port].lump_type = type;
}

static struct fake *system_fake;
int open(const char *path, int flags, ...) {
  int rc = fake_open(path, flags, system_fake);
  if (rc < 0) {
    errno = -rc;
    return -1;
  }
  return rc;
}
int ioctl(int fd, unsigned long command, ...) {
  va_list ap;
  va_start(ap, command);
  unsigned long argument = va_arg(ap, unsigned long);
  va_end(ap);
  int rc = fake_ioctl(fd, (int)command, argument, system_fake);
  if (rc < 0) {
    errno = -rc;
    return -1;
  }
  return rc;
}
int close(int fd) {
  int rc = fake_close(fd, system_fake);
  if (rc < 0) {
    errno = -rc;
    return -1;
  }
  return rc;
}

int main(void) {
  struct btsensor_modern_operation op = {0};
  struct fake f = {0};
  struct btsensor_modern_backend_io io = fake_io(&f);
  /* Two identical motors remain independently addressable by physical port. */
  uart_device(&f, 0, 48);
  uart_device(&f, 4, 48);
  op.kind = BTSENSOR_MODERN_OP_MOTOR;
  op.port = 0;
  op.speed = 75;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  op.port = 4;
  op.speed = -30;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.ports[0].duty == 7500 && f.ports[4].duty == -3000);
  assert(f.opens[0] == 1 && f.opens[4] == 1);
  assert(f.closes[0] == 0 && f.closes[4] == 0);
  /* Retained descriptor prevents close from immediately auto-coasting. */
  op.port = 0;
  op.speed = 10;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.opens[0] == 1 && f.ports[0].duty == 1000);
  op.speed = 0;
  op.has_end_state = true;
  op.end_state = 0;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.ports[0].coast_count == 1);
  op.end_state = 1;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.ports[0].brake_count == 1);
  op.end_state = 2;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -ENOTSUP);
  /* Reject connected wrong devices and pinned supply ports. */
  f.ports[1].device_type = LEGOPORT_TYPE_LPF2_LIGHT;
  f.ports[1].flags = LEGOPORT_FLAG_CONNECTED;
  op.port = 1;
  op.speed = 50;
  op.has_end_state = false;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -ENODEV);
  uart_device(&f, 2, 61);
  op.port = 2;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -ENODEV);
  uart_device(&f, 3, 49);
  f.ports[3].pinned = true;
  op.port = 3;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -EBUSY);
  /* Passive motors are accepted; disconnected ports are not. */
  f.ports[5].device_type = LEGOPORT_TYPE_LPF2_LMOTOR;
  f.ports[5].flags = LEGOPORT_FLAG_CONNECTED;
  op.port = 5;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  f.ports[5].flags = 0;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -ENODEV);
  /* Exact 3x3 matrix LUMP protocol remains port-indexed. */
  uart_device(&f, 2, 64);
  memset(&op, 0, sizeof(op));
  op.kind = BTSENSOR_MODERN_OP_MATRIX3;
  op.port = 2;
  op.pixels[4] = 0x99;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.ports[2].matrix.mode == 2 && f.ports[2].matrix.len == 9 &&
         f.ports[2].matrix.data[4] == 0x99);
  op.pixels[0] = 0xb9;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -ERANGE);
  /* Exact current-firmware Python translations use the built-in matrix. */
  memset(&op, 0, sizeof(op));
  op.kind = BTSENSOR_MODERN_OP_MATRIX5_PIXEL;
  op.x = 4;
  op.y = 3;
  op.brightness = 100;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.led_writes == 1 && f.led.channel == 22 &&
         f.led.value == UINT16_MAX);

  op.kind = BTSENSOR_MODERN_OP_MATRIX5_CLEAR;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == 0);
  assert(f.led_writes == 26 && f.led.channel == 9 && f.led.value == 0);
  assert(f.rgb_opens == 2 && f.rgb_closes == 2);

  memset(&op, 0, sizeof(op));
  op.kind = BTSENSOR_MODERN_OP_TUNNEL_OPAQUE;
  op.opaque = (const uint8_t *)"import os";
  op.opaque_length = 9;
  assert(btsensor_modern_backend_operation_with_io(&op, &io) == -ENOTSUP);
  btsensor_modern_backend_reset_with_io(&io);
  assert(f.closes[0] == 1 && f.closes[4] == 1);

  /* Link generation owns the production failsafe per physical port. */
  memset(&f, 0, sizeof(f));
  uart_device(&f, 4, 48);
  system_fake = &f;
  memset(&op, 0, sizeof(op));
  op.kind = BTSENSOR_MODERN_OP_MOTOR;
  op.port = 4;
  op.speed = 50;
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, true, 7);
  assert(btsensor_modern_backend_operation_for_link(BRICKWRIGHT_HUB_LINK_BLE,
                                                    &op) == 0);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, true, 8);
  assert(f.ports[4].coast_count == 1);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, false, 7);
  assert(f.ports[4].coast_count == 1);
  assert(btsensor_modern_backend_operation_for_link(BRICKWRIGHT_HUB_LINK_BLE,
                                                    &op) == 0);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, false, 8);
  assert(f.ports[4].coast_count == 2);
  btsensor_modern_backend_shutdown();
  assert(f.ports[4].coast_count == 3 && f.closes[4] == 1);
  btsensor_modern_backend_shutdown();
  assert(f.ports[4].coast_count == 3 && f.closes[4] == 1);

  /* Ownership follows the last successful command across transports.  A
   * disconnect from the displaced owner must not touch the motor. */
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, true, 9);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, true, 10);
  btsensor_modern_backend_set_motor_owner(BRICKWRIGHT_HUB_LINK_CLASSIC, 4,
                                          true);
  assert(btsensor_modern_backend_operation_for_link(
      BRICKWRIGHT_HUB_LINK_BLE, &op) == 0);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, false, 9);
  assert(f.ports[4].coast_count == 3);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, false, 10);
  assert(f.ports[4].coast_count == 4);

  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, true, 11);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, true, 12);
  assert(btsensor_modern_backend_operation_for_link(
      BRICKWRIGHT_HUB_LINK_BLE, &op) == 0);
  btsensor_modern_backend_set_motor_owner(BRICKWRIGHT_HUB_LINK_CLASSIC, 4,
                                          true);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, false, 12);
  assert(f.ports[4].coast_count == 4);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, false, 11);
  assert(f.ports[4].coast_count == 5);

  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, true, 13);
  assert(btsensor_modern_backend_operation_for_link(
      BRICKWRIGHT_HUB_LINK_BLE, &op) == 0);
  btsensor_modern_backend_set_motor_owner(BRICKWRIGHT_HUB_LINK_CLASSIC, 4,
                                          false);
  btsensor_modern_backend_link_state(BRICKWRIGHT_HUB_LINK_BLE, false, 13);
  assert(f.ports[4].coast_count == 5);

  /* A timed completion carries the exact successful command token.  The
   * ownership check and end-state write are atomic with a BLE takeover. */
  uint32_t classic_token = 0;
  uint32_t ble_token = 0;
  assert(btsensor_modern_backend_operation_for_link_tagged(
      BRICKWRIGHT_HUB_LINK_CLASSIC, &op, &classic_token) == 0);
  assert(classic_token != 0);
  assert(btsensor_modern_backend_operation_for_link_tagged(
      BRICKWRIGHT_HUB_LINK_BLE, &op, &ble_token) == 0);
  assert(ble_token != 0 && ble_token != classic_token);
  int coast_before = f.ports[4].coast_count;
  int brake_before = f.ports[4].brake_count;
  assert(btsensor_modern_backend_end_motor_if_owned(
      BRICKWRIGHT_HUB_LINK_CLASSIC, 4, classic_token, 1) == -ESTALE);
  assert(f.ports[4].coast_count == coast_before &&
         f.ports[4].brake_count == brake_before && f.ports[4].duty == 5000);
  assert(btsensor_modern_backend_end_motor_if_owned(
      BRICKWRIGHT_HUB_LINK_BLE, 4, ble_token, 1) == 0);
  assert(f.ports[4].brake_count == brake_before + 1);
  assert(btsensor_modern_backend_end_motor_if_owned(
      BRICKWRIGHT_HUB_LINK_BLE, 4, ble_token, 0) == -ESTALE);

  puts("btsensor modern backend tests: OK");
  return 0;
}
