/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Host-only qualification: real LittleFS, simulated NOR, process termination.
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include "lfs.h"
#include "../storage.h"

#define FLASH_BYTES (31u * 1024u * 1024u)
static uint8_t *flash;
static lfs_t fs;
static lfs_file_t file;
static int opened;
static unsigned events, cut, phase, formats;
static int armed;
static void boundary(unsigned when) {
  if (armed && cut && events == cut && phase == when) _exit(77);
}
static int flash_read(const struct lfs_config *c,lfs_block_t b,lfs_off_t o,void *p,lfs_size_t n) {
  (void)c;assert(b*4096u+o+n<=FLASH_BYTES);memcpy(p,flash+b*4096u+o,n);return 0;
}
static int flash_prog(const struct lfs_config *c,lfs_block_t b,lfs_off_t o,const void *p,lfs_size_t n) {
  unsigned i;const uint8_t *s=p;(void)c;events++;boundary(0);
  for(i=0;i<n;i++) {assert((flash[b*4096u+o+i]&s[i])==s[i]);flash[b*4096u+o+i]&=s[i];if(i+1==n/2+128u)boundary(1);}
  boundary(2);return 0;
}
static int flash_erase(const struct lfs_config *c,lfs_block_t b) {
  (void)c;events++;boundary(0);memset(flash+b*4096u,255,2048);boundary(1);
  memset(flash+b*4096u+2048,255,2048);boundary(2);return 0;
}
static int flash_sync(const struct lfs_config *c) {
  (void)c;events++;boundary(0);boundary(1);boundary(2);return 0;
}
static const struct lfs_config config={
  .read=flash_read,.prog=flash_prog,.erase=flash_erase,.sync=flash_sync,
  .read_size=1024,.prog_size=1024,.block_size=4096,.block_count=FLASH_BYTES/4096,
  .block_cycles=200,.cache_size=1024,.lookahead_size=992
};
/* Keep the firmware's actual storage encoder/save/restore implementation. */
static int posix_result(int rc) {if(rc<0){errno=-rc;return -1;}return rc;}
static int flash_open(const char *path,int flags,...) {
  int mode=(flags&O_WRONLY)?LFS_O_WRONLY:LFS_O_RDONLY;
  assert(!opened);if(flags&O_CREAT)mode|=LFS_O_CREAT;if(flags&O_TRUNC)mode|=LFS_O_TRUNC;
  int rc=lfs_file_open(&fs,&file,path,mode);if(rc<0)return posix_result(rc);opened=1;return 5;
}
static ssize_t flash_write(int fd,const void *p,size_t n) {assert(fd==5&&opened);return posix_result(lfs_file_write(&fs,&file,p,n));}
static ssize_t flash_read_file(int fd,void *p,size_t n) {assert(fd==5&&opened);return posix_result(lfs_file_read(&fs,&file,p,n));}
static int flash_fsync(int fd) {assert(fd==5&&opened);return posix_result(lfs_file_sync(&fs,&file));}
static int flash_close(int fd) {assert(fd==5&&opened);opened=0;return posix_result(lfs_file_close(&fs,&file));}
static int flash_rename(const char *a,const char *b) {return posix_result(lfs_rename(&fs,a,b));}
static int flash_unlink(const char *p) {return posix_result(lfs_remove(&fs,p));}
#define open flash_open
#define write flash_write
#define read flash_read_file
#define fsync flash_fsync
#define close flash_close
#define rename flash_rename
#define unlink flash_unlink
#include "../storage.c"
#undef open
#undef write
#undef read
#undef fsync
#undef close
#undef rename
#undef unlink

