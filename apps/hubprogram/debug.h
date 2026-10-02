/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_DEBUG_H
#define BRICKWRIGHT_PROGRAM_DEBUG_H
#include <stdint.h>
/* Third transport for emulator tests. The same program service handles its
 * packets; this never supplies encoder feedback or bypasses port drivers.
 * Host writes odd request_seq, bounded packet/length, then even request_seq.
 * Firmware publishes reply_seq and a separately coherent snapshot. */
struct bw_program_debug {
  uint32_t magic,version,request_seq,length;
  uint8_t request[20];
  uint32_t reply_seq;
  uint8_t reply[20];
  uint32_t publish_seq,clock_ms,state,id,pc;
  int32_t error,position_a_deg,position_b_deg,speed_a_dps,speed_b_dps;
  int32_t duty_a,duty_b;
  uint32_t valid_ports;
};
extern volatile struct bw_program_debug g_bw_program_debug;
#endif
