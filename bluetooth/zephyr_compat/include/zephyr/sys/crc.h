/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_CRC_H
#define BRICKWRIGHT_ZEPHYR_SYS_CRC_H

#include <stddef.h>
#include <stdint.h>

static inline uint16_t crc16_reflect(uint16_t polynomial, uint16_t initial,
                                     const uint8_t *data, size_t length)
{
  uint16_t crc = initial;
  for (size_t i = 0; i < length; ++i)
    {
      crc ^= data[i];
      for (unsigned int bit = 0; bit < 8; ++bit)
        {
          crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ polynomial) :
                            (uint16_t)(crc >> 1);
        }
    }
  return crc;
}

#endif
