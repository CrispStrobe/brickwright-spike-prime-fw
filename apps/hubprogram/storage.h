/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_STORAGE_H
#define BRICKWRIGHT_STORAGE_H
#include "program.h"
/* Caller serializes access and excludes staging and unwinding Python VMs.
 * Paths are supplied by trusted firmware configuration, never packets. */
int bw_program_save(const struct bw_program *, uint32_t id, const char *path);
int bw_program_restore(struct bw_program *, uint32_t id, const char *path);
#endif
