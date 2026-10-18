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
  int no_reading;    /* the firmware gets no battery voltage */
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
  bw_motor_supply(p->no_reading ? 0 : (int32_t)(p->volts*1000.0+0.5));
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
/* Speed averaged over five ticks (50 ms) of the true angle: what a robot's
 * travel shows, without the 10 ms PWM-step ripple. */
#define AVERAGE 5
static double speed_at(const struct trace *t,unsigned k) { return (t->angle[k]-t->angle[k-AVERAGE])*100.0/AVERAGE; }
struct result { double steady, error, peak, overshoot, ripple, rise; };
static struct result measure(const struct trace *t,double command) {
  struct result r={0,0,-1e9,0,0,-1}; double low=1e9, high=-1e9, sign=command<0 ? -1 : 1;
  unsigned n=0;
  for(unsigned k=AVERAGE;k<t->ticks;k++) {
    double v=speed_at(t,k)*sign;
    if(v>r.peak)r.peak=v;
    if(r.rise<0 && v>=0.9*command*sign)r.rise=k*TICK_MS/1000.0;
    if(k>=150) { r.steady+=v; n++; if(v<low)low=v; if(v>high)high=v; } /* last 0.5 s */
  }
  r.steady/=n; r.error=(r.steady-command*sign)/(command*sign)*100.0;
  r.overshoot=(r.peak-command*sign)/(command*sign)*100.0; r.ripple=(high-low)/(command*sign)*100.0;
  return r;
}
static struct result check(const char *name,const struct plant *p,int32_t command,
                           double max_error,double max_overshoot,double max_ripple,double max_rise) {
  static struct trace t; struct result r;
  run(p,command,200,&t); r=measure(&t,command);
  printf("%-44s steady %7.1f deg/s (%+.2f %%) overshoot %4.1f %% ripple %4.1f %% rise %.2f s\n",
         name,r.steady,r.error,r.overshoot,r.ripple,r.rise);
  assert(r.error<max_error && r.error>-max_error);
  assert(r.overshoot<=max_overshoot);
  assert(r.ripple<max_ripple);
  assert(r.rise>0 && r.rise<=max_rise);
  return r;
}
int main(void) {
  static struct trace t; char name[64];
  /* The grid: battery 7.2 and 8.3 V, bare rotor to four times its inertia,
   * no friction (the linear fit) and the measured 0.018 N*m, encoder reports
   * one or two ticks old. Overshoot <= 3 %, steady state (last 0.5 s) < 1 %. Rise to 90 %
   * of 300 deg/s is bounded below the old loop's on the same plant (0.22,
   * 0.31, 0.51 s without friction; with friction it never got there). */
  const double volts[]={7.2,8.3}, inertia[]={1,2,4}, friction[]={0,0.018};
  const double rise_bare[]={0.15,0.25,0.40};
  for(unsigned a=0;a<2;a++) for(unsigned b=0;b<3;b++) for(unsigned f=0;f<2;f++)
    for(unsigned lat=1;lat<=2;lat++) {
      struct plant p={volts[a],inertia[b],friction[f],0,lat,0,0};
      snprintf(name,sizeof(name),"300 deg/s %.1f V %.0fx J friction %.3f late %u",volts[a],inertia[b],friction[f],lat);
      check(name,&p,300,1,3,10,f ? 0.8 : rise_bare[b]);
      snprintf(name,sizeof(name),"800 deg/s %.1f V %.0fx J friction %.3f late %u",volts[a],inertia[b],friction[f],lat);
      check(name,&p,800,1,3,10,f ? 0.8 : rise_bare[b]+0.05);
    }
  struct plant nominal={7.2,1,0,0,1,0,0};
  check("-300 deg/s, 7.2 V",&nominal,-300,1,3,10,0.15);
  /* At low speed friction is most of the drive, and the integral that
   * supplies it settles last: within 1 % over the last 0.5 s, 90 % within 1 s. */
  struct plant friction100={7.2,1,0.018,0,1,0,0};
  check("100 deg/s, friction 0.018 N*m",&friction100,100,1,5,25,1.0);
  struct plant loaded={7.2,2,0.018,0.02,1,0,0};
  check("300 deg/s, 2x inertia, friction + load",&loaded,300,1,3,10,1.0);
  /* Without a battery reading the loop assumes 7.2 V; a full battery then
   * overdrives the feed-forward by 15 %. Bounded, but not the 3 % target. */
  struct plant unread={8.3,1,0,0,1,0,1};
  check("300 deg/s, 8.3 V, no battery reading",&unread,300,1,10,10,0.15);
  /* The old loop's failure (Robot Lab lockstep, 2026-10-18): a 2 s run at
   * 300 deg/s turned 563 deg. The ramp and reference model cost ~20 deg. */
  run(&nominal,300,200,&t);
  printf("angle after 2 s at 300 deg/s: %.1f deg\n",t.angle[199]);
  assert(t.angle[199]>575 && t.angle[199]<600);
  /* Saturation and anti-windup: a stall holds the duty at full scale, the
   * integral stops advancing, and release does not run away. */
  struct plant stalled={7.2,1,0,0,1,1000,0};
  run(&stalled,600,200,&t);
  assert(t.duty[99]==10000);
  assert(t.integral[99]==t.integral[60] && t.integral[99]<=181818);
  double after=0; for(unsigned k=102;k<200;k++) if(speed_at(&t,k)>after)after=speed_at(&t,k);
  printf("stall released at 1 s: peak %.1f deg/s, final %.1f deg/s\n",after,speed_at(&t,199));
  assert(after<600*1.25); /* no wound-up runaway */
  assert(speed_at(&t,199)>594 && speed_at(&t,199)<606);
  puts("speed loop tests passed");
  return 0;
}
