/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_cmd.h"
#include "btsensor_peripheral.h"
#include "btsensor_tx.h"
#include <float.h>
#include <math.h>
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
struct fixture {
  char replies[32][BTSENSOR_TX_RESPONSE_MAX_LEN + 1];
  imu_fusion_snapshot_t snapshot;
  bool starting, running, stopping;
  unsigned fusion_calls;
  imu_xyz_t base_front, base_top;
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
  assert(strlen(s) < sizeof(f.replies[0]));
  strcpy(f.replies[f.nr++], s);
  return 0;
}
int btsensor_tx_enqueue_response_for_link(enum brickwright_hub_link link, const char *s) {
  f.link = link;
  return btsensor_tx_enqueue_response(s);
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
static int fusion_start(void *p) {
  struct fixture *x = p;
  x->fusion_calls++;
  strcpy(x->op, "fusion_start");
  return x->result;
}
static int fusion_stop(void *p) {
  struct fixture *x = p;
  x->fusion_calls++;
  strcpy(x->op, "fusion_stop");
  return x->result;
}
static int fusion_calibration_save(void *p) {
  struct fixture *x = p; x->fusion_calls++; strcpy(x->op, "fusion_save"); return x->result;
}
static int fusion_calibration_load(void *p) {
  struct fixture *x = p; x->fusion_calls++; strcpy(x->op, "fusion_load"); return x->result;
}
static int fusion_status(void *p, bool *starting, bool *running, bool *stopping) {
  struct fixture *x = p;
  x->fusion_calls++;
  *starting = x->starting; *running = x->running; *stopping = x->stopping;
  return x->result;
}
static int fusion_snapshot(void *p, imu_fusion_snapshot_t *out) {
  struct fixture *x = p;
  x->fusion_calls++;
  *out = x->snapshot;
  return x->result;
}
static int fusion_set_base_axes(void *p, const imu_xyz_t *front, const imu_xyz_t *top) {
  struct fixture *x = p;
  x->fusion_calls++;
  x->base_front = *front; x->base_top = *top;
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
                                             .imu_capture_stop = cap_stop,
                                             .fusion_start = fusion_start,
                                             .fusion_stop = fusion_stop,
                                             .fusion_calibration_save = fusion_calibration_save,
                                             .fusion_calibration_load = fusion_calibration_load,
                                             .fusion_status = fusion_status,
                                             .fusion_snapshot = fusion_snapshot,
                                             .fusion_set_base_axes = fusion_set_base_axes};
static void reset(void) {
  memset(&f, 0, sizeof(f));
  btsensor_cmd_init();
  btsensor_cmd_set_peripheral_ops(&ops);
}
static void send(enum brickwright_hub_link l, const char *s) {
  btsensor_cmd_feed_link(l, (const uint8_t *)s, strlen(s));
}
static void expect(const char *s) {
  if (!f.nr || strcmp(f.replies[f.nr - 1], s))
    fprintf(stderr, "expected %s got %s", s, f.nr ? f.replies[f.nr - 1] : "<none>");
  assert(f.nr && strcmp(f.replies[f.nr - 1], s) == 0);
}
static void expect_errno(int value) {
  char line[64];
  snprintf(line, sizeof(line), "ERR errno=%d\n", value);
  expect(line);
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
  expect_errno(ENODEV);
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
static void test_fusion(void) {
  reset();
  send(0, "FUSION START\n");
  expect("OK\n");
  assert(!strcmp(f.op, "fusion_start"));
  send(0, "FUSION STOP\n");
  expect("OK\n");
  assert(f.link == 0 && !strcmp(f.op, "fusion_stop"));
  unsigned initial_calls = f.fusion_calls;
  const char *ble[] = {"FUSION START\n", "FUSION STOP\n",
                       "FUSION STATUS\n", "FUSION GET\n"};
  for (size_t i = 0; i < sizeof(ble) / sizeof(*ble); i++) {
    send(1, ble[i]); expect_errno(ENOTSUP);
  }
  assert(f.fusion_calls == initial_calls);
  f.starting = true; f.stopping = true;
  send(0, "FUSION STATUS\n");
  expect("FUSION STATUS 1 0 1\n");
  unsigned calls = f.fusion_calls;
  const char *bad[] = {"FUSION\n", "FUSION START extra\n", "FUSION STOP 0\n",
                       "FUSION STATUS extra\n", "FUSION GET extra\n", "FUSION start\n"};
  for (size_t i = 0; i < sizeof(bad) / sizeof(*bad); i++) {
    send(0, bad[i]);
    expect("ERR invalid FUSION\n");
  }
  assert(f.fusion_calls == calls);
  f.result = -EAGAIN;
  send(0, "FUSION GET\n");
  char error[64];
  snprintf(error, sizeof(error), "ERR errno=%d\n", EAGAIN);
  expect(error);
  f.result = 0;
  send(0, "FUSION GET\n");
  expect("ERR errno=5\n");
  f.snapshot = (imu_fusion_snapshot_t){
      .valid = true, .ready = true, .sequence = UINT64_MAX,
      .timestamp_us = UINT64_MAX - 1, .up_side = IMU_SIDE_BOTTOM,
      .accel_mms2 = {.values = {1, -2, 9806.65f}},
      .gyro_dps = {.values = {4, 5, -6}}, .heading_1d = 7, .heading_3d = 8,
      .orientation = {.values = {1, 2, 3, 4, 5, 6, 7, 8, 9}}};
  send(0, "FUSION GET\n");
  expect("FUSION SNAP 18446744073709551615 18446744073709551614 1 6 1 -2 9806.65 4 5 -6 7 8 1 2 3 4 5 6 7 8 9\n");
  assert(f.link == 0);
  f.snapshot.up_side = (imu_side_t)99;
  send(0, "FUSION GET\n"); expect_errno(EIO);
  f.snapshot.up_side = IMU_SIDE_TOP;
  f.snapshot.gyro_dps.z = NAN;
  send(0, "FUSION GET\n"); expect("ERR errno=5\n");
  f.snapshot.gyro_dps.z = 0;
  f.snapshot.orientation.m33 = INFINITY;
  send(0, "FUSION GET\n"); expect("ERR errno=5\n");
  for (size_t i = 0; i < 3; i++) {
    f.snapshot.accel_mms2.values[i] = -FLT_MAX;
    f.snapshot.gyro_dps.values[i] = FLT_MIN;
  }
  for (size_t i = 0; i < 9; i++) f.snapshot.orientation.values[i] = -FLT_MAX;
  f.snapshot.heading_1d = -FLT_MAX; f.snapshot.heading_3d = FLT_MIN;
  send(0, "FUSION GET\n");
  expect_errno(E2BIG);
  struct btsensor_peripheral_ops absent = {.context = &f};
  btsensor_cmd_set_peripheral_ops(&absent);
  send(0, "FUSION STOP\n"); expect_errno(ENOTSUP);
  btsensor_cmd_set_peripheral_ops(NULL);
  send(0, "FUSION GET\n"); expect_errno(ENOTSUP);
  send(0, "FUSION STATUS\n"); expect_errno(ENOTSUP);
  send(0, "FUSION START\n"); expect_errno(ENOTSUP);
}
static void test_fusion_calibration(void) {
  reset();
  send(0, "FUSION CAL SAVE\n"); expect("OK\n"); assert(!strcmp(f.op, "fusion_save"));
  send(0, "FUSION CAL LOAD\n"); expect("OK\n"); assert(!strcmp(f.op, "fusion_load"));
  unsigned calls = f.fusion_calls;
  send(1, "FUSION CAL SAVE\n"); expect_errno(ENOTSUP);
  send(1, "FUSION CAL LOAD\n"); expect_errno(ENOTSUP);
  const char *bad[] = {"FUSION CAL\n", "FUSION CAL save\n", "FUSION CAL ERASE\n",
                       "FUSION CAL SAVE path\n", "FUSION CAL LOAD 1\n"};
  for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
    send(0,bad[i]);expect("ERR invalid FUSION CAL\n");
  }
  assert(f.fusion_calls == calls);
  f.result=-ENOENT;send(0,"FUSION CAL LOAD\n");expect_errno(ENOENT);
  f.result=-ENOSPC;send(0,"FUSION CAL SAVE\n");expect_errno(ENOSPC);
  f.result=-EAGAIN;send(0,"FUSION CAL SAVE\n");expect_errno(EAGAIN);
  btsensor_cmd_set_peripheral_ops(NULL);
  send(0,"FUSION CAL SAVE\n");expect_errno(ENOTSUP);
  send(0,"FUSION CAL LOAD\n");expect_errno(ENOTSUP);
}
static void test_fusion_base(void) {
  reset();
  send(0, "FUSION BASE 1 0 0 0 0 1\n");
  expect("OK\n");
  assert(f.fusion_calls == 1 && f.base_front.x == 1 && f.base_top.z == 1);
  send(0, "FUSION BASE 0 -1 0 1 0 0\n");
  expect("OK\n");
  assert(f.fusion_calls == 2 && f.base_front.y == -1 && f.base_top.x == 1);
  send(1, "FUSION BASE 1 0 0 0 0 1\n");
  expect_errno(ENOTSUP);
  assert(f.fusion_calls == 2 && f.link == 1);
  const char *bad[] = {
    "FUSION BASE\n", "FUSION BASE 1 0 0 0 1\n",
    "FUSION BASE 1 0 0 0 0 1 extra\n", "FUSION BASE 0 0 0 0 0 1\n",
    "FUSION BASE 1 1 0 0 0 1\n", "FUSION BASE 1 0 0 -1 0 0\n",
    "FUSION BASE 1 0 0 1 0 0\n", "FUSION BASE 2 0 0 0 0 1\n",
    "FUSION BASE 1.0 0 0 0 0 1\n", "FUSION BASE 1e0 0 0 0 0 1\n",
    "FUSION BASE +1 0 0 0 0 1\n", "FUSION BASE 01 0 0 0 0 1\n",
    "FUSION BASE 1 -0 0 0 0 1\n", "FUSION BASE nan 0 0 0 0 1\n"
  };
  for (size_t i = 0; i < sizeof(bad) / sizeof(*bad); i++) {
    send(0, bad[i]); expect("ERR invalid FUSION BASE\n");
  }
  assert(f.fusion_calls == 2);
  f.result = -EBUSY;
  send(0, "FUSION BASE 1 0 0 0 0 1\n"); expect("ERR busy\n");
  f.result = -EAGAIN;
  send(0, "FUSION BASE 1 0 0 0 0 1\n"); expect_errno(EAGAIN);
  btsensor_cmd_set_peripheral_ops(NULL);
  send(0, "FUSION BASE 1 0 0 0 0 1\n"); expect_errno(ENOTSUP);
  struct btsensor_peripheral_ops absent = {.context = &f};
  btsensor_cmd_set_peripheral_ops(&absent);
  send(0, "FUSION BASE 1 0 0 0 0 1\n"); expect_errno(ENOTSUP);
}
int main(void) {
  test_fusion_base();
  test_fusion_calibration();
  test_fusion();
  test_operations();
  test_errors();
  test_fixed_arity();
  reset();
  btsensor_cmd_set_peripheral_ops(NULL);
  send(0, "SET ODR 100\n");
  expect_errno(ENOTSUP);
  puts("btsensor neutral legacy command tests passed");
}
