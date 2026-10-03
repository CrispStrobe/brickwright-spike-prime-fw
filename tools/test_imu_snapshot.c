/* SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Christian Strobele
 * Synthetic host checks for the licensed IMU fusion implementation.
 */
#include <assert.h>
#include <float.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "imu_fusion.h"

static bool stationary;
static atomic_bool writer_done;

bool imu_stationary_is_stationary(void)
{
  return stationary;
}

static bool near(float a, float b)
{
  return fabsf(a - b) < 0.01f;
}

static imu_settings_t settings(void)
{
  imu_settings_t s = {0};
  for (int i = 0; i < 3; i++)
    {
      s.gravity_pos.values[i] = IMU_STANDARD_GRAVITY;
      s.gravity_neg.values[i] = -IMU_STANDARD_GRAVITY;
      s.angular_velocity_scale.values[i] = 360.0f;
    }
  s.heading_correction_1d = 360.0f;
  return s;
}

static void validity_and_recovery(void)
{
  imu_fusion_snapshot_t snap;
  imu_xyz_t gyro = {.z = 90};
  imu_xyz_t accel = {.z = IMU_STANDARD_GRAVITY};
  imu_xyz_t zero = {0};
  imu_fusion_init();
  memset(&snap, 0xff, sizeof(snap));
  assert(!imu_fusion_get_snapshot(&snap, 100, 10));
  assert(!snap.valid && snap.timestamp_us == 0 && snap.sequence == 0);
  assert(!imu_fusion_update_timestamped(&gyro, &zero, .01f, 100));
  assert(!imu_fusion_update_timestamped(&gyro, &accel, .01f, 0));
  assert(imu_fusion_update_timestamped(&gyro, &accel, .01f, 100));
  assert(imu_fusion_get_snapshot(&snap, 110, 10));
  assert(snap.valid && !snap.ready && snap.sequence == 1);
  assert(near(snap.gyro_dps.z, 90));
  assert(near(snap.accel_mms2.z, IMU_STANDARD_GRAVITY));
  assert(near(snap.heading_1d, -.9f));
  /* Same-step orientation must already include this sample's rotation. */
  assert(fabsf(snap.orientation.m12) > .01f);
  assert(snap.up_side == IMU_SIDE_TOP);
  imu_fusion_snapshot_t again;
  assert(imu_fusion_get_snapshot(&again, 110, 10));
  assert(memcmp(&snap, &again, sizeof(snap)) == 0);
  assert(!imu_fusion_get_snapshot(&again, 99, 100));
  assert(!imu_fusion_get_snapshot(&again, 111, 10));
  assert(imu_fusion_get_snapshot(&again, 110, 10));
  assert(!imu_fusion_update_timestamped(&gyro, &accel, .01f, 100));
  assert(!imu_fusion_get_snapshot(&again, 110, 10));
  gyro.x = NAN;
  assert(!imu_fusion_update_timestamped(&gyro, &accel, .01f, 101));
  gyro.x = 0;
  assert(!imu_fusion_update_timestamped(&gyro, &accel, INFINITY, 101));
  assert(!imu_fusion_update_timestamped(&gyro, &accel, 0, 101));
  assert(!imu_fusion_update_timestamped(&gyro, &accel, -.01f, 101));
  gyro.x = FLT_MAX;
  assert(!imu_fusion_update_timestamped(&gyro, &accel, FLT_MAX, 101));
  gyro.x = 0;
  assert(imu_fusion_update_timestamped(&gyro, &accel, .01f, 101));
  assert(imu_fusion_get_snapshot(&snap, 101, 0) && snap.sequence == 2);
  assert(isfinite(snap.heading_1d) && isfinite(snap.orientation.m11));
  imu_fusion_init();
  assert(!imu_fusion_get_snapshot(&snap, 101, 100));
  assert(imu_fusion_update_timestamped(&gyro, &accel, .01f, 1));
  assert(imu_fusion_get_snapshot(&snap, 1, 0) && snap.sequence == 1);
  assert(!imu_fusion_get_snapshot(NULL, 1, 0));
}

