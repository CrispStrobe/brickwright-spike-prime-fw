/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "btsensor_nuttx_peripheral.h"
#include "btsensor_peripheral.h"

static const struct btsensor_peripheral_ops *g_installed;
static int g_imu_init_rc, g_sensor_init_rc, g_bundle_init_rc;
static int g_imu_init_calls, g_sensor_init_calls, g_bundle_init_calls;
static int g_imu_deinit_calls, g_sensor_deinit_calls, g_bundle_deinit_calls;
static int g_forward_rc;
static const void *g_forward_ptr;
static size_t g_forward_count;
static uint8_t g_forward_class, g_forward_mode;
static uint8_t g_forward_port = 3;
static enum brickwright_hub_link g_owner_link;
static bool g_owner_running;

void btsensor_cmd_set_peripheral_ops(const struct btsensor_peripheral_ops *ops)
{
  g_installed = ops;
}
int imu_sampler_init(void) { g_imu_init_calls++; return g_imu_init_rc; }
void imu_sampler_deinit(void) { g_imu_deinit_calls++; }
int sensor_sampler_init(void) { g_sensor_init_calls++; return g_sensor_init_rc; }
void sensor_sampler_deinit(void) { g_sensor_deinit_calls++; }
int bundle_emitter_init(void) { g_bundle_init_calls++; return g_bundle_init_rc; }
void bundle_emitter_deinit(void) { g_bundle_deinit_calls++; }
int bundle_emitter_set_imu_enabled(bool on) { g_forward_count = on; return g_forward_rc; }
int bundle_emitter_set_sensor_enabled(bool on) { g_forward_count = on; return g_forward_rc; }
int imu_sampler_set_odr_hz(uint32_t v) { g_forward_count = v; return g_forward_rc; }
int imu_sampler_set_accel_fsr(uint32_t v) { g_forward_count = v; return g_forward_rc; }
int imu_sampler_set_gyro_fsr(uint32_t v) { g_forward_count = v; return g_forward_rc; }
int imu_sampler_get_odr_idx(uint32_t *v) { *v = 7; return g_forward_rc; }
int imu_sampler_get_accel_fsr_idx(uint32_t *v) { *v = 2; return g_forward_rc; }
int imu_sampler_get_gyro_fsr_idx(uint32_t *v) { *v = 4; return g_forward_rc; }
int sensor_sampler_select_mode(uint8_t c, uint8_t m)
{ g_forward_class = c; g_forward_mode = m; return g_forward_rc; }
int sensor_sampler_send(uint8_t c, uint8_t m, const uint8_t *p, size_t n)
{ g_forward_class = c; g_forward_mode = m; g_forward_ptr = p; g_forward_count = n; return g_forward_rc; }
int sensor_sampler_set_pwm_with_port(uint8_t c, const int16_t *p, size_t n,
                                    uint8_t *port)
{
  g_forward_class = c;
  g_forward_ptr = p;
  g_forward_count = n;
  if (!g_forward_rc) *port = g_forward_port;
  return g_forward_rc;
}
void btsensor_modern_backend_set_motor_owner(enum brickwright_hub_link link,
                                             uint8_t port, bool running)
{ g_owner_link = link; g_forward_port = port; g_owner_running = running; }

static void reset(void)
{
  btsensor_nuttx_peripheral_stop();
  g_installed = NULL;
  g_imu_init_rc = g_sensor_init_rc = g_bundle_init_rc = 0;
  g_imu_init_calls = g_sensor_init_calls = g_bundle_init_calls = 0;
  g_imu_deinit_calls = g_sensor_deinit_calls = g_bundle_deinit_calls = 0;
  g_forward_rc = -EIO;
  g_forward_ptr = NULL;
  g_forward_count = 0;
  g_forward_class = g_forward_mode = 0;
  g_owner_link = BRICKWRIGHT_HUB_LINK_CLASSIC;
  g_owner_running = false;
}

static void test_lifecycle(void)
{
  reset();
  assert(btsensor_nuttx_peripheral_start() == 0 && g_installed != NULL);
  assert(g_imu_init_calls == 1 && g_sensor_init_calls == 1 && g_bundle_init_calls == 1);
  assert(btsensor_nuttx_peripheral_start() == 0 && g_imu_init_calls == 1);
  btsensor_nuttx_peripheral_stop();
  assert(g_installed == NULL);
  assert(g_bundle_deinit_calls == 1 && g_sensor_deinit_calls == 1 && g_imu_deinit_calls == 1);
  btsensor_nuttx_peripheral_stop();
  assert(g_bundle_deinit_calls == 1);
}

