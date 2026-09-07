/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_BOARD_RGBLED_H
#define TEST_BOARD_RGBLED_H

#include <stdint.h>

#define RGBLEDIOC_SETDUTY 0x5050

struct rgbled_duty_s
{
  uint8_t channel;
  uint16_t value;
};

#endif
