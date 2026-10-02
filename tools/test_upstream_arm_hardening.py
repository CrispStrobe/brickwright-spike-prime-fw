#!/usr/bin/env python3
"""Compile actual backported timer/SPI function bodies against register mocks.

SPDX-License-Identifier: BSD-3-Clause
Copyright (c) 2026, Christian Strobele
"""
import argparse
from pathlib import Path
import subprocess
import tempfile


def function(text, signature):
    start = text.index('\n' + signature) + 1
    brace = text.index('{', start)
    level = 1
    end = brace + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def run(source, defines=()):
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / 'regression.c'
        exe = Path(tmp) / 'regression'
        c.write_text(source)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        *['-D' + x for x in defines], str(c), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--nuttx', type=Path, required=True)
    args = parser.parse_args()
    timer = (args.nuttx / 'arch/arm/src/stm32/stm32_tickless.c').read_text()
    timer_body = '\n'.join(function(timer, name) for name in
                           ['int up_timer_cancel(', 'int up_timer_start('])
    prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <time.h>
#define OK 0
#define USEC_PER_SEC 1000000
#define NSEC_PER_USEC 1000
#define DEBUGASSERT(x) assert(x)
#define tmrinfo(...) ((void)0)
typedef int irqstate_t;
static struct {bool pending; unsigned channel; uint32_t period, frequency; void *tch;} g_tickless;
static uint32_t counter, latency, compare;
static uint16_t status;
static bool enabled;
static int reads, events;
static irqstate_t enter_critical_section(void) {return 0;}
static void leave_critical_section(irqstate_t f) {(void)f;}
static uint32_t getcounter(void) {return counter + (reads++ ? latency : 0);}
#define STM32_TIM_GETCOUNTER(t) getcounter()
#define STM32_TIM_SETCOMPARE(t,ch,p) (compare=(p))
static void stm32_tickless_disableint(int c) {(void)c;enabled=false;}
static void stm32_tickless_enableint(int c) {(void)c;enabled=true;}
static void stm32_tickless_ackint(int c) {status &= ~(1u<<c);}
static uint16_t stm32_tickless_getint(void) {return status;}
static void stm32_tickless_trigint(int c) {status |= 1u<<c; events++;}
static void reset(uint32_t c) {
 counter=c;latency=0;reads=0;events=0;status=0;enabled=false;
 g_tickless.pending=false;g_tickless.channel=1;g_tickless.frequency=100000;g_tickless.tch=&counter;
}
static struct timespec delay(unsigned ticks) {
 struct timespec t={(time_t)(ticks/100000), (long)(ticks%100000)*10000};return t;
}
'''
    suffix = r'''
