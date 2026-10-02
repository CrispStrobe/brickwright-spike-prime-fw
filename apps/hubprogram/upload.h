/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_UPLOAD_H
#define BRICKWRIGHT_PROGRAM_UPLOAD_H
#include "program.h"
#define BW_PROGRAM_REQUEST 0x70u
#define BW_PROGRAM_REPLY 0x71u
#define BW_PROGRAM_PACKET_LIMIT 20u
struct bw_program_upload {
  union { uint8_t bytes[BW_PROGRAM_LIMIT * 16u];
    struct bw_instruction code[BW_PROGRAM_LIMIT]; } buffer;
  uint32_t id, crc, owner;
  uint16_t size, received;
  uint64_t activity;
  unsigned active, language;
};
uint32_t bw_program_crc32(const uint8_t *, size_t);
/* One serialized firmware service handles both USB and BLE. owner identifies
 * the transport session. Replies always fit the mandatory BLE ATT payload. */
int bw_program_request(struct bw_program *, struct bw_program_upload *,
  uint32_t owner, uint64_t now, const uint8_t *, size_t,
  uint8_t reply[BW_PROGRAM_PACKET_LIMIT]);
#endif
