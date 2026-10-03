/*
 * Upstream source/reference notices retained conservatively; see
 * policy/pybricks-reuse.json and licenses/. No clean-room claim is made.
 * SPDX-License-Identifier: MIT
 * Copyright (c) 2022-2023 The Pybricks Authors
 */
/****************************************************************************
 * apps/imu/imu_fusion.c
 *
 * Sensor fusion for IMU processing.
 * Ported from pybricks imu.c (MIT License, Pybricks Authors).
 ****************************************************************************/

#include <math.h>
#include <pthread.h>
#include <string.h>
#include <time.h>

#include "imu_fusion.h"
#include "imu_geometry.h"
#include "imu_stationary.h"

/****************************************************************************
 * Private Data
 ****************************************************************************/

/* Quaternion - rotation of hub w.r.t. inertial frame */

static imu_quaternion_t g_quaternion =
{
  .q1 = 0.0f, .q2 = 0.0f, .q3 = 0.0f, .q4 = 1.0f,
};

static bool g_quaternion_init = false;

/* Rotation matrix from quaternion */

static imu_matrix_3x3_t g_rotation =
{
  .m11 = 1.0f, .m12 = 0.0f, .m13 = 0.0f,
  .m21 = 0.0f, .m22 = 1.0f, .m23 = 0.0f,
  .m31 = 0.0f, .m32 = 0.0f, .m33 = 1.0f,
};

/* Base orientation (identity = hub flat) */

static imu_matrix_3x3_t g_base_orientation =
{
  .m11 = 1.0f, .m12 = 0.0f, .m13 = 0.0f,
  .m21 = 0.0f, .m22 = 1.0f, .m23 = 0.0f,
  .m31 = 0.0f, .m32 = 0.0f, .m33 = 1.0f,
};

/* Cached velocity / acceleration in hub frame */

static imu_xyz_t g_angvel_uncal;
static imu_xyz_t g_angvel_cal;
static imu_xyz_t g_accel_uncal;
static imu_xyz_t g_accel_cal;

/* 1D integrated rotation per axis */

static imu_xyz_t g_single_axis_rotation;

/* Heading */

static float g_heading_projection;
static int32_t g_heading_rotations;
static float g_heading_offset_1d;
static float g_heading_offset_3d;

/* Gyro bias */

static imu_xyz_t g_gyro_bias;

/* Settings */

static imu_settings_t g_settings_copy;
static imu_settings_t *g_settings;

/* Serialize publication and all legacy access to the fusion state. */

static pthread_mutex_t g_fusion_lock = PTHREAD_MUTEX_INITIALIZER;
static uint64_t g_timestamp_us;
static uint64_t g_sequence;
static bool g_sample_valid;

/* Stationary readiness */

static uint32_t g_stationary_counter;
static uint32_t g_stationary_time_last;

/****************************************************************************
 * Private Functions
 ****************************************************************************/

static float imu_fusion_get_heading_unlocked(imu_heading_type_t type);
static void imu_fusion_set_heading_unlocked(float desired);
static bool imu_fusion_is_ready_unlocked(void);

static uint32_t get_time_ms(void)
{
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint32_t)((uint64_t)ts.tv_sec * 1000U +
                    (uint32_t)ts.tv_nsec / 1000000U);
}

static void update_heading_projection(void)
{
  /* Transform application x axis back into hub frame (R_base^T * x) */

  imu_xyz_t x_app =
  {
    .x = g_base_orientation.m11,
    .y = g_base_orientation.m12,
    .z = g_base_orientation.m13,
  };

  /* Transform into inertial frame */

  imu_xyz_t x_inertial;
  imu_vector_map(&g_rotation, &x_app, &x_inertial);

  /* Project onto horizontal plane */

  float heading_now = atan2f(-x_inertial.y, x_inertial.x) * IMU_RAD_TO_DEG;

  /* Track full rotations across 180/-180 boundary */

  if (heading_now < -90.0f && g_heading_projection > 90.0f)
    {
      g_heading_rotations++;
    }
  else if (heading_now > 90.0f && g_heading_projection < -90.0f)
    {
      g_heading_rotations--;
    }

  g_heading_projection = heading_now;
}

/****************************************************************************
 * Public Functions
 ****************************************************************************/

