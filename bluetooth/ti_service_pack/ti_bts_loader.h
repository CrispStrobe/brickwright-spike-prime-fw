/* SPDX-License-Identifier: MIT */
#ifndef BRICKWRIGHT_TI_BTS_LOADER_H
#define BRICKWRIGHT_TI_BTS_LOADER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Public BTS container action identifiers. The loader deliberately treats
 * every action payload as opaque except for standard HCI packet framing. */
enum ti_bts_action_type
{
  TI_BTS_ACTION_SEND_COMMAND = 1,
  TI_BTS_ACTION_WAIT_EVENT = 2,
  TI_BTS_ACTION_SERIAL = 3,
  TI_BTS_ACTION_DELAY = 4,
  TI_BTS_ACTION_RUN_SCRIPT = 5,
  TI_BTS_ACTION_REMARKS = 6,
};

enum ti_bts_result
{
  TI_BTS_OK = 0,
  TI_BTS_ERROR_ARGUMENT = -1,
  TI_BTS_ERROR_FORMAT = -2,
  TI_BTS_ERROR_UNSUPPORTED = -3,
  TI_BTS_ERROR_TRANSPORT = -4,
  TI_BTS_ERROR_HCI = -5,
};

struct ti_bts_transport
{
  /* Send one complete H4 HCI command, byte-for-byte as stored in the BTS. */
  int (*send_command)(void *context, const uint8_t *command, size_t length);

  /* Receive one complete H4 HCI event. Return zero and set *length on
   * success. The implementation owns timing and must honor timeout_ms. */
  int (*receive_event)(void *context, uint8_t *event, size_t capacity,
                       size_t *length, uint32_t timeout_ms);

  /* Optional platform actions. A script requiring an absent callback fails
   * closed rather than silently applying incomplete controller setup. */
  int (*set_serial)(void *context, uint32_t baud, uint32_t flow_control);
  int (*delay_ms)(void *context, uint32_t duration_ms);
  void *context;
};

struct ti_bts_report
{
  uint32_t actions;
  uint32_t commands;
};

/* Execute a complete BTSB image held in caller-owned memory. Restricted bytes
 * are neither copied into persistent storage nor modified. */
int ti_bts_execute(const uint8_t *image, size_t image_size,
                   const struct ti_bts_transport *transport,
                   struct ti_bts_report *report);

#ifdef __cplusplus
}
#endif

#endif
