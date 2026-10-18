/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "motor.h"
#include <string.h>

/* Speed loop for the SPIKE angular motors. Tuning belongs to this firmware
 * and is derived from the real motor below; it is intentionally distinct from
 * any simulator's (the arena's) mechanical model.
 *
 * Plant (Technic medium angular motor, the drivebase motor, at 7.2 V): a DC
 * motor fitted to measured data, no-load speed w0 = 1055 deg/s (18.41 rad/s),
 * stall torque Ts = 0.104 N*m, reflected rotor inertia J = 3.0e-4 kg*m^2
 * (a published observer model identified on this motor; sources in
 * docs/project/motor-speed-loop.md). Mechanical time constant
 * tau = J*w0/Ts = 3.0e-4*18.41/0.104 = 53 ms. Coulomb friction 0.018-0.021 N*m
 * (15-20 % duty) and the load are not modelled; the integral supplies them.
 *
 * Actuator: duty d in -10000..10000 sets CCR = d/10 of the ARR+1 = 1001 tick
 * PWM period (stm32_legoport_pwm.c), so full scale is 99.9 % and the unloaded
 * steady speed is w = 1055*d/10010 deg/s at 7.2 V: K = 0.1054 deg/s per duty.
 * K scales with the battery (7.2-8.3 V, +15 %), so the loop works in duty at
 * 7.2 V and scales its output by 7200 mV / battery (bw_motor_supply), as
 * the identified models do. Without a plausible reading it assumes 7.2 V.
 *
 * Measurement: integer-degree LUMP positions every T = 10 ms. Speed is the
 * position difference over the last SPEED_WINDOW ticks (20 ms: a 50 deg/s
 * quantum instead of 100), about 20 ms effective delay with the PWM hold.
 *
 * Reference: the command is rate-limited to reach the rated 1110 deg/s in
 * 100 ms (stop from it in 150 ms) and then passes a first-order model wm with
 * TAU_M = 50 ms. Feed-forward d_ff = (wm + tau*dwm/dt)/K makes the unloaded
 * plant follow wm exactly, so the feedback only sees what the model lacks.
 *
 * Feedback: PI on wm - w. Kp = 8 duty per deg/s: lambda (IMC) tuning
 * Kp = tau/(K*(lambda + Td)) with lambda + Td = 63 ms; the 50 deg/s quantum
 * costs 400 duty of jitter. Ki = 55 duty per degree of integrated error
 * (Ti = 145 ms, slower than tau) keeps the loop overdamped up to four times
 * the rotor inertia (tau ~ 0.2 s), where a faster integral rings.
 *
 * No overshoot from the integral: a load heavier than the model lags the
 * reference while it accelerates, and an integral fed that lag must later
 * give the angle back as overshoot. The integral therefore advances only
 * while the reference model is steady (|dwm/dt| <= 50 deg/s^2); the lag
 * closes under P and feed-forward alone, which cannot overshoot a first-order
 * plant, and the integral then removes the persistent part (friction, load,
 * battery) from below. Measured on the host plant: <= 3 % at 7.2 and 8.3 V up
 * to 4x inertia (speed_loop_test.c).
 *
 * The integral is kept as an angle: the model's angle minus the measured
 * encoder angle (mdeg), exact over any number of ticks, so there is no
 * steady-state speed error and two wheels commanded alike turn alike.
 * Anti-windup: the integral does not advance while the output is saturated
 * in the direction that advance would push it, and it is bounded to the angle
 * whose term alone is full scale. */