static void imu_fusion_init_unlocked(void)
{
  g_quaternion.q1 = 0.0f;
  g_quaternion.q2 = 0.0f;
  g_quaternion.q3 = 0.0f;
  g_quaternion.q4 = 1.0f;
  g_quaternion_init = false;

  g_rotation.m11 = 1.0f; g_rotation.m12 = 0.0f; g_rotation.m13 = 0.0f;
  g_rotation.m21 = 0.0f; g_rotation.m22 = 1.0f; g_rotation.m23 = 0.0f;
  g_rotation.m31 = 0.0f; g_rotation.m32 = 0.0f; g_rotation.m33 = 1.0f;

  g_base_orientation.m11 = 1.0f; g_base_orientation.m12 = 0.0f;
  g_base_orientation.m13 = 0.0f;
  g_base_orientation.m21 = 0.0f; g_base_orientation.m22 = 1.0f;
  g_base_orientation.m23 = 0.0f;
  g_base_orientation.m31 = 0.0f; g_base_orientation.m32 = 0.0f;
  g_base_orientation.m33 = 1.0f;

  memset(&g_angvel_uncal, 0, sizeof(g_angvel_uncal));
  memset(&g_angvel_cal, 0, sizeof(g_angvel_cal));
  memset(&g_accel_uncal, 0, sizeof(g_accel_uncal));
  memset(&g_accel_cal, 0, sizeof(g_accel_cal));
  memset(&g_single_axis_rotation, 0, sizeof(g_single_axis_rotation));
  memset(&g_gyro_bias, 0, sizeof(g_gyro_bias));

  g_heading_projection = 0.0f;
  g_heading_rotations = 0;
  g_heading_offset_1d = 0.0f;
  g_heading_offset_3d = 0.0f;

  g_settings = NULL;
  g_timestamp_us = 0;
  g_sequence = 0;
  g_sample_valid = false;
  g_stationary_counter = 0;
  g_stationary_time_last = 0;
}

static void imu_fusion_set_settings_unlocked(imu_settings_t *settings)
{
  g_sample_valid = false;
  if (settings == NULL)
    {
      g_settings = NULL;
      memset(&g_gyro_bias, 0, sizeof(g_gyro_bias));
      return;
    }

  g_settings_copy = *settings;
  g_settings = &g_settings_copy;
  settings = g_settings;

  /* Load initial gyro bias from saved settings */

  g_gyro_bias.x = settings->angular_velocity_bias_start.x;
  g_gyro_bias.y = settings->angular_velocity_bias_start.y;
  g_gyro_bias.z = settings->angular_velocity_bias_start.z;
}

static void imu_fusion_set_base_orientation_unlocked(imu_xyz_t *front, imu_xyz_t *top)
{
  imu_matrix_3x3_t base;
  unsigned int i;
  if (front == NULL || top == NULL ||
      imu_map_from_base_axes(front, top, &base) < 0)
    {
      return;
    }

  for (i = 0; i < 9; i++)
    {
      if (!isfinite(base.values[i]))
        {
          return;
        }
    }

  /* The geometry helper returns the declared basis columns in physical hub
   * coordinates. Report components along those axes using its transpose. */

  g_base_orientation = (imu_matrix_3x3_t)
  {
    .m11 = base.m11, .m12 = base.m21, .m13 = base.m31,
    .m21 = base.m12, .m22 = base.m22, .m23 = base.m32,
    .m31 = base.m13, .m32 = base.m23, .m33 = base.m33,
  };
  update_heading_projection();
  imu_fusion_set_heading_unlocked(0.0f);
}

