/*
 * Upstream source/reference notices retained conservatively; see
 * policy/pybricks-reuse.json and licenses/. No clean-room claim is made.
 * SPDX-License-Identifier: MIT
 * Copyright (c) 2022-2023 The Pybricks Authors
 */
/****************************************************************************
 * apps/imu/imu_fusion.h
 *
 * Sensor fusion for IMU processing.
 * Ported from pybricks imu.c (MIT License, Pybricks Authors).
 ****************************************************************************/

#ifndef __APPS_IMU_FUSION_H
#define __APPS_IMU_FUSION_H

#include "imu_types.h"

/* One coherent fusion step. Acceleration/gyro use the configured base axes;
 * orientation keeps the legacy hub-to-inertial matrix convention. Readiness
 * means stationary calibration readiness, independently of sample validity.
 * Timestamps use the caller's monotonic microsecond time domain.
 */

typedef struct
{
  uint64_t timestamp_us;
  uint64_t sequence;
  bool valid;
  bool ready;
  imu_xyz_t accel_mms2;
  imu_xyz_t gyro_dps;
  imu_matrix_3x3_t orientation;
  float heading_1d;
  float heading_3d;
  imu_side_t up_side;
} imu_fusion_snapshot_t;

bool imu_fusion_update_timestamped(const imu_xyz_t *gyro_dps,
                                 const imu_xyz_t *accel_mms2,
                                 float sample_time, uint64_t timestamp_us);
/* Failure clears out. Reading a snapshot does not consume it. */
bool imu_fusion_get_snapshot(imu_fusion_snapshot_t *out, uint64_t now_us,
                             uint64_t max_age_us);

void imu_fusion_init(void);
/* Copies settings; the caller's storage is never retained or modified. */
void imu_fusion_set_settings(imu_settings_t *settings);
/* Exports the coherent copy, including learned stationary bias for saving. */
bool imu_fusion_get_settings(imu_settings_t *out);
void imu_fusion_set_base_orientation(imu_xyz_t *front, imu_xyz_t *top);

/* Called per-sample with gyro (deg/s) + accel (mm/s^2) */

void imu_fusion_update(imu_xyz_t *gyro_dps, imu_xyz_t *accel_mms2,
                       float sample_time);

/* Called when stationary period detected */

void imu_fusion_stationary_update(const int32_t *gyro_sum,
                                  const int32_t *accel_sum,
                                  uint32_t num_samples,
                                  float gyro_scale);

/* Getters */

void imu_fusion_get_accel(imu_xyz_t *out, bool calibrated);
void imu_fusion_get_gyro(imu_xyz_t *out, bool calibrated);
void imu_fusion_get_tilt(imu_xyz_t *out);
imu_side_t imu_fusion_get_up_side(bool calibrated);
int imu_fusion_get_single_axis_rotation(imu_xyz_t *axis, float *angle,
                                        bool calibrated);
float imu_fusion_get_heading(imu_heading_type_t type);
void imu_fusion_set_heading(float desired);
void imu_fusion_get_orientation(imu_matrix_3x3_t *out);
bool imu_fusion_is_ready(void);

#endif /* __APPS_IMU_FUSION_H */
