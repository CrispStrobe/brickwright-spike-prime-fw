/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_DEVICE_H
#define BRICKWRIGHT_PROGRAM_DEVICE_H
#include "program.h"
#include "debug.h"
void bw_device_init(struct bw_program_io *);
int bw_device_tick(uint64_t now);
void bw_device_release(void);
void bw_device_snapshot(volatile struct bw_program_debug *);
#endif
