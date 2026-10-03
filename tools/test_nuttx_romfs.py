#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Read generated init files with the pinned NuttX ROMFS implementation."""
import argparse
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from make_romfs import make_image, checksum


def function(text, signature):
    match = re.search(r'^' + re.escape(signature) + r'[^;{]*\n\{', text, re.M)
    if not match:
        raise ValueError(f'Implementation missing: {signature}')
    end = match.end()
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


def declaration(text, name):
    start = text.index('struct ' + name + '\n{')
    end = text.index('};', start) + 2
    return text[start:end]


def parser_source(nuttx):
    source = (nuttx / 'fs/romfs/fs_romfsutil.c').read_text()
    header = (nuttx / 'fs/romfs/fs_romfs.h').read_text()
    result = source[:source.index('*/') + 2] + '\n'
    result += header[:header.index('*/') + 2] + '\n'
    result += r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#define FAR
#define NAME_MAX 255
#define LINK_NOT_FOLLOWED 0
#define LINK_FOLLOWED 1
#define NODEINFO_NINCR 4
#define fs_heap_free free
#define fs_heap_realloc realloc
#define fs_heap_zalloc(n) calloc(1,n)
#define ferr(...) ((void)0)
#define finfo(...) ((void)0)
typedef int rmutex_t;
'''
    lines = iter(re.sub(r'/\*.*?\*/', '', header, flags=re.S).splitlines())
    for line in lines:
        if re.match(r'#define (ROMFS_|ROMF_|RFNEXT_|IS_|SEC_)', line):
            result += line + '\n'
            while line.endswith('\\'):
                line = next(lines)
                result += line + '\n'
    for name in ('romfs_mountpt_s', 'romfs_nodeinfo_s'):
        result += declaration(header, name) + '\n'
    result += declaration(source, 'romfs_entryname_s') + '\n'
    result += r'''
static uint8_t *image;static size_t image_size;
/* Only the sector transport is mocked; parsing and lookup are unchanged. */
static int16_t romfs_devcacheread(struct romfs_mountpt_s *rm,uint32_t offset) {
  if(offset>=image_size)return -EIO;
  rm->rm_buffer=image+(offset/512)*512;return offset%512;
}
#ifdef CONFIG_FS_ROMFS_CACHE_NODE
void romfs_freenode(struct romfs_nodeinfo_s *nodeinfo);
#endif
'''
    for sig in ('static uint32_t romfs_devread32(',
                'static int romfs_followhardlinks(',
                'int romfs_parsedirentry(', 'int romfs_parsefilename('):
        result += function(source, sig) + '\n'
    result += '#ifndef CONFIG_FS_ROMFS_CACHE_NODE\n'
    result += function(source, 'static inline int romfs_checkentry(') + '\n#endif\n'
    result += '#ifdef CONFIG_FS_ROMFS_CACHE_NODE\n'
    for sig in ('static int romfs_nodeinfo_search(',
                'static int romfs_nodeinfo_compare(',
                'static int romfs_cachenode(', 'void romfs_freenode('):
        result += function(source, sig) + '\n'
    result += '#endif\n'
    for sig in ('static inline int romfs_searchdir(', 'int romfs_fsconfigure(',
                'int romfs_finddirentry(', 'int romfs_datastart('):
        result += function(source, sig) + '\n'
    result += r'''
static void check_file(struct romfs_mountpt_s *rm,const char *path,const char *expected) {
  struct romfs_nodeinfo_s info={0};uint32_t offset;
  assert(romfs_finddirentry(rm,&info,path)==0);assert(IS_FILE(info.rn_next));
  assert(romfs_datastart(rm,&info,&offset)==0);
  assert(info.rn_size==strlen(expected));assert(offset+info.rn_size<=image_size);
  assert(!memcmp(image+offset,expected,info.rn_size));
}
int main(int argc,char **argv) {
  struct romfs_mountpt_s rm={0};struct romfs_nodeinfo_s info={0};FILE *input;
  assert(argc==3);input=fopen(argv[1],"rb");assert(input);
  assert(!fseek(input,0,SEEK_END));image_size=ftell(input);rewind(input);
  image=malloc(image_size);assert(image);assert(fread(image,1,image_size,input)==image_size);assert(!fclose(input));
  rm.rm_hwsectorsize=512;assert(romfs_fsconfigure(&rm)==0);
  if(!strcmp(argv[2],"missing")) {
    assert(romfs_finddirentry(&rm,&info,"init.d/rcS")==-ENOENT);
    puts("ROMFS: old isolated-root layout rejected by actual NuttX lookup");
  } else {
    check_file(&rm,"init.d/rcS","hubprogram serve\nbtsensor start\n");
    check_file(&rm,"init.d/rc.sysinit","# init\n");
    check_file(&rm,"long-directory-name-spanning-several-header-chunks/file","long-name data\n");
    check_file(&rm,"sibling","sibling data\n");
    assert(romfs_finddirentry(&rm,&info,"init.d")==0&&IS_DIRECTORY(info.rn_next));
    assert(romfs_finddirentry(&rm,&info,"init.d/absent")==-ENOENT);
    assert(romfs_finddirentry(&rm,&info,"empty")==0&&info.rn_size==0);
    puts("ROMFS: rcS/sysinit bytes, nested/sibling paths, long names, empty and missing files passed");
  }
#ifdef CONFIG_FS_ROMFS_CACHE_NODE
  romfs_freenode(rm.rm_root);
#endif
  free(image);return 0;
}
'''
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nuttx', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='bw-nuttx-romfs-') as temp:
        root = Path(temp)
        tree = root / 'input'
        (tree / 'init.d').mkdir(parents=True)
        (tree / 'init.d/rcS').write_text('hubprogram serve\nbtsensor start\n')
        (tree / 'init.d/rc.sysinit').write_text('# init\n')
        (tree / 'sibling').write_text('sibling data\n')
        (tree / 'empty').write_bytes(b'')
        long = tree / 'long-directory-name-spanning-several-header-chunks'
        long.mkdir()
        (long / 'file').write_text('long-name data\n')
        image = make_image(tree)
        (root / 'correct.romfs').write_bytes(image)
        # Reproduce the former layout while keeping both checksums valid.
        old = bytearray(image)
        offset = (image.index(0, 16) + 16) & ~15
        next_and_mode = struct.unpack_from('>I', old, offset)[0]
        struct.pack_into('>I', old, offset, next_and_mode & 15)
        end = (image.index(0, offset + 16) + 16) & ~15
        struct.pack_into('>I', old, offset + 12, 0)
        struct.pack_into('>I', old, offset + 12, checksum(old[offset:end]))
        struct.pack_into('>I', old, 12, 0)
        struct.pack_into('>I', old, 12, checksum(old[:512]))
        (root / 'old.romfs').write_bytes(old)
        c = root / 'parser.c'
        c.write_text(parser_source(args.nuttx))
        for cached in (False, True):
            binary = root / 'parser'
            defines = ['-DCONFIG_FS_ROMFS_CACHE_NODE'] if cached else []
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-sign-compare', '-Wno-unused-parameter', *defines, str(c), '-o', str(binary)], check=True)
            subprocess.run([str(binary), str(root / 'correct.romfs'), 'present'], check=True)
            subprocess.run([str(binary), str(root / 'old.romfs'), 'missing'], check=True)
            print(f'ROMFS: actual NuttX parser cache_node={cached} passed', flush=True)


if __name__ == '__main__':
    main()
