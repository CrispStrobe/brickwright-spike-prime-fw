/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_PERIPHERAL_H
#define BTSENSOR_PERIPHERAL_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <brickwright/hub_transport.h>

enum btsensor_peripheral_class {
  BTSENSOR_PERIPHERAL_COLOR = 0,
  BTSENSOR_PERIPHERAL_ULTRASONIC,
  BTSENSOR_PERIPHERAL_FORCE,
  BTSENSOR_PERIPHERAL_MOTOR_M,
  BTSENSOR_PERIPHERAL_MOTOR_R,
  BTSENSOR_PERIPHERAL_MOTOR_L,
  BTSENSOR_PERIPHERAL_CLASS_COUNT
};

#define BTSENSOR_PERIPHERAL_PAYLOAD_MAX 32

/* Transport-neutral operations used by the legacy ASCII adapter. Backends
 * may use NuttX peripherals or simulated devices and return negated errno. */
struct btsensor_peripheral_ops {
  void *context;
  int (*set_imu_enabled)(void *, bool);
  int (*set_sensor_enabled)(void *, bool);
  int (*set_imu_odr_hz)(void *, uint32_t);
  int (*set_accel_fsr)(void *, uint32_t);
  int (*set_gyro_fsr)(void *, uint32_t);
  int (*get_imu_odr_idx)(void *, uint32_t *);
  int (*get_accel_fsr_idx)(void *, uint32_t *);
  int (*get_gyro_fsr_idx)(void *, uint32_t *);
  int (*sensor_select_mode)(void *, uint8_t, uint8_t);
  int (*sensor_send)(void *, uint8_t, uint8_t, const uint8_t *, size_t);
  int (*sensor_set_pwm)(void *, enum brickwright_hub_link, uint8_t,
                        const int16_t *, size_t);
  int (*imu_capture_start)(void *, uint32_t);
  int (*imu_capture_stop)(void *);
};

/* The backend object must remain valid until it is replaced or cleared. */
void btsensor_cmd_set_peripheral_ops(const struct btsensor_peripheral_ops *ops);
#endif
