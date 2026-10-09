#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile the real request core against syscall doubles; not ARM qualification."""
import os
from pathlib import Path
import re
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def check(executable):
    def run(operation, scenario='empty', code=0):
        p = subprocess.run([str(executable), operation, scenario], capture_output=True,
                           text=True, timeout=10, preexec_fn=no_core)
        assert p.returncode == code, (operation, scenario, p.returncode, p.stderr)
        return p.stdout.splitlines()
    for invalid in ('<null>', '', 'unknown', 'poll extra', 'x' * 32, 'x' * 4096):
        assert run(invalid, 'reject', code=1) == []
    assert run('poll', 'open-fail', 1) == ['BW_LUMP_REQUEST_OPEN v=1 op=poll rc=-1 errno=16']
    for operation, size in [('poll', 48), ('legacy', 36), ('poll-e', 48)]:
        lines = run(operation)
        assert lines == [f'BW_LUMP_REQUEST v=1 op={operation} step=1 rc=-1 errno=11 bytes='+('a5'*size),
                         f'BW_LUMP_REQUEST_END v=1 op={operation} calls=1 close_rc=0 close_errno=0']
        data = run(operation, 'data')
        match = re.fullmatch(r'.* rc=0 errno=0 bytes=([0-9a-f]+)', data[0]); assert match
        raw = bytes.fromhex(match[1]); assert len(raw) == size
        if operation in ('poll','poll-e'):
            assert int.from_bytes(raw[:8], 'little') == 0x1020304050607080
            assert raw[8:16] == bytes([2, 4, 0, 0])+b'ABCD' and raw[16:] == bytes(32)
        else:
            assert raw[:5] == bytes([3, 1, 0, 0, 42]) and raw[5:] == bytes(31)
    faults = ('null', 'readonly', 'kernel', 'wrap', 'legacy-tail')
    for i, operation in enumerate(faults):
        assert run(operation)[0] == f'BW_LUMP_REQUEST v=1 op={operation} step=1 rc=-1 errno={22 if i == 0 else 14} bytes=-'
    batch = run('invalid-then-poll', 'data')
    assert len(batch) == 7
    for i in range(5):
        assert batch[i] == f'BW_LUMP_REQUEST v=1 op=invalid-then-poll step={i+1} rc=-1 errno={22 if i == 0 else 14} bytes=-'
    assert 'step=6 rc=0 errno=0 bytes=8070605040302010' in batch[5]
    assert batch[6] == 'BW_LUMP_REQUEST_END v=1 op=invalid-then-poll calls=6 close_rc=0 close_errno=0'
    batch_e = run('invalid-then-poll-e', 'data')
    assert batch_e == [line.replace('invalid-then-poll', 'invalid-then-poll-e') for line in batch]
    assert run('poll', 'close-fail', 1)[-1].endswith('close_rc=-1 close_errno=5')
    assert run('invalid-then-poll', 'startup') == []


def main():
    with tempfile.TemporaryDirectory(prefix='lump-request-control-') as directory:
        root = Path(directory); (root/'nuttx/fs').mkdir(parents=True)
        (root/'nuttx/config.h').write_text('#define CONFIG_BUILD_PROTECTED 1\n#define CONFIG_LEGO_LUMP 1\n#define CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK 1\n')
        (root/'nuttx/fs/ioctl.h').write_text('#include <sys/ioctl.h>\n#undef _IOC\n#define _IOC(base,nr) ((base)|(nr))\n')
        board=root/'arch/board';board.mkdir(parents=True)
        for name in ('board_lump.h', 'board_legoport.h'):
            (board/name).write_bytes((ROOT/'boards/spike-prime-hub/include'/name).read_bytes())
        for name in ('lumpprobe.h', 'test_lumprequest.c'):
            (root/name).write_bytes((ROOT/'apps/port'/name).read_bytes())
        source=(ROOT/'apps/port/lumpprobe.c').read_text()
        variants = {'baseline': source,
                    'startup-writes-console': source.replace('return request_run("invalid-then-poll", false, NULL) == 0 ? 0 : 1;', 'return request_run("invalid-then-poll", true, NULL) == 0 ? 0 : 1;'),
                    'lost-errno': source.replace('result, error, NULL, 0, emit);', 'result, ((void)error, 0), NULL, 0, emit);'),
                    'close-between-requests': source.replace('request_reply(operation, ++calls, result, error, NULL, 0, emit);', 'request_reply(operation, ++calls, result, error, NULL, 0, emit); if (selected == 7 && calls == 1) (void)close(fd);')}
        variants['route-e-to-f'] = source.replace(
            'open(selected < 8 ? "/dev/legoport5" : "/dev/legoport4", O_RDONLY)',
            'open("/dev/legoport5", O_RDONLY)')
        for name, text in variants.items():
            assert name == 'baseline' or text != source
            (root/'lumpprobe.c').write_text(text)
            executable=root/name
            subprocess.run([os.environ.get('CC','cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-I'+str(root), str(root/'test_lumprequest.c'), '-o', str(executable)], check=True)
            if name == 'baseline': check(executable); print('Request contract host controls PASS')
            else:
                try: check(executable)
                except AssertionError: print(name+': DETECTED')
                else: raise AssertionError('Request mutation escaped: '+name)

if __name__ == '__main__': main()
