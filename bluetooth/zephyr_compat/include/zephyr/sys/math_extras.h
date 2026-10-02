/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_MATH_EXTRAS_H
#define BRICKWRIGHT_ZEPHYR_SYS_MATH_EXTRAS_H

#include <stdbool.h>
#include <stdint.h>

static inline bool u16_add_overflow(uint16_t first, uint16_t second,
                                    uint16_t *result)
{
  uint32_t sum = (uint32_t)first + second;
  *result = (uint16_t)sum;
  return sum > UINT16_MAX;
}

#endif
