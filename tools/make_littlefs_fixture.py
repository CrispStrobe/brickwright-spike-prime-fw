#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Generate an optional synthetic, already-formatted empty LittleFS fixture.

Requires exact external qualified sources; never downloads or vendors them.
This fixture does not exercise erased-media first-boot formatting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

SOURCES = {
    'lfs.c': '59d1bf5cd621c76e8373881b8104079f3208fb471ffba13f952baee823bafb78',
    'lfs.h': '56b76d9ffbe450aa1552f7f593546e5fa2bafa420720eacaecf6cfe5c6a28c98',
    'lfs_util.c': '8e1376a90e923a2897388a54ebaa756ad3ea07a0e2a87e73c0045515c0a82685',
    'lfs_util.h': '0cad77a4c385f4a77b96148096c3a235c95b199a9e95e57a515241769a49ed44',
    'LICENSE.md': '0cb4ff1daf5fdc1359c6a6ee3116092f08fc100c9d58b1b77ab17bfd801f856d',
}
GEOMETRY = dict(chip_size=32*1024*1024, partition_offset=1024*1024,
                partition_size=31*1024*1024, erased_byte=255, page_size=256,
                block_size=4096, block_count=7936, read_size=1024,
                prog_size=1024, cache_size=1024, block_cycles=200,
                lookahead_size=992, name_max=32, file_max=2147483647, attr_max=1022)
