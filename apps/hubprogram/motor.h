/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_MOTOR_H
#define BRICKWRIGHT_PROGRAM_MOTOR_H
#include <stdint.h>
#define SPEED_WINDOW 2                /* control ticks per speed estimate */
struct bw_motor_control {
  int32_t requested, reference, duty; /* deg/s (ramped reference), duty */
  int32_t window_speed;               /* encoder speed over the window, deg/s */
  int64_t target;                     /* positioning target, mdeg */
  int64_t integral;                   /* model angle - encoder angle, mdeg */
  int64_t model, model_previous;      /* reference model speed, mdeg/s */
  int64_t acceleration;               /* reference model, deg/s^2 */
  int64_t last_position;              /* encoder at the previous step, mdeg */
  int64_t window_position[SPEED_WINDOW];
  uint64_t window_time[SPEED_WINDOW];
  uint64_t last;
  unsigned positioning, active, settled, timed, window_fill;
};
/* Battery voltage for every port's output scaling; outside 5.5-9 V (no
 * reading, or a simulator's empty ADC channel) the loop assumes 7.2 V. */
void bw_motor_supply(int32_t millivolts);
void bw_motor_speed(struct bw_motor_control *,int32_t speed);
void bw_motor_position(struct bw_motor_control *,int64_t position_mdeg,int32_t delta_deg,int32_t speed);
/* Firmware control output: signed duty -10000..10000. Requires measured
 * encoder position and speed; it never receives simulated targets as feedback.
 * Time is monotonic milliseconds. Repeated/backward calls do not advance
 * acceleration, integration or settling; long intervals are capped at 50 ms.
 * The loop's derivation from the motor is documented in motor.c. */
int32_t bw_motor_step(struct bw_motor_control *,uint64_t now,
                     int64_t position_mdeg,int32_t speed_dps);
#endif
