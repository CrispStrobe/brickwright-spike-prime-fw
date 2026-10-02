/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#define _POSIX_C_SOURCE 200809L
#define SCHED_PRIORITY_DEFAULT 100
#include <assert.h>
#include <stdio.h>
#include <sys/types.h>
static pid_t task_create(const char *,int,int,int (*)(int,char **),char **);
#include "../service.c"
static unsigned saves,loads;
static pid_t task_create(const char *n,int p,int s,int (*f)(int,char **),char **a) {
  (void)n;(void)p;(void)s;(void)f;(void)a;return 1;
}
void bw_device_init(struct bw_program_io *io){memset(io,0,sizeof(*io));}
int bw_device_tick(uint64_t now){(void)now;return 0;}
void bw_device_release(void){}
void bw_device_snapshot(volatile struct bw_program_debug *d){(void)d;}
int bw_python_execute(const char *source){(void)source;return 0;}
int bw_program_save(const struct bw_program *p,uint32_t id,const char *path) {
  assert(p==&g_program && id==42 && !strcmp(path,"/mnt/flash/brickwright.program"));
  saves++;return 0;
}
int bw_program_restore(struct bw_program *p,uint32_t id,const char *path) {
  assert(p==&g_program && id==42 && !strcmp(path,"/mnt/flash/brickwright.program"));
  loads++;p->state=BW_PROGRAM_READY;return 0;
}
int main(void) {
  uint8_t packet[20]={0x70,1,8,0,42,0,0,0},reply[20];unsigned i;
  g_initialized=1;g_program.state=BW_PROGRAM_READY;g_program.id=42;
  assert(bw_program_service_request(1,packet,8,reply)==0 && saves==1);
  assert(reply[2]==8 && reply[3]==BW_PROGRAM_READY && reply[4]==42);
  packet[2]=9;assert(bw_program_service_request(2,packet,8,reply)==0 && loads==1);
  g_python_active=1;
  assert(bw_program_service_request(1,packet,8,reply)==-EBUSY && loads==1);
  g_python_active=0;g_program.state=BW_PROGRAM_RUNNING;
  assert(bw_program_service_request(1,packet,8,reply)==-EBUSY && loads==1);
  g_program.state=BW_PROGRAM_READY;g_upload.active=1;g_upload.activity=now_ms();
  assert(bw_program_service_request(1,packet,8,reply)==-EBUSY && loads==1);
  g_upload.active=0;
  for(i=0;i<8;i++) {
    uint8_t value=packet[i];packet[i]=0xff;
    /* Changing a high ID byte passes framing, so only check reserved/header. */
    if(i<2 || i==3)assert(bw_program_service_request(1,packet,8,reply)==-EINVAL);
    packet[i]=value;
  }
  assert(bw_program_service_request(0,packet,8,reply)==-EINVAL);
  assert(bw_program_service_request(1,packet,9,reply)==-EINVAL);
  assert(bw_program_service_request(1,NULL,0,reply)==-EINVAL);
  assert(loads==1);
  g_bw_program_debug.length=8;g_bw_program_debug.request_seq=2;
  for(i=0;i<8;i++)g_bw_program_debug.request[i]=packet[i];
  debug_locked(now_ms());assert(loads==2 && g_bw_program_debug.reply_seq==2);
  /* Oversized mailbox packets cannot be accepted by truncating their prefix. */
  g_bw_program_debug.length=21;g_bw_program_debug.request_seq=4;
  debug_locked(now_ms());assert(loads==2 && g_bw_program_debug.reply_seq==4);
  puts("service: fixed storage slot, transport guards and oversized mailbox rejection passed");
  return 0;
}
