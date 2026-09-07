/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_BOARD_LEGOPORT_H
#define TEST_BOARD_LEGOPORT_H
#include <stdint.h>
#define BOARD_LEGOPORT_COUNT 6
#define BOARD_LEGOPORT_DEVPATH_FMT "/dev/legoport%d"
#define LEGOPORT_TYPE_NONE 0
#define LEGOPORT_TYPE_LPF2_MMOTOR 1
#define LEGOPORT_TYPE_LPF2_TRAIN 2
#define LEGOPORT_TYPE_LPF2_TURN 3
#define LEGOPORT_TYPE_LPF2_POWER 4
#define LEGOPORT_TYPE_LPF2_LMOTOR 6
#define LEGOPORT_TYPE_LPF2_XMOTOR 7
#define LEGOPORT_TYPE_LPF2_LIGHT 8
#define LEGOPORT_TYPE_LPF2_UNKNOWN_UART 14
#define LEGOPORT_FLAG_CONNECTED (1u << 0)
#define LEGOPORT_FLAG_IS_UART (1u << 1)
#define LEGOPORT_GET_DEVICE_INFO 0x4802
#define LEGOPORT_LUMP_GET_INFO 0x4808
#define LEGOPORT_LUMP_SEND 0x480a
#define LEGOPORT_PWM_SET_DUTY 0x4810
#define LEGOPORT_PWM_COAST 0x4811
#define LEGOPORT_PWM_BRAKE 0x4812
#define LEGOPORT_PWM_GET_STATUS 0x4813
#define LEGOPORT_PWM_FLAG_PINNED (1u << 0)
#define LUMP_DATA_INT8 0
#define LUMP_DATA_INT16 1
struct legoport_info_s
{
  uint8_t device_type, flags, reserved[2];
  uint32_t event_counter;
};
struct legoport_pwm_status_s
{
  int16_t duty;
  uint8_t state, flags, reserved[4];
};
struct lump_mode_info_s { uint8_t num_values, data_type, writable; };
struct lump_device_info_s
{
  uint8_t type_id, num_modes, current_mode, flags;
  struct lump_mode_info_s modes[8];
};
struct legoport_lump_send_arg_s
{
  uint8_t mode, len, reserved[2], data[32];
};
#endif
