#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile actual patched Apps functions with fault-injection host stubs.

This verifies error paths, resource cleanup and packet buffer bounds, not a
complete NuttX or Zmodem session. --baseline checks that the previous source
fails each relevant regression (plus the deliberately weakened Zmodem margin).
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

FUNCTIONS = [
    ('nshlib/nsh_console.c', 'nsh_consolewrite'),
    ('nshlib/nsh_fsutils.c', 'nsh_catfile'),
    ('nshlib/nsh_envcmds.c', 'cmd_cd'),
    ('nshlib/nsh_fscmds.c', 'cmd_cat'),
    ('nshlib/nsh_fscmds.c', 'fdinfo_callback'),
    ('system/readline/readline_fd.c', 'readline_fd'),
    ('system/zmodem/zm_proto.c', 'zm_putzdle'),
    ('system/zmodem/zm_send.c', 'zms_sendpacket'),
]

def extract(source, name):
    # Blank comments without changing offsets, so braces in comments cannot
    # affect function extraction. These selected functions contain no brace
    # characters inside string literals.
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: ' ' * len(m[0]), source, flags=re.S)
    match = re.search(r'^.*\b' + name + r'\([^;{}]*?\)\s*\{', clean, re.M)
    if not match:
        raise ValueError('Cannot find definition of ' + name)
    start = clean.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    return source[match.start():end]

PRELUDE = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <termios.h>
#include <dirent.h>
#include <ctype.h>
#include <libgen.h>
#define FAR
#define OK 0
#define ERROR -1
#define UNUSED(x) (void)(x)
#define NSH_ERRNO errno
#define NSH_ERRNO_OF(x) (x)
#define IOBUFFERSIZE 512
#define OUTFD(x) ((x)->outfd)
#define DIRENT_ISDIRECTORY(t) ((t) == DT_DIR)
#define CONFIG_READLINE_ECHO 1
struct nsh_vtbl_s { int dummy; };
struct console_stdio_s { struct nsh_vtbl_s vtbl; int outfd; };
struct readline_vtbl_s { int (*rl_getc)(struct readline_vtbl_s *); void (*rl_putc)(struct readline_vtbl_s *, int); void (*rl_write)(struct readline_vtbl_s *, const char *, size_t); };
struct readline_s { struct readline_vtbl_s vtbl; int infd, outfd; };
static const char *g_fmtcmdfailed="failed", *g_fmtsignalrecvd="signal", *g_fmtcmdoutofmemory="oom", *g_home="/home", *g_oldpwd="OLDPWD";
static int errors, logs, reads, writes, closes, frees, changes, allocations;
static int fail_malloc, fail_strdup, fail_fullpath, fail_asprintf, fail_write;
static int tty, fail_getattr, fail_setattr, sets;
static struct termios initial_termios, active_termios;
static void reset(void) {
  errors=logs=reads=writes=closes=frees=changes=allocations=sets=0;
  fail_malloc=fail_strdup=fail_fullpath=fail_asprintf=fail_write=0;
  tty=fail_getattr=fail_setattr=0;
  memset(&initial_termios,0,sizeof(initial_termios));
  initial_termios.c_lflag=ICANON|ECHO; active_termios=initial_termios;
}
static void *test_malloc(size_t n) { allocations++; return fail_malloc ? NULL : malloc(n); }
static void test_free(void *p) { if(p) frees++; free(p); }
static char *test_strdup(const char *s) { allocations++; return fail_strdup ? NULL : strdup(s); }
static int test_asprintf(char **p,const char *fmt,...) { (void)fmt; allocations++; if(fail_asprintf) { *p=NULL; return -1; } *p=strdup("/proc/123/group/fd"); return 18; }
static int test_open(const char *p,int flags,...) { (void)flags; assert(p); return 7; }
static int test_close(int fd) { assert(fd==7); closes++; return 0; }
static ssize_t test_read(int fd,void *p,size_t n) { assert(fd==7); assert(p); reads++; if(reads==1) { memset(p,'x',n); return n; } return 0; }
static ssize_t test_write(int fd,const void *p,size_t n) { (void)fd; assert(p); writes++; if(fail_write) { errno=EPIPE; return -1; } return n; }
static int test_chdir(const char *p) { assert(p); changes++; return 0; }
static void nsh_error(struct nsh_vtbl_s *v,const char *fmt,...) { (void)v; (void)fmt; errors++; }
static void nsh_output(struct nsh_vtbl_s *v,const char *fmt,...) { (void)v; (void)fmt; }
static void test_log(const char *fmt,...) { (void)fmt; logs++; }
static ssize_t nsh_write(struct nsh_vtbl_s *v,const void *p,size_t n) { (void)v; return test_write(9,p,n); }
static ssize_t nsh_read(struct nsh_vtbl_s *v,void *p,size_t n) { (void)v; return test_read(7,p,n); }
static const char *nsh_getwd(const char *p) { (void)p; return "/old"; }
static const char *nsh_getcwd(struct nsh_vtbl_s *v) { (void)v; return "/parent/child"; }
static char *nsh_getfullpath(struct nsh_vtbl_s *v,const char *p) { (void)v; (void)p; allocations++; return fail_fullpath ? NULL : strdup("/full"); }
static void nsh_freefullpath(char *p) { test_free(p); }
static int test_isatty(int fd) { (void)fd; return tty; }
static int test_tcgetattr(int fd,struct termios *t) { (void)fd; if(fail_getattr) return -1; *t=initial_termios; return 0; }
static int test_tcsetattr(int fd,int action,const struct termios *t) { (void)fd; (void)action; sets++; if(fail_setattr) return -1; active_termios=*t; return 0; }
static int readline_getc(struct readline_vtbl_s *v) { (void)v; return 0; }
static void readline_putc(struct readline_vtbl_s *v,int c) { (void)v; (void)c; }
static void readline_write(struct readline_vtbl_s *v,const char *s,size_t n) { (void)v; (void)s; (void)n; }
static ssize_t readline_common(struct readline_vtbl_s *v,char *b,int n) { (void)v; assert(n>1); b[0]='x'; b[1]=0; return 1; }
#define malloc test_malloc
#define free test_free
#define strdup test_strdup
#define asprintf test_asprintf
#define open test_open
#define close test_close
#define read test_read
#define write test_write
#define chdir test_chdir
#define isatty test_isatty
#define tcgetattr test_tcgetattr
#define tcsetattr test_tcsetattr
#define _err test_log
#define CONFIG_SYSTEM_ZMODEM_SNDBUFSIZE 1024
#define CONFIG_SYSTEM_ZMODEM_RESPTIME 30
#define ASCII_DLE 16
#define ASCII_DC1 17
#define ASCII_DC3 19
#define ASCII_GS 29
#define ASCII_DEL 127
#define ZDLE 24
#define ZRUB0 'l'
#define ZRUB1 'm'
#define ZCRCE 'h'
#define ZCRCG 'i'
#define ZCRCQ 'j'
#define ZCRCW 'k'
#define ZEOF 11
#define ZM_FLAG_CRC32 (1<<0)
#define ZM_FLAG_EOF (1<<2)
#define ZM_FLAG_ATSIGN (1<<3)
#define ZM_FLAG_ESCCTRL (1<<4)
#define ZM_FLAG_WAIT (1<<6)
#define ZMS_SENDWAIT 1
#define ZMS_SENDDONE 2
#define ZMS_SENDING 3
#define ZMS_SENDEOF 4
#define DEBUGASSERT assert
#define zmdbg(...) ((void)0)
struct zm_state_s { int flags,state,timeout,remfd; uint8_t scratch[1040]; };
struct zms_state_s { struct zm_state_s cmn; int filesize,offset,lastoffs,rcvmax,infd; uint8_t dpkttype; };
static unsigned sample_byte;
static int packet_count, max_packet;
static uint8_t zm_getc(int fd) { (void)fd; return sample_byte; }
/* Deliberately force an all-escaped checksum trailer to exercise the maximum
 * possible expansion; this is a bounds test, not CRC correctness validation.
 */