static void imu_fusion_update_unlocked(imu_xyz_t *gyro_dps, imu_xyz_t *accel_mms2,
                       float sample_time)
{
  uint8_t i;

  /* Initialize quaternion from first valid gravity sample */

  if (!g_quaternion_init)
    {
      imu_xyz_t g_norm;
      if (imu_vector_normalize(accel_mms2, &g_norm) == 0)
        {
          imu_quaternion_from_gravity(&g_norm, &g_quaternion);
          g_quaternion_init = true;
        }
      else
        {
          return;
        }
    }

  /* Update rotation matrix from quaternion */

  imu_quaternion_to_rotation_matrix(&g_quaternion, &g_rotation);



  /* Cache uncalibrated values */

  g_angvel_uncal = *gyro_dps;
  g_accel_uncal = *accel_mms2;

  /* Compute calibrated values */

  for (i = 0; i < 3; i++)
    {
      if (g_settings)
        {
          float accel_offset =
            (g_settings->gravity_pos.values[i] +
             g_settings->gravity_neg.values[i]) / 2.0f;
          float accel_scale =
            (g_settings->gravity_pos.values[i] -
             g_settings->gravity_neg.values[i]) / 2.0f;

          g_accel_cal.values[i] =
            (g_accel_uncal.values[i] - accel_offset) *
            IMU_STANDARD_GRAVITY / accel_scale;

          g_angvel_cal.values[i] =
            (g_angvel_uncal.values[i] - g_gyro_bias.values[i]) *
            360.0f / g_settings->angular_velocity_scale.values[i];
        }
      else
        {
          g_accel_cal.values[i] = g_accel_uncal.values[i];
          g_angvel_cal.values[i] = g_angvel_uncal.values[i];
        }

      /* Integrate single axis rotation */

      g_single_axis_rotation.values[i] +=
        g_angvel_cal.values[i] * sample_time;
    }

  /* Gravity estimate from rotation matrix row 3 */

  imu_xyz_t s =
  {
    .x = g_rotation.m31,
    .y = g_rotation.m32,
    .z = g_rotation.m33,
  };

  /* Cross product correction (complementary filter) */

  imu_xyz_t correction;
  imu_vector_cross(&s, &g_accel_cal, &correction);

  /* Stationary measure for fusion blending */

  float accel_err =
    imu_absf(imu_vector_norm(&g_accel_cal) - IMU_STANDARD_GRAVITY);
  float gyro_err = imu_absf(imu_vector_norm(&g_angvel_cal));

  const float gyro_min = 10.0f;
  const float accel_min = 150.0f;

  float stat_measure =
    accel_min / imu_maxf(accel_err, accel_min) *
    gyro_min / imu_maxf(gyro_err, gyro_min);

  /* Fusion correction strength */

  float fusion = -stat_measure / IMU_STANDARD_GRAVITY * 200.0f;

  imu_xyz_t adj_angvel;
  adj_angvel.x = g_angvel_cal.x + correction.x * fusion;
  adj_angvel.y = g_angvel_cal.y + correction.y * fusion;
  adj_angvel.z = g_angvel_cal.z + correction.z * fusion;

  /* Quaternion integration */

  imu_quaternion_t dq;
  imu_quaternion_get_rate_of_change(&g_quaternion, &adj_angvel, &dq);

  for (i = 0; i < 4; i++)
    {
      g_quaternion.values[i] += dq.values[i] * sample_time;
    }

  imu_quaternion_normalize(&g_quaternion);

  /* Publish the orientation after integrating this sample, not the previous
   * sample's matrix.  Heading and acceleration now belong to one step.
   */

  imu_quaternion_to_rotation_matrix(&g_quaternion, &g_rotation);
  update_heading_projection();
}

static void imu_fusion_stationary_update_unlocked(const int32_t *gyro_sum,
                                  const int32_t *accel_sum,
                                  uint32_t num_samples,
                                  float gyro_scale)
{
  uint8_t i;

  (void)accel_sum;
  if (gyro_sum == NULL || num_samples == 0 || !isfinite(gyro_scale) ||
      !imu_stationary_is_stationary())
    {
      return;
    }

  /* Reset counter if not recently stationary */

  if (!imu_fusion_is_ready_unlocked())
    {
      g_stationary_counter = 0;
    }

  g_stationary_time_last = get_time_ms();
  g_stationary_counter++;

  /* Exponential smoothing weight */

  float weight = g_stationary_counter >= 20 ?
    0.05f : 1.0f / g_stationary_counter;

  for (i = 0; i < 3; i++)
    {
      /* Average gyro rate while stationary */

      float avg_now = gyro_sum[i] * gyro_scale / num_samples;

      /* Update bias with decreasing rate */

      g_gyro_bias.values[i] =
        g_gyro_bias.values[i] * (1.0f - weight) + weight * avg_now;
    }

  /* Save initial bias to settings if never saved */

  if (g_settings &&
      !(g_settings->flags & IMU_FLAG_GYRO_BIAS) &&
      g_stationary_counter > 2)
    {
      g_settings->angular_velocity_bias_start = g_gyro_bias;
      g_settings->flags |= IMU_FLAG_GYRO_BIAS;
    }
}

