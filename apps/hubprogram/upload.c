/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "upload.h"
#include <errno.h>
#include <string.h>
static uint32_t get32(const uint8_t *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p, uint32_t v) {
  unsigned i; for(i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i));
}
static void put16(uint8_t *p, uint16_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
uint32_t bw_program_crc32(const uint8_t *data, size_t size) {
  uint32_t crc=0xffffffffu; size_t i; unsigned bit;
  for(i=0;i<size;i++) { crc^=data[i]; for(bit=0;bit<8;bit++) crc=(crc>>1)^((crc&1u)?0xedb88320u:0u); }
  return ~crc;
}
static int32_t signed32(const uint8_t *p) {
  uint32_t v=get32(p); return v<=INT32_MAX ? (int32_t)v : -(int32_t)(~v)-1;
}
int bw_program_request(struct bw_program *p, struct bw_program_upload *u,
  uint32_t owner, uint64_t now, const uint8_t *data, size_t size, uint8_t reply[20])
{
  uint32_t id=0;
  unsigned op=0;
  int rc=-EINVAL;
  if (u->active && (now<u->activity || now-u->activity>=30000u)) u->active=0;
  if (!owner || !data || size<8 || size>20 || data[0]!=BW_PROGRAM_REQUEST || data[1]!=1 || data[3]!=0) goto respond;
  op=data[2]; id=get32(data+4);
  if (!id && op!=5) goto respond;
  switch(op) {
    case 7: /* Python source begin (byte length, CRC), no filesystem access */
    case 0: /* begin: count, CRC-32/ISO-HDLC of little-endian instructions */
      if(size!=16) break;
      if(p->state==BW_PROGRAM_RUNNING || u->active) { rc=-EBUSY; break; }
      { uint32_t count=get32(data+8);
        if(count==0 || count>(op==7 ? 4095u : BW_PROGRAM_LIMIT)) break;
        u->id=id; u->owner=owner; u->crc=get32(data+12); u->language=op==7; u->size=(uint16_t)(u->language ? count : count*16);
        u->received=0; u->active=1; u->activity=now; rc=0;
      } break;
    case 1: /* ordered chunk, at most 10 payload bytes; retry idempotently */
      if(size<11 || !u->active || u->owner!=owner || u->id!=id) break;
      { unsigned offset=(unsigned)data[8]|((unsigned)data[9]<<8);
        size_t n=size-10;
        if(offset+n>u->size) break;
        if(offset<u->received) {
          if(offset+n<=u->received && memcmp(u->buffer.bytes+offset,data+10,n)==0) rc=0;
        } else if(offset==u->received) {
          memcpy(u->buffer.bytes+offset,data+10,n); u->received=(uint16_t)(offset+n); rc=0;
        }
        if(rc==0) u->activity=now;
      } break;
    case 2: /* commit: no mutation of active program until all checks pass */
      if(size!=8 || !u->active || u->owner!=owner || u->id!=id || u->received!=u->size) break;
      if(bw_program_crc32(u->buffer.bytes,u->size)!=u->crc) { rc=-EBADMSG; u->active=0; break; }
      if(u->language) {
        if(memchr(u->buffer.bytes,0,u->size)) {rc=-EINVAL;u->active=0;break;}
        if(p->state==BW_PROGRAM_RUNNING) {rc=-EBUSY;break;}
        memcpy(p->source,u->buffer.bytes,u->size);p->source[u->size]=0;
        p->language=1;p->count=u->size;p->id=id;p->pc=0;p->error=0;p->state=BW_PROGRAM_READY;
        u->active=0;rc=0;break;
      }
      /* The union guarantees row alignment. Decode only after checksum;
       * validation and load remain transactional, without a large stack. */
      { uint32_t i, count=u->size/16;
        for(i=0;i<count;i++) {
          const uint8_t *b=u->buffer.bytes+16*i;
          u->buffer.code[i].op=signed32(b); u->buffer.code[i].a=signed32(b+4);
          u->buffer.code[i].b=signed32(b+8); u->buffer.code[i].c=signed32(b+12);
        }
        rc=bw_program_load(p,id,u->buffer.code,count); u->active=0;
      } break;
    case 3:
      if(size!=8) break;
      rc=u->active ? -EBUSY : bw_program_start(p,id,now); break;
    case 4:
      if(size!=8 || id!=p->id) break;
      rc=bw_program_stop(p); break;
    case 5: if(size==8) rc=0; break;
    case 6:
      if(size!=8 || !u->active || id!=u->id || owner!=u->owner) break;
      u->active=0; rc=0; break;
  }
respond:
  memset(reply,0,20); reply[0]=BW_PROGRAM_REPLY; reply[1]=1; reply[2]=(uint8_t)op;
  reply[3]=(uint8_t)p->state;
  /* Correlate transactions even when the committed program is unchanged. */
  put32(reply+4,op==5 && id==0 ? p->id : id); put32(reply+8,(uint32_t)rc);
  put16(reply+12,(uint16_t)p->pc); put16(reply+14,(uint16_t)p->count);
  put16(reply+16,u->active ? u->received : 0); put16(reply+18,(uint16_t)p->error);
  return rc;
}
