/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "../upload.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct devices { int speed[2], moving[2], brakes[2], sensor, failure; };
static int motor(void *ctx,unsigned port,int32_t speed) {
  struct devices *d=ctx; d->speed[port]=speed; return d->failure;
}
static int position(void *ctx,unsigned port,int32_t degrees,int32_t speed) {
  struct devices *d=ctx; assert(degrees==-90); assert(speed==500); d->moving[port]=1; return d->failure;
}
static int done(void *ctx,unsigned port) { return !((struct devices *)ctx)->moving[port]; }
static int brake(void *ctx,unsigned port) {
  struct devices *d=ctx; d->speed[port]=0; d->moving[port]=0; d->brakes[port]++; return 0;
}
static int sensor(void *ctx,unsigned predicate,int32_t *value) {
  struct devices *d=ctx; assert(predicate==1); *value=d->sensor; return 0;
}
static void init(struct bw_program *p,struct devices *d) {
  struct bw_program_io io={motor,position,done,brake,sensor,d};
  memset(d,0,sizeof(*d)); bw_program_init(p,&io);
}
static void put32(uint8_t *p,uint32_t v) { unsigned i; for(i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i)); }
static void header(uint8_t *b,unsigned op,uint32_t id) {
  memset(b,0,20); b[0]=BW_PROGRAM_REQUEST; b[1]=1; b[2]=(uint8_t)op; put32(b+4,id);
}
static void lifecycle(void) {
  struct bw_program p; struct devices d;
  const struct bw_instruction code[]={{1,0,400,0},{1,1,-400,0},{2,10,0,0},{0,0,0,0}};
  init(&p,&d); assert(bw_program_load(&p,7,code,4)==0);
  assert(bw_program_start(&p,8,100)==-EINVAL);
  assert(bw_program_start(&p,7,100)==0); bw_program_tick(&p,100);
  assert(d.speed[0]==400 && d.speed[1]==-400 && p.pc==3);
  assert(bw_program_load(&p,9,code,4)==-EBUSY);
  bw_program_tick(&p,109); assert(p.state==BW_PROGRAM_RUNNING && d.speed[0]==400);
  bw_program_tick(&p,110); assert(d.brakes[0]==1 && d.brakes[1]==1);
  bw_program_tick(&p,111); assert(p.state==BW_PROGRAM_COMPLETE);
}
static void position_and_sensor(void) {
  struct bw_program p; struct devices d;
  const struct bw_instruction code[]={{1,0,300,0},{6,1,-90,500},{3,1,250,0},{0,0,0,0}};
  init(&p,&d); d.sensor=-1; assert(!bw_program_load(&p,1,code,4)); assert(!bw_program_start(&p,1,0));
  bw_program_tick(&p,0); assert(d.speed[0]==300 && d.moving[1]);
  bw_program_tick(&p,10); assert(p.pc==2);
  d.moving[1]=0; bw_program_tick(&p,20); assert(p.pc==2);
  d.sensor=300; bw_program_tick(&p,30); assert(p.pc==2);
  d.sensor=249; bw_program_tick(&p,40); assert(p.ending);
  bw_program_tick(&p,50); assert(p.state==BW_PROGRAM_COMPLETE);
}
static void bounds_and_failures(void) {
  struct bw_program p; struct devices d; struct bw_instruction code[256]; unsigned i;
  init(&p,&d); for(i=0;i<255;i++) code[i]=(struct bw_instruction){2,0,0,0};
  code[255]=(struct bw_instruction){0,0,0,0}; assert(!bw_program_load(&p,1,code,256));
  code[0].a=-1; assert(bw_program_load(&p,2,code,256)==-EINVAL && p.id==1);
  code[0]=(struct bw_instruction){4,0,0,0}; assert(!bw_program_load(&p,2,code,256));
  assert(!bw_program_start(&p,2,0)); bw_program_tick(&p,1); assert(p.pc==0 && p.state==BW_PROGRAM_RUNNING);
  bw_program_tick(&p,120000); assert(p.state==BW_PROGRAM_FAULT && p.error==-ETIMEDOUT);
  code[0]=(struct bw_instruction){1,1,500,0}; assert(!bw_program_load(&p,3,code,256));
  d.failure=-ENODEV; assert(!bw_program_start(&p,3,0)); bw_program_tick(&p,1);
  assert(p.state==BW_PROGRAM_FAULT && p.error==-ENODEV && d.brakes[1]==1 && d.brakes[0]==0);
  d.failure=0; assert(!bw_program_load(&p,4,code,256)); assert(!bw_program_start(&p,4,0));
  bw_program_tick(&p,10); assert(d.speed[1]==500); assert(!bw_program_stop(&p));
  assert(d.speed[1]==0 && p.state==BW_PROGRAM_STOPPED);
  assert(!bw_program_load(&p,5,code,256)); assert(!bw_program_start(&p,5,10));
  bw_program_tick(&p,9); assert(p.state==BW_PROGRAM_FAULT && p.error==-ERANGE);
}
static void upload(void) {
  struct bw_program p; struct devices d; struct bw_program_upload u;
  uint8_t data[20],reply[20],bytes[32]={0}; unsigned offset;
  memset(&u,0,sizeof(u)); init(&p,&d); put32(bytes,1); put32(bytes+8,500);
  header(data,0,9); put32(data+8,2); put32(data+12,bw_program_crc32(bytes,32));
  assert(!bw_program_request(&p,&u,1,0,data,16,reply));
  assert(reply[4]==9 && reply[5]==0);
  header(data,1,9); memcpy(data+10,bytes,10);
  assert(bw_program_request(&p,&u,2,1,data,20,reply)==-EINVAL);
  assert(!bw_program_request(&p,&u,1,1,data,20,reply));
  assert(!bw_program_request(&p,&u,1,2,data,20,reply)); assert(u.received==10);
  data[10]^=1; assert(bw_program_request(&p,&u,1,3,data,20,reply)==-EINVAL);
  header(data,2,9); assert(bw_program_request(&p,&u,1,4,data,8,reply)==-EINVAL);
  for(offset=10;offset<32;offset+=10) {
    unsigned n=32-offset; if(n>10)n=10; header(data,1,9); data[8]=(uint8_t)offset;
    memcpy(data+10,bytes+offset,n); assert(!bw_program_request(&p,&u,1,5,data,n+10,reply));
  }
  header(data,2,9); assert(!bw_program_request(&p,&u,1,6,data,8,reply));
  assert(p.state==BW_PROGRAM_READY && p.code[0].b==500);
  header(data,3,9); assert(!bw_program_request(&p,&u,2,7,data,8,reply));
  bw_program_tick(&p,7); assert(d.speed[0]==0 && p.ending);
  header(data,4,9); assert(!bw_program_request(&p,&u,2,8,data,8,reply));
  /* Reject corrupted upload while preserving committed code. */
  header(data,0,10); put32(data+8,1); put32(data+12,1);
  assert(!bw_program_request(&p,&u,1,9,data,16,reply));
  for(offset=0;offset<16;offset+=8) {
    header(data,1,10); data[8]=(uint8_t)offset;
    assert(!bw_program_request(&p,&u,1,10,data,18,reply));
  }
  header(data,2,10); assert(bw_program_request(&p,&u,1,11,data,8,reply)==-EBADMSG);
  assert(p.id==9 && p.code[0].b==500 && !u.active);
  header(data,0,11); put32(data+8,1); assert(!bw_program_request(&p,&u,1,12,data,16,reply));
  header(data,5,0); assert(!bw_program_request(&p,&u,2,30012,data,8,reply) && !u.active);
}
static void python_upload(void) {
  struct bw_program p;struct bw_program_upload u={0};struct devices d;
  uint8_t data[20],reply[20];unsigned offset;
  uint8_t source[4095];memset(source,' ',sizeof(source));source[0]='1';
  init(&p,&d);
  header(data,7,12);put32(data+8,4096);put32(data+12,0);
  assert(bw_program_request(&p,&u,1,0,data,16,reply)==-EINVAL && !u.active);
  put32(data+8,sizeof(source));put32(data+12,bw_program_crc32(source,sizeof(source)));
  assert(!bw_program_request(&p,&u,1,0,data,16,reply));
  for(offset=0;offset<sizeof(source);offset+=10) {
    unsigned n=sizeof(source)-offset;if(n>10)n=10;
    header(data,1,12);data[8]=(uint8_t)offset;data[9]=(uint8_t)(offset>>8);
    memcpy(data+10,source+offset,n);
    assert(!bw_program_request(&p,&u,1,1,data,n+10,reply));
  }
  header(data,2,12);assert(!bw_program_request(&p,&u,1,2,data,8,reply));
  assert(p.language==1 && p.count==4095 && p.source[4095]==0 && p.source[0]=='1');
  header(data,3,12);assert(!bw_program_request(&p,&u,1,3,data,8,reply));
  header(data,7,13);put32(data+8,1);
  assert(bw_program_request(&p,&u,1,4,data,16,reply)==-EBUSY);
  header(data,4,12);assert(!bw_program_request(&p,&u,1,5,data,8,reply));
  /* A NUL-containing source cannot replace the committed program. */
  header(data,7,13);put32(data+8,1);put32(data+12,bw_program_crc32((const uint8_t *)"",1));
  assert(!bw_program_request(&p,&u,1,6,data,16,reply));
  header(data,1,13);data[10]=0;assert(!bw_program_request(&p,&u,1,7,data,11,reply));
  header(data,2,13);assert(bw_program_request(&p,&u,1,8,data,8,reply)==-EINVAL);
  assert(p.id==12 && p.source[0]=='1' && !u.active);
  header(data,5,0);assert(bw_program_request(&p,&u,1,9,data,21,reply)==-EINVAL);
  assert(bw_program_request(&p,&u,1,9,NULL,0,reply)==-EINVAL);
}
int main(void) {
  assert(bw_program_crc32((const uint8_t *)"123456789",9)==0xcbf43926u);
  lifecycle(); position_and_sensor(); bounds_and_failures(); upload();python_upload();
  puts("firmware program lifecycle, feedback, boundaries and transactional upload: PASS"); return 0;
}
