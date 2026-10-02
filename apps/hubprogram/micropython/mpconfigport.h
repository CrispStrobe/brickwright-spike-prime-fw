/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include <port/mpconfigport_common.h>
#define MICROPY_CONFIG_ROM_LEVEL (MICROPY_CONFIG_ROM_LEVEL_CORE_FEATURES)
#define MICROPY_ENABLE_COMPILER (1)
#define MICROPY_ENABLE_GC (1)
#define MICROPY_PY_GC (1)
#define MICROPY_FLOAT_IMPL (MICROPY_FLOAT_IMPL_FLOAT)
#define MICROPY_STACK_CHECK (1)
#define MICROPY_ENABLE_FINALISER (0)
#define MICROPY_PY_BUILTINS_OPEN (0)
#define MICROPY_PY_SYS (0)
#define MICROPY_PY_IO (0)
#define MICROPY_READER_POSIX (0)
void bw_python_poll(void);
#define MICROPY_VM_HOOK_LOOP bw_python_poll();
#define MICROPY_VM_HOOK_RETURN bw_python_poll();
