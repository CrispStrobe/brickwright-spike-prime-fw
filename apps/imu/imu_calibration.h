/*
 * Upstream source/reference notices retained conservatively; see
 * policy/pybricks-reuse.json and licenses/. No clean-room claim is made.
 * SPDX-License-Identifier: MIT
 * Copyright (c) 2022-2023 The Pybricks Authors
 */
/****************************************************************************
 * apps/imu/imu_calibration.h
 *
 * Calibration persistence for IMU processing.
 * Ported from pybricks (MIT License, Pybricks Authors).
 ****************************************************************************/

#ifndef __APPS_IMU_CALIBRATION_H
#define __APPS_IMU_CALIBRATION_H

#include "imu_types.h"

void imu_calibration_init(imu_settings_t *settings);
void imu_calibration_set_defaults(imu_settings_t *settings);
/* Save synchronizes a same-directory temporary before atomic replacement.
 * Load rejects incomplete, trailing or nonfinite/degenerate settings and leaves
 * the active settings unchanged on failure. Native record layout is retained;
 * no checksum, authentication or filesystem-independent durability is claimed. */
int imu_calibration_save(const char *path);
int imu_calibration_save_copy(const char *path, const imu_settings_t *settings);
int imu_calibration_load(const char *path);
imu_settings_t *imu_calibration_get_settings(void);

#endif /* __APPS_IMU_CALIBRATION_H */
