/*
 * Upstream source/reference notices retained conservatively; see
 * policy/pybricks-reuse.json and licenses/. No clean-room claim is made.
 * SPDX-License-Identifier: MIT
 * Copyright (c) 2022-2023 The Pybricks Authors
 * Copyright (c) 2026 Christian Strobele (atomic persistence and validation)
 */
/****************************************************************************
 * apps/imu/imu_calibration.c
 *
 * Calibration persistence for IMU processing.
 * Ported from pybricks (MIT License, Pybricks Authors).
 ****************************************************************************/

#include <fcntl.h>
#include <errno.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>

#include "imu_calibration.h"

/****************************************************************************
 * Private Data
 ****************************************************************************/

static imu_settings_t g_settings;

/****************************************************************************
 * Public Functions
 ****************************************************************************/

void imu_calibration_set_defaults(imu_settings_t *settings)
{
  settings->flags = 0;
  settings->gyro_stationary_threshold = 2.0f;
  settings->accel_stationary_threshold = 2500.0f;

  settings->gravity_pos.x = IMU_STANDARD_GRAVITY;
  settings->gravity_pos.y = IMU_STANDARD_GRAVITY;
  settings->gravity_pos.z = IMU_STANDARD_GRAVITY;

  settings->gravity_neg.x = -IMU_STANDARD_GRAVITY;
  settings->gravity_neg.y = -IMU_STANDARD_GRAVITY;
  settings->gravity_neg.z = -IMU_STANDARD_GRAVITY;

  settings->angular_velocity_bias_start.x = 0.0f;
  settings->angular_velocity_bias_start.y = 0.0f;
  settings->angular_velocity_bias_start.z = 0.0f;

  settings->angular_velocity_scale.x = 360.0f;
  settings->angular_velocity_scale.y = 360.0f;
  settings->angular_velocity_scale.z = 360.0f;

  settings->heading_correction_1d = 360.0f;
}

void imu_calibration_init(imu_settings_t *settings)
{
  imu_calibration_set_defaults(settings);
}

int imu_calibration_save(const char *path)
{
  return imu_calibration_save_copy(path, &g_settings);
}

/* Keep the existing native settings layout for compatibility. Atomic rename
 * protects the previous record from failed writes; it does not authenticate a
 * record or make arbitrary filesystem/power-loss guarantees. */
static bool settings_valid(const imu_settings_t *settings)
{
  unsigned int i;
  const uint32_t known_flags = IMU_FLAG_GYRO_THRESHOLD |
    IMU_FLAG_ACCEL_THRESHOLD | IMU_FLAG_GYRO_BIAS | IMU_FLAG_GYRO_SCALE |
    IMU_FLAG_ACCEL_CALIBRATED | IMU_FLAG_HEADING_1D;

  if (settings == NULL || (settings->flags & ~known_flags) != 0 ||
      !isfinite(settings->gyro_stationary_threshold) ||
      settings->gyro_stationary_threshold < 0.0f ||
      !isfinite(settings->accel_stationary_threshold) ||
      settings->accel_stationary_threshold < 0.0f ||
      !isfinite(settings->heading_correction_1d) ||
      fabsf(settings->heading_correction_1d) < 1.0e-6f)
    {
      return false;
    }

  for (i = 0; i < 3; i++)
    {
      float span = settings->gravity_pos.values[i] -
                   settings->gravity_neg.values[i];
      if (!isfinite(settings->gravity_pos.values[i]) ||
          !isfinite(settings->gravity_neg.values[i]) ||
          !isfinite(span) || fabsf(span) < 1.0e-6f ||
          !isfinite(settings->angular_velocity_bias_start.values[i]) ||
          !isfinite(settings->angular_velocity_scale.values[i]) ||
          fabsf(settings->angular_velocity_scale.values[i]) < 1.0e-6f)
        {
          return false;
        }
    }

  return true;
}

static int transfer_settings(int fd, void *buffer, size_t length, bool writing)
{
  unsigned char *bytes = buffer;
  while (length > 0)
    {
      ssize_t count = writing ? write(fd, bytes, length) :
                                read(fd, bytes, length);
      if (count < 0)
        {
          if (errno == EINTR)
            {
              continue;
            }
          return -1;
        }
      if (count == 0)
        {
          errno = writing ? EIO : EBADMSG;
          return -1;
        }
      bytes += count;
      length -= (size_t)count;
    }
  return 0;
}

int imu_calibration_save_copy(const char *path, const imu_settings_t *settings)
{
  char *temporary;
  imu_settings_t snapshot;
  int fd;
  int result;
  int saved_errno;
  size_t length;

  if (path == NULL || path[0] == '\0' || !settings_valid(settings))
    {
      errno = EINVAL;
      return -1;
    }

  snapshot = *settings;
  length = strlen(path);
  temporary = malloc(length + sizeof(".tmpXXXXXX"));
  if (temporary == NULL)
    {
      errno = ENOMEM;
      return -1;
    }
  memcpy(temporary, path, length);
  memcpy(temporary + length, ".tmpXXXXXX", sizeof(".tmpXXXXXX"));
  fd = mkstemp(temporary);
  if (fd < 0)
    {
      free(temporary);
      return -1;
    }

  result = transfer_settings(fd, &snapshot, sizeof(snapshot), true);
  if (result == 0)
    {
      result = fsync(fd);
    }
  saved_errno = errno;
  if (close(fd) < 0 && result == 0)
    {
      result = -1;
      saved_errno = errno;
    }
  if (result == 0 && rename(temporary, path) < 0)
    {
      result = -1;
      saved_errno = errno;
    }
  if (result < 0)
    {
      unlink(temporary);
    }
  free(temporary);
  if (result < 0)
    {
      errno = saved_errno;
    }
  return result;
}

int imu_calibration_load(const char *path)
{
  imu_settings_t temporary;
  unsigned char extra;
  int fd;
  int result;
  int saved_errno;
  ssize_t count;

  if (path == NULL || path[0] == '\0')
    {
      errno = EINVAL;
      return -1;
    }
  fd = open(path, O_RDONLY);
  if (fd < 0)
    {
      return -1;
    }
  result = transfer_settings(fd, &temporary, sizeof(temporary), false);
  if (result == 0)
    {
      do
        {
          count = read(fd, &extra, 1);
        }
      while (count < 0 && errno == EINTR);
      if (count != 0)
        {
          result = -1;
          if (count > 0)
            {
              errno = EBADMSG;
            }
        }
      else if (!settings_valid(&temporary))
        {
          result = -1;
          errno = EBADMSG;
        }
    }
  saved_errno = errno;
  if (close(fd) < 0 && result == 0)
    {
      result = -1;
      saved_errno = errno;
    }
  if (result == 0)
    {
      g_settings = temporary;
    }
  else
    {
      errno = saved_errno;
    }
  return result;
}

imu_settings_t *imu_calibration_get_settings(void)
{
  return &g_settings;
}