COMPILE_DEFINITIONS = [
    'LFS_NAME_MAX=32', 'LFS_FILE_MAX=2147483647', 'LFS_ATTR_MAX=1022',
]
BLOCK_HASHES = (
    'f11900b4e77fdd93fed3dbfe5db5bf8b9e2c3107d61bf7f61936101467b1efc3',
    'f1b8c5aaf33085b6d6c864a22bfbef3a98f5803e75a757cae144d133e3b0b25c',
)
HARNESS = r'''/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Original host fixture adapter; external LittleFS retains its own notices.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lfs.h"
#define BYTES (31u*1024u*1024u)
static uint8_t *flash;
static unsigned writes;
static int rd(const struct lfs_config *c,lfs_block_t b,lfs_off_t o,void *p,lfs_size_t n) {
  (void)c;assert(b*4096u+o+n<=BYTES);memcpy(p,flash+b*4096u+o,n);return 0;
}
static int prog(const struct lfs_config *c,lfs_block_t b,lfs_off_t o,const void *p,lfs_size_t n) {
  unsigned i;const uint8_t *s=p;(void)c;assert(b*4096u+o+n<=BYTES);writes++;
  for(i=0;i<n;i++){assert((flash[b*4096u+o+i]&s[i])==s[i]);flash[b*4096u+o+i]&=s[i];}return 0;
}
static int erase(const struct lfs_config *c,lfs_block_t b) {
  (void)c;assert(b<7936);memset(flash+b*4096u,255,4096);writes++;return 0;
}
static int sync_flash(const struct lfs_config *c) {(void)c;return 0;}
static const struct lfs_config cfg={.read=rd,.prog=prog,.erase=erase,.sync=sync_flash,
  .read_size=1024,.prog_size=1024,.block_size=4096,.block_count=7936,
  .block_cycles=200,.cache_size=1024,.lookahead_size=992};
int main(int argc, char **argv) {
  lfs_t fs={0};lfs_dir_t dir;struct lfs_info info;unsigned b,i,dots=0;int rc;
  flash=malloc(BYTES);assert(flash);memset(flash,255,BYTES);
  if(argc==3) {
    FILE *input=fopen(argv[1],"rb");uint8_t offset[4];assert(input);
    while(fread(offset,1,4,input)==4) {
      b=((unsigned)offset[0]<<24)|((unsigned)offset[1]<<16)|((unsigned)offset[2]<<8)|offset[3];
      assert(b<7936);assert(fread(flash+b*4096u,1,4096,input)==4096);
    }
    assert(feof(input));assert(fclose(input)==0);
    rc=lfs_mount(&fs,&cfg);assert(rc==atoi(argv[2]));
    if(rc==0)assert(lfs_unmount(&fs)==0);
    free(flash);return 0;
  }
  assert(argc==1);assert(lfs_format(&fs,&cfg)==0);
  /* The serialized state must mount as an empty filesystem without writes. */
  writes=0;assert(lfs_mount(&fs,&cfg)==0);assert(lfs_dir_open(&fs,&dir,"/")==0);
  while((rc=lfs_dir_read(&fs,&dir,&info))>0) {
    assert(info.type==LFS_TYPE_DIR);assert(!strcmp(info.name,".")||!strcmp(info.name,".."));dots++;
  }
  assert(rc==0&&dots==2);assert(lfs_dir_close(&fs,&dir)==0);assert(lfs_unmount(&fs)==0);assert(!writes);
  for(b=0;b<7936;b++) {
    for(i=0;i<4096;i++)if(flash[b*4096u+i]!=255)break;
    if(i<4096) {
      uint8_t offset[4]={(uint8_t)(b>>24),(uint8_t)(b>>16),(uint8_t)(b>>8),(uint8_t)b};
      assert(fwrite(offset,1,4,stdout)==4);assert(fwrite(flash+b*4096u,1,4096,stdout)==4096);
    }
  }
  free(flash);assert(fflush(stdout)==0);return 0;
}
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_sources(source):
    for name, expected in SOURCES.items():
        if digest((source / name).read_bytes()) != expected:
            raise ValueError(f'{name}: does not match the qualified LittleFS source')


def compile_harness(source, temp, definitions=COMPILE_DEFINITIONS):
    """Compile with the same persistent-limit definitions as NuttX Make.defs."""
    (temp / 'nuttx/mm').mkdir(parents=True)
    (temp / 'nuttx/mm/mm.h').write_text('/* Host allocator shim. */\n')
    (temp / 'fs_heap.h').write_text('#include <stdlib.h>\n#define fs_heap_malloc malloc\n#define fs_heap_free free\n')
    c = temp / 'fixture.c'
    c.write_text(HARNESS)
    binary = temp / 'fixture'
    subprocess.run(['cc', '-std=c99', '-O1', '-Wall', '-Wextra', '-Werror',
                    '-Wno-sign-compare', '-DLFS_NO_DEBUG', '-DLFS_NO_WARN',
                    '-DLFS_NO_ERROR', *['-D' + definition for definition in definitions],
                    '-I' + str(source), '-I' + str(temp),
                    str(c), str(source / 'lfs.c'), str(source / 'lfs_util.c'),
                    '-o', str(binary)], check=True)
    return binary


def compile_fixture(source, temp):
    """Return records produced by real format/mount calls, not canned bytes."""
    binary = compile_harness(source, temp)
    first = subprocess.check_output([str(binary)])
    if subprocess.check_output([str(binary)]) != first:
        raise ValueError('Independent format/mount runs produced different bytes')
    return first


def fixture_from_records(records):
    if len(records) != 2 * (4 + 4096):
        raise ValueError('Unexpected changed-block count')
    blocks = []
    payload = bytearray()
    for i, expected_hash in enumerate(BLOCK_HASHES):
        start = i * 4100
        block = struct.unpack_from('>I', records, start)[0]
        data = records[start + 4:start + 4100]
        if block != i or digest(data) != expected_hash:
            raise ValueError('Formatted block differs from qualified empty-media state')
        blocks.append(dict(chip_offset=GEOMETRY['partition_offset'] + block*4096,
                           payload_offset=len(payload), length=4096,
                           sha256=digest(data)))
        payload.extend(data)
    receipt = dict(schema=1, purpose='synthetic already-formatted empty LittleFS boot',
                   covers_erased_first_boot=False, littlefs_version='v2.5.1',
                   source_sha256=SOURCES, geometry=GEOMETRY,
                   compile_definitions=COMPILE_DEFINITIONS, blocks=blocks,
                   payload_file='flash-blocks.bin', payload_size=len(payload),
                   payload_sha256=digest(payload))
    return bytes(payload), receipt


def verify_fixture(directory):
    receipt = json.loads((directory / 'receipt.json').read_text())
    payload = (directory / 'flash-blocks.bin').read_bytes()
    if (receipt.get('schema') != 1 or receipt.get('source_sha256') != SOURCES or
            receipt.get('littlefs_version') != 'v2.5.1' or
            receipt.get('compile_definitions') != COMPILE_DEFINITIONS):
        raise ValueError('Fixture source provenance differs from qualification')
    if receipt.get('geometry') != GEOMETRY or receipt.get('covers_erased_first_boot') is not False:
        raise ValueError('Fixture geometry or coverage claim differs')
    if receipt.get('payload_file') != 'flash-blocks.bin' or receipt.get('payload_size') != 8192:
        raise ValueError('Unexpected payload layout')
    if len(payload) != 8192 or receipt.get('payload_sha256') != digest(payload):
        raise ValueError('Payload size/hash mismatch')
    expected = []
    for i, expected_hash in enumerate(BLOCK_HASHES):
        if digest(payload[i*4096:(i+1)*4096]) != expected_hash:
            raise ValueError('Payload block differs from qualified empty-media state')
        expected.append(dict(chip_offset=1024*1024+i*4096, payload_offset=i*4096,
                             length=4096, sha256=expected_hash))
    if receipt.get('blocks') != expected:
        raise ValueError('Block offsets, bounds or hashes differ')
    return receipt


def generate(source, output):
    verify_sources(source)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty; existing data preserved')
    with tempfile.TemporaryDirectory(prefix='bw-lfs-fixture-') as temp:
        payload, receipt = fixture_from_records(compile_fixture(source, Path(temp)))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'flash-blocks.bin').write_bytes(payload)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    verify_fixture(output)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--littlefs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        source = args.littlefs.resolve()
        verify_sources(source)
        receipt = verify_fixture(args.output) if args.check else generate(source, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'LittleFS fixture: {exc}\n')
    print(f'LittleFS fixture: {receipt["payload_size"]} synthetic bytes; existing-filesystem boot only')


if __name__ == '__main__':
    main()
