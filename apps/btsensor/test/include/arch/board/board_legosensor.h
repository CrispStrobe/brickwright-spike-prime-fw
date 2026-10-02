/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_BOARD_LEGOSENSOR_H
#define TEST_BOARD_LEGOSENSOR_H
#include <stdint.h>
#include "board_legoport.h"
#define LEGOSENSOR_GET_INFO 0xf1
#define LEGOSENSOR_CLAIM 0xf5
#define LEGOSENSOR_SET_PWM 0xf7
#define LEGOSENSOR_GET_LATEST 0xf8
#define LEGOSENSOR_MOTOR_M_COAST 0x131
#define LEGOSENSOR_MOTOR_M_BRAKE 0x132
#define LEGOSENSOR_MOTOR_R_COAST 0x141
#define LEGOSENSOR_MOTOR_R_BRAKE 0x142
#define LEGOSENSOR_MOTOR_L_COAST 0x151
#define LEGOSENSOR_MOTOR_L_BRAKE 0x152
struct legosensor_info_arg_s
{
  uint8_t port, reserved[3];
  struct lump_device_info_s info;
};
struct legosensor_pwm_arg_s
{
  uint8_t num_channels, reserved[3];
  int16_t channels[4];
};
struct lump_sample_s
{
  uint64_t timestamp;
  uint32_t seq, generation;
  uint8_t port, type_id, mode_id, data_type, num_values, len;
  uint16_t reserved;
  union { uint8_t raw[32]; int16_t i16[16]; int32_t i32[8]; } data;
};
#endif
