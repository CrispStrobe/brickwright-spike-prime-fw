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
#include "imu_calibration.h"

#define FLASH_BYTES (31u * 1024u * 1024u)
static uint8_t *flash;
static lfs_t fs;
static lfs_file_t file;
static int opened;
static unsigned events, cut, phase;
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
static unsigned temporary_serial;
static int flash_mkstemp(char *path) {
  size_t n=strlen(path);struct lfs_info info;
  do {
    assert(n>=6);snprintf(path+n-6,7,"%06u",++temporary_serial);
  } while(lfs_stat(&fs,path,&info)==0);
  return flash_open(path,O_WRONLY|O_CREAT|O_TRUNC);
}
#define open flash_open
#define mkstemp flash_mkstemp
#define write flash_write
#define read flash_read_file
#define fsync flash_fsync
#define close flash_close
#define rename flash_rename
#define unlink flash_unlink
#include "../apps/imu/imu_calibration.c"
#undef open
#undef mkstemp
#undef write
#undef read
#undef fsync
#undef close
#undef rename
#undef unlink

static unsigned crash_cases;
static void mount_flash(void) {memset(&fs,0,sizeof(fs));opened=0;assert(lfs_mount(&fs,&config)==0);}
static void scenario(bool have_old, unsigned warmup) {
  imu_settings_t old={0},next;
  uint8_t *baseline=malloc(FLASH_BYTES);unsigned total;
  assert(baseline);memset(flash,255,FLASH_BYTES);assert(lfs_format(&fs,&config)==0);mount_flash();
  imu_calibration_set_defaults(&old);next=old;
  next.flags|=IMU_FLAG_GYRO_BIAS;next.angular_velocity_bias_start.x=2.5f;
  if(have_old)for(unsigned i=0;i<=warmup;i++)assert(imu_calibration_save_copy("imu.calibration",&old)==0);
  assert(lfs_unmount(&fs)==0);memcpy(baseline,flash,FLASH_BYTES);
  mount_flash();events=0;assert(imu_calibration_save_copy("imu.calibration",&next)==0);
  total=events;assert(total);assert(lfs_unmount(&fs)==0);
  for(unsigned k=1;k<=total;k++)for(unsigned mode=0;mode<3;mode++) {
    pid_t child;int status;memcpy(flash,baseline,FLASH_BYTES);child=fork();assert(child>=0);
    if(!child) {mount_flash();events=0;cut=k;phase=mode;armed=1;
      int rc=imu_calibration_save_copy("imu.calibration",&next);_exit(rc?78:0);}
    assert(waitpid(child,&status,0)==child);assert(WIFEXITED(status)&&WEXITSTATUS(status)==77);
    mount_flash();*imu_calibration_get_settings()=old;
    int rc=imu_calibration_load("imu.calibration");
    if(rc<0)assert(!have_old&&errno==ENOENT);
    else assert(!memcmp(imu_calibration_get_settings(),&next,sizeof(next)) ||
                (have_old&&!memcmp(imu_calibration_get_settings(),&old,sizeof(old))));
    assert(imu_calibration_save_copy("imu.calibration",&next)==0);
    assert(lfs_unmount(&fs)==0);mount_flash();
    assert(imu_calibration_load("imu.calibration")==0);
    assert(!memcmp(imu_calibration_get_settings(),&next,sizeof(next)));
    assert(lfs_unmount(&fs)==0);crash_cases++;
  }
  printf("IMU calibration %s, %u prior replacements: %u flash operations, %u power cuts passed\n",
         have_old?"replacement":"first save",warmup,total,total*3);
  free(baseline);
}
int main(void) {
  flash=mmap(NULL,FLASH_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
  assert(flash!=MAP_FAILED);scenario(false,0);scenario(true,0);scenario(true,64);
  assert(munmap(flash,FLASH_BYTES)==0);
  printf("%u real LittleFS IMU calibration crash/restart cases passed\n",crash_cases);
  return 0;
}
