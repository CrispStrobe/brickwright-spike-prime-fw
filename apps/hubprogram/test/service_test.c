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
static unsigned saves,loads,releases;
#ifdef BW_SIM_SESSION_DIAGNOSTICS
static unsigned diagnostics;
void bw_lump_request_mailbox_step(void) { diagnostics++; }
#endif
static pid_t task_create(const char *n,int p,int s,int (*f)(int,char **),char **a) {
  (void)n;(void)p;(void)s;(void)f;(void)a;return 1;
}
void bw_device_init(struct bw_program_io *io){memset(io,0,sizeof(*io));}
int bw_device_tick(uint64_t now){(void)now;return 0;}
void bw_device_release(void){releases++;}
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
static int fixture_motor(void *ctx,unsigned port,int32_t speed) {
  (void)ctx;assert(port<6 && speed==300);return port==3 ? -ENODEV : 0;
}
static int fixture_position(void *ctx,unsigned port,int32_t degrees,int32_t speed) {
  (void)ctx;assert(port<6 && degrees==90 && speed==300);return port==4 ? -ENOENT : 0;
}
static int fixture_done(void *ctx,unsigned port) {(void)ctx;assert(port<6);return 1;}
static int fixture_brake(void *ctx,unsigned port) {(void)ctx;assert(port<6);return 0;}
static unsigned sensor_reads;
static int fixture_sensor(void *ctx,unsigned predicate,int32_t *value) {
  (void)ctx;(void)predicate;sensor_reads++;*value=0;return 0;
}
static void sensor_lifecycle_guards(void) {
  const enum bw_program_state states[]={BW_PROGRAM_EMPTY,BW_PROGRAM_READY,BW_PROGRAM_COMPLETE,BW_PROGRAM_STOPPED,BW_PROGRAM_FAULT};
  int32_t value=-999;unsigned before=sensor_reads;
  g_program.io.sensor=fixture_sensor;
  for(unsigned i=0;i<sizeof(states)/sizeof(states[0]);i++) {
    g_program.state=states[i];
    assert(bw_program_service_sensor(0x121,&value)==-EINVAL && value==-999 && sensor_reads==before);
  }
  g_program.state=BW_PROGRAM_RUNNING;
  assert(bw_program_service_sensor(0x121,NULL)==-EINVAL && sensor_reads==before);
  assert(!bw_program_service_sensor(0x121,&value) && value==0 && sensor_reads==before+1);
  g_program.io.sensor=NULL;value=-999;
  assert(bw_program_service_sensor(0x121,&value)==-EINVAL && value==-999);
}
static void restart_transport(void) {
  const struct bw_instruction code[]={{0,0,0,0}};
  const struct bw_program_io io={fixture_motor,fixture_position,fixture_done,fixture_brake,fixture_sensor,NULL};
  uint8_t packet[8]={BW_PROGRAM_REQUEST,1,3,0,42,0,0,0},reply[20];
  const enum bw_program_state states[]={BW_PROGRAM_COMPLETE,BW_PROGRAM_STOPPED,BW_PROGRAM_FAULT};
  unsigned i;
  bw_program_init(&g_program,&io);assert(!bw_program_load(&g_program,42,code,1));
  for(i=0;i<sizeof(states)/sizeof(states[0]);i++) {
    g_program.state=states[i];g_program.error=-ENODEV;g_program.pc=1;
    /* A previous Python execution must unwind before its retained source can
     * be started by any other transport. */
    g_python_active=1;
    assert(bw_program_service_request(2,packet,8,reply)==-EBUSY);
    assert(reply[2]==3 && reply[3]==states[i] && g_program.error==-ENODEV);
    g_python_active=0;
    assert(!bw_program_service_request(2,packet,8,reply));
    assert(reply[2]==3 && reply[3]==BW_PROGRAM_RUNNING && reply[4]==42);
    assert(!g_program.pc && !g_program.error && !reply[12] && !reply[18] && !reply[19]);
    assert(bw_program_service_request(1,packet,8,reply)==-EBUSY);
    packet[2]=4;assert(!bw_program_service_request(1,packet,8,reply));packet[2]=3;
  }
}
static void six_port_wrappers(void) {
  g_program.state=BW_PROGRAM_RUNNING;g_program.owned=0;
  g_program.io.motor=fixture_motor;g_program.io.position=fixture_position;g_program.io.done=fixture_done;
  assert(g_bw_program_storage_abi==1u && g_bw_program_debug.version==1);
  assert(g_bw_program_addressed_sensor_abi==1u);
  for(unsigned port=0;port<6;port++) {
    assert(bw_program_service_motor(port,300)==(port==3 ? -ENODEV : 0));
    assert(bw_program_service_position(port,90,300)==(port==4 ? -ENOENT : 0));
    assert(bw_program_service_done(port)==1);
  }
  assert(g_program.owned==63);
  assert(bw_program_service_motor(6,300)==-EINVAL);
  assert(bw_program_service_position((unsigned)-1,90,300)==-EINVAL);
  assert(bw_program_service_done(6)==-EINVAL);
  g_program.state=BW_PROGRAM_READY;
  assert(bw_program_service_motor(5,300)==-EINVAL && bw_program_service_position(5,90,300)==-EINVAL);
  memset(&g_program.io,0,sizeof(g_program.io));g_program.owned=0;
}
int main(void) {
  uint8_t packet[20]={0x70,1,8,0,42,0,0,0},reply[20];unsigned i;
  six_port_wrappers();
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
  /* STOP must release ports without waiting for the next worker tick. */
  packet[2]=4;g_program.state=BW_PROGRAM_RUNNING;
  assert(bw_program_service_request(1,packet,8,reply)==0 && releases==1);
  packet[2]=9;assert(bw_program_service_request(1,packet,8,reply)==0);
  assert(g_program.state==BW_PROGRAM_READY && releases>=1);
  /* A still-unwinding Python VM retains ports until its worker returns. */
  g_python_active=1;g_program.state=BW_PROGRAM_RUNNING;i=releases;
  packet[2]=4;assert(bw_program_service_request(1,packet,8,reply)==0 && releases==i);
  packet[2]=9;assert(bw_program_service_request(1,packet,8,reply)==-EBUSY && releases==i);
  g_python_active=0;assert(bw_program_service_request(1,packet,8,reply)==0 && releases>i);
  sensor_lifecycle_guards();restart_transport();
#ifdef BW_SIM_SESSION_DIAGNOSTICS
  g_program.state=BW_PROGRAM_READY;g_program.error=0;
  assert(bw_program_service_poll()==-ECANCELED && diagnostics==1);
#endif
  puts("service: fixed storage slot, transport guards, oversized mailbox rejection and retained-program restart passed");
  return 0;
}
