/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "python_output.h"
volatile struct bw_python_output g_bw_python_output;
void bw_python_output_reset(void) {
  g_bw_python_output.sequence++;
  g_bw_python_output.length=0;
  g_bw_python_output.truncated=0;
  g_bw_python_output.sequence++;
}
void mp_hal_stdout_tx_strn_cooked(const char *str, size_t length) {
  size_t available=BW_PYTHON_OUTPUT_CAPACITY-g_bw_python_output.length;
  size_t count=length<available ? length : available;
  size_t i;
  g_bw_python_output.sequence++;
  for(i=0;i<count;i++)g_bw_python_output.bytes[g_bw_python_output.length+i]=str[i];
  g_bw_python_output.length+=(uint32_t)count;
  if(count<length)g_bw_python_output.truncated=1;
  g_bw_python_output.sequence++;
}
