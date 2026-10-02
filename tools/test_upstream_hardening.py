#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile real changed C paths with fault-injection boundary mocks.

This exercises implementation bodies, not a reimplementation of their
algorithms. It is a host regression test; it does not replace an ARM build
or physical flash power-loss testing. Run with --nuttx PATH to the pinned
NuttX checkout containing the reviewed backports.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nuttx', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    board = (root / 'boards/spike-prime-hub/src/stm32_w25q256.c').read_text()
    files = (args.nuttx / 'fs/inode/fs_files.c').read_text()
    group = (args.nuttx / 'sched/group/group_create.c').read_text()
    prctl = (args.nuttx / 'sched/task/task_prctl.c').read_text()
    fd = function(files, 'static int fdlist_extend(')
    fd = fd[:fd.index('  fds = fs_heap_malloc')] + '  return 0;\n}'
    cleanup = group.split('errout_with_group:\n', 1)[1].split('\n}', 1)[0]
    getname = prctl.split('/* The returned value will be null-terminated', 1)[1]
    getname = getname.split('*/', 1)[1].split('\n            }', 1)[0]
    wake = board.split('  /* Release deep power-down before probing.', 1)[1]
    wake = wake.split('*/', 1)[1].split('  w25q256_unlock(priv);', 1)[0]
    source = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#define FAR
#define OPEN_MAX 256
#define CONFIG_NFILE_DESCRIPTORS_PER_BLOCK 8
#define CONFIG_TASK_NAME_SIZE 31
#define W25Q256_PAGE_SIZE 256u
#define W25Q256_SECTOR_SIZE 4096u
#define W25Q256_CHIP_SIZE (32u * 1024u * 1024u)
#define W25Q256_RESERVED_BYTES (1u * 1024u * 1024u)
#define W25Q256_ERASED_STATE 0xff
#define W25Q256_MTDBLOCK_PATH "/dev/mtdblock0"
#define W25Q256_MOUNT_POINT "/mnt/flash"
#define W25Q256_FS_TYPE "littlefs"
#define W25Q256_CMD_RDP 0xab
#define LOG_INFO 0
#define syslog(...) ((void)0)
struct file {};
struct fd {};
struct fdlist { uint8_t fl_rows; };
static int dumps;
static void fdlist_dump(struct fdlist *f) { (void)f; dumps++; }
struct task_group_s { int dummy; };
static struct task_group_s g_kthread_group;
struct tcb_s { struct task_group_s *group; char name[32]; };
static int frees, allocation_failure;
static unsigned allocations, scan_frees;
static void *scan_buffer;
static void *kmm_malloc(size_t n) {
  assert(n==W25Q256_SECTOR_SIZE && !scan_buffer);allocations++;
  return allocation_failure ? NULL : (scan_buffer=malloc(n));
}
static void kmm_free(void *p) {
  if(p==scan_buffer){assert(p);scan_frees++;free(p);scan_buffer=NULL;}
  else {assert(p!=&g_kthread_group);frees++;}
}
#define strlcpy test_strlcpy
static size_t test_strlcpy(char *d,const char *s,size_t n) {
  size_t len=strlen(s); if(n){size_t copy=len<n?len:n-1;memcpy(d,s,copy);d[copy]=0;}return len;
}
struct mtd_dev_s {int dummy;};
static unsigned reads, mount_calls, formats;
static int mount_error,format_error,read_error,short_read;
static off_t dirty_at;
static ssize_t mock_read(struct mtd_dev_s *m,off_t offset,size_t n,uint8_t *b) {
  (void)m; assert(offset>=0);assert(offset+(off_t)n <= W25Q256_CHIP_SIZE-W25Q256_RESERVED_BYTES);
  assert(n==W25Q256_SECTOR_SIZE && offset==(off_t)(reads*W25Q256_SECTOR_SIZE));
  reads++; if(read_error)return read_error; if(short_read)return n-1;
  memset(b,255,n);if(dirty_at>=offset && dirty_at<offset+(off_t)n)b[dirty_at-offset]=0;return n;
}
#define MTD_READ mock_read
static int nx_mount(const char *source,const char *target,const char *fs,unsigned long flags,const void *data) {
  assert(strcmp(source,W25Q256_MTDBLOCK_PATH)==0);
  assert(strcmp(target,W25Q256_MOUNT_POINT)==0);assert(strcmp(fs,"littlefs")==0);assert(flags==0);
  assert(!scan_buffer);mount_calls++;if(data){assert(strcmp(data,"forceformat")==0);formats++;return format_error;}return mount_error;
}
static char events[16];static unsigned event_count;
struct w25q256_dev_s {void *spi;};
#define SPIDEV_FLASH(x) (x)
static void w25q256_lock(struct w25q256_dev_s *p){(void)p;events[event_count++]='L';}
static void mock_select(void *p,int id,bool on){(void)p;assert(id==0);events[event_count++]=on?'S':'s';}
static void mock_send(void *p,int byte){(void)p;assert(byte==W25Q256_CMD_RDP);events[event_count++]='W';}
#define SPI_SELECT mock_select
#define SPI_SEND mock_send
static int nxsched_usleep(unsigned delay){assert(delay>=20);events[event_count++]='D';return 0;}
static int w25q256_read_jedec(struct w25q256_dev_s *p,uint32_t *id){(void)p;*id=0xef4019;events[event_count++]='J';return 0;}
'''
    source += fd + '\n'
    source += 'static int fail_group(struct task_group_s *group,struct tcb_s *tcb,int ret) {\n' + cleanup + '\n}\n'
    source += 'static void get_name(struct tcb_s *tcb,char *name) {\n' + getname + '\n}\n'
    source += 'static int wake_probe(struct w25q256_dev_s *priv) {int ret;uint32_t jedec;\n' + wake + '\nreturn ret;}\n'
    source += function(board, 'static int w25q256_partition_erased(') + '\n'
    source += function(board, 'static int w25q256_mount(') + '\n'
    source += r'''
