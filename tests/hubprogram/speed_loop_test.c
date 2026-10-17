/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
/* Closed-loop host test of the firmware speed controller (motor.c) against a
 * simulated SPIKE medium motor. The plant is the DC model the gains were
 * derived from (motor.c): J*w' = Ts*(d/10010 - w/w0) - friction - load, with
 * w0 = 1055 deg/s and Ts = 0.104 N*m at 7.2 V and J = 3.0e-4 kg*m^2, integrated
 * at 0.1 ms. The controller sees what device.c gives it on the hub: integer
 * encoder degrees sampled every 10 ms (optionally reported late) and their
 * backward-difference speed. Variations cover a full battery, Coulomb
 * friction, heavier loads and a stall. */
#include "../../apps/hubprogram/motor.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define PI 3.14159265358979323846
#define SUBSTEPS 100            /* 0.1 ms */
#define TICK_MS 10
struct plant {
  double volts;      /* 7.2 nominal; the stall torque scales with it */
  double inertia;    /* multiple of the bare rotor's 3.0e-4 kg*m^2 */
  double friction;   /* Coulomb friction, N*m */
  double load;       /* constant opposing torque, N*m */
  unsigned latency;  /* encoder report age, ticks */
  int stall_until;   /* shaft blocked until this time, ms (0: never) */
};
struct trace {
  double angle[400];  /* true shaft angle at each tick, deg */
  int32_t duty[400];
  int64_t integral[400];
  unsigned ticks;
};
static long floor_deg(double deg) { long v=(long)deg; return (double)v>deg ? v-1 : v; }
static void run(const struct plant *p,int32_t command,unsigned ticks,struct trace *out) {
  struct bw_motor_control m;
  const double ts=0.104*p->volts/7.2, w0=1055.0*PI/180.0*p->volts/7.2;
  const double j=3.0e-4*p->inertia, h=1e-3/SUBSTEPS;
  double w=0, theta=0; long reports[400]; int64_t previous=0; int32_t duty=0;
  assert(ticks<=400);
  memset(&m,0,sizeof(m));memset(out,0,sizeof(*out));
  bw_motor_speed(&m,command);
  for(unsigned k=0;k<ticks;k++) {
    unsigned now=k*TICK_MS;
    reports[k]=floor_deg(theta*180.0/PI);
    long seen=k>=p->latency ? reports[k-p->latency] : 0;
    int64_t position=(int64_t)seen*1000;
    int32_t speed=k ? (int32_t)((position-previous)/TICK_MS) : 0;
    previous=position;
    duty=bw_motor_step(&m,now,position,speed);
    out->angle[k]=theta*180.0/PI;out->duty[k]=duty;out->integral[k]=m.integral;
    for(unsigned s=0;s<TICK_MS*SUBSTEPS;s++) {
      double torque=ts*((double)duty/10010.0-w/w0)-(w>=0 ? p->load : -p->load);
      if(p->stall_until && (int)now<p->stall_until) { w=0; continue; }
      if(w==0 && torque<=p->friction && torque>=-p->friction) continue;
      torque-=(w>0 || (w==0 && torque>0)) ? p->friction : -p->friction;
      double next=w+torque/j*h;
      if((w>0 && next<0) || (w<0 && next>0))next=0;
      w=next;theta+=w*h;
    }
  }
  out->ticks=ticks;
}
/* Speed averaged over two ticks (20 ms) of the true angle. */
static double speed_at(const struct trace *t,unsigned k) { return (t->angle[k]-t->angle[k-2])*50.0; }
struct result { double steady, error, peak, overshoot, ripple, rise; };
static struct result measure(const struct trace *t,double command) {
  struct result r={0,0,-1e9,0,0,-1}; double low=1e9, high=-1e9, sign=command<0 ? -1 : 1;
  unsigned n=0;
  for(unsigned k=2;k<t->ticks;k++) {
    double v=speed_at(t,k)*sign;
    if(v>r.peak)r.peak=v;
    if(r.rise<0 && v>=0.9*command*sign)r.rise=k*TICK_MS/1000.0;
    if(k>=100) { r.steady+=v; n++; if(v<low)low=v; if(v>high)high=v; }
  }
  r.steady/=n; r.error=(r.steady-command*sign)/(command*sign)*100.0;
  r.overshoot=(r.peak-command*sign)/(command*sign)*100.0; r.ripple=(high-low)/(command*sign)*100.0;
  return r;
}
static struct result check(const char *name,const struct plant *p,int32_t command,
                           double max_error,double max_overshoot,double max_ripple,double max_rise) {
  static struct trace t; struct result r;
  run(p,command,200,&t); r=measure(&t,command);
  printf("%-34s steady %7.1f deg/s (%+.2f %%) overshoot %5.1f %% ripple %4.1f %% rise %.2f s\n",
         name,r.steady,r.error,r.overshoot,r.ripple,r.rise);
  assert(r.error<max_error && r.error>-max_error);
  assert(r.overshoot<max_overshoot);
  assert(r.ripple<max_ripple);
  assert(r.rise>0 && r.rise<max_rise);
  return r;
}
int main(void) {
  struct plant nominal={7.2,1,0,0,1,0};
  static struct trace t;
  /* Steady state < 1 %, no ringing, 90 % within 0.2 s on the bare motor. */
  check("300 deg/s, 7.2 V",&nominal,300,1,15,10,0.15);
  check("-300 deg/s, 7.2 V",&nominal,-300,1,15,10,0.15);
  check("800 deg/s, 7.2 V",&nominal,800,1,10,10,0.15);
  struct plant battery={8.3,1,0,0,1,0};
  check("300 deg/s, full battery 8.3 V",&battery,300,1,25,10,0.15);
  struct plant friction={7.2,1,0.018,0,1,0};
  check("300 deg/s, friction 0.018 N*m",&friction,300,1,10,10,0.2);
  check("100 deg/s, friction 0.018 N*m",&friction,100,1,15,20,0.4);
  struct plant loaded={7.2,2,0.018,0.02,1,0};
  check("300 deg/s, 2x inertia, load",&loaded,300,1,10,10,0.35);
  struct plant heavy={7.2,4,0.018,0,2,0};
  check("300 deg/s, 4x inertia, late reports",&heavy,300,1,30,10,0.3);
  /* The old loop's failure (Robot Lab lockstep, 2026-10-18): a 2 s run at
   * 300 deg/s turned 563 deg. The ramp alone costs 4 deg at 300 deg/s. */
  run(&nominal,300,200,&t);
  printf("angle after 2 s at 300 deg/s: %.1f deg\n",t.angle[199]+speed_at(&t,199)*0.01);
  assert(t.angle[199]>590 && t.angle[199]<606);
  /* Saturation and anti-windup: a stall holds the duty at full scale, the
   * integral stops advancing, and release does not run away. */
  struct plant stalled={7.2,1,0,0,1,1000};
  run(&stalled,600,200,&t);
  assert(t.duty[99]==10000);
  assert(t.integral[99]==t.integral[60] && t.integral[99]<=106382);
  double after=0; for(unsigned k=102;k<200;k++) if(speed_at(&t,k)>after)after=speed_at(&t,k);
  printf("stall released at 1 s: peak %.1f deg/s, final %.1f deg/s\n",after,speed_at(&t,199));
  assert(after<600*1.25); /* no wound-up runaway */
  assert(speed_at(&t,199)>594 && speed_at(&t,199)<606);
  puts("speed loop tests passed");
  return 0;
}
