#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
"""Host-build the complete actual chardev with neutral NuttX service boundaries."""
from pathlib import Path
import resource
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    with tempfile.TemporaryDirectory(prefix='lump-ioctl-') as directory:
        root = Path(directory)

        def write(name, content):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        for name in ['board_usercheck.h', 'stm32_legoport_chardev.c', 'lump_data_queue.h']:
            (root / name).write_bytes((ROOT / 'boards/spike-prime-hub/src' / name).read_bytes())
        for name in ['board_legoport.h', 'board_lump.h']:
            path = root / 'arch/board' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / 'boards/spike-prime-hub/include' / name).read_bytes())
        write('nuttx/config.h', '#define CONFIG_LEGO_PORT 1\n#define CONFIG_LEGO_LUMP 1\n'
              '#define CONFIG_BUILD_PROTECTED 1\n#define FAR\n#define OK 0\n'
              '#define UNUSED(x) ((void)(x))\n')
        write('nuttx/compiler.h', '#define FAR\n')
        write('nuttx/semaphore.h', '')
        write('spike_prime_hub.h', '')
        write('nuttx/fs/ioctl.h', '#define _IOC(base,nr) ((base)|(nr))\n')
        write('nuttx/mutex.h', 'typedef int mutex_t;\n'
              'static inline int nxmutex_init(mutex_t *m) {(void)m;return 0;}\n'
              'static inline int nxmutex_lock(mutex_t *m) {(void)m;return 0;}\n'
              'static inline int nxmutex_unlock(mutex_t *m) {(void)m;return 0;}\n')
        write('poll.h', '#define POLLIN 1\nstruct pollfd {int events;void *priv;};\n'
              'static inline void poll_notify(struct pollfd **p,int n,int e) {(void)p;(void)n;(void)e;}\n')
        write('nuttx/fs/fs.h', '''struct inode {void *i_private;};
struct file {struct inode *f_inode;};
struct file_operations {
 int (*open)(struct file *); int (*close)(struct file *);
 ssize_t (*read)(struct file *, char *, size_t);
 ssize_t (*write)(struct file *, const char *, size_t);
 void *seek; int (*ioctl)(struct file *,int,unsigned long);
 void *mmap; void *truncate;
 int (*poll)(struct file *,struct pollfd *,bool);
};
static inline int register_driver(const char *p,const struct file_operations *f,int m,void *v)
{(void)p;(void)f;(void)m;(void)v;return 0;}
''')
        stubs = '#include <errno.h>\n#include <nuttx/config.h>\n#include <arch/board/board_legoport.h>\n#include <arch/board/board_lump.h>\n'
        # Every unrelated service is a refusal, with no side effects.
        signatures = {
            'stm32_legoport_get_info': 'int p, struct legoport_info_s *o',
            'stm32_legoport_wait_change': 'int p, uint32_t s, uint32_t t, uint32_t *o',
            'stm32_legoport_pwm_set_duty': 'int p, int16_t d',
            'stm32_legoport_pwm_coast': 'int p',
            'stm32_legoport_pwm_brake': 'int p',
            'stm32_legoport_pwm_close_cleanup': 'int p',
            'stm32_legoport_pwm_get_status': 'int p, struct legoport_pwm_status_s *o',
            'lump_get_info': 'int p, struct lump_device_info_s *o',
            'lump_select_mode': 'int p, uint8_t m',
            'lump_send_data': 'int p, uint8_t m, const uint8_t *b, size_t n',
            'lump_get_status_full': 'int p, struct lump_status_full_s *o',
        }
        for name, args in signatures.items():
            voids = ''.join('(void)' + arg.strip().split()[-1].lstrip('*') + ';'
                            for arg in args.split(','))
            stubs += 'int ' + name + '(' + args + '){' + voids + 'return -ENOTSUP;}\n'
        stubs += 'void stm32_legoport_get_stats(struct legoport_stats_s *o){(void)o;}\n'
        stubs += 'void stm32_legoport_reset_stats(void){}\n'
        write('stubs.c', stubs)
        source = ROOT / 'boards/spike-prime-hub/test/test_lump_session_ioctl.c'
        # The actual source and pointer checker are copied byte-for-byte; only
        # neutral dependency headers and unrelated service definitions are fake.
        actual = (root / 'stm32_legoport_chardev.c').read_text()
        start = actual.index('      case LEGOPORT_LUMP_POLL_DATA_SESSION:')
        end = actual.index('      case LEGOPORT_LUMP_GET_STATUS_EX:', start)
        case = actual[start:end]
        mutations = {
            'validate-only-legacy-size': (
                'board_user_out_ok(user, sizeof(*user))',
                'board_user_out_ok(user, sizeof(struct lump_data_frame_s))'),
            'consume-before-range-check': (
                '          if (!board_user_out_ok(user, sizeof(*user)))',
                '          struct lump_data_session_frame_s early;\n'
                '          lump_pop_data_session_frame(priv->port, &early);\n'
                '          if (!board_user_out_ok(user, sizeof(*user)))'),
            'copy-on-refused-poll': ('if (rc < 0)', 'if (false)'),
        }
        for name, mutation in [('baseline', None), *mutations.items()]:
            candidate = actual
            if mutation:
                before, after = mutation
                assert case.count(before) == 1, name
                candidate = actual[:start] + case.replace(before, after) + actual[end:]
            (root / 'stm32_legoport_chardev.c').write_text(candidate)
            executable = root / name
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-ffunction-sections', '-fdata-sections',
                            '-Wl,--gc-sections', '-I' + str(root),
                            str(source), str(root / 'stubs.c'), '-o', str(executable)], check=True)
            result = subprocess.run([str(executable)], capture_output=True, text=True,
                                    timeout=10, preexec_fn=no_core)
            if mutation:
                assert result.returncode != 0 and 'Assertion' in result.stderr, name
            else:
                assert result.returncode == 0, result.stderr
            print(name + ': ' + ('DETECTED' if mutation else 'PASS'))


if __name__ == '__main__':
    main()
