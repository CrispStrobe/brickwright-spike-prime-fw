/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "motor.h"
#include <string.h>
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
  int64_t step,error,output;
  if(!m->timed || now>m->last)m->last=now;
  m->timed=1; if(dt>50)dt=50;
  if(!m->active) { m->duty=0; return 0; }
  if(m->positioning) {
    int64_t remaining=m->target-pos;
    /* Linear distance-dependent speed cap; tuning belongs to this firmware,
     * and is intentionally distinct from the arena's mechanical model. */
    int64_t cap=clamp(remaining*2/1000,-m->requested,m->requested);
    desired=(int32_t)cap;
    if(remaining>=-1000 && remaining<=1000 && speed>=-20 && speed<=20) {
      if(dt && ++m->settled>=3) { m->active=0; m->duty=0; return 0; }
    } else m->settled=0;
  }
  step=(int64_t)(desired==0 ? 4000 : 2000)*dt/1000;
  m->reference=(int32_t)clamp(desired,(int64_t)m->reference-step,(int64_t)m->reference+step);
  error=(int64_t)m->reference-speed;
  m->integral=clamp(m->integral+error*(int64_t)dt,-2000000,2000000);
  output=(int64_t)m->reference*10000/1110+error*3+m->integral/1000;
  m->duty=(int32_t)clamp(output,-10000,10000); return m->duty;
}
