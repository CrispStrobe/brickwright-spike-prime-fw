/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_cmd.h"
#include "btsensor_peripheral.h"
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
struct fixture {
  char replies[32][64];
  int nr;
  enum brickwright_hub_link link;
  char op[16];
  bool enabled;
  uint32_t value;
  uint8_t cls, mode, data[32];
  size_t count;
  int16_t pwm[4];
  int result;
};
static struct fixture f;
void btsensor_tx_set_link(enum brickwright_hub_link l, bool selected) {
  assert(selected);
  f.link = l;
}
int btsensor_tx_enqueue_response(const char *s) {
  assert(f.nr < 32);
  strcpy(f.replies[f.nr++], s);
  return 0;
}
static int toggle(void *p, bool v) {
  ((struct fixture *)p)->enabled = v;
  return ((struct fixture *)p)->result;
}
static int setv(void *p, uint32_t v) {
  ((struct fixture *)p)->value = v;
  return ((struct fixture *)p)->result;
}
static int getv(void *p, uint32_t *v) {
  struct fixture *x = p;
  if (!x->result)
    *v = x->value;
  return x->result;
}
static int mode(void *p, uint8_t c, uint8_t m) {
  struct fixture *x = p;
  strcpy(x->op, "mode");
  x->cls = c;
  x->mode = m;
  return x->result;
}
static int send_data(void *p, uint8_t c, uint8_t m, const uint8_t *d,
                     size_t n) {
  struct fixture *x = p;
  strcpy(x->op, "send");
  x->cls = c;
  x->mode = m;
  memcpy(x->data, d, n);
  x->count = n;
  return x->result;
}
static int pwm(void *p, enum brickwright_hub_link link, uint8_t c,
               const int16_t *v, size_t n) {
  struct fixture *x = p;
  x->link = link;
  strcpy(x->op, "pwm");
  x->cls = c;
  memcpy(x->pwm, v, n * sizeof(*v));
  x->count = n;
  return x->result;
}
static int cap_start(void *p, uint32_t v) {
  struct fixture *x = p;
  strcpy(x->op, "cap_start");
  x->value = v;
  return x->result;
}
static int cap_stop(void *p) {
  struct fixture *x = p;
  strcpy(x->op, "cap_stop");
  return x->result;
}
static struct btsensor_peripheral_ops ops = {.context = &f,
                                             .set_imu_enabled = toggle,
                                             .set_sensor_enabled = toggle,
                                             .set_imu_odr_hz = setv,
                                             .set_accel_fsr = setv,
                                             .set_gyro_fsr = setv,
                                             .get_imu_odr_idx = getv,
                                             .get_accel_fsr_idx = getv,
                                             .get_gyro_fsr_idx = getv,
                                             .sensor_select_mode = mode,
                                             .sensor_send = send_data,
                                             .sensor_set_pwm = pwm,
                                             .imu_capture_start = cap_start,
                                             .imu_capture_stop = cap_stop};
static void reset(void) {
  memset(&f, 0, sizeof(f));
  btsensor_cmd_init();
  btsensor_cmd_set_peripheral_ops(&ops);
}
static void send(enum brickwright_hub_link l, const char *s) {
  btsensor_cmd_feed_link(l, (const uint8_t *)s, strlen(s));
}
static void expect(const char *s) {
  assert(f.nr && strcmp(f.replies[f.nr - 1], s) == 0);
}
static void test_operations(void) {
  reset();
  send(0, "PI");
  send(0, "NG\r\n");
  expect("OK PONG\n");
  send(0, "IMU ON\n");
  expect("OK\n");
  assert(f.enabled);
  send(0, "SENSOR off\n");
  assert(!f.enabled);
  send(0, "SET ODR 833\n");
  assert(f.value == 833);
  f.value = 7;
  send(0, "GET ODR\n");
  expect("OK 7\n");
  send(0, "SENSOR MODE color 3\n");
  assert(f.cls == 0 && f.mode == 3);
  send(0, "SENSOR SEND motor_l 7 00aB ff\n");
  assert(f.cls == 5 && f.mode == 7 && f.count == 3 && f.data[1] == 0xab);
  send(0, "SENSOR PWM 4 -10000 25\n");
  assert(f.link == 0 && f.cls == 4 && f.count == 2 && f.pwm[0] == -10000);
  send(0, "_IMU_CAP START 60\n");
  assert(f.value == 60 && !strcmp(f.op, "cap_start"));
  send(0, "_IMU_CAP STOP\n");
  assert(!strcmp(f.op, "cap_stop"));
}
static void test_errors(void) {
  reset();
  f.result = -EBUSY;
  send(1, "IMU ON\n");
  expect("ERR busy\n");
  assert(f.link == 1);
  f.result = -ENODEV;
  send(0, "SENSOR MODE force 1\n");
  expect("ERR errno=19\n");
  f.result = 0;
  send(0, "SET ODR 12junk\n");
  expect("ERR invalid value\n");
  send(0, "SET ODR 4294967296\n");
  expect("ERR invalid value\n");
  send(0, "SENSOR WHAT\n");
  expect("ERR invalid WHAT\n");
  send(0, "SENSOR MODE nope 1\n");
  expect("ERR invalid class\n");
  send(0, "SENSOR SEND color 8 aa\n");
  expect("ERR invalid mode\n");
  send(0, "SENSOR SEND color 1 abc\n");
  expect("ERR invalid hex\n");
  send(0, "SENSOR PWM motor_m 10001\n");
  expect("ERR invalid pwm\n");
  send(0, "_IMU_CAP START 86401\n");
  expect("ERR invalid duration\n");
  send(0, "BAD\n");
  expect("ERR unknown BAD\n");
  char line[BTSENSOR_CMD_MAX_LINE + 8];
  memset(line, 'x', sizeof(line));
  line[sizeof(line) - 1] = '\n';
  btsensor_cmd_feed_link(0, (uint8_t *)line, sizeof(line));
  expect("ERR overflow\n");
  send(0, "PING\n");
  expect("OK PONG\n");
}
static void test_fixed_arity(void) {
  reset();
  send(0, "PING extra\n");
  expect("ERR invalid PING\n");
  send(0, "IMU ON extra\n");
  expect("ERR invalid IMU\n");
  assert(!f.enabled);
  send(0, "SENSOR OFF extra\n");
  expect("ERR invalid SENSOR\n");
  send(0, "SET ODR 100 extra\n");
  expect("ERR invalid SET\n");
  assert(f.value == 0);
  send(0, "GET ODR extra\n");
  expect("ERR invalid GET\n");
  send(0, "SENSOR MODE color 1 extra\n");
  expect("ERR invalid mode\n");
  assert(f.op[0] == '\0');
  send(0, "_IMU_CAP START 1 extra\n");
  expect("ERR invalid _IMU_CAP\n");
  assert(f.op[0] == '\0');
  send(0, "_IMU_CAP STOP extra\n");
  expect("ERR invalid _IMU_CAP\n");
  assert(f.op[0] == '\0');
}
int main(void) {
  test_operations();
  test_errors();
  test_fixed_arity();
  reset();
  btsensor_cmd_set_peripheral_ops(NULL);
  send(0, "SET ODR 100\n");
  expect("ERR errno=95\n");
  puts("btsensor neutral legacy command tests passed");
}
