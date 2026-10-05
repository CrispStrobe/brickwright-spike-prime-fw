#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Christian Strobele
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/include/nuttx/sensors" "$work/include/arch/board"
cat > "$work/include/nuttx/config.h" <<'EOF'
#define FAR
#ifndef CLOCK_BOOTTIME
#define CLOCK_BOOTTIME CLOCK_MONOTONIC
#endif
EOF
cat > "$work/include/nuttx/sensors/sensor.h" <<'EOF'
#include <stdint.h>
struct sensor_imu
{
  uint32_t timestamp;
  int16_t ax, ay, az, gx, gy, gz, temperature_raw;
  uint8_t odr_idx, fsr_xl_idx, fsr_gy_idx, reserved[3];
};
struct sensor_mag { float x, y, z; };
EOF
: > "$work/include/arch/board/board_lsm6dsl.h"
"${CC:-cc}" -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror \
  -fsanitize=undefined,float-cast-overflow -fno-sanitize-recover=all \
  -pthread -I"$work/include" -I"$root/apps/imu" \
  "$root/tools/test_imu_daemon.c" "$root/apps/imu/imu_fusion.c" \
  "$root/apps/imu/imu_geometry.c" "$root/apps/imu/imu_stationary.c" \
  "$root/apps/imu/imu_calibration.c" -lm -o "$work/test_imu_daemon"
"$work/test_imu_daemon"