/* Extracted board policy, with real lfs_mount/lfs_format behind nx_mount. */
#define FAR
#define W25Q256_PAGE_SIZE 256u
#define W25Q256_CHIP_SIZE (32u*1024u*1024u)
#define W25Q256_RESERVED_BYTES (1024u*1024u)
#define W25Q256_ERASED_STATE 255
#define W25Q256_MTDBLOCK_PATH "/dev/mtdblock0"
#define W25Q256_MOUNT_POINT "/mnt/flash"
#define W25Q256_FS_TYPE "littlefs"
#define LOG_INFO 0
#define syslog(...) ((void)0)
struct mtd_dev_s {int unused;};
static ssize_t partition_read(struct mtd_dev_s *p,off_t off,size_t n,uint8_t *out) {
  (void)p;assert(off>=0&&(size_t)off+n<=FLASH_BYTES);memcpy(out,flash+off,n);return (ssize_t)n;
}
#define MTD_READ partition_read
static int nx_mount(const char *a,const char *b,const char *type,unsigned long flags,const void *data) {
  (void)a;(void)b;(void)type;(void)flags;
  if(data) {assert(!strcmp(data,"forceformat"));formats++;assert(lfs_format(&fs,&config)==0);}
  memset(&fs,0,sizeof(fs));int rc=lfs_mount(&fs,&config);
  /* Match the NuttX VFS mapping for damaged metadata. */
  return rc==LFS_ERR_CORRUPT?-EFAULT:rc;
}
#include "board_policy.h"
static void mount_flash(void) {memset(&fs,0,sizeof(fs));opened=0;assert(lfs_mount(&fs,&config)==0);}
static void make_program(struct bw_program *p,unsigned lang,char payload) {
  bw_program_init(p,NULL);p->id=42;p->state=BW_PROGRAM_READY;p->language=lang;p->count=lang?4095:256;
  if(lang){memset(p->source,payload,4095);p->source[4095]=0;}
  else {memset(p->code,0,sizeof(p->code));p->code[0].op=2;p->code[0].a=payload;}
}
static unsigned crash_cases;
static int same_program(const struct bw_program *a,const struct bw_program *b) {
  return a->id==b->id&&a->language==b->language&&a->count==b->count&&
    (a->language?!memcmp(a->source,b->source,a->count+1):!memcmp(a->code,b->code,a->count*sizeof(a->code[0])));
}
static void scenario(unsigned oldlang,unsigned newlang,unsigned warmup) {
  struct bw_program old,new,restored;uint8_t *baseline=malloc(FLASH_BYTES);unsigned total,k,mode;
  assert(baseline);memset(flash,255,FLASH_BYTES);assert(lfs_format(&fs,&config)==0);mount_flash();
  make_program(&old,oldlang,'a');make_program(&new,newlang,'b');
  if(oldlang<2) {
    for(k=0;k<=warmup;k++)assert(bw_program_save(&old,42,"program")==0);
  }
  assert(lfs_unmount(&fs)==0);memcpy(baseline,flash,FLASH_BYTES);
  mount_flash();events=0;assert(bw_program_save(&new,42,"program")==0);total=events;assert(total);assert(lfs_unmount(&fs)==0);
  for(k=1;k<=total;k++)for(mode=0;mode<3;mode++) {
    pid_t child;int status;memcpy(flash,baseline,FLASH_BYTES);child=fork();assert(child>=0);
    if(!child) {mount_flash();events=0;cut=k;phase=mode;armed=1;int rc=bw_program_save(&new,42,"program");_exit(rc?78:0);}
    assert(waitpid(child,&status,0)==child);assert(WIFEXITED(status)&&WEXITSTATUS(status)==77);
    mount_flash();bw_program_init(&restored,NULL);
    int rc=bw_program_restore(&restored,42,"program");
    if(rc==-ENOENT)assert(oldlang==2&&restored.state==BW_PROGRAM_EMPTY);
    else {
      assert(rc==0&&restored.state==BW_PROGRAM_READY);
      assert((oldlang<2&&same_program(&restored,&old))||same_program(&restored,&new));
    }
    /* Recovery must also allow another complete replacement. */
    assert(bw_program_save(&new,42,"program")==0);assert(lfs_unmount(&fs)==0);mount_flash();
    assert(bw_program_restore(&restored,42,"program")==0);assert(same_program(&restored,&new));
    assert(lfs_unmount(&fs)==0);crash_cases++;
  }
  printf("native/Python/absent %u -> %u, %u prior replacements: %u flash operations, %u power cuts passed\n",oldlang,newlang,warmup,total,total*3);
  free(baseline);
}
int main(void) {
  struct mtd_dev_s part={0};uint8_t *damaged;unsigned block;
  flash=mmap(NULL,FLASH_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);assert(flash!=MAP_FAILED);
  scenario(0,0,0);scenario(0,1,0);scenario(1,0,0);scenario(1,1,0);
  scenario(0,0,64);scenario(0,1,64);scenario(1,0,64);scenario(1,1,64);
  scenario(2,0,0);scenario(2,1,0);
  /* Truly erased partitions may format, corrupt/nonblank partitions may not. */
  memset(flash,255,FLASH_BYTES);formats=0;assert(w25q256_mount(&part)==0&&formats==1);assert(lfs_unmount(&fs)==0);
  /* Destroy both metadata-pair blocks; assert the actual board does not write. */
  memset(flash,0,8192);damaged=malloc(FLASH_BYTES);assert(damaged);memcpy(damaged,flash,FLASH_BYTES);
  formats=0;assert(w25q256_mount(&part)==-EFAULT);assert(!formats&&!memcmp(damaged,flash,FLASH_BYTES));
  /* Dirty byte at either end defeats the wholly-erased criterion. */
  for(block=0;block<2;block++) {
    memset(flash,255,FLASH_BYTES);flash[block?FLASH_BYTES-1:0]=0;memcpy(damaged,flash,FLASH_BYTES);
    assert(w25q256_mount(&part)==-EFAULT);assert(!formats&&!memcmp(damaged,flash,FLASH_BYTES));
  }
  free(damaged);assert(munmap(flash,FLASH_BYTES)==0);
  printf("%u real LittleFS crash/restart cases; corrupted metadata/nonblank flash preserved byte-for-byte\n",crash_cases);
  return 0;
}
