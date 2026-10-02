/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#define _POSIX_C_SOURCE 200809L
#include "../storage.h"
#include "../upload.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static struct bw_program p,loaded,before;
static void unchanged(int rc) {
  assert(rc<0);assert(!memcmp(&loaded,&before,sizeof(loaded)));
}
int main(void) {
  char dir[]="/tmp/bw-storage-XXXXXX",path[128],tmp[132];
  struct bw_instruction code[]={{1,0,-400,0},{2,50,0,0},{0,0,0,0}};
  unsigned i;int fd;unsigned char bytes[8192];ssize_t size;
  assert(mkdtemp(dir));snprintf(path,sizeof(path),"%s/program",dir);
  snprintf(tmp,sizeof(tmp),"%s.tmp",path);
  bw_program_init(&p,NULL);bw_program_init(&loaded,NULL);
  assert(bw_program_load(&p,42,code,3)==0);
  assert(bw_program_save(&p,42,path)==0);
  loaded.owned=3;loaded.ending=1;loaded.waiting=1;
  assert(bw_program_restore(&loaded,42,path)==0);
  assert(!loaded.owned && !loaded.ending && !loaded.waiting && loaded.moving==-1);
  assert(loaded.state==BW_PROGRAM_READY && loaded.id==42 && loaded.count==3);
  assert(!memcmp(loaded.code,code,sizeof(code)));
  before=loaded;unchanged(bw_program_restore(&loaded,43,path));
  fd=open(path,O_RDONLY);assert(fd>=0);size=read(fd,bytes,sizeof(bytes));assert(size==72);assert(!close(fd));
  /* Every metadata/payload/checksum byte is covered, including program ID. */
  for(i=0;i<(unsigned)size;i++) {
    bytes[i]^=1;fd=open(path,O_WRONLY|O_TRUNC);assert(fd>=0);
    assert(write(fd,bytes,(size_t)size)==size);assert(!close(fd));
    unchanged(bw_program_restore(&loaded,42,path));bytes[i]^=1;
  }
  for(i=0;i<(unsigned)size;i++) {
    fd=open(path,O_WRONLY|O_TRUNC);assert(fd>=0);
    assert(write(fd,bytes,i)==(ssize_t)i);assert(!close(fd));
    unchanged(bw_program_restore(&loaded,42,path));
  }
  /* A matching checksum cannot authorize an invalid instruction. */
  bytes[20]=99;
  { uint32_t checksum=bw_program_crc32(bytes,(size_t)size-4);unsigned j;
    for(j=0;j<4;j++)bytes[size-4+j]=(unsigned char)(checksum>>(8*j)); }
  fd=open(path,O_WRONLY|O_TRUNC);assert(fd>=0);
  assert(write(fd,bytes,(size_t)size)==size);assert(!close(fd));
  unchanged(bw_program_restore(&loaded,42,path));
  assert(bw_program_save(&p,42,path)==0);
  fd=open(path,O_WRONLY|O_APPEND);assert(fd>=0);assert(write(fd,"x",1)==1);assert(!close(fd));
  unchanged(bw_program_restore(&loaded,42,path));
  /* Failed temporary-file creation preserves the previous slot. */
  assert(bw_program_save(&p,42,path)==0);assert(!symlink("/nonexistent/bw-slot",tmp));
  assert(bw_program_save(&p,42,path)<0);assert(bw_program_restore(&loaded,42,path)==0);
  before=loaded;loaded.state=BW_PROGRAM_RUNNING;
  assert(bw_program_restore(&loaded,42,path)==-EBUSY);
  assert(bw_program_save(&loaded,42,path)==-EBUSY);loaded=before;
  p.language=1;p.count=4095;memset(p.source,'a',4095);p.source[4095]=0;
  assert(bw_program_save(&p,42,path)==0);assert(bw_program_restore(&loaded,42,path)==0);
  assert(loaded.language==1 && loaded.count==4095 && !strcmp(loaded.source,p.source));
  p.source[12]=0;assert(bw_program_save(&p,42,path)==-EINVAL);
  p.language=0;p.count=256;memset(p.code,0,sizeof(p.code));
  assert(bw_program_save(&p,42,path)==0);assert(bw_program_restore(&loaded,42,path)==0);
  assert(loaded.count==256 && loaded.language==0);
  before=loaded;assert(!unlink(path));unchanged(bw_program_restore(&loaded,42,path));
  assert(!rmdir(dir));puts("storage: native/Python round trips, bounds, corruption, truncation, busy and failure preservation passed");
  return 0;
}
