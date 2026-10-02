/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "service.h"
#include "device.h"
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <syslog.h>
#include <time.h>
#include <string.h>
#include "debug.h"
volatile struct bw_program_debug g_bw_program_debug={.magic=0x42574e50u,.version=1};
static struct bw_program g_program;
static struct bw_program_upload g_upload;
static pthread_mutex_t g_lock=PTHREAD_MUTEX_INITIALIZER;
static pid_t g_worker;
static unsigned g_initialized,g_python_active;
static uint64_t now_ms(void) {
  struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
  return (uint64_t)ts.tv_sec*1000+(uint64_t)ts.tv_nsec/1000000;
}
static void debug_locked(uint64_t now) {
  uint32_t seq=g_bw_program_debug.request_seq;
  if(seq && !(seq&1u) && seq!=g_bw_program_debug.reply_seq) {
    uint8_t packet[20],reply[20];uint32_t length=g_bw_program_debug.length;unsigned i;
    /* Reject an oversized packet rather than accepting its valid prefix. */
    if(length>20)length=0;
    for(i=0;i<length;i++)packet[i]=g_bw_program_debug.request[i];
    if(seq==g_bw_program_debug.request_seq) {
      if(g_python_active && length>=3 && (packet[2]==0 || packet[2]==2 || packet[2]==3 || packet[2]==7)) {
        uint8_t status[8]={BW_PROGRAM_REQUEST,1,5,0,0,0,0,0};
        (void)bw_program_request(&g_program,&g_upload,3,now,status,8,reply);
        reply[2]=packet[2];memcpy(reply+4,packet+4,4);
        reply[8]=(uint8_t)(-EBUSY);reply[9]=reply[10]=reply[11]=255;
      } else (void)bw_program_request(&g_program,&g_upload,3,now,packet,length,reply);
      for(i=0;i<20;i++)g_bw_program_debug.reply[i]=reply[i];
      g_bw_program_debug.reply_seq=seq;
    }
  }
  g_bw_program_debug.publish_seq++;
  g_bw_program_debug.clock_ms=(uint32_t)now;
  g_bw_program_debug.state=g_program.state;g_bw_program_debug.id=g_program.id;
  g_bw_program_debug.pc=g_program.pc;g_bw_program_debug.error=g_program.error;
  bw_device_snapshot(&g_bw_program_debug);
  g_bw_program_debug.publish_seq++;
}
static void tick_locked(void) {
  uint64_t now=now_ms(); int rc;
  debug_locked(now);
  if(g_program.state!=BW_PROGRAM_RUNNING)return;
  rc=bw_device_tick(now);
  if(rc<0 || now-g_program.started>=BW_PROGRAM_TIME_LIMIT) {
    (void)bw_program_stop(&g_program);g_program.state=BW_PROGRAM_FAULT;
    g_program.error=rc<0 ? rc : -ETIMEDOUT;return;
  }
  if(!g_program.language)bw_program_tick(&g_program,now);
}
static void *worker(void *arg) {
  (void)arg;
  for(;;) {
    struct timespec pause={0,10000000}; unsigned run;
    pthread_mutex_lock(&g_lock);
    tick_locked();
    run=g_program.state==BW_PROGRAM_RUNNING && g_program.language && !g_python_active;
    if(run)g_python_active=1;
    if(!g_python_active && (g_program.state==BW_PROGRAM_COMPLETE || g_program.state==BW_PROGRAM_STOPPED || g_program.state==BW_PROGRAM_FAULT))bw_device_release();
    pthread_mutex_unlock(&g_lock);
    if(run) {
      int rc=bw_python_execute(g_program.source);
      pthread_mutex_lock(&g_lock);
      if(g_program.state==BW_PROGRAM_RUNNING) {
        int stopped=bw_program_stop(&g_program);
        g_program.state=rc<0 || stopped<0 ? BW_PROGRAM_FAULT : BW_PROGRAM_RUNNING;
        if(g_program.state==BW_PROGRAM_RUNNING) {g_program.language=0;g_program.ending=1;g_program.moving=-1;}
        g_program.error=rc<0 ? rc : stopped;
      }
      g_python_active=0;
      pthread_mutex_unlock(&g_lock);
    }
    nanosleep(&pause,NULL);
  }
  return NULL;
}
static int worker_main(int argc,char **argv) {
  (void)argc;(void)argv;worker(NULL);return 0;
}
int bw_program_service_init(void) {
  struct bw_program_io io; int rc=0;
  pthread_mutex_lock(&g_lock);
  if(!g_initialized) {
    bw_device_init(&io);bw_program_init(&g_program,&io);
    /* A separate NuttX task group survives the packet CLI returning.
     * A pthread in that CLI's task group would die with its main thread. */
    g_worker=task_create("hubprogram",SCHED_PRIORITY_DEFAULT,16384,worker_main,NULL);
    if(g_worker<0)rc=errno;
    if(rc)syslog(LOG_ERR,"hubprogram: worker startup failed: %d\n",rc);
    if(!rc)g_initialized=1;
  }
  pthread_mutex_unlock(&g_lock);return rc ? -rc : 0;
}
int bw_program_service_request(uint32_t owner,const uint8_t *data,size_t n,uint8_t reply[20]) {
  int rc=bw_program_service_init();
  if(rc<0) {
    unsigned i;
    memset(reply,0,20);reply[0]=BW_PROGRAM_REPLY;reply[1]=1;
    reply[2]=data && n>=3 ? data[2] : 255;
    for(i=0;i<4;i++)reply[8+i]=(uint8_t)((uint32_t)rc>>(8*i));
    return rc;
  }
  pthread_mutex_lock(&g_lock);
  /* A stopped Python VM must finish unwinding before its source can change. */
  if(g_python_active && data && n>=3 && (data[2]==0 || data[2]==2 || data[2]==3 || data[2]==7)) {
    uint8_t status[8]={BW_PROGRAM_REQUEST,1,5,0,0,0,0,0};
    (void)bw_program_request(&g_program,&g_upload,owner,now_ms(),status,8,reply);
    reply[2]=data[2];if(n>=8)memcpy(reply+4,data+4,4);
    reply[8]=(uint8_t)(-EBUSY);reply[9]=reply[10]=reply[11]=255;rc=-EBUSY;
  } else rc=bw_program_request(&g_program,&g_upload,owner,now_ms(),data,n,reply);
  pthread_mutex_unlock(&g_lock);return rc;
}
int bw_program_service_stop(void) {
  int rc=0;
  pthread_mutex_lock(&g_lock);
  if(g_initialized) {
    rc=bw_program_stop(&g_program);
    memset(&g_upload,0,sizeof(g_upload));
    if(!g_python_active)bw_device_release();
  }
  pthread_mutex_unlock(&g_lock);return rc;
}
int bw_program_service_poll(void) {
  int rc;
  pthread_mutex_lock(&g_lock);tick_locked();
  rc=g_program.state==BW_PROGRAM_RUNNING ? 0 : g_program.error ? g_program.error : -ECANCELED;
  pthread_mutex_unlock(&g_lock);return rc;
}
int bw_program_service_motor(unsigned port,int32_t speed) {
  int rc;
  pthread_mutex_lock(&g_lock);
  if(g_program.state!=BW_PROGRAM_RUNNING || port>=2)rc=-EINVAL;
  else {g_program.owned|=1u<<port;rc=g_program.io.motor(NULL,port,speed);}
  pthread_mutex_unlock(&g_lock);return rc;
}
int bw_program_service_position(unsigned port,int32_t degrees,int32_t speed) {
  int rc;
  pthread_mutex_lock(&g_lock);
  if(g_program.state!=BW_PROGRAM_RUNNING || port>=2)rc=-EINVAL;
  else {g_program.owned|=1u<<port;rc=g_program.io.position(NULL,port,degrees,speed);}
  pthread_mutex_unlock(&g_lock);return rc;
}
int bw_program_service_done(unsigned port) {
  int rc;
  pthread_mutex_lock(&g_lock);rc=port>=2 ? -EINVAL : g_program.io.done(NULL,port);
  pthread_mutex_unlock(&g_lock);return rc;
}
int bw_program_service_sensor(unsigned predicate,int32_t *value) {
  int rc;
  pthread_mutex_lock(&g_lock);rc=g_program.io.sensor(NULL,predicate,value);
  pthread_mutex_unlock(&g_lock);return rc;
}
