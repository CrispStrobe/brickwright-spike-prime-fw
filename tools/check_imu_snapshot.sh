#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Christian Strobele
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
"${CC:-cc}" -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror \
  -pthread -I"$root/apps/imu" "$root/tools/test_imu_snapshot.c" \
  "$root/apps/imu/imu_fusion.c" "$root/apps/imu/imu_geometry.c" \
  -lm -o "$work/test_imu_snapshot"
"$work/test_imu_snapshot"
