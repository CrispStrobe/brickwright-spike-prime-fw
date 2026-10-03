/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright (c) 2026 Christian Strobele */
#ifndef BRICKWRIGHT_IMU_TIMESTAMP_H
#define BRICKWRIGHT_IMU_TIMESTAMP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* The driver publishes CLOCK_BOOTTIME microseconds modulo 2^32. Resolve
 * the most recent past epoch using the consumer's same clock, including a
 * consumer first started after the wrap. Reject future/ambiguous old samples.
 * A 30-second age bound is deliberately much smaller than the 71-minute wrap;
 * this is a freshness policy, not a physical sampling-rate guarantee.
 */
static inline bool imu_timestamp_expand(uint32_t raw, uint64_t now,
                                        uint64_t *out)
{
  uint64_t candidate;
  if (out == NULL) return false;
  *out = 0;
  candidate = (now & ~UINT64_C(0xffffffff)) | raw;
  if (candidate > now)
    {
      if (candidate < (UINT64_C(1) << 32)) return false;
      candidate -= UINT64_C(1) << 32;
    }
  if (now - candidate > UINT64_C(30000000)) return false;
  *out = candidate;
  return true;
}

#endif
