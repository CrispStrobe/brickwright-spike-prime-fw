/* SPDX-License-Identifier: MIT
 * Copyright (c) 2021 x-io Technologies
 * Copyright (c) 2026 Brickwright contributors
 *
 * Adapted from FusionAhrs.c: HalfGravity, Residual and the inclination
 * feedback in FusionAhrsUpdate, xioTechnologies/Fusion at
 * a8d7224f36a0ec82345ef49a3db50e65f8d3bab8. Full grant:
 * licenses/Fusion-MIT.txt. This is a reduced adapter, not the full Fusion
 * library: caller supplies acceleration rejection, initial attitude and
 * gain. Gyroscope input is rad/s. Quaternion is body-to-world, w,x,y,z.
 * Integration uses an exponential rotation rather than Fusion's Euler step.
 */

#ifndef DRIVEBASE_ORIENTATION_H
#define DRIVEBASE_ORIENTATION_H

#include <math.h>

static inline void db_orientation_update(float q[4], const float a[3],
                                         const float gyro[3], float dt,
                                         float gain)
{
  if (!isfinite(dt) || dt <= 0.0f || !isfinite(gain) || gain < 0.0f)
    return;
  for (int i = 0; i < 3; i++)
    if (!isfinite(a[i]) || !isfinite(gyro[i]))
      return;

  const float w = q[0], x = q[1], y = q[2], z = q[3];
  float rate[3] = {gyro[0], gyro[1], gyro[2]};
  const float norm = sqrtf(a[0]*a[0] + a[1]*a[1] + a[2]*a[2]);
  if (norm > 1e-6f)
    {
      const float sensor[3] = {a[0]/norm, a[1]/norm, a[2]/norm};
      const float gravity[3] = {x*z - w*y, y*z + w*x, w*w + z*z - 0.5f};
      float residual[3] = {
        sensor[1]*gravity[2] - sensor[2]*gravity[1],
        sensor[2]*gravity[0] - sensor[0]*gravity[2],
        sensor[0]*gravity[1] - sensor[1]*gravity[0]
      };
      if (sensor[0]*gravity[0] + sensor[1]*gravity[1] + sensor[2]*gravity[2] <= 0)
        {
          const float length = sqrtf(residual[0]*residual[0] +
                                     residual[1]*residual[1] + residual[2]*residual[2]);
          if (length > 1e-6f)
            for (int i = 0; i < 3; i++)
              residual[i] /= length;
        }
      for (int i = 0; i < 3; i++)
        rate[i] += 2.0f * gain * residual[i];
    }

  const float speed = sqrtf(rate[0]*rate[0] + rate[1]*rate[1] + rate[2]*rate[2]);
  const float angle = 0.5f * speed * dt;
  const float scale = speed > 1e-6f ? sinf(angle)/speed : 0.5f*dt;
  const float r = cosf(angle);
  const float u = rate[0]*scale, v = rate[1]*scale, t = rate[2]*scale;
  float next[4] = {w*r - x*u - y*v - z*t,
                   w*u + x*r + y*t - z*v,
                   w*v - x*t + y*r + z*u,
                   w*t + x*v - y*u + z*r};
  const float length = sqrtf(next[0]*next[0] + next[1]*next[1] +
                             next[2]*next[2] + next[3]*next[3]);
  if (isfinite(length) && length > 1e-6f)
    for (int i = 0; i < 4; i++)
      q[i] = next[i]/length;
}

#endif
