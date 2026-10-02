/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BW_PYTHON_OUTPUT_H
#define BW_PYTHON_OUTPUT_H
#include <stddef.h>
#include <stdint.h>
#define BW_PYTHON_OUTPUT_CAPACITY 1024u
/* Single VM writer. Readers use an even, unchanged sequence around a copy.
 * Full output is truncated; it never waits for an absent USB/BLE consumer. */
struct bw_python_output {
  uint32_t sequence, length, truncated;
  char bytes[BW_PYTHON_OUTPUT_CAPACITY];
};
extern volatile struct bw_python_output g_bw_python_output;
void bw_python_output_reset(void);
void mp_hal_stdout_tx_strn_cooked(const char *str, size_t length);
#endif
