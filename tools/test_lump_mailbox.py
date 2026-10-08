#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Compile real diagnostic admission against syscall doubles, not guest code."""
import os
from pathlib import Path
import resource
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
def no_core(): resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
def main():
    with tempfile.TemporaryDirectory(prefix='lump-mailbox-control-') as directory:
        root = Path(directory); (root/'nuttx/fs').mkdir(parents=True)
        (root/'nuttx/config.h').write_text('#define CONFIG_BUILD_PROTECTED 1\n#define CONFIG_LEGO_LUMP 1\n#define CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK 1\n')
        (root/'nuttx/fs/ioctl.h').write_text('#include <sys/ioctl.h>\n#undef _IOC\n#define _IOC(base,nr) ((base)|(nr))\n')
        board=root/'arch/board';board.mkdir(parents=True)
        for name in ('board_lump.h','board_legoport.h'):
            (board/name).write_bytes((ROOT/'boards/spike-prime-hub/include'/name).read_bytes())
        for name in ('lumpprobe.h','test_lumprequest.c','test_lumpmailbox.c'):
            (root/name).write_bytes((ROOT/'apps/port'/name).read_bytes())
        (root/'Make.defs').write_text('')
        (root/'Application.mk').write_text('$(info DIAGNOSTIC_FLAGS:$(CFLAGS))\nall:;@true\n')
        flags=['CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK','CONFIG_BUILD_PROTECTED','CONFIG_LEGO_LUMP','CONFIG_APP_PORT']
        for selection in range(16):
            output=subprocess.check_output(['make','--no-print-directory','-f',str(ROOT/'apps/hubprogram/Makefile'),
                                            'APPDIR='+str(root),*[name+'='+('y' if selection&(1<<i) else 'n') for i,name in enumerate(flags)]],text=True)
            assert ('-DBW_SIM_SESSION_DIAGNOSTICS=1' in output)==(selection==15),(selection,output)
        print('Diagnostic worker build guard: all 16 selections PASS')
        source=(ROOT/'apps/port/lumpprobe.c').read_text()
        variants={'baseline':source,
                  'repeat-admission':source.replace('!seq || seq <= previous','!seq'),
                  'keep-old-reply-live':source.replace('g_bw_lump_request_mailbox.reply_seq = 0;', '(void)0;'),
                  'ignore-version':source.replace('version == 1 && selector < 8','((void)version, true) && selector < 8'),
                  'ignore-core-owner':source.replace('if (__sync_lock_test_and_set(&g_request_busy, 1)) return -EBUSY;', '(void)__sync_lock_test_and_set(&g_request_busy, 1);')}
        for name,text in variants.items():
            assert name=='baseline' or text!=source
            (root/'lumpprobe.c').write_text(text)
            exe=root/name
            subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I'+str(root),str(root/'test_lumpmailbox.c'),'-o',str(exe)],check=True)
            p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10,preexec_fn=no_core)
            if name=='baseline':
                assert p.returncode==0 and p.stdout=='Request mailbox C controls PASS\n',(p.returncode,p.stdout,p.stderr)
                print(p.stdout.strip())
            else:
                assert p.returncode!=0 and 'Assertion' in p.stderr,(name,p.returncode,p.stderr)
                print(name+': DETECTED')
if __name__=='__main__': main()
