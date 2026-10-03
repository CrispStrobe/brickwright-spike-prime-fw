/* SPDX-License-Identifier: Apache-2.0 */

#ifdef __NuttX__
#include <nuttx/config.h>
#endif
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "btsensor_nuttx_peripheral.h"
#include "btsensor_modern_backend.h"
#include "btsensor_peripheral.h"
#include "bundle_emitter.h"
#include "sensor_sampler.h"
#ifdef CONFIG_APP_IMU
#include "imu_service.h"
#endif

/* Keep this adapter independent of the board-only sensor_imu layout exposed
 * by imu_sampler.h; these control functions are its complete dependency. */
int imu_sampler_init(void);
void imu_sampler_deinit(void);
int imu_sampler_set_odr_hz(uint32_t hz);
int imu_sampler_set_accel_fsr(uint32_t g);
int imu_sampler_set_gyro_fsr(uint32_t dps);
int imu_sampler_get_odr_idx(uint32_t *out);
int imu_sampler_get_accel_fsr_idx(uint32_t *out);
int imu_sampler_get_gyro_fsr_idx(uint32_t *out);

#define BTSENSOR_PWM_CHANNELS_MAX 4

static bool g_started;

static int set_imu_enabled(void *context, bool on)
{
  (void)context;
  return bundle_emitter_set_imu_enabled(on);
}

static int set_sensor_enabled(void *context, bool on)
{
  (void)context;
  return bundle_emitter_set_sensor_enabled(on);
}

static int set_imu_odr_hz(void *context, uint32_t value)
{
  (void)context;
  return imu_sampler_set_odr_hz(value);
}

static int set_accel_fsr(void *context, uint32_t value)
{
  (void)context;
  return imu_sampler_set_accel_fsr(value);
}

static int set_gyro_fsr(void *context, uint32_t value)
{
  (void)context;
  return imu_sampler_set_gyro_fsr(value);
}

static int get_imu_odr_idx(void *context, uint32_t *value)
{
  (void)context;
  return imu_sampler_get_odr_idx(value);
}

static int get_accel_fsr_idx(void *context, uint32_t *value)
{
  (void)context;
  return imu_sampler_get_accel_fsr_idx(value);
}

static int get_gyro_fsr_idx(void *context, uint32_t *value)
{
  (void)context;
  return imu_sampler_get_gyro_fsr_idx(value);
}

static int sensor_select_mode(void *context, uint8_t class_id, uint8_t mode)
{
  (void)context;
  if (class_id >= BTSENSOR_PERIPHERAL_CLASS_COUNT)
    {
      return -EINVAL;
    }

  return sensor_sampler_select_mode(class_id, mode);
}

static int sensor_send(void *context, uint8_t class_id, uint8_t mode,
                       const uint8_t *data, size_t length)
{
  (void)context;
  if (class_id >= BTSENSOR_PERIPHERAL_CLASS_COUNT ||
      length > BTSENSOR_PERIPHERAL_PAYLOAD_MAX ||
      (length != 0 && data == NULL))
    {
      return -EINVAL;
    }

  return sensor_sampler_send(class_id, mode, data, length);
}

static int sensor_set_pwm(void *context, enum brickwright_hub_link link,
                          uint8_t class_id,
                          const int16_t *channels, size_t count)
{
  uint8_t port;
  (void)context;
  if ((unsigned)link > BRICKWRIGHT_HUB_LINK_BLE ||
      class_id >= BTSENSOR_PERIPHERAL_CLASS_COUNT ||
      count > BTSENSOR_PWM_CHANNELS_MAX ||
      (count != 0 && channels == NULL))
    {
      return -EINVAL;
    }

  int rc = sensor_sampler_set_pwm_with_port(class_id, channels, count, &port);
  if (rc == 0 && class_id >= BTSENSOR_PERIPHERAL_MOTOR_M)
    btsensor_modern_backend_set_motor_owner(link, port, channels[0] != 0);
  return rc;
}

static int imu_capture_unavailable_start(void *context, uint32_t duration_sec)
{
  (void)context;
  (void)duration_sec;
  return -ENOTSUP;
}

static int imu_capture_unavailable_stop(void *context)
{
  (void)context;
  return -ENOTSUP;
}

#ifdef CONFIG_APP_IMU
static int fusion_start(void *context)
{
  (void)context;
  return imu_service_start();
}

static int fusion_stop(void *context)
{
  (void)context;
  return imu_service_stop();
}

static int fusion_status(void *context, bool *starting, bool *running,
                         bool *stopping)
{
  (void)context;
  imu_service_status(starting, running, stopping);
  return 0;
}

static int fusion_set_base_axes(void *context, const imu_xyz_t *front,
                                const imu_xyz_t *top)
{
  (void)context;
  return imu_service_set_base_axes(front, top);
}

static int fusion_snapshot(void *context, imu_fusion_snapshot_t *out)
{
  (void)context;
  return imu_service_snapshot(out);
}
#endif

static const struct btsensor_peripheral_ops g_ops =
{
  .context = NULL,
  .set_imu_enabled = set_imu_enabled,
  .set_sensor_enabled = set_sensor_enabled,
  .set_imu_odr_hz = set_imu_odr_hz,
  .set_accel_fsr = set_accel_fsr,
  .set_gyro_fsr = set_gyro_fsr,
  .get_imu_odr_idx = get_imu_odr_idx,
  .get_accel_fsr_idx = get_accel_fsr_idx,
  .get_gyro_fsr_idx = get_gyro_fsr_idx,
  .sensor_select_mode = sensor_select_mode,
  .sensor_send = sensor_send,
  .sensor_set_pwm = sensor_set_pwm,
  .imu_capture_start = imu_capture_unavailable_start,
  .imu_capture_stop = imu_capture_unavailable_stop,
#ifdef CONFIG_APP_IMU
  .fusion_start = fusion_start,
  .fusion_stop = fusion_stop,
  .fusion_status = fusion_status,
  .fusion_snapshot = fusion_snapshot,
  .fusion_set_base_axes = fusion_set_base_axes,
#endif
};

int btsensor_nuttx_peripheral_start(void)
{
  int ret;

  if (g_started)
    {
      return 0;
    }

  ret = imu_sampler_init();
  if (ret < 0)
    {
      return ret;
    }

  ret = sensor_sampler_init();
  if (ret < 0)
    {
      imu_sampler_deinit();
      return ret;
    }

  ret = bundle_emitter_init();
  if (ret < 0)
    {
      sensor_sampler_deinit();
      imu_sampler_deinit();
      return ret;
    }

  btsensor_cmd_set_peripheral_ops(&g_ops);
  g_started = true;
  return 0;
}

void btsensor_nuttx_peripheral_stop(void)
{
  if (!g_started)
    {
      return;
    }

  btsensor_cmd_set_peripheral_ops(NULL);
#ifdef CONFIG_APP_IMU
  (void)imu_service_stop();
#endif
  bundle_emitter_deinit();
  sensor_sampler_deinit();
  imu_sampler_deinit();
  g_started = false;
}
