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
/* Guest-owned read-only diagnostic publication; never a host command mailbox.
 * state: 0 absent, 1 running, 2 completed (including syscall/close errors),
 * 3 open failed. Observer checks sequence/state before and after its read.
 * A record contains exact syscall result, saved errno and 0/36/48 output bytes.
 */
struct bw_lump_request_record
{
  int32_t result;
  uint32_t error, length;
  uint8_t bytes[48];
};
struct bw_lump_request_result
{
  uint32_t magic, version, state, sequence, selector, calls;
  int32_t open_result;
  uint32_t open_error;
  int32_t close_result;
  uint32_t close_error;
  struct bw_lump_request_record records[6];
};
extern volatile struct bw_lump_request_result g_bw_lump_request;
/* Fixed, bounded requests on F; replies are observations, not test verdicts. */
int bw_lump_request_run(const char *operation);
int bw_lump_request_startup(void);
#endif
