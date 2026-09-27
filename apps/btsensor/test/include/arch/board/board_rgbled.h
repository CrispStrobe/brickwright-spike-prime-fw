/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_BOARD_RGBLED_H
#define TEST_BOARD_RGBLED_H

#include <stdint.h>

#define RGBLEDIOC_SETDUTY 0x5050

/* Same channel numbers as boards/spike-prime-hub/include/board_rgbled.h. */
#define TLC5955_CH_STATUS_TOP_B    3
#define TLC5955_CH_STATUS_TOP_G    4
#define TLC5955_CH_STATUS_TOP_R    5
#define TLC5955_CH_STATUS_BTM_B    6
#define TLC5955_CH_STATUS_BTM_G    7
#define TLC5955_CH_STATUS_BTM_R    8

struct rgbled_duty_s
{
  uint8_t channel;
  uint16_t value;
};

#endif
