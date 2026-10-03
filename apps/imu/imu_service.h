/* SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Christian Strobele
 */
#ifndef BRICKWRIGHT_IMU_SERVICE_H
#define BRICKWRIGHT_IMU_SERVICE_H

#include "imu_fusion.h"

/* Start reserves the producer asynchronously. Already starting/running is
 * success; a pending stop returns -EBUSY. Task creation errors are -errno.
 * Stop is asynchronous and idempotent, including during startup. */
int imu_service_start(void);
int imu_service_stop(void);
void imu_service_status(bool *starting, bool *running, bool *stopping);

/* Nonconsuming coherent snapshot in CLOCK_BOOTTIME microseconds; clears out
 * on failure. Requires a running producer without pending stop and a sample
 * no older than 300 ms. Returns 0 or negative errno (-EAGAIN if unavailable).
 * Units and orientation convention are those of imu_fusion_snapshot_t. */
int imu_service_snapshot(imu_fusion_snapshot_t *out);

#endif
