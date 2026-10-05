/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "program.h"
#include <errno.h>
#include <string.h>
static int between(int32_t v, int32_t low, int32_t high) { return v >= low && v <= high; }
static int predicate(int32_t selector, int32_t value)
{
  if (selector == 1 || selector == 2) return between(value, 0, 65535);
  if (selector == 3) return between(value, 0, 1);
  if (selector == 4) return between(value, 0, 255);
  return (selector == 5 || selector == 6) && between(value, 0, 100);
}
int bw_program_validate(const struct bw_instruction *code, uint32_t count)
{
  uint32_t i;
  if (!code || count == 0 || count > BW_PROGRAM_LIMIT) return -EINVAL;
  for (i = 0; i < count; i++) {
    const struct bw_instruction *p = code + i;
    int valid = 0;
    switch (p->op) {
      case 0: valid = p->a == 0 && p->b == 0 && p->c == 0; break;
      case 1: valid = between(p->a,0,BW_PROGRAM_PORT_COUNT-1) && between(p->b,-1110,1110) && p->c == 0; break;
      case 2: valid = between(p->a,0,120000) && p->b == 0 && p->c == 0; break;
      case 3: valid = predicate(p->a,p->b) && p->c == 0; break;
      case 4: valid = between(p->a,0,(int32_t)count-1) && p->b == 0 && p->c == 0; break;
      case 5: valid = predicate(p->a,p->b) && between(p->c,0,(int32_t)count-1); break;
      case 6: valid = between(p->a,0,BW_PROGRAM_PORT_COUNT-1) && between(p->b,-36000,36000) && between(p->c,1,1110); break;
    }
    if (!valid) return -EINVAL;
  }
  return code[count-1].op == 0 ? 0 : -EINVAL;
}
void bw_program_init(struct bw_program *p, const struct bw_program_io *io)
{
  memset(p,0,sizeof(*p));
  if (io) p->io = *io;
  p->moving = -1;
}
int bw_program_load(struct bw_program *p, uint32_t id,
                    const struct bw_instruction *code, uint32_t count)
{
  int rc;
  if (p->state == BW_PROGRAM_RUNNING) return -EBUSY;
  if (!id) return -EINVAL;
  rc = bw_program_validate(code,count);
  if (rc < 0) return rc;
  memmove(p->code,code,count*sizeof(*code));
  p->language=0; p->source[0]=0; p->count=count; p->id=id; p->pc=0; p->error=0; p->owned=0; p->moving=-1; p->waiting=0; p->ending=0; p->state=BW_PROGRAM_READY;
  return 0;
}
int bw_program_start(struct bw_program *p, uint32_t id, uint64_t now)
{
  if (p->state == BW_PROGRAM_RUNNING) return -EBUSY;
  /* A terminal execution keeps its committed program. Re-running it does
   * not require a second upload or a filesystem round trip. */
  if ((p->state != BW_PROGRAM_READY && p->state != BW_PROGRAM_COMPLETE &&
       p->state != BW_PROGRAM_STOPPED && p->state != BW_PROGRAM_FAULT) ||
      p->id != id || now>UINT64_MAX-BW_PROGRAM_TIME_LIMIT) return -EINVAL;
  if (!p->io.motor || !p->io.position || !p->io.done || !p->io.brake || !p->io.sensor) return -ENOSYS;
  p->pc=0; p->owned=0; p->moving=-1; p->waiting=0; p->ending=0; p->deadline=0;
  p->started=p->last_tick=now; p->error=0; p->state=BW_PROGRAM_RUNNING;
  return 0;
}
static int brake_owned(struct bw_program *p)
{
  int result=0;
  unsigned port;
  for (port=0;port<BW_PROGRAM_PORT_COUNT;port++) if (p->owned & (1u<<port)) {
    int rc=p->io.brake(p->io.context,port);
    if (rc<0 && result==0) result=rc;
  }
  return result;
}
static void fault(struct bw_program *p, int error)
{
  (void)brake_owned(p); p->error=error; p->state=BW_PROGRAM_FAULT;
}
int bw_program_stop(struct bw_program *p)
{
  int rc=brake_owned(p);
  if (rc<0) fault(p,rc);
  else if (p->state != BW_PROGRAM_EMPTY) p->state=BW_PROGRAM_STOPPED;
  return rc;
}
static int condition(struct bw_program *p, int selector, int threshold)
{
  int32_t value=0;
  int rc=p->io.sensor(p->io.context,(unsigned)selector,&value);
  if (rc==-EAGAIN) return 0;
  if (rc<0) return rc;
  if ((selector==1 || selector==2) && value<0) return 0;
  if (selector==1 || selector==5) return value<threshold;
  if (selector==2 || selector==6) return value>threshold;
  return value==threshold;
}
void bw_program_tick(struct bw_program *p, uint64_t now)
{
  unsigned budget=32;
  int rc;
  if (p->state != BW_PROGRAM_RUNNING) return;
  if (now<p->last_tick) { fault(p,-ERANGE); return; }
  p->last_tick=now;
  if (now-p->started>=BW_PROGRAM_TIME_LIMIT) { fault(p,-ETIMEDOUT); return; }
  if (p->waiting) { if (now<p->deadline) return; p->waiting=0; }
  if (p->moving>=0) {
    rc=p->io.done(p->io.context,(unsigned)p->moving);
    if (rc<0) { fault(p,rc); return; }
    if (!rc) return;
    p->moving=-1;
  }
  if (p->ending) {
    unsigned port;
    for (port=0;port<BW_PROGRAM_PORT_COUNT;port++) if (p->owned&(1u<<port)) {
      rc=p->io.done(p->io.context,port);
      if (rc<0) { fault(p,rc); return; }
      if (!rc) return;
    }
    p->state=BW_PROGRAM_COMPLETE; return;
  }
  while (budget--) {
    const struct bw_instruction *ins;
    if (p->pc>=p->count) { fault(p,-EPROTO); return; }
    ins=p->code+p->pc;
    switch (ins->op) {
      case 0:
        rc=brake_owned(p);
        if (rc<0) { fault(p,rc); return; }
        p->ending=1; return;
      case 1:
        p->owned|=1u<<(unsigned)ins->a;
        rc=p->io.motor(p->io.context,(unsigned)ins->a,ins->b);
        if (rc<0) { fault(p,rc); return; }
        p->pc++; break;
      case 2:
        p->deadline=now+(uint32_t)(ins->a ? ins->a : 1);
        p->waiting=1; p->pc++; return;
      case 3:
        rc=condition(p,ins->a,ins->b);
        if (rc<0) { fault(p,rc); return; }
        if (!rc) return;
        p->pc++; break;
      case 4: p->pc=(uint32_t)ins->a; break;
      case 5:
        rc=condition(p,ins->a,ins->b);
        if (rc<0) { fault(p,rc); return; }
        p->pc=rc ? (uint32_t)ins->c : p->pc+1; break;
      case 6:
        p->owned|=1u<<(unsigned)ins->a;
        rc=p->io.position(p->io.context,(unsigned)ins->a,ins->b,ins->c);
        if (rc<0) { fault(p,rc); return; }
        p->moving=ins->a; p->pc++; return;
      default: fault(p,-EPROTO); return;
    }
  }
}