static void setup(int error,off_t dirty) {
  assert(!scan_buffer);allocations=scan_frees=0;allocation_failure=0;
  reads=mount_calls=formats=0;mount_error=error;format_error=read_error=short_read=0;dirty_at=dirty;
}
int main(void) {
  struct fdlist list={1};struct tcb_s tcb={0};struct task_group_s dynamic={0};
  struct {char name[CONFIG_TASK_NAME_SIZE];unsigned char guard;} result;
  struct mtd_dev_s part;struct w25q256_dev_s flash={0};unsigned i;
  const off_t boundaries[]={4095,4096,65535,65536};
  assert(fdlist_extend(&list,1)==0);assert(fdlist_extend(&list,2)==0);
  assert(fdlist_extend(&list,OPEN_MAX/8)==0);
  assert(fdlist_extend(&list,OPEN_MAX/8+1)==-EMFILE);assert(dumps==1);
  assert(fdlist_extend(&list,400/8+1)==-EMFILE);assert(dumps==2);
  tcb.group=&g_kthread_group;assert(fail_group(tcb.group,&tcb,-ENOMEM)==-ENOMEM);
  assert(frees==0 && tcb.group==NULL);
  tcb.group=&dynamic;assert(fail_group(tcb.group,&tcb,-ENOMEM)==-ENOMEM);
  assert(frees==1 && tcb.group==NULL);
  memset(tcb.name,'x',sizeof(tcb.name)-1);tcb.name[31]=0;result.guard=0xaa;
  get_name(&tcb,result.name);assert(result.guard==0xaa);assert(strlen(result.name)==30);
  strcpy(tcb.name,"hubprogram");get_name(&tcb,result.name);assert(strcmp(result.name,"hubprogram")==0);
  assert(wake_probe(&flash)==0);assert(event_count==6);assert(memcmp(events,"LSWsDJ",6)==0);
  setup(0,-1);assert(w25q256_mount(&part)==0);assert(reads==0 && formats==0 && mount_calls==1);
  setup(-EIO,-1);assert(w25q256_mount(&part)==-EIO);assert(reads==0 && formats==0);
  setup(-EINVAL,-1);assert(w25q256_mount(&part)==0);assert(formats==1 && mount_calls==2);
  assert(reads==(W25Q256_CHIP_SIZE-W25Q256_RESERVED_BYTES)/W25Q256_SECTOR_SIZE);assert(allocations==1&&scan_frees==1&&!scan_buffer);
  setup(-EFAULT,-1);assert(w25q256_mount(&part)==0);assert(formats==1);
  setup(-EFAULT,-1);allocation_failure=1;assert(w25q256_mount(&part)==-ENOMEM);
  assert(!reads&&!formats&&allocations==1&&!scan_frees&&!scan_buffer);
  setup(-EFAULT,0);assert(w25q256_mount(&part)==-EFAULT);assert(reads==1 && formats==0 && scan_frees==1 && !scan_buffer);
  setup(-EINVAL,W25Q256_CHIP_SIZE-W25Q256_RESERVED_BYTES-1);
  assert(w25q256_mount(&part)==-EINVAL);assert(formats==0);
  assert(reads==(W25Q256_CHIP_SIZE-W25Q256_RESERVED_BYTES)/W25Q256_SECTOR_SIZE);assert(allocations==1&&scan_frees==1&&!scan_buffer);
  /* Detect a dirty byte at every position in a scan block and on both
   * sides of sector and 16-bit DMA-count boundaries. */
  for(i=0;i<W25Q256_SECTOR_SIZE;i++) {
    setup(-EFAULT,i);assert(w25q256_mount(&part)==-EFAULT);
    assert(reads==1&&!formats&&scan_frees==1&&!scan_buffer);
  }
  for(i=0;i<sizeof(boundaries)/sizeof(boundaries[0]);i++) {
    setup(-EINVAL,boundaries[i]);assert(w25q256_mount(&part)==-EINVAL);
    assert(reads==(unsigned)(boundaries[i]/W25Q256_SECTOR_SIZE)+1);
    assert(!formats&&scan_frees==1&&!scan_buffer);
  }
  setup(-EINVAL,-1);read_error=-EIO;assert(w25q256_mount(&part)==-EIO);assert(formats==0&&scan_frees==1&&!scan_buffer);
  setup(-EFAULT,-1);short_read=1;assert(w25q256_mount(&part)==-EIO);assert(formats==0&&scan_frees==1&&!scan_buffer);
  setup(-EINVAL,-1);format_error=-ENOSPC;assert(w25q256_mount(&part)==-ENOSPC);assert(formats==1);
  printf("flash scan: full 31 MiB in %u reads, previously %u; allocation/error/edge frees verified\n",(W25Q256_CHIP_SIZE-W25Q256_RESERVED_BYTES)/W25Q256_SECTOR_SIZE,(W25Q256_CHIP_SIZE-W25Q256_RESERVED_BYTES)/W25Q256_PAGE_SIZE);
  puts("NuttX hardening fault-injection and flash recovery tests passed");return 0;
}
'''
    compiler = shutil.which('cc')
    if not compiler:
        raise SystemExit('C compiler required')
    with tempfile.TemporaryDirectory(prefix='bw-hardening-test-') as directory:
        cfile = Path(directory) / 'test.c'
        executable = Path(directory) / 'test'
        cfile.write_text(source)
        subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Wno-unused-variable', '-Wno-sign-compare', '-fsanitize=address,undefined', '-g', str(cfile), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == '__main__':
    main()
