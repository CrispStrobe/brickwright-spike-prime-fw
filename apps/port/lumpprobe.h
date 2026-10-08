/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_LUMPPROBE_H
#define BRICKWRIGHT_LUMPPROBE_H
#include <stdint.h>

/* Guest-owned publication only; there is no host request or writable command.
 * state: 0 not started, 1 running, 2 passed, 3 failed. The harness must verify
 * the ELF symbol/range, then read final state before and after other fields.
 * failure: 1 open, 2 attachment, 3..7 invalid pointers, 8 session poll,
 * 9 legacy poll, 10 close. checks: completed checks, bits 0..8 in that order
 * excluding open. readonly_address must identify user flash in the ARM ELF.
 */
struct bw_lump_probe_result
{
  uint32_t magic, version, state, checks, failure;
  int32_t result;
  uint32_t error, readonly_address;
};
extern volatile struct bw_lump_probe_result g_bw_lump_probe;
int bw_lump_probe_run(void);
#endif