static void calibration_base_heading(void)
{
  imu_settings_t s = settings();
  imu_xyz_t gyro = {.x = 10, .z = 20};
  imu_xyz_t accel = {.z = IMU_STANDARD_GRAVITY};
  imu_fusion_snapshot_t snap;
  imu_fusion_init();
  s.angular_velocity_bias_start.x = 2;
  s.angular_velocity_scale.x = 180;
  imu_fusion_set_settings(&s);
  s.angular_velocity_scale.x = 0; /* No retained mutable caller pointer. */
  assert(imu_fusion_update_timestamped(&gyro, &accel, .01f, 1));
  assert(imu_fusion_get_snapshot(&snap, 1, 0));
  assert(near(snap.gyro_dps.x, 16));
  imu_xyz_t legacy;
  imu_fusion_get_gyro(&legacy, true);
  assert(near(legacy.x, snap.gyro_dps.x));
  imu_fusion_get_gyro(&legacy, false);
  assert(near(legacy.x, 10));
  imu_xyz_t axis = {.x = 1};
  float angle;
  assert(imu_fusion_get_single_axis_rotation(&axis, &angle, true) == 0);
  assert(near(angle, .16f));
  assert(imu_fusion_get_single_axis_rotation(&axis, &angle, false) == 0);
  assert(near(angle, .08f));
  imu_fusion_set_heading(42);
  assert(near(imu_fusion_get_heading(IMU_HEADING_1D), 42));
  assert(near(imu_fusion_get_heading(IMU_HEADING_3D), 42));
  imu_fusion_set_heading(NAN);
  assert(near(imu_fusion_get_heading(IMU_HEADING_1D), 42));
  imu_xyz_t front = {.y = 1}, top = {.z = 1};
  imu_fusion_set_base_orientation(&front, &top);
  assert(near(imu_fusion_get_heading(IMU_HEADING_1D), 0));
  assert(imu_fusion_get_snapshot(&snap, 1, 0));
  imu_fusion_get_gyro(&legacy, true);
  assert(near(legacy.x, snap.gyro_dps.x));
  assert(near(snap.gyro_dps.y, 16));
  imu_fusion_get_tilt(&legacy);
  assert(isfinite(legacy.x));
  int32_t sum[3] = {0};
  stationary = true;
  imu_fusion_stationary_update(sum, sum, 0, 1); /* No divide by zero. */
  assert(!imu_fusion_is_ready());
  imu_fusion_stationary_update(sum, sum, 10, 1);
  assert(imu_fusion_is_ready());
  imu_fusion_stationary_update(sum, sum, 10, 1);
  imu_fusion_stationary_update(sum, sum, 10, 1);
  imu_settings_t saved;
  assert(imu_fusion_get_settings(&saved));
  assert(saved.flags & IMU_FLAG_GYRO_BIAS);
  assert(near(saved.angular_velocity_bias_start.x, 0));
  assert(!(s.flags & IMU_FLAG_GYRO_BIAS));
  assert(imu_fusion_get_snapshot(&snap, 1, 0) && snap.ready);
  stationary = false;
  s = settings();
  s.angular_velocity_scale.x = 0;
  imu_fusion_set_settings(&s);
  assert(!imu_fusion_get_snapshot(&snap, 1, 0));
  assert(!imu_fusion_update_timestamped(&gyro, &accel, .01f, 2));
  s = settings();
  imu_fusion_set_settings(&s);
  assert(imu_fusion_update_timestamped(&gyro, &accel, .01f, 2));
  imu_fusion_set_settings(NULL);
  assert(!imu_fusion_get_snapshot(&snap, 2, 0));
  assert(!imu_fusion_get_settings(&saved));
  assert(saved.flags == 0);
  assert(!imu_fusion_get_settings(NULL));
}

static void *writer(void *arg)
{
  (void)arg;
  for (uint64_t n = 1; n <= 20000; n++)
    {
      imu_xyz_t gyro = {.x = (float)n};
      imu_xyz_t accel = {.x = 2.0f * n, .z = IMU_STANDARD_GRAVITY};
      assert(imu_fusion_update_timestamped(&gyro, &accel, 1e-6f, n));
    }
  atomic_store(&writer_done, true);
  return NULL;
}

static void *reader(void *arg)
{
  (void)arg;
  uint64_t last = 0;
  do
    {
      imu_fusion_snapshot_t snap;
      if (imu_fusion_get_snapshot(&snap, UINT64_MAX, UINT64_MAX))
        {
          assert(snap.valid && snap.sequence >= last);
          assert(snap.sequence == snap.timestamp_us);
          assert(snap.gyro_dps.x == (float)snap.timestamp_us);
          assert(snap.accel_mms2.x == 2.0f * snap.gyro_dps.x);
          assert(isfinite(snap.heading_1d));
          for (int i = 0; i < 9; i++)
            {
              assert(isfinite(snap.orientation.values[i]));
            }
          last = snap.sequence;
        }
    }
  while (!atomic_load(&writer_done));
  return NULL;
}

int main(void)
{
  validity_and_recovery();
  calibration_base_heading();
  imu_fusion_init();
  pthread_t threads[4];
  atomic_init(&writer_done, false);
  for (int i = 0; i < 3; i++)
    {
      assert(pthread_create(&threads[i], NULL, reader, NULL) == 0);
    }
  assert(pthread_create(&threads[3], NULL, writer, NULL) == 0);
  for (int i = 0; i < 4; i++)
    {
      assert(pthread_join(threads[i], NULL) == 0);
    }
  puts("IMU snapshot validity, calibration, recovery and threaded coherence: PASS");
  return 0;
}
