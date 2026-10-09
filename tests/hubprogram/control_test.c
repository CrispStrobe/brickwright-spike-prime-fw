/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
/* Substitute only the syscall boundary; compile the actual board ABI and
 * device implementation, without a NuttX kernel or attached motors. */
#define open fixture_open
#define close fixture_close
#define ioctl fixture_ioctl
#include "../../apps/hubprogram/device.c"
#undef open
#undef close
#undef ioctl

static struct lump_data_frame_s frames[6][32];
static unsigned head[6], tail[6], polls, writes, brakes, closes, session_polls;
static uint64_t sessions[6];
static int fail_op, fail_errno, open_error, synced=1, type_id=48;
static int port_type[6], unavailable[6];
static unsigned port_writes[6], port_brakes[6], selections[6];
static int32_t written;
int fixture_open(const char *path,int flags,...) {
  (void)flags;
  if(open_error) {errno=open_error;return -1;}
  unsigned port=(unsigned)atoi(path+13);
  if(unavailable[port]) {errno=ENOENT;return -1;}
  return 100+port;
}
int fixture_close(int fd) {(void)fd;closes++;return 0;}
int fixture_ioctl(int fd,unsigned long op,...) {
  va_list ap; unsigned long arg; unsigned port=(unsigned)(fd-100);
  assert(port<6);
  va_start(ap,op);arg=va_arg(ap,unsigned long);va_end(ap);
  if((int)op==fail_op) {errno=fail_errno;return -1;}
  if(op==LEGOPORT_LUMP_GET_INFO) {
    struct lump_device_info_s *info=(void *)arg;
    memset(info,0,sizeof(*info));info->type_id=port_type[port] ? port_type[port] : type_id;
    info->flags=synced ? LUMP_FLAG_SYNCED : 0;return 0;
  }
  if(op==LEGOPORT_LUMP_SELECT) {selections[port]++;return 0;}
  if(op==LEGOPORT_LUMP_POLL_DATA_SESSION) {
    struct lump_data_session_frame_s *sample=(void *)arg;
    session_polls++;
    if(head[port]==tail[port]) {errno=EAGAIN;return -1;}
    memset(sample,0,sizeof(*sample));sample->session=sessions[port];
    sample->frame=frames[port][head[port]++];return 0;
  }
  if(op==LEGOPORT_LUMP_POLL_DATA) {
    polls++;
    if(head[port]==tail[port]) {errno=EAGAIN;return -1;}
    *(struct lump_data_frame_s *)arg=frames[port][head[port]++];return 0;
  }
  if(op==LEGOPORT_PWM_SET_DUTY) {writes++;port_writes[port]++;written=(int32_t)(long)arg;return 0;}
  if(op==LEGOPORT_PWM_BRAKE) {brakes++;port_brakes[port]++;return 0;}
  assert(0);return -1;
}
static void queue(unsigned port,int mode,int32_t degrees) {
  struct lump_data_frame_s *f=&frames[port][tail[port]++];
  uint32_t raw=(uint32_t)degrees;unsigned i;
  assert(tail[port]<=32);memset(f,0,sizeof(*f));f->mode=mode;f->len=4;
  for(i=0;i<4;i++)f->data[i]=(uint8_t)(raw>>(i*8));
}
static struct bw_program_io reset(void) {
  struct bw_program_io io;
  bw_device_release();memset(head,0,sizeof(head));memset(tail,0,sizeof(tail));
  polls=writes=brakes=closes=session_polls=0;
  for(unsigned i=0;i<6;i++) {sessions[i]=1;}
  fail_op=fail_errno=open_error=0;synced=1;type_id=48;
  memset(port_type,0,sizeof(port_type));memset(unavailable,0,sizeof(unavailable));
  memset(port_writes,0,sizeof(port_writes));memset(port_brakes,0,sizeof(port_brakes));
  memset(selections,0,sizeof(selections));
  bw_device_init(&io);return io;
}
static void motor_tests(void) {
  struct bw_motor_control m={0};int32_t duty;
  bw_motor_speed(&m,1110);duty=bw_motor_step(&m,0,0,0);
  assert(m.reference==20 && duty>0 && duty<10000);
  assert(bw_motor_step(&m,0,0,0)==duty && m.reference==20);
  bw_motor_step(&m,10,0,0);assert(m.reference==40);
  bw_motor_step(&m,5,0,0);assert(m.reference==40 && m.last==10);
  bw_motor_step(&m,10000,0,0);assert(m.reference==140);
  bw_motor_speed(&m,0);bw_motor_step(&m,10010,0,0);assert(m.reference==100);
  bw_motor_speed(&m,-1110);bw_motor_step(&m,10020,0,0);assert(m.reference==80);
  for(unsigned i=0;i<100;i++)bw_motor_step(&m,10030+i*50,0,INT32_MAX);
  assert(m.integral==-2000000 && m.duty==-10000);
  memset(&m,0,sizeof(m));bw_motor_position(&m,100000,-90,300);
  assert(m.target==10000);bw_motor_step(&m,0,100000,0);assert(m.reference<0);
  for(unsigned i=1;i<100;i++)bw_motor_step(&m,i*10,100000,0);
  assert(m.active); /* A stalled encoder never completes a position move. */
  bw_motor_step(&m,1000,10000,0);assert(m.active && m.settled==1);
  bw_motor_step(&m,1000,10000,0);assert(m.settled==1);
  bw_motor_step(&m,1010,10000,21);assert(m.settled==0);
  bw_motor_step(&m,1020,10000,0);bw_motor_step(&m,1030,10000,0);
  assert(bw_motor_step(&m,1040,10000,0)==0 && !m.active);
  bw_motor_speed(&m,300);assert(m.reference==0 && m.integral==0 && !m.timed);
}
static void device_tests(void) {
  struct bw_program_io io=reset();struct bw_program_debug debug={0};unsigned before;
  assert(io.motor(NULL,6,100)==-EINVAL && io.motor(NULL,0,1111)==-EINVAL);
  open_error=EBUSY;assert(io.motor(NULL,0,100)==-EBUSY);open_error=0;
  synced=0;assert(io.motor(NULL,0,100)==-EAGAIN);synced=1;
  type_id=62;assert(io.motor(NULL,0,100)==-ENODEV);type_id=48;
  assert(io.position(NULL,0,90,300)==0 && io.done(NULL,0)==0);
  assert(bw_device_tick(0)==0 && writes==0);
  queue(0,1,999);queue(0,2,0);assert(bw_device_tick(10)==0 && writes==1);
  queue(0,2,1);queue(0,2,3);assert(bw_device_tick(20)==0);
  bw_device_snapshot(&debug);assert(debug.position_a_deg==3 && debug.speed_a_dps==300);
  queue(0,2,4);assert(bw_device_tick(20)==0);
  bw_device_snapshot(&debug);assert(debug.speed_a_dps==400);
  queue(0,2,-1);assert(bw_device_tick(30)==0);
  bw_device_snapshot(&debug);assert(debug.speed_a_dps==-500);
  before=polls;assert(bw_device_tick(29)==-EINVAL && polls==before);
  assert(io.done(NULL,0)==0);assert(bw_device_tick(131)==-EAGAIN);
  assert(io.done(NULL,0)==-EIO);
  bw_device_release();assert(closes==1);bw_device_snapshot(&debug);
  assert(debug.valid_ports==0 && debug.speed_a_dps==0 && debug.duty_a==0);
  io=reset();assert(io.position(NULL,0,90,300)==0);
  assert(io.motor(NULL,0,100)==0);queue(0,2,0);assert(bw_device_tick(10)==0);
  assert(!g_ports[0].deferred && !g_ports[0].control.positioning);
  assert(io.brake(NULL,0)==0 && brakes==1);queue(0,2,10);
  assert(bw_device_tick(20)==0 && io.done(NULL,0)==0);
  queue(0,2,10);assert(bw_device_tick(30)==0 && io.done(NULL,0)==1);
  assert(io.motor(NULL,0,100)==0);queue(0,2,10);assert(bw_device_tick(40)==0);
  assert(g_ports[0].control.reference==20 && written>0);
  fail_op=LEGOPORT_PWM_SET_DUTY;fail_errno=EIO;queue(0,2,10);
  assert(bw_device_tick(50)==-EIO);fail_op=0;
  queue(0,2,10);frames[0][tail[0]-1].len=3;assert(bw_device_tick(60)==-EPROTO);
  fail_op=LEGOPORT_LUMP_POLL_DATA;fail_errno=ENODEV;assert(bw_device_tick(70)==-ENODEV);
  fail_op=0;bw_device_release();
  assert(io.motor(NULL,0,-100)==0);queue(0,2,-1);
  assert(bw_device_tick(80)==0 && g_ports[0].control.reference==-20);
  bw_device_release();
}
static void sensor_tests(void) {
  struct bw_program_io io=reset();int32_t value;
  type_id=62;
  const int32_t distances[]={0,32767,32768,65534,65535};
  for(unsigned i=0;i<sizeof(distances)/sizeof(distances[0]);i++) {
    queue(3,0,distances[i]);frames[3][tail[3]-1].len=2;
    assert(io.sensor(NULL,1,&value)==0);
    assert(value==(distances[i]==65535 ? -1 : distances[i]));
  }
  bw_device_release();
}
static void six_port_tests(void) {
  struct bw_program_io io=reset();struct bw_program_debug debug={0};int32_t value;
  /* Real sensor identities are never relabelled by a motor command. */
  port_type[2]=61;port_type[3]=62;port_type[4]=63;
  for(unsigned port=2;port<5;port++) {
    assert(io.motor(NULL,port,100)==-ENODEV);
    assert(io.position(NULL,port,90,300)==-ENODEV);
    assert(io.done(NULL,port)==-ENODEV);
    assert(io.brake(NULL,port)==0 && !port_brakes[port] && !selections[port]);
  }
  unavailable[5]=1;assert(io.motor(NULL,5,100)==-ENOENT);
  unavailable[5]=0;port_type[5]=49;
  assert(io.position(NULL,5,90,300)==0 && io.done(NULL,5)==0);
  queue(5,2,-10);assert(bw_device_tick(10)==0);
  assert(g_ports[5].control.target==80000 && port_writes[5]==1);
  queue(5,2,80);assert(bw_device_tick(20)==0 && !io.done(NULL,5));
  for(unsigned t=30;t<=50;t+=10) {queue(5,2,80);assert(!bw_device_tick(t));}
  assert(io.done(NULL,5)==1 && port_brakes[5]==1);
  queue(2,0,7);frames[2][tail[2]-1].len=1;
  assert(!io.sensor(NULL,4,&value) && value==7);
  queue(3,0,250);frames[3][tail[3]-1].len=2;
  assert(!io.sensor(NULL,1,&value) && value==250);
  queue(4,1,1);frames[4][tail[4]-1].len=1;
  assert(!io.sensor(NULL,3,&value) && value==1);
  bw_device_snapshot(&debug);assert(debug.valid_ports==0);
  bw_device_release();assert(closes==4);
  assert(!port_brakes[2] && !port_brakes[3] && !port_brakes[4]);
  /* This separate attached-motor fixture covers all six physical ports. */
  io=reset();
  const int types[]={48,49,46,65,48,49};
  for(unsigned port=0;port<6;port++) {
    port_type[port]=types[port];assert(!io.motor(NULL,port,100));queue(port,2,0);
  }
  assert(!bw_device_tick(10));
  for(unsigned port=0;port<6;port++) {
    assert(port_writes[port]==1);queue(port,2,-2);
  }
  assert(!bw_device_tick(20));
  for(unsigned port=0;port<6;port++) {
    assert(g_ports[port].speed==-200);assert(!io.brake(NULL,port));queue(port,2,-2);
  }
  assert(!bw_device_tick(30));
  for(unsigned port=0;port<6;port++)assert(io.done(NULL,port)==1);
  bw_device_snapshot(&debug);assert(debug.valid_ports==3);
  bw_device_release();assert(closes==6);
  for(unsigned port=0;port<6;port++)assert(port_brakes[port]==2);
  /* Replacement with a sensor must reject demand and cleanup PWM. */
  io=reset();assert(!io.motor(NULL,5,100));queue(5,2,0);assert(!bw_device_tick(10));
  unsigned selected=selections[5], written_before=port_writes[5], braked=port_brakes[5];
  port_type[5]=62;assert(bw_device_tick(20)==-ENODEV);
  assert(io.done(NULL,5)==-ENODEV && io.brake(NULL,5)==-ENODEV);
  bw_device_release();assert(selections[5]==selected && port_writes[5]==written_before && port_brakes[5]==braked);
}
static void distance_frame(unsigned port,int mode,unsigned raw,unsigned len) {
  queue(port,mode,(int32_t)raw);frames[port][tail[port]-1].len=(uint8_t)len;
}
static void explicit_sensor_tests(void) {
  struct bw_program_io io=reset();int32_t value;unsigned before;
  type_id=62;
  for(unsigned port=0;port<6;port++) {
    distance_frame(port,0,300+port,2);value=-999;
    assert(!io.sensor(NULL,0x101+(port<<3),&value) && value==(int32_t)(300+port));
    value=-999;assert(io.sensor(NULL,0x102+(port<<3),&value)==-EAGAIN && value==-999);
  }
  assert(session_polls==12 && !writes && !brakes);
  const unsigned invalid[]={0,7,0x100,0x103,0x107,0x128,0x12b,0x130,0x141,UINT32_MAX};
  before=session_polls;
  for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
    value=-999;assert(io.sensor(NULL,invalid[i],&value)==-EINVAL && value==-999);
  }
  assert(io.sensor(NULL,0x101,NULL)==-EINVAL && session_polls==before);
  /* Explicit reads never substitute a recent legacy cached value. */
  distance_frame(3,0,444,2);assert(!io.sensor(NULL,1,&value) && value==444);
  value=-999;assert(io.sensor(NULL,0x119,&value)==-EAGAIN && value==-999);
  distance_frame(3,0,555,2);assert(!io.sensor(NULL,0x119,&value) && value==555);
  /* Replacement with identical payload still latches ESTALE, even if caught. */
  sessions[3]=2;distance_frame(3,0,555,2);value=-999;
  assert(io.sensor(NULL,0x119,&value)==-ESTALE && value==-999);
  before=session_polls;distance_frame(3,0,666,2);
  assert(io.sensor(NULL,0x11a,&value)==-ESTALE && value==-999 && session_polls==before);
  assert(!io.sensor(NULL,1,&value) && value==666);value=-999;
  assert(io.sensor(NULL,0x119,&value)==-ESTALE && value==-999);
  bw_device_release();distance_frame(3,0,777,2);
  assert(!io.sensor(NULL,0x119,&value) && value==777);
  io=reset();type_id=62;
  /* Failed first frame does not bind a session; successful unknown does. */
  sessions[4]=0;distance_frame(4,0,100,2);value=-999;
  assert(io.sensor(NULL,0x121,&value)==-EPROTO && value==-999);
  sessions[4]=7;distance_frame(4,1,100,2);
  assert(io.sensor(NULL,0x121,&value)==-EPROTO && value==-999);
  distance_frame(4,0,100,1);assert(io.sensor(NULL,0x121,&value)==-EPROTO && value==-999);
  distance_frame(4,0,100,LUMP_MAX_PAYLOAD+1);assert(io.sensor(NULL,0x121,&value)==-EPROTO && value==-999);
  sessions[4]=8;distance_frame(4,0,65535,2);assert(!io.sensor(NULL,0x121,&value) && value==-1);
  sessions[4]=9;distance_frame(4,1,100,1);value=-999;
  assert(io.sensor(NULL,0x121,&value)==-ESTALE && value==-999);
  /* Wrong type and syscall failures preserve output and cause no PWM. */
  type_id=48;value=-999;before=session_polls;
  assert(io.sensor(NULL,0x129,&value)==-ENODEV && value==-999 && session_polls==before);
  type_id=62;synced=0;assert(io.sensor(NULL,0x129,&value)==-EAGAIN && value==-999);synced=1;
  fail_op=LEGOPORT_LUMP_POLL_DATA_SESSION;fail_errno=EIO;
  assert(io.sensor(NULL,0x129,&value)==-EIO && value==-999);fail_op=0;
  assert(!writes && !brakes);
  bw_device_release();
}
int main(void) {struct bw_program_io io;bw_device_init(&io);explicit_sensor_tests();motor_tests();device_tests();sensor_tests();six_port_tests();puts("hubprogram motor/device tests passed");return 0;}