static void imu_fusion_get_accel_unlocked(imu_xyz_t *out, bool calibrated)
{
  imu_xyz_t *src = calibrated ? &g_accel_cal : &g_accel_uncal;
  imu_vector_map(&g_base_orientation, src, out);
}

static void imu_fusion_get_gyro_unlocked(imu_xyz_t *out, bool calibrated)
{
  imu_xyz_t *src = calibrated ? &g_angvel_cal : &g_angvel_uncal;
  imu_vector_map(&g_base_orientation, src, out);
}

static void imu_fusion_get_tilt_unlocked(imu_xyz_t *out)
{
  imu_xyz_t direction =
  {
    .x = g_rotation.m31,
    .y = g_rotation.m32,
    .z = g_rotation.m33,
  };

  imu_vector_map(&g_base_orientation, &direction, out);
}

static imu_side_t imu_fusion_get_up_side_unlocked(bool calibrated)
{
  imu_xyz_t up;

  if (calibrated)
    {
      up.x = g_rotation.m31;
      up.y = g_rotation.m32;
      up.z = g_rotation.m33;
    }
  else
    {
      up = g_accel_uncal;
    }

  return imu_side_from_vector(&up);
}

static int imu_fusion_get_single_axis_rotation_unlocked(imu_xyz_t *axis, float *angle,
                                        bool calibrated)
{
  imu_xyz_t axis_rot = g_single_axis_rotation;

  if (!calibrated && g_settings)
    {
      uint8_t i;

      for (i = 0; i < 3; i++)
        {
          axis_rot.values[i] *=
            g_settings->angular_velocity_scale.values[i] / 360.0f;
        }
    }

  imu_xyz_t rot_user;
  imu_vector_map(&g_base_orientation, &axis_rot, &rot_user);

  return imu_vector_project(axis, &rot_user, angle);
}

static float imu_fusion_get_heading_unlocked(imu_heading_type_t type)
{
  float correction = 1.0f;

  if (g_settings && (g_settings->flags & IMU_FLAG_HEADING_1D))
    {
      correction = 360.0f / g_settings->heading_correction_1d;
    }

  if (type == IMU_HEADING_3D)
    {
      return (g_heading_rotations * 360.0f + g_heading_projection) *
        correction - g_heading_offset_3d;
    }

  /* 1D heading: map per-axis rotation to user frame, take -z */

  imu_xyz_t heading_mapped;
  imu_vector_map(&g_base_orientation, &g_single_axis_rotation,
                 &heading_mapped);

  return -heading_mapped.z * correction - g_heading_offset_1d;
}

static void imu_fusion_set_heading_unlocked(float desired)
{
  if (!isfinite(desired))
    {
      return;
    }

  g_heading_rotations = 0;
  g_heading_offset_3d =
    imu_fusion_get_heading_unlocked(IMU_HEADING_3D) +
    g_heading_offset_3d - desired;
  g_heading_offset_1d =
    imu_fusion_get_heading_unlocked(IMU_HEADING_1D) +
    g_heading_offset_1d - desired;
}

static void imu_fusion_get_orientation_unlocked(imu_matrix_3x3_t *out)
{
  *out = g_rotation;
}

static bool imu_fusion_is_ready_unlocked(void)
{
  return g_stationary_counter > 0 &&
         get_time_ms() - g_stationary_time_last < 10u * 60u * 1000u;
}

/****************************************************************************
 * Synchronized Public Interface
 ****************************************************************************/

static bool finite_vector(const imu_xyz_t *v)
{
  return v != NULL && isfinite(v->x) && isfinite(v->y) && isfinite(v->z);
}

