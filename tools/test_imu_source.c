/* SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Christian Strobele
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "imu_timestamp.h"
#include "imu_calibration.h"

static void timestamps(void)
{
  const uint64_t wrap = UINT64_C(1) << 32;
  uint64_t value = 99;
  assert(imu_timestamp_expand(123, 124, &value) && value == 123);
  assert(imu_timestamp_expand(UINT32_MAX - 10, wrap + 5, &value));
  assert(value == wrap - 11);
  assert(imu_timestamp_expand(0, wrap + 5, &value) && value == wrap);
  assert(imu_timestamp_expand(123, 2 * wrap + 200, &value));
  assert(value == 2 * wrap + 123);
  assert(imu_timestamp_expand(1, 30000001, &value) && value == 1);
  assert(!imu_timestamp_expand(1, 30000002, &value) && value == 0);
  assert(!imu_timestamp_expand(125, 124, &value) && value == 0);
  assert(!imu_timestamp_expand(201, 2 * wrap + 200, &value) && value == 0);
  assert(!imu_timestamp_expand(1, 2 * wrap + 30000002, &value) && value == 0);
  assert(!imu_timestamp_expand(1, 2, NULL));
}

static void calibration_copy(void)
{
  char path[] = "/tmp/brickwright-imu-calibration-XXXXXX";
  int fd = mkstemp(path);
  assert(fd >= 0 && close(fd) == 0);
  imu_settings_t defaults = {0}, learned = {0}, saved = {0};
  imu_calibration_set_defaults(&defaults);
  *imu_calibration_get_settings() = defaults;
  learned = defaults;
  learned.flags |= IMU_FLAG_GYRO_BIAS;
  learned.angular_velocity_bias_start.x = 1.25f;
  learned.angular_velocity_bias_start.y = -2.5f;
  learned.angular_velocity_bias_start.z = 3.75f;
  assert(imu_calibration_save_copy(path, &learned) == 0);
  assert(memcmp(imu_calibration_get_settings(), &defaults, sizeof(defaults)) == 0);
  fd = open(path, O_RDONLY);
  assert(fd >= 0 && read(fd, &saved, sizeof(saved)) == sizeof(saved));
  assert(close(fd) == 0 && memcmp(&saved, &learned, sizeof(saved)) == 0);
  assert(imu_calibration_load(path) == 0);
  assert(memcmp(imu_calibration_get_settings(), &learned, sizeof(learned)) == 0);
  assert(imu_calibration_save(path) == 0);
  errno = 0;
  assert(imu_calibration_save_copy(NULL, &learned) == -1 && errno == EINVAL);
  errno = 0;
  assert(imu_calibration_save_copy(path, NULL) == -1 && errno == EINVAL);
  assert(unlink(path) == 0);
}

int main(void)
{
  timestamps();
  calibration_copy();
  puts("IMU timestamp wrap/freshness and calibration persistence: PASS");
  return 0;
}
