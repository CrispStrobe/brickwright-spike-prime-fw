/* SPDX-License-Identifier: MIT */

#include "ti_bts_loader.h"

#include <stdbool.h>
#include <string.h>

#define BTS_HEADER_SIZE 32u
#define BTS_ACTION_HEADER_SIZE 4u
#define BTS_H4_COMMAND 0x01u
#define BTS_H4_EVENT 0x04u
#define HCI_EVENT_COMMAND_COMPLETE 0x0eu
#define HCI_EVENT_COMMAND_STATUS 0x0fu
#define BTS_EVENT_CAPACITY 260u

static uint16_t get_le16(const uint8_t *value)
{
  return (uint16_t)value[0] | ((uint16_t)value[1] << 8);
}

static uint32_t get_le32(const uint8_t *value)
{
  return (uint32_t)value[0] | ((uint32_t)value[1] << 8) |
         ((uint32_t)value[2] << 16) | ((uint32_t)value[3] << 24);
}

static int validate_command(const uint8_t *command, size_t length,
                            uint16_t *opcode)
{
  if (length < 4 || command[0] != BTS_H4_COMMAND ||
      (size_t)command[3] + 4u != length)
    {
      return TI_BTS_ERROR_FORMAT;
    }

  *opcode = get_le16(command + 1);
  return TI_BTS_OK;
}

static int validate_response(const uint8_t *event, size_t length,
                             uint16_t opcode)
{
  uint8_t event_code;
  uint8_t parameter_length;
  const uint8_t *parameters;

  if (length < 3 || event[0] != BTS_H4_EVENT)
    {
      return TI_BTS_ERROR_HCI;
    }

  event_code = event[1];
  parameter_length = event[2];
  parameters = event + 3;
  if ((size_t)parameter_length + 3u != length)
    {
      return TI_BTS_ERROR_HCI;
    }

  if (event_code == HCI_EVENT_COMMAND_COMPLETE)
    {
      if (parameter_length < 4 || get_le16(parameters + 1) != opcode ||
          parameters[3] != 0)
        {
          return TI_BTS_ERROR_HCI;
        }
      return TI_BTS_OK;
    }

  if (event_code == HCI_EVENT_COMMAND_STATUS)
    {
      if (parameter_length != 4 || get_le16(parameters + 2) != opcode ||
          parameters[0] != 0)
        {
          return TI_BTS_ERROR_HCI;
        }
      return TI_BTS_OK;
    }

  return TI_BTS_ERROR_HCI;
}

int ti_bts_execute(const uint8_t *image, size_t image_size,
                   const struct ti_bts_transport *transport,
                   struct ti_bts_report *report)
{
  size_t offset = BTS_HEADER_SIZE;
  bool command_pending = false;
  uint16_t pending_opcode = 0;
  struct ti_bts_report result = {0, 0};

  if (image == NULL || transport == NULL ||
      transport->send_command == NULL || transport->receive_event == NULL)
    {
      return TI_BTS_ERROR_ARGUMENT;
    }
  if (image_size < BTS_HEADER_SIZE || memcmp(image, "BTSB", 4) != 0)
    {
      return TI_BTS_ERROR_FORMAT;
    }

  while (offset < image_size)
    {
      uint16_t type;
      uint16_t payload_size;
      const uint8_t *payload;
      int status;

      if (image_size - offset < BTS_ACTION_HEADER_SIZE)
        {
          return TI_BTS_ERROR_FORMAT;
        }
      type = get_le16(image + offset);
      payload_size = get_le16(image + offset + 2);
      offset += BTS_ACTION_HEADER_SIZE;
      if ((size_t)payload_size > image_size - offset)
        {
          return TI_BTS_ERROR_FORMAT;
        }
      payload = image + offset;
      offset += payload_size;
      result.actions++;

      switch (type)
        {
          case TI_BTS_ACTION_SEND_COMMAND:
            if (command_pending)
              {
                return TI_BTS_ERROR_FORMAT;
              }
            status = validate_command(payload, payload_size, &pending_opcode);
            if (status != TI_BTS_OK)
              {
                return status;
              }
            if (transport->send_command(transport->context, payload,
                                        payload_size) != 0)
              {
                return TI_BTS_ERROR_TRANSPORT;
              }
            command_pending = true;
            result.commands++;
            break;

          case TI_BTS_ACTION_WAIT_EVENT:
            {
              uint8_t event[BTS_EVENT_CAPACITY];
              size_t event_length = 0;
              uint32_t timeout_ms;

              /* Public BTS WAIT_EVENT framing is timeout, expected-data size,
               * then opaque expected data. We only need the timeout here. */
              if (!command_pending || payload_size < 8 ||
                  get_le32(payload + 4) != (uint32_t)payload_size - 8u)
                {
                  return TI_BTS_ERROR_FORMAT;
                }
              timeout_ms = get_le32(payload);
              if (transport->receive_event(transport->context, event,
                                           sizeof(event), &event_length,
                                           timeout_ms) != 0)
                {
                  return TI_BTS_ERROR_TRANSPORT;
                }
              status = validate_response(event, event_length, pending_opcode);
              if (status != TI_BTS_OK)
                {
                  return status;
                }
              command_pending = false;
            }
            break;

          case TI_BTS_ACTION_SERIAL:
            if (payload_size != 8 || transport->set_serial == NULL)
              {
                return payload_size == 8 ? TI_BTS_ERROR_UNSUPPORTED :
                                           TI_BTS_ERROR_FORMAT;
              }
            if (transport->set_serial(transport->context, get_le32(payload),
                                      get_le32(payload + 4)) != 0)
              {
                return TI_BTS_ERROR_TRANSPORT;
              }
            break;

          case TI_BTS_ACTION_DELAY:
            if (payload_size != 4 || transport->delay_ms == NULL)
              {
                return payload_size == 4 ? TI_BTS_ERROR_UNSUPPORTED :
                                           TI_BTS_ERROR_FORMAT;
              }
            if (transport->delay_ms(transport->context,
                                    get_le32(payload)) != 0)
              {
                return TI_BTS_ERROR_TRANSPORT;
              }
            break;

          case TI_BTS_ACTION_REMARKS:
            break;

          case TI_BTS_ACTION_RUN_SCRIPT:
          default:
            return TI_BTS_ERROR_UNSUPPORTED;
        }
    }

  if (command_pending || result.actions == 0)
    {
      return TI_BTS_ERROR_FORMAT;
    }
  if (report != NULL)
    {
      *report = result;
    }
  return TI_BTS_OK;
}