static bool calibration_valid(void)
{
  unsigned int i;
  if (g_settings == NULL)
    {
      return true;
    }

  for (i = 0; i < 3; i++)
    {
      float span = g_settings->gravity_pos.values[i] -
                   g_settings->gravity_neg.values[i];
      if (!isfinite(span) || fabsf(span) < 1.0e-6f ||
          !isfinite(g_settings->angular_velocity_scale.values[i]) ||
          fabsf(g_settings->angular_velocity_scale.values[i]) < 1.0e-6f ||
          !isfinite(g_gyro_bias.values[i]))
        {
          return false;
        }
    }

  return !(g_settings->flags & IMU_FLAG_HEADING_1D) ||
         (isfinite(g_settings->heading_correction_1d) &&
          fabsf(g_settings->heading_correction_1d) >= 1.0e-6f);
}

bool imu_fusion_update_timestamped(const imu_xyz_t *gyro_dps,
                                 const imu_xyz_t *accel_mms2,
                                 float sample_time, uint64_t timestamp_us)
{
  unsigned int i;
  bool valid;
  pthread_mutex_lock(&g_fusion_lock);
  g_sample_valid = false;
  valid = finite_vector(gyro_dps) && finite_vector(accel_mms2) &&
          isfinite(sample_time) && sample_time > 0.0f &&
          timestamp_us != 0 && timestamp_us > g_timestamp_us &&
          calibration_valid();
  if (valid)
    {
      imu_quaternion_t quaternion = g_quaternion;
      imu_matrix_3x3_t rotation = g_rotation;
      imu_xyz_t single_axis = g_single_axis_rotation;
      imu_xyz_t angvel_uncal = g_angvel_uncal;
      imu_xyz_t angvel_cal = g_angvel_cal;
      imu_xyz_t accel_uncal = g_accel_uncal;
      imu_xyz_t accel_cal = g_accel_cal;
      float heading_projection = g_heading_projection;
      int32_t heading_rotations = g_heading_rotations;
      bool quaternion_init = g_quaternion_init;
      imu_xyz_t gyro = *gyro_dps;
      imu_xyz_t accel = *accel_mms2;
      imu_fusion_update_unlocked(&gyro, &accel, sample_time);
      float quaternion_norm_squared =
        g_quaternion.q1 * g_quaternion.q1 +
        g_quaternion.q2 * g_quaternion.q2 +
        g_quaternion.q3 * g_quaternion.q3 +
        g_quaternion.q4 * g_quaternion.q4;
      valid = g_quaternion_init && finite_vector(&g_angvel_cal) &&
              finite_vector(&g_accel_cal) &&
              isfinite(quaternion_norm_squared) &&
              fabsf(quaternion_norm_squared - 1.0f) < 0.001f;
      for (i = 0; i < 9 && valid; i++)
        {
          valid = isfinite(g_rotation.values[i]);
        }

      valid = valid && isfinite(imu_fusion_get_heading_unlocked(IMU_HEADING_1D)) &&
              isfinite(imu_fusion_get_heading_unlocked(IMU_HEADING_3D));
      if (valid)
        {
          g_timestamp_us = timestamp_us;
          g_sequence++;
          g_sample_valid = true;
        }
      else
        {
          /* Failed arithmetic must not poison the next valid step. */
          g_quaternion = quaternion;
          g_rotation = rotation;
          g_single_axis_rotation = single_axis;
          g_angvel_uncal = angvel_uncal;
          g_angvel_cal = angvel_cal;
          g_accel_uncal = accel_uncal;
          g_accel_cal = accel_cal;
          g_heading_projection = heading_projection;
          g_heading_rotations = heading_rotations;
          g_quaternion_init = quaternion_init;
        }
    }

  pthread_mutex_unlock(&g_fusion_lock);
  return valid;
}

bool imu_fusion_get_snapshot(imu_fusion_snapshot_t *out, uint64_t now_us,
                             uint64_t max_age_us)
{
  bool valid;
  if (out == NULL)
    {
      return false;
    }

  pthread_mutex_lock(&g_fusion_lock);
  memset(out, 0, sizeof(*out));
  valid = g_sample_valid && now_us >= g_timestamp_us &&
          now_us - g_timestamp_us <= max_age_us;
  if (valid)
    {
      out->timestamp_us = g_timestamp_us;
      out->sequence = g_sequence;
      out->valid = true;
      out->ready = imu_fusion_is_ready_unlocked();
      imu_fusion_get_accel_unlocked(&out->accel_mms2, true);
      imu_fusion_get_gyro_unlocked(&out->gyro_dps, true);
      imu_fusion_get_orientation_unlocked(&out->orientation);
      out->heading_1d = imu_fusion_get_heading_unlocked(IMU_HEADING_1D);
      out->heading_3d = imu_fusion_get_heading_unlocked(IMU_HEADING_3D);
      out->up_side = imu_fusion_get_up_side_unlocked(true);
    }

  pthread_mutex_unlock(&g_fusion_lock);
  return valid;
}

