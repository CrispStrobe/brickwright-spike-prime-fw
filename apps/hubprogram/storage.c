/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "storage.h"
#include "upload.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#define HEADER 20u
#define MAX_RECORD (HEADER + 4096u + 4u)
static uint32_t get32(const uint8_t *b) {
  return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);
}
static void put32(uint8_t *b,uint32_t v) {
  unsigned i;for(i=0;i<4;i++)b[i]=(uint8_t)(v>>(8*i));
}
static int32_t signed32(const uint8_t *b) {
  uint32_t v=get32(b);return v<=INT32_MAX ? (int32_t)v : -(int32_t)(~v)-1;
}
static int transfer(int fd,uint8_t *b,size_t n,int writing) {
  while(n) {
    ssize_t got=writing ? write(fd,b,n) : read(fd,b,n);
    if(got<0) {if(errno==EINTR)continue;return -errno;}
    if(!got)return writing ? -EIO : -EBADMSG;
    b+=got;n-=(size_t)got;
  }
  return 0;
}
int bw_program_save(const struct bw_program *p,uint32_t id,const char *path) {
  uint8_t *b;char *tmp;size_t n,i;int fd,rc;
  if(p->state==BW_PROGRAM_RUNNING)return -EBUSY;
  if(!id || p->id!=id || p->state==BW_PROGRAM_EMPTY || p->language>1)return -EINVAL;
  if(p->language) {
    if(!p->count || p->count>4095 || memchr(p->source,0,p->count))return -EINVAL;
  } else if(bw_program_validate(p->code,p->count)<0)return -EINVAL;
  n=p->language ? p->count : p->count*16u;
  b=malloc(HEADER+n+4);tmp=malloc(strlen(path)+5);
  if(!b || !tmp){free(b);free(tmp);return -ENOMEM;}
  memcpy(b,"BWP1",4);b[4]=1;b[5]=(uint8_t)p->language;b[6]=b[7]=0;
  put32(b+8,id);put32(b+12,p->count);put32(b+16,(uint32_t)n);
  if(p->language)memcpy(b+HEADER,p->source,n);
  else for(i=0;i<p->count;i++) {
    const struct bw_instruction *r=p->code+i;
    put32(b+HEADER+16*i,(uint32_t)r->op);put32(b+HEADER+16*i+4,(uint32_t)r->a);
    put32(b+HEADER+16*i+8,(uint32_t)r->b);put32(b+HEADER+16*i+12,(uint32_t)r->c);
  }
  put32(b+HEADER+n,bw_program_crc32(b,HEADER+n));
  strcpy(tmp,path);strcat(tmp,".tmp");
  fd=open(tmp,O_WRONLY|O_CREAT|O_TRUNC,0600);
  rc=fd<0 ? -errno : transfer(fd,b,HEADER+n+4,1);
  if(fd>=0) {
    if(!rc && fsync(fd)<0)rc=-errno;
    if(close(fd)<0 && !rc)rc=-errno;
  }
  if(!rc && rename(tmp,path)<0)rc=-errno;
  if(rc)unlink(tmp);
  free(tmp);free(b);return rc;
}
int bw_program_restore(struct bw_program *p,uint32_t id,const char *path) {
  /* malloc alignment and the 20-byte header allow decoding rows in place. */
  uint8_t *b;uint32_t count=0,n=0,i;int fd,rc;uint8_t extra;
  if(p->state==BW_PROGRAM_RUNNING)return -EBUSY;
  if(!id)return -EINVAL;
  b=malloc(MAX_RECORD);if(!b)return -ENOMEM;
  fd=open(path,O_RDONLY);if(fd<0){rc=-errno;goto out;}
  rc=transfer(fd,b,HEADER,0);if(rc)goto closed;
  count=get32(b+12);n=get32(b+16);
  if(memcmp(b,"BWP1",4) || b[4]!=1 || b[5]>1 || b[6] || b[7] || !count ||
     (b[5] ? count>4095 || n!=count : count>BW_PROGRAM_LIMIT || n!=count*16u)) {
    rc=-EBADMSG;goto closed;
  }
  rc=transfer(fd,b+HEADER,n+4,0);if(rc)goto closed;
  do {rc=(int)read(fd,&extra,1);}while(rc<0 && errno==EINTR);
  if(rc<0){rc=-errno;goto closed;}
  if(rc || get32(b+HEADER+n)!=bw_program_crc32(b,HEADER+n)){rc=-EBADMSG;goto closed;}
  if(get32(b+8)!=id){rc=-ENOENT;goto closed;}
  if(b[5] && memchr(b+HEADER,0,n)){rc=-EBADMSG;goto closed;}
  if(!b[5]) {
    struct bw_instruction *rows=(struct bw_instruction *)(void *)(b+HEADER);
    for(i=0;i<count;i++) {
      uint8_t *r=b+HEADER+16*i;
      rows[i].op=signed32(r);rows[i].a=signed32(r+4);
      rows[i].b=signed32(r+8);rows[i].c=signed32(r+12);
    }
    rc=bw_program_validate(rows,count);if(rc){rc=-EBADMSG;goto closed;}
  }
  rc=0;
closed:
  if(close(fd)<0 && !rc)rc=-errno;
  if(!rc) {
    if(b[5]) {
      memcpy(p->source,b+HEADER,n);p->source[n]=0;
      p->language=1;p->id=id;p->count=count;p->pc=0;p->error=0;p->owned=0;p->moving=-1;p->waiting=0;p->ending=0;p->state=BW_PROGRAM_READY;
    } else rc=bw_program_load(p,id,(const struct bw_instruction *)(const void *)(b+HEADER),count);
  }
out:
  free(b);return rc;
}
