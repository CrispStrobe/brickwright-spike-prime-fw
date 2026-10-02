/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_MOTOR_H
#define BRICKWRIGHT_PROGRAM_MOTOR_H
#include <stdint.h>
struct bw_motor_control {
  int32_t requested, reference, duty;
  int64_t target, integral;
  uint64_t last;
  unsigned positioning, active, settled, timed;
};
void bw_motor_speed(struct bw_motor_control *,int32_t speed);
void bw_motor_position(struct bw_motor_control *,int64_t position_mdeg,int32_t delta_deg,int32_t speed);
/* Firmware control output: signed duty -10000..10000. Requires measured
 * encoder position and speed; it never receives simulated targets as feedback.
 * Time is monotonic milliseconds. Repeated/backward calls do not advance
 * acceleration, integration or settling; long intervals are capped at 50 ms. */
int32_t bw_motor_step(struct bw_motor_control *,uint64_t now,
                     int64_t position_mdeg,int32_t speed_dps);
#endif