#define FF_NUM 10010          /* duty = deg/s * FF_NUM / FF_DEN (7.2 V) */
#define FF_DEN 1055
#define TAU_MS 53             /* plant mechanical time constant */
#define TAU_M_MS 50           /* reference model time constant */
#define KP 8                  /* duty per deg/s */
#define KI 55                 /* duty per degree */
#define INTEGRATE_BELOW 50    /* deg/s^2 of the reference model */
#define ACCEL 11100           /* deg/s^2: 0 -> 1110 deg/s in 100 ms */
#define DECEL 7400            /* deg/s^2: 1110 deg/s -> 0 in 150 ms */
#define NOMINAL_MV 7200
#define SUPPLY_MIN_MV 5500    /* below: no plausible reading, assume nominal */
#define SUPPLY_MAX_MV 9000
#define DUTY_MAX 10000
#define INTEGRAL_MAX ((int64_t)DUTY_MAX*1000/KI) /* mdeg */
static int32_t g_supply_mv;
static int64_t clamp(int64_t v,int64_t low,int64_t high) { return v<low ? low : v>high ? high : v; }
void bw_motor_supply(int32_t millivolts) { g_supply_mv=millivolts; }
void bw_motor_speed(struct bw_motor_control *m,int32_t speed) {
  if(!m->active)memset(m,0,sizeof(*m));
  m->requested=speed; m->positioning=0; m->active=1; m->settled=0;
}
void bw_motor_position(struct bw_motor_control *m,int64_t pos,int32_t delta,int32_t speed) {
  if(!m->active)memset(m,0,sizeof(*m));
  m->target=pos+(int64_t)delta*1000; m->requested=speed; m->positioning=1; m->active=1; m->settled=0;
}
int32_t bw_motor_step(struct bw_motor_control *m,uint64_t now,int64_t pos,int32_t speed) {
  int32_t desired=m->requested;
  uint64_t dt=m->timed ? (now>m->last ? now-m->last : 0) : 10;
  int64_t supply=g_supply_mv>=SUPPLY_MIN_MV && g_supply_mv<=SUPPLY_MAX_MV ? g_supply_mv : NOMINAL_MV;
  int64_t limit=(int64_t)DUTY_MAX*supply/NOMINAL_MV; /* full scale in 7.2 V duty */
  int64_t candidate,error,output,ff;
  if(!m->timed)m->last_position=pos;
  if(!m->timed || now>m->last)m->last=now;
  m->timed=1; if(dt>50)dt=50;
  if(!m->active) { m->duty=0; return 0; }
  if(m->positioning) {
    int64_t remaining=m->target-pos;
    /* Linear distance-dependent speed cap. */
    int64_t cap=clamp(remaining*2/1000,-m->requested,m->requested);
    desired=(int32_t)cap;
    if(remaining>=-1000 && remaining<=1000 && speed>=-20 && speed<=20) {
      if(dt && ++m->settled>=3) { m->active=0; m->duty=0; return 0; }
    } else m->settled=0;
  }
  candidate=m->integral;
  if(dt) {
    int64_t ref=m->reference;
    int64_t rate=(ref>0 && desired<ref) || (ref<0 && desired>ref) ? DECEL : ACCEL;
    int64_t step=rate*(int64_t)dt/1000;
    unsigned i;
    m->reference=(int32_t)clamp(desired,ref-step,ref+step);
    m->model_previous=m->model;
    m->model+=((int64_t)m->reference*1000-m->model)*(int64_t)dt/(TAU_M_MS+(int64_t)dt);
    m->acceleration=(m->model-m->model_previous)/(int64_t)dt;
    if(m->acceleration<=INTEGRATE_BELOW && m->acceleration>=-INTEGRATE_BELOW)
      candidate+=m->model_previous*(int64_t)dt/1000-(pos-m->last_position);
    /* Windowed speed from the encoder history once it spans SPEED_WINDOW. */
    if(m->window_fill==SPEED_WINDOW) {
      if(now>m->window_time[0])m->window_speed=(int32_t)clamp((pos-m->window_position[0])/(int64_t)(now-m->window_time[0]),INT32_MIN,INT32_MAX);
      for(i=1;i<SPEED_WINDOW;i++) { m->window_position[i-1]=m->window_position[i]; m->window_time[i-1]=m->window_time[i]; }
      m->window_fill--;
    } else m->window_speed=speed;
    m->window_position[m->window_fill]=pos; m->window_time[m->window_fill]=now; m->window_fill++;
  }
  m->last_position=pos;
  error=m->model_previous/1000-m->window_speed;
  ff=(m->model+(int64_t)TAU_MS*m->acceleration)*FF_NUM/((int64_t)FF_DEN*1000);
  output=ff+error*KP+candidate*KI/1000;
  if((output>limit && candidate>m->integral) || (output<-limit && candidate<m->integral))
    output=ff+error*KP+m->integral*KI/1000;
  else m->integral=clamp(candidate,-INTEGRAL_MAX,INTEGRAL_MAX);
  m->duty=(int32_t)clamp(output*NOMINAL_MV/supply,-DUTY_MAX,DUTY_MAX); return m->duty;
}
