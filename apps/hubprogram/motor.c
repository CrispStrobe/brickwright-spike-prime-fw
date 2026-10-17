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
 * docs/project/motor-speed-loop.md). Mechanical time
 * constant tau = J*w0/Ts = 3.0e-4*18.41/0.104 = 53 ms.
 *
 * Actuator: duty d in -10000..10000 sets CCR = d/10 of the ARR+1 = 1001 tick
 * PWM period (stm32_legoport_pwm.c), so full scale is 99.9 % and the unloaded
 * steady speed is w = 1055*d/10010 deg/s: gain K = 0.1054 deg/s per duty.
 *
 * Measurement: integer-degree LUMP positions sampled every T = 10 ms; the
 * backward-difference speed (device.c) has a 100 deg/s quantum and, with the
 * sample age and the PWM hold, an effective delay Td of about 20 ms.
 *
 * Feed-forward: d_ff = (wm + tau*dwm/dt)/K + d_f, the duty that makes the
 * plant follow the reference model wm. The reference is the commanded speed
 * rate-limited to reach the rated 1110 deg/s in 100 ms (and to stop from it in
 * 150 ms), then a first-order model with TAU_M = 35 ms whose derivative stays
 * bounded for the acceleration term. d_f compensates half of the motor's
 * Coulomb friction: measured as 0.018 N*m (no-load current 0.1 A at
 * R = 10.6 ohm, the same data as the fit) and identified as 0.021 N*m by
 * that observer model, i.e. about 1400 duty at 7.2 V. Friction varies by unit, wear and
 * temperature, and an over-compensated motor overshoots, so 700 duty is fed
 * forward and the integral supplies the rest. It fades in over the first
 * 50 deg/s so that holding still does not chatter between signs.
 *
 * Feedback: PI on wm - w with lambda (IMC) tuning of K*e^(-Td*s)/(tau*s + 1):
 * Kp = tau/(K*(lambda + Td)), Ti = tau. lambda = 64 ms gives
 * Kp = 0.053/(0.1054*0.084) = 6 duty per deg/s; its response to the 100 deg/s
 * quantum (600 duty) stays near 5 % of full scale. Ti is lengthened from tau
 * (53 ms) to lambda (64 ms), Ki = Kp/Ti = 94 duty per degree of integrated
 * error, so that a load four times the rotor inertia (tau ~ 0.2 s: a robot or
 * an arm) still settles without ringing. The remaining friction, load and the
 * battery (7.2-8.3 V, +15 % on K) are left to the integral: no steady-state
 * speed error.
 *
 * The integral is kept as an angle: the model's angle minus the measured
 * encoder angle (mdeg), exact over any number of ticks, so two wheels
 * commanded alike turn alike. The feedback compares the measurement with the
 * model one tick earlier, the measurement's own delay, so the start-up
 * transient does not wind the integral. Anti-windup: the integral does not
 * advance while the output is saturated in the direction that advance would
 * push it, and it is bounded to the angle whose term alone is full scale. */
#define FF_NUM 10010          /* duty = deg/s * FF_NUM / FF_DEN */
#define FF_DEN 1055
#define TAU_MS 53             /* plant mechanical time constant */
#define TAU_M_MS 35           /* reference model time constant */
#define KP 6                  /* duty per deg/s */
#define KI 94                 /* duty per degree */
#define FRICTION_DUTY 700     /* half of the identified Coulomb friction */
#define FRICTION_FADE 50      /* deg/s over which it fades in */
#define ACCEL 11100           /* deg/s^2: 0 -> 1110 deg/s in 100 ms */
#define DECEL 7400            /* deg/s^2: 1110 deg/s -> 0 in 150 ms */
#define DUTY_MAX 10000
#define INTEGRAL_MAX ((int64_t)DUTY_MAX*1000/KI) /* mdeg */
static int64_t clamp(int64_t v,int64_t low,int64_t high) { return v<low ? low : v>high ? high : v; }
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
    m->reference=(int32_t)clamp(desired,ref-step,ref+step);
    m->model_previous=m->model;
    m->model+=((int64_t)m->reference*1000-m->model)*(int64_t)dt/(TAU_M_MS+(int64_t)dt);
    m->acceleration=(m->model-m->model_previous)/(int64_t)dt;
    candidate+=m->model_previous*(int64_t)dt/1000-(pos-m->last_position);
  }
  m->last_position=pos;
  error=m->model_previous/1000-speed;
  ff=(m->model+(int64_t)TAU_MS*m->acceleration)*FF_NUM/((int64_t)FF_DEN*1000)
    +clamp(m->model/FRICTION_FADE,-1000,1000)*FRICTION_DUTY/1000;
  output=ff+error*KP+candidate*KI/1000;
  if((output>DUTY_MAX && candidate>m->integral) || (output<-DUTY_MAX && candidate<m->integral))
    output=ff+error*KP+m->integral*KI/1000;
  else m->integral=clamp(candidate,-INTEGRAL_MAX,INTEGRAL_MAX);
  m->duty=(int32_t)clamp(output,-DUTY_MAX,DUTY_MAX); return m->duty;
}
