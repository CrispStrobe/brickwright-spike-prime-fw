/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "device.h"
#include "motor.h"
#include <arch/board/board_legoport.h>
#include <arch/board/board_lump.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
struct port_state {
  int fd,mode,braking,valid,deferred;
  int32_t delta,velocity;
  int64_t position,previous;
  int32_t speed,value;
  uint64_t sampled,previous_sampled;
  struct bw_motor_control control;
};
static struct port_state g_ports[6];
static uint64_t g_now;
static int call(int fd,int op,unsigned long arg) { return ioctl(fd,op,arg)<0 ? -errno : 0; }
static int open_port(unsigned port,unsigned type,int mode) {
  struct lump_device_info_s info;
  struct port_state *p;
  char path[24]; int rc;
  if(port>=6)return -EINVAL;
  p=g_ports+port;
  if(p->fd<0) {
    snprintf(path,sizeof(path),"/dev/legoport%u",port);
    p->fd=open(path,O_RDWR|O_NONBLOCK);
    if(p->fd<0)return -errno;
  }
  rc=call(p->fd,LEGOPORT_LUMP_GET_INFO,(unsigned long)&info);
  if(rc<0)return rc;
  if(!(info.flags&LUMP_FLAG_SYNCED))return -EAGAIN;
  if(type==48) {
    if(info.type_id!=48 && info.type_id!=49 && info.type_id!=46 && info.type_id!=65)return -ENODEV;
  } else if(info.type_id!=type)return -ENODEV;
  if(p->mode!=mode) {
    rc=call(p->fd,LEGOPORT_LUMP_SELECT,(unsigned long)mode);
    if(rc<0)return rc;
    p->mode=mode; p->valid=0;
  }
  return 0;
}
static int poll_port(unsigned port) {
  struct port_state *p=g_ports+port;
  struct lump_data_frame_s frame;
  unsigned budget=16; int rc, updated=0;
  while(budget--) {
    rc=call(p->fd,LEGOPORT_LUMP_POLL_DATA,(unsigned long)&frame);
    if(rc==-EAGAIN)break;
    if(rc<0)return rc;
    if(frame.mode!=p->mode)continue;
    if(port<2) {
      uint32_t raw; int32_t degrees;
      if(frame.len<4)return -EPROTO;
      raw=(uint32_t)frame.data[0]|((uint32_t)frame.data[1]<<8)|((uint32_t)frame.data[2]<<16)|((uint32_t)frame.data[3]<<24);
      degrees=raw<=INT32_MAX ? (int32_t)raw : -(int32_t)(~raw)-1;
      /* Keep the prior tick as the baseline while draining this tick,
       * including another poll at the same timestamp. */
      if(!updated && (!p->valid || g_now!=p->sampled)) {
        p->previous=p->position;
        p->previous_sampled=p->valid ? p->sampled : g_now;
      }
      p->position=(int64_t)degrees*1000;
    } else if(port==3) {
      if(frame.len<2)return -EPROTO;
      uint16_t raw=(uint16_t)frame.data[0]|((uint16_t)frame.data[1]<<8);
      p->value=raw==UINT16_MAX ? -1 : raw;
    } else {
      if(frame.len<1)return -EPROTO;
      p->value=frame.data[0];
    }
    updated=1;
  }
  if(updated) {
    if(port<2 && p->valid && g_now>p->previous_sampled) {
      uint64_t elapsed=g_now-p->previous_sampled;
      int64_t measured=elapsed>INT64_MAX ? 0 :
        (p->position-p->previous)/(int64_t)elapsed;
      p->speed=measured<INT32_MIN ? INT32_MIN : measured>INT32_MAX ? INT32_MAX : (int32_t)measured;
    }
    p->sampled=g_now; p->valid=1;
  }
  return p->valid && g_now>=p->sampled && g_now-p->sampled<=100 ? 0 : -EAGAIN;
}
static int speed(void *ctx,unsigned port,int32_t value) {
  int rc; (void)ctx;
  if(port>=2 || value < -1110 || value>1110)return -EINVAL;
  rc=open_port(port,48,2); if(rc<0)return rc;
  g_ports[port].braking=0; g_ports[port].deferred=0; bw_motor_speed(&g_ports[port].control,value); return 0;
}
static int position(void *ctx,unsigned port,int32_t degrees,int32_t velocity) {
  int rc; (void)ctx;
  if(port>=2 || degrees < -36000 || degrees>36000 || velocity<1 || velocity>1110)return -EINVAL;
  rc=open_port(port,48,2); if(rc<0)return rc;
  rc=poll_port(port); if(rc<0 && rc!=-EAGAIN)return rc;
  g_ports[port].braking=0;
  if(rc==-EAGAIN) {
    g_ports[port].delta=degrees;g_ports[port].velocity=velocity;g_ports[port].deferred=1;return 0;
  }
  g_ports[port].deferred=0;
  bw_motor_position(&g_ports[port].control,g_ports[port].position,degrees,velocity); return 0;
}
static int brake(void *ctx,unsigned port) {
  struct port_state *p; (void)ctx;
  if(port>=2)return -EINVAL;
  p=g_ports+port; if(p->fd<0)return 0;
  memset(&p->control,0,sizeof(p->control)); p->deferred=0; p->braking=1;
  return call(p->fd,LEGOPORT_PWM_BRAKE,0);
}
static int done(void *ctx,unsigned port) {
  struct port_state *p; (void)ctx;
  if(port>=2)return -EINVAL;
  p=g_ports+port;
  if(p->deferred || !p->valid)return 0;
  if(g_now<p->sampled || g_now-p->sampled>100)return -EIO;
  if(p->braking)return p->speed>=-20 && p->speed<=20;
  return !p->control.active;
}
static int sensor(void *ctx,unsigned predicate,int32_t *value) {
  unsigned port,type; int mode,rc; (void)ctx;
  if(predicate==1 || predicate==2) {port=3;type=62;mode=0;}
  else if(predicate==3) {port=4;type=63;mode=1;}
  else if(predicate>=4 && predicate<=6) {port=2;type=61;mode=predicate==4 ? 0 : 1;}
  else return -EINVAL;
  rc=open_port(port,type,mode); if(rc<0)return rc;
  rc=poll_port(port); if(rc<0)return rc;
  *value=g_ports[port].value; return 0;
}
void bw_device_init(struct bw_program_io *io) {
  unsigned i; g_now=0; memset(g_ports,0,sizeof(g_ports));
  for(i=0;i<6;i++) {g_ports[i].fd=-1;g_ports[i].mode=-1;}
  *io=(struct bw_program_io){speed,position,done,brake,sensor,NULL};
}
int bw_device_tick(uint64_t now) {
  unsigned i;
  if(now<g_now)return -EINVAL;
  g_now=now;
  for(i=0;i<2;i++) if(g_ports[i].fd>=0) {
    struct port_state *p=g_ports+i;
    int rc=poll_port(i);
    if(rc==-EAGAIN && !p->valid)continue; /* initial mode negotiation */
    if(rc<0)return rc;
    if(p->deferred) {
      bw_motor_position(&p->control,p->position,p->delta,p->velocity);p->deferred=0;
    }
    if(p->control.active && !p->braking) {
      int32_t duty=bw_motor_step(&p->control,now,p->position,p->speed);
      rc=call(p->fd,p->control.active ? LEGOPORT_PWM_SET_DUTY : LEGOPORT_PWM_BRAKE,(unsigned long)(long)duty);
      if(rc<0)return rc;
    }
  }
  return 0;
}
void bw_device_release(void) {
  unsigned i;
  for(i=0;i<6;i++) {
    if(g_ports[i].fd>=0) {
      if(i<2)(void)brake(NULL,i);
      (void)close(g_ports[i].fd);
    }
    memset(g_ports+i,0,sizeof(g_ports[i]));
    g_ports[i].fd=-1;g_ports[i].mode=-1;
  }
}

void bw_device_snapshot(volatile struct bw_program_debug *out) {
  out->position_a_deg=(int32_t)(g_ports[0].position/1000);
  out->position_b_deg=(int32_t)(g_ports[1].position/1000);
  out->speed_a_dps=g_ports[0].speed;out->speed_b_dps=g_ports[1].speed;
  out->duty_a=g_ports[0].braking ? 0 : g_ports[0].control.duty;
  out->duty_b=g_ports[1].braking ? 0 : g_ports[1].control.duty;
  out->valid_ports=(g_ports[0].valid ? 1u : 0u)|(g_ports[1].valid ? 2u : 0u);
}