static uint32_t crc32part(const uint8_t *p,size_t n,uint32_t c) { (void)p; (void)n; (void)c; return ~UINT32_C(0x18181818); }
static uint16_t crc16xmodempart(const uint8_t *p,size_t n,uint16_t c) { (void)p; (void)n; (void)c; return 0x1818; }
static void zm_be32toby(uint32_t v,uint8_t b[4]) { for(int i=0;i<4;i++) b[i]=(v>>(24-8*i))&255; }
static int zm_sendhexhdr(struct zm_state_s *p,int type,const uint8_t *b) { (void)p; (void)type; (void)b; return 0; }
static ssize_t zm_remwrite(int fd,const uint8_t *p,size_t n) { (void)fd; assert(n<1024); assert(p[1024]==0xa5); packet_count++; if((int)n>max_packet) max_packet=n; return n; }
'''

TESTS = r'''
int main(int argc,char **argv) {
  assert(argc==2); struct nsh_vtbl_s v={0}; reset();
  if(!strcmp(argv[1],"stdout")) {
    struct console_stdio_s c={.outfd=9}; fail_write=1;
    assert(nsh_consolewrite(&c.vtbl,"x",1)==-1); assert(errno==EPIPE); assert(logs==0);
    assert(nsh_catfile(&v,"cat","/dev/log")==-1);
    assert(reads==1 && closes==1 && frees==1); /* no read after failed write */
    reset(); assert(nsh_catfile(&v,"cat","/file")==0);
    assert(reads==2 && writes==1 && closes==1 && frees==1);
  } else if(!strcmp(argv[1],"readline")) {
    char b[8]; tty=1; assert(readline_fd(b,8,0,1)==1);
    assert(sets==2 && active_termios.c_lflag==initial_termios.c_lflag);
    reset(); tty=1; fail_getattr=1; assert(readline_fd(b,8,0,1)==1); assert(sets==0);
    reset(); tty=1; fail_setattr=1; assert(readline_fd(b,8,0,1)==1); assert(sets==1);
    reset(); tty=1; initial_termios.c_lflag=ECHO;
    assert(readline_fd(b,8,0,1)==1); assert(sets==0);
    reset(); assert(readline_fd(b,8,0,1)==1); assert(sets==0);
  } else if(!strcmp(argv[1],"cd")) {
    char *a[]={"cd","-",NULL}; fail_strdup=1;
    assert(cmd_cd(&v,2,a)==-1 && changes==0 && errors==1);
    reset(); fail_strdup=1; a[1]="..";
    assert(cmd_cd(&v,2,a)==-1 && changes==0 && errors==1);
    reset(); fail_fullpath=1; a[1]="folder";
    assert(cmd_cd(&v,2,a)==-1 && changes==0 && errors==1);
    reset(); assert(cmd_cd(&v,2,a)==0 && changes==1 && frees==1);
    reset(); a[1]=".."; assert(cmd_cd(&v,2,a)==0 && changes==1 && frees==1);
  } else if(!strcmp(argv[1],"cat")) {
    char *a[]={"cat",NULL}; fail_malloc=1;
    assert(cmd_cat(&v,1,a)==-ENOMEM && reads==0 && writes==0);
    reset(); assert(cmd_cat(&v,1,a)==0); assert(reads==2 && writes==1 && frees==1);
  } else if(!strcmp(argv[1],"fdinfo")) {
    struct dirent ent={0}; ent.d_type=DT_DIR; strcpy(ent.d_name,"123"); fail_asprintf=1;
    assert(fdinfo_callback(&v,"/proc",&ent,NULL)==-1);
    assert(reads==0 && writes==0 && closes==0);
    reset(); assert(fdinfo_callback(&v,"/proc",&ent,NULL)==0);
    assert(reads==2 && writes==1 && closes==1 && frees==2);
  } else if(!strcmp(argv[1],"zmodem")) {
    for(int crc=0;crc<2;crc++) for(unsigned byte=0;byte<256;byte++) {
      for(int length=1;length<=4096;length+=(length<32?1:127)) {
        struct zms_state_s s={0}; s.filesize=length; s.dpkttype=ZCRCW;
        s.cmn.flags=crc?ZM_FLAG_CRC32:0; sample_byte=byte;
        memset(s.cmn.scratch,0xa5,sizeof(s.cmn.scratch));
        assert(zms_sendpacket(&s.cmn)==0);
        assert(s.offset>0 && s.offset<=length && s.cmn.scratch[1024]==0xa5);
      }
    }
    assert(packet_count>30000 && max_packet<1024);
    printf("Zmodem: %d boundary/escaping packets, max %d bytes\n",packet_count,max_packet);
  } else assert(0);
  return 0;
}
'''


def sources(apps, revision=None):
    pieces = []
    for path, name in FUNCTIONS:
        if revision:
            source = subprocess.run(['git','show',revision+':'+path],cwd=apps,
                                    capture_output=True,text=True,check=True).stdout
        else:
            source = (apps/path).read_text()
        pieces.append(extract(source,name))
    return PRELUDE+'\n'+'\n'.join(pieces)+'\n'+TESTS


def compile_source(source, directory, label):
    cfile=directory/(label+'.c'); binary=directory/label
    cfile.write_text(source)
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O0','-g',
                    '-Wall','-Wextra','-Wno-unused-function','-Wno-unused-variable',
                    str(cfile),'-o',str(binary)],check=True)
    return binary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps',type=Path,required=True)
    parser.add_argument('--baseline',help='Optional previous Apps Git revision; expect old regressions to fail')
    args=parser.parse_args()
    cases=('stdout','readline','cd','cat','fdinfo','zmodem')
    with tempfile.TemporaryDirectory(prefix='bw-apps-hardening-') as folder:
        directory=Path(folder)
        current=sources(args.apps)
        binary=compile_source(current,directory,'patched')
        for case in cases:
            subprocess.run([str(binary),case],check=True,timeout=15)
            print('PASS '+case,flush=True)
        if args.baseline:
            old=compile_source(sources(args.apps,args.baseline),directory,'baseline')
            for case in cases[:-1]:
                result=subprocess.run([str(old),case],capture_output=True,timeout=15)
                if result.returncode==0:
                    raise SystemExit('Regression test failed to detect baseline: '+case)
                print('PASS baseline rejected '+case,flush=True)
            weakened=current.replace('CONFIG_SYSTEM_ZMODEM_SNDBUFSIZE - 16','CONFIG_SYSTEM_ZMODEM_SNDBUFSIZE - 10')
            if weakened==current:
                raise SystemExit('Cannot locate preserved Zmodem margin')
            mutant=compile_source(weakened,directory,'old-margin')
            result=subprocess.run([str(mutant),'zmodem'],capture_output=True,timeout=15)
            if result.returncode==0:
                raise SystemExit('Boundary test failed to detect old Zmodem margin')
            print('PASS old Zmodem margin rejected',flush=True)

if __name__=='__main__':
    main()
