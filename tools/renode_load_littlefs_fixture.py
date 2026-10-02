# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Explicit existing-filesystem fixture loading using the NOR SPI interface.

Compatible with Renode IronPython and CPython. No model state reflection, reset,
chip erase or implicit test seeding. This never qualifies erased-media first boot.

After platform reset, while paused and before starting the guest:
  include @tools/renode_load_littlefs_fixture.py
  load_littlefs_fixture @.local/firmware-images/existing-filesystem

Only explicitly selected existing-filesystem tests may invoke this command.
"""
import hashlib
import json
import os

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
                lookahead_size=992, name_max=32,
                file_max=2147483647, attr_max=1022)
BLOCK_HASHES = (
    'f11900b4e77fdd93fed3dbfe5db5bf8b9e2c3107d61bf7f61936101467b1efc3',
    'f1b8c5aaf33085b6d6c864a22bfbef3a98f5803e75a757cae144d133e3b0b25c',
)

COMPILE_DEFINITIONS = ['LFS_NAME_MAX=32', 'LFS_FILE_MAX=2147483647',
                       'LFS_ATTR_MAX=1022']

PAYLOAD_SHA256 = '4ae9878c92b095387721da4d128722faa7eefef68250b4875256cef4bc82ccad'


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_fixture(directory):
    # Bounds apply before parsing or issuing any peripheral command.
    with open(os.path.join(directory, 'receipt.json'), 'rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError('Fixture receipt exceeds size limit')
    receipt = json.loads(raw.decode('utf-8'))
    if (receipt.get('schema') != 1 or receipt.get('littlefs_version') != 'v2.5.1'
            or receipt.get('source_sha256') != SOURCES
            or receipt.get('compile_definitions') != COMPILE_DEFINITIONS):
        raise ValueError('Fixture source provenance differs from qualification')
    if (receipt.get('geometry') != GEOMETRY
            or receipt.get('covers_erased_first_boot') is not False
            or receipt.get('purpose') != 'synthetic already-formatted empty LittleFS boot'):
        raise ValueError('Fixture geometry or coverage differs')
    if receipt.get('payload_file') != 'flash-blocks.bin' or receipt.get('payload_size') != 8192:
        raise ValueError('Unexpected payload layout')
    with open(os.path.join(directory, 'flash-blocks.bin'), 'rb') as stream:
        payload = stream.read(8193)
    if (len(payload) != 8192 or _digest(payload) != PAYLOAD_SHA256
            or receipt.get('payload_sha256') != PAYLOAD_SHA256):
        raise ValueError('Fixture payload size/hash differs')
    expected = []
    for i, known_hash in enumerate(BLOCK_HASHES):
        if _digest(payload[i*4096:(i+1)*4096]) != known_hash:
            raise ValueError('Fixture block hash differs')
        expected.append(dict(chip_offset=1048576+i*4096, payload_offset=i*4096,
                             length=4096, sha256=known_hash))
    if receipt.get('blocks') != expected:
        raise ValueError('Fixture block offsets, bounds or hashes differ')
    return payload, receipt


def _byte(value):
    return value if isinstance(value, int) else ord(value)


def _transaction(flash, command, data):
    # FinishTransmission supplies the CS boundary for every command, including
    # failures. Only the existing public ISPIPeripheral methods are used.
    try:
        flash.Transmit(command)
        return bytearray(int(flash.Transmit(_byte(value))) for value in data)
    finally:
        flash.FinishTransmission()


def _address(address):
    return [(address >> shift) & 255 for shift in (24, 16, 8, 0)]


def _read(flash, address, length):
    result = _transaction(flash, 0x0C, _address(address) + [0] + [255]*length)
    return result[5:]


def load_fixture(flash, directory):
    payload, receipt = validate_fixture(directory)
    # Check both destinations before any WREN/program command. The caller must
    # invoke this after platform creation/reset and before starting the guest.
    for block in receipt['blocks']:
        if any(value != 255 for value in _read(flash, block['chip_offset'], block['length'])):
            raise ValueError('Fixture destination is not erased; refusing to alter it')
    pages = 0
    for block in receipt['blocks']:
        for offset in range(0, block['length'], 256):
            _transaction(flash, 0x06, [])
            begin = block['payload_offset'] + offset
            _transaction(flash, 0x12, _address(block['chip_offset'] + offset)
                         + [_byte(value) for value in payload[begin:begin+256]])
            pages += 1
    for block in receipt['blocks']:
        actual = _read(flash, block['chip_offset'], block['length'])
        if _digest(actual) != block['sha256']:
            raise ValueError('NOR fixture readback differs')
    return dict(pages_programmed=pages, bytes_programmed=len(payload),
                partition_offset=1048576, partition_size=32505856,
                payload_sha256=PAYLOAD_SHA256, covers_erased_first_boot=False,
                littlefs_version=receipt['littlefs_version'],
                compile_definitions=receipt['compile_definitions'],
                source_sha256=receipt['source_sha256'],
                geometry=receipt['geometry'], blocks=receipt['blocks'])


def mc_load_littlefs_fixture(directory):
    if not monitor.Machine.IsPaused:
        raise ValueError('Pause the machine before explicit fixture loading')
    flash = monitor.Machine['sysbus.spi2.flashMux.norFlash']
    proof = load_fixture(flash, str(directory).lstrip('@'))
    print('LittleFS existing-media fixture: ' + json.dumps(proof, sort_keys=True))
    monitor.Parse('log "MILESTONE existing filesystem ready"')
