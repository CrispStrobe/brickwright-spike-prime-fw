/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_H
#define BRICKWRIGHT_PROGRAM_H
#include <stddef.h>
#include <stdint.h>
#define BW_PROGRAM_LIMIT 256u
#define BW_PROGRAM_TIME_LIMIT 120000u
struct bw_instruction { int32_t op, a, b, c; };
enum bw_program_state { BW_PROGRAM_EMPTY, BW_PROGRAM_READY, BW_PROGRAM_RUNNING,
  BW_PROGRAM_COMPLETE, BW_PROGRAM_STOPPED, BW_PROGRAM_FAULT };
/* Calls execute in the firmware worker, never the emulator/GUI. Negative errno
 * is failure. done returns 0 pending, 1 complete, or negative errno. */
struct bw_program_io {
  int (*motor)(void *, unsigned, int32_t speed_dps);
  int (*position)(void *, unsigned, int32_t degrees, int32_t speed_dps);
  int (*done)(void *, unsigned);
  int (*brake)(void *, unsigned);
  int (*sensor)(void *, unsigned predicate, int32_t *value);
  void *context;
};
struct bw_program {
  struct bw_instruction code[BW_PROGRAM_LIMIT];
  char source[4096];
  unsigned language;
  struct bw_program_io io;
  uint32_t count, pc, id, owned;
  enum bw_program_state state;
  int error, moving;
  uint64_t started, deadline, last_tick;
  unsigned waiting, ending;
};
int bw_program_validate(const struct bw_instruction *, uint32_t);
void bw_program_init(struct bw_program *, const struct bw_program_io *);
int bw_program_load(struct bw_program *, uint32_t id,
                    const struct bw_instruction *, uint32_t count);
int bw_program_start(struct bw_program *, uint32_t id, uint64_t now_ms);
int bw_program_stop(struct bw_program *);
void bw_program_tick(struct bw_program *, uint64_t now_ms);
#endif
