/* SPDX-License-Identifier: Apache-2.0 */
#include <zephyr/sys/util.h>

static int hex_value(char value)
{
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

size_t hex2bin(const char *hex, size_t hex_length, uint8_t *output,
               size_t output_length)
{
  size_t converted = 0;
  if (!hex || !output || (hex_length & 1U)) return 0;
  while (hex_length >= 2 && converted < output_length) {
    int high = hex_value(*hex++);
    int low = hex_value(*hex++);
    if (high < 0 || low < 0) return 0;
    output[converted++] = (uint8_t)((high << 4) | low);
    hex_length -= 2;
  }
  return hex_length == 0 ? converted : 0;
}