static void test_start_rollback(void)
{
  reset(); g_imu_init_rc = -ENODEV;
  assert(btsensor_nuttx_peripheral_start() == -ENODEV);
  assert(g_sensor_init_calls == 0 && g_imu_deinit_calls == 0);
  reset(); g_sensor_init_rc = -ENOMEM;
  assert(btsensor_nuttx_peripheral_start() == -ENOMEM);
  assert(g_imu_deinit_calls == 1 && g_sensor_deinit_calls == 0);
  reset(); g_bundle_init_rc = -EAGAIN;
  assert(btsensor_nuttx_peripheral_start() == -EAGAIN);
  assert(g_sensor_deinit_calls == 1 && g_imu_deinit_calls == 1 && g_installed == NULL);
}

static void test_forwarding_and_bounds(void)
{
  uint8_t payload[BTSENSOR_PERIPHERAL_PAYLOAD_MAX] = {0};
  int16_t pwm[4] = {0};
  uint32_t value = 0;
  reset();
  assert(btsensor_nuttx_peripheral_start() == 0);
  assert(g_installed->set_imu_odr_hz(NULL, 833) == -EIO && g_forward_count == 833);
  assert(g_installed->get_imu_odr_idx(NULL, &value) == -EIO && value == 7);
  assert(g_installed->sensor_send(NULL, BTSENSOR_PERIPHERAL_COLOR, 3,
                                  payload, sizeof(payload)) == -EIO);
  assert(g_forward_ptr == payload && g_forward_count == sizeof(payload));
  assert(g_forward_class == BTSENSOR_PERIPHERAL_COLOR && g_forward_mode == 3);
  assert(g_installed->sensor_send(NULL, BTSENSOR_PERIPHERAL_CLASS_COUNT, 0, payload, 1) == -EINVAL);
  assert(g_installed->sensor_send(NULL, 0, 0, NULL, 1) == -EINVAL);
  assert(g_installed->sensor_send(NULL, 0, 0, payload, sizeof(payload) + 1) == -EINVAL);
  assert(g_installed->sensor_set_pwm(NULL, BRICKWRIGHT_HUB_LINK_CLASSIC,
                                     BTSENSOR_PERIPHERAL_MOTOR_M, pwm, 4) == -EIO);
  assert(g_forward_ptr == pwm && g_forward_count == 4);
  assert(g_installed->sensor_set_pwm(NULL, BRICKWRIGHT_HUB_LINK_CLASSIC,
                                     0, NULL, 1) == -EINVAL);
  assert(g_installed->sensor_set_pwm(NULL, BRICKWRIGHT_HUB_LINK_CLASSIC,
                                     0, pwm, 5) == -EINVAL);
  assert(g_installed->sensor_set_pwm(NULL,
                                     (enum brickwright_hub_link)99,
                                     BTSENSOR_PERIPHERAL_MOTOR_L,
                                     pwm, 1) == -EINVAL);
  g_forward_rc = 0;
  pwm[0] = 2500;
  assert(g_installed->sensor_set_pwm(NULL, BRICKWRIGHT_HUB_LINK_CLASSIC,
                                     BTSENSOR_PERIPHERAL_MOTOR_L, pwm, 1) == 0);
  assert(g_owner_link == BRICKWRIGHT_HUB_LINK_CLASSIC &&
         g_forward_port == 3 && g_owner_running);
  pwm[0] = 0;
  assert(g_installed->sensor_set_pwm(NULL, BRICKWRIGHT_HUB_LINK_CLASSIC,
                                     BTSENSOR_PERIPHERAL_MOTOR_L, pwm, 1) == 0);
  assert(!g_owner_running);
  assert(g_installed->sensor_select_mode(NULL, BTSENSOR_PERIPHERAL_CLASS_COUNT, 0) == -EINVAL);
  assert(g_installed->imu_capture_start(NULL, 10) == -ENOTSUP);
  assert(g_installed->imu_capture_stop(NULL) == -ENOTSUP);
  btsensor_nuttx_peripheral_stop();
}

int main(void)
{
  test_lifecycle();
  test_start_rollback();
  test_forwarding_and_bounds();
  puts("btsensor NuttX peripheral backend tests passed");
  return 0;
}