void imu_fusion_update(imu_xyz_t *gyro_dps, imu_xyz_t *accel_mms2,
                       float sample_time)
{
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0)
    {
      imu_fusion_update_timestamped(gyro_dps, accel_mms2, sample_time,
        (uint64_t)ts.tv_sec * 1000000U + (uint64_t)ts.tv_nsec / 1000U);
    }
}

void imu_fusion_init(void)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_init_unlocked();
  pthread_mutex_unlock(&g_fusion_lock);
}

void imu_fusion_set_settings(imu_settings_t *settings)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_set_settings_unlocked(settings);
  pthread_mutex_unlock(&g_fusion_lock);
}

bool imu_fusion_get_settings(imu_settings_t *out)
{
  bool available;
  if (out == NULL)
    {
      return false;
    }

  pthread_mutex_lock(&g_fusion_lock);
  available = g_settings != NULL;
  if (available)
    {
      *out = *g_settings;
    }
  else
    {
      memset(out, 0, sizeof(*out));
    }

  pthread_mutex_unlock(&g_fusion_lock);
  return available;
}

void imu_fusion_set_base_orientation(imu_xyz_t *front, imu_xyz_t *top)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_set_base_orientation_unlocked(front, top);
  pthread_mutex_unlock(&g_fusion_lock);
}

void imu_fusion_stationary_update(const int32_t *gyro_sum,
                                  const int32_t *accel_sum,
                                  uint32_t num_samples,
                                  float gyro_scale)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_stationary_update_unlocked(gyro_sum, accel_sum, num_samples, gyro_scale);
  pthread_mutex_unlock(&g_fusion_lock);
}

void imu_fusion_get_accel(imu_xyz_t *out, bool calibrated)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_get_accel_unlocked(out, calibrated);
  pthread_mutex_unlock(&g_fusion_lock);
}

void imu_fusion_get_gyro(imu_xyz_t *out, bool calibrated)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_get_gyro_unlocked(out, calibrated);
  pthread_mutex_unlock(&g_fusion_lock);
}

void imu_fusion_get_tilt(imu_xyz_t *out)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_get_tilt_unlocked(out);
  pthread_mutex_unlock(&g_fusion_lock);
}

imu_side_t imu_fusion_get_up_side(bool calibrated)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_side_t result = imu_fusion_get_up_side_unlocked(calibrated);
  pthread_mutex_unlock(&g_fusion_lock);
  return result;
}

int imu_fusion_get_single_axis_rotation(imu_xyz_t *axis, float *angle,
                                        bool calibrated)
{
  pthread_mutex_lock(&g_fusion_lock);
  int result = imu_fusion_get_single_axis_rotation_unlocked(axis, angle, calibrated);
  pthread_mutex_unlock(&g_fusion_lock);
  return result;
}

float imu_fusion_get_heading(imu_heading_type_t type)
{
  pthread_mutex_lock(&g_fusion_lock);
  float result = imu_fusion_get_heading_unlocked(type);
  pthread_mutex_unlock(&g_fusion_lock);
  return result;
}

void imu_fusion_set_heading(float desired)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_set_heading_unlocked(desired);
  pthread_mutex_unlock(&g_fusion_lock);
}

void imu_fusion_get_orientation(imu_matrix_3x3_t *out)
{
  pthread_mutex_lock(&g_fusion_lock);
  imu_fusion_get_orientation_unlocked(out);
  pthread_mutex_unlock(&g_fusion_lock);
}

bool imu_fusion_is_ready(void)
{
  pthread_mutex_lock(&g_fusion_lock);
  bool result = imu_fusion_is_ready_unlocked();
  pthread_mutex_unlock(&g_fusion_lock);
  return result;
}