int main(void) {
 const unsigned requests[]={1,1000,32767,32768,40000,65535};
 const uint32_t starts[]={0,1000,65000,65535,UINT32_MAX-100};
 for(size_t i=0;i<sizeof(requests)/sizeof(requests[0]);i++) {
  for(size_t j=0;j<sizeof(starts)/sizeof(starts[0]);j++) {
   reset(starts[j]);struct timespec t=delay(requests[i]),out;
   assert(up_timer_start(&t)==0);assert(enabled);assert(events==0);
#ifdef HAVE_32BIT_TICKLESS
   assert(compare==(uint32_t)(starts[j]+requests[i]));
#else
   assert(compare==(uint16_t)(starts[j]+requests[i]));
#endif
   assert(up_timer_cancel(&out)==0);
   assert((uint64_t)out.tv_sec*100000+out.tv_nsec/10000==requests[i]);
   assert(!enabled&&!g_tickless.pending);
  }
 }
 reset(65000);struct timespec t=delay(1000),out;up_timer_start(&t);
 counter=65020;reads=0;up_timer_cancel(&out);assert(out.tv_nsec==9800000);
 reset(1000);t=delay(5);latency=6;up_timer_start(&t);assert(events==1);
 assert(status==2);reads=0;up_timer_cancel(&out);assert(out.tv_sec==0&&out.tv_nsec==0);
 reset(65534);t=delay(2);latency=3;up_timer_start(&t);assert(events==1);
 for(int k=0;k<3;k++) {reset(100);t.tv_sec=k==2?-1:0;t.tv_nsec=k==1?999:0;
  up_timer_start(&t);assert(events==1);up_timer_cancel(&out);assert(out.tv_sec==0&&out.tv_nsec==0);}
 reset(1);out.tv_sec=1;out.tv_nsec=1;up_timer_cancel(&out);assert(out.tv_sec==0&&out.tv_nsec==0);
 return 0;
}
'''
    run(prefix + timer_body + suffix)
    run(prefix + timer_body + suffix, ['HAVE_32BIT_TICKLESS'])
    spi = (args.nuttx / 'arch/arm/src/stm32/stm32_spi.c').read_text()
    start = spi.index('      static uint16_t rxdummy = 0xffff;', spi.index('static void spi_exchange('))
    end = spi.index('\n    }\n}', start)
    body = spi[start:end]
    prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define OK 0
#define STM32_SPI_DMA_MAX_XFER 65535u
#define DEBUGASSERT(x) assert(x)
#define spiinfo(...) ((void)0)
struct spi_mock {unsigned nbits,spibase;bool defertrig,trigarmed;uint8_t *txbuf,*rxbuf;size_t buflen;};
static size_t total,chunks,last;static int starts;
static const uint8_t *expected_tx;static uint8_t *expected_rx;
static void spi_dmarxsetup(struct spi_mock *p,uint8_t *r,uint16_t *d,size_t n) {
 (void)d;assert(n&&n<=65535);assert(r==expected_rx);
 if(r) {expected_rx+=n*(p->nbits>8?2:1);}
 last=n;total+=n;chunks++;
}
static void spi_dmatxsetup(struct spi_mock *p,const uint8_t *t,const uint16_t *d,size_t n) {
 (void)d;assert(n==last);assert(t==expected_tx);if(t)expected_tx+=n*(p->nbits>8?2:1);
}
static void spi_dmarxstart(struct spi_mock *p){(void)p;starts++;}
static void spi_dmatxstart(struct spi_mock *p){(void)p;}
static int spi_dmarxwait(struct spi_mock *p){
#ifdef CONFIG_SPI_TRIGGER
 if(p->defertrig&&chunks==1){assert(p->trigarmed);spi_dmarxstart(p);}
#else
 (void)p;
#endif
 return 0;
}
static int spi_dmatxwait(struct spi_mock *p){(void)p;return 0;}
static void exchange(struct spi_mock *priv,const void *txbuffer,void *rxbuffer,size_t nwords) {
 size_t nbytes=nwords*(priv->nbits>8?2:1);void *xbuffer=rxbuffer;int ret;
'''
    suffix = r'''
}
int main(void) {
 uint8_t *tx=malloc(300000),*rx=malloc(300000);assert(tx&&rx);
 const size_t sizes[]={1,65535,65536,65537,131070};
 for(unsigned bits=8;bits<=16;bits+=8) for(int deferred=0;deferred<2;deferred++)
 for(size_t i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++) for(int mode=0;mode<3;mode++) {
  struct spi_mock p={.nbits=bits,.spibase=1,.defertrig=deferred};
  const uint8_t *t=mode==1?NULL:tx;uint8_t *r=mode==2?NULL:rx;
  expected_tx=t;expected_rx=r;total=chunks=last=0;starts=0;
  exchange(&p,t,r,sizes[i]);assert(total==sizes[i]);assert(chunks==(sizes[i]+65534)/65535);
  assert(starts==(int)chunks);assert(!p.trigarmed);
 }
 free(tx);free(rx);return 0;
}
'''
    run(prefix+body+suffix)
    run(prefix+body+suffix, ['CONFIG_SPI_TRIGGER'])
    syscall = (args.nuttx / 'arch/arm/src/armv7-m/arm_svcall.c').read_text()
    start = syscall.index('          if (cmd < CONFIG_SYS_RESERVED')
    end = syscall.index('          /* Use ip', start)
    guard = syscall[start:end]
    harness = r"""
#include <assert.h>
#include <errno.h>
#define CONFIG_SYS_RESERVED 4
#define SYS_maxsyscall 300
#define CONFIG_SYS_NNEST 2
#define REG_R0 0
static int call(unsigned cmd,int index) {
 int regs[1]={123};
 switch(cmd) {default: {
""" + guard + r"""
 regs[0]=456;break;
 }}return regs[0];
}
int main(void) {
 for(unsigned n=0;n<400;n++)for(int i=0;i<4;i++)
 assert(call(n,i)==(n>=4&&n<300&&i<2?456:-ENOSYS));
 assert(call(~0u,0)==-ENOSYS);return 0;
}
"""
    run(harness)
    print('PASS: timer start/cancel (16/32-bit), SPI DMA (normal/deferred), syscall bounds')


if __name__ == '__main__':
    main()
