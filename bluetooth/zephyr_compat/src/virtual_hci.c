/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <string.h>
#include <brickwright/virtual_hci.h>

#define H4_COMMAND 0x01
#define H4_ACL 0x02
#define H4_EVENT 0x04
#define HCI_COMMAND_COMPLETE 0x0e
#define HCI_LE_META_EVENT 0x3e
#define HCI_LE_CONNECTION_COMPLETE 0x01
#define HCI_DISCONNECTION_COMPLETE 0x05
#define HCI_CONNECTION_COMPLETE 0x03
#define HCI_CONNECTION_REQUEST 0x04
#define HCI_STATUS_UNKNOWN_COMMAND 0x01
#define HCI_OP_RESET 0x0c03
#define HCI_OP_SET_EVENT_MASK 0x0c01
#define HCI_OP_WRITE_LOCAL_NAME 0x0c13
#define HCI_OP_WRITE_PAGE_TIMEOUT 0x0c18
#define HCI_OP_WRITE_CLASS_OF_DEVICE 0x0c24
#define HCI_OP_WRITE_INQUIRY_MODE 0x0c45
#define HCI_OP_WRITE_SSP_MODE 0x0c56
#define HCI_OP_WRITE_LE_HOST_SUPPORT 0x0c6d
#define HCI_OP_READ_DEFAULT_LINK_POLICY 0x080e
#define HCI_OP_WRITE_DEFAULT_LINK_POLICY 0x080f
#define HCI_OP_READ_LOCAL_VERSION 0x1001
#define HCI_OP_READ_SUPPORTED_COMMANDS 0x1002
#define HCI_OP_READ_LOCAL_FEATURES 0x1003
#define HCI_OP_READ_BUFFER_SIZE 0x1005
#define HCI_OP_READ_BD_ADDR 0x1009
#define HCI_OP_LE_SET_EVENT_MASK 0x2001
#define HCI_OP_LE_READ_BUFFER_SIZE 0x2002
#define HCI_OP_LE_READ_LOCAL_FEATURES 0x2003
#define HCI_OP_LE_SET_ADV_PARAM 0x2006
#define HCI_OP_LE_SET_ADV_DATA 0x2008
#define HCI_OP_LE_SET_SCAN_RSP_DATA 0x2009
#define HCI_OP_LE_SET_ADV_ENABLE 0x200a
#define HCI_OP_LE_LTK_REQ_REPLY 0x201a
#define HCI_OP_ACCEPT_CONN_REQ 0x0409
#define HCI_OP_READ_REMOTE_FEATURES 0x041b
#define HCI_OP_WRITE_SCAN_ENABLE 0x0c1a
#define HCI_OP_READ_CLASS_OF_DEVICE 0x0c23
#define HCI_OP_WRITE_CURRENT_IAC_LAP 0x0c3a

static int send_complete(struct brickwright_virtual_hci *controller,
                         uint16_t opcode, uint8_t status,
                         const uint8_t *parameters, size_t length)
{
  uint8_t frame[71] = {
    H4_EVENT, HCI_COMMAND_COMPLETE, (uint8_t)(4 + length), 1,
    (uint8_t)opcode, (uint8_t)(opcode >> 8), status
  };

  if (length > sizeof(frame) - 7)
    {
      return -EMSGSIZE;
    }

  if (length)
    {
      memcpy(frame + 7, parameters, length);
    }

  return controller->send(frame, 7 + length, controller->context);
}

static int send_status(struct brickwright_virtual_hci *controller,
                       uint16_t opcode, uint8_t status)
{
  const uint8_t frame[] = {
    H4_EVENT, 0x0f, 4, status, 1, (uint8_t)opcode, (uint8_t)(opcode >> 8)
  };
  return controller->send(frame, sizeof(frame), controller->context);
}

static int receive_command(uint8_t type, const uint8_t *packet, size_t length,
                           void *context)
{
  struct brickwright_virtual_hci *controller = context;

  if (type == H4_ACL)
    {
      if (length < 4 || length != (size_t)(packet[2] | (packet[3] << 8)) + 4 ||
          length > sizeof(controller->host_acl))
        {
          return -EPROTO;
        }
      memcpy(controller->host_acl, packet, length);
      controller->host_acl_length = length;
      const uint8_t completed[] = {
        H4_EVENT, 0x13, 5, 1, packet[0], (uint8_t)(packet[1] & 0x0f), 1, 0
      };
      return controller->send(completed, sizeof(completed), controller->context);
    }

  if (type != H4_COMMAND || length < 3 || length != (size_t)packet[2] + 3)
    {
      return -EPROTO;
    }

  uint16_t opcode = packet[0] | ((uint16_t)packet[1] << 8);
  if ((opcode & 0xfc00) == 0xfc00 &&
      controller->acknowledge_vendor_commands)
    {
      /* A simulation may acknowledge an opaque controller bootstrap stream
       * at the HCI boundary.  The parameters are deliberately not parsed or
       * interpreted: this models command completion, not TI firmware.
       */
      return send_complete(controller, opcode, 0, NULL, 0);
    }
  if (opcode == HCI_OP_RESET && packet[2] == 0)
    {
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_READ_BD_ADDR && packet[2] == 0)
    {
      return send_complete(controller, opcode, 0, controller->address,
                           sizeof(controller->address));
    }

  if (opcode == HCI_OP_READ_LOCAL_VERSION && packet[2] == 0)
    {
      /* Bluetooth 4.2, Brickwright controller revision 1, Linux Foundation. */
      const uint8_t version[] = {0x08, 0x01, 0x00, 0x08, 0x98, 0x05,
                                 0x01, 0x00};
      return send_complete(controller, opcode, 0, version, sizeof(version));
    }

  if (opcode == HCI_OP_READ_SUPPORTED_COMMANDS && packet[2] == 0)
    {
      const uint8_t commands[64] = {0};
      return send_complete(controller, opcode, 0, commands, sizeof(commands));
    }

  if (opcode == HCI_OP_READ_LOCAL_FEATURES && packet[2] == 0)
    {
      /* Dual-mode controller: BR/EDR is supported and LE is enabled. */
      const uint8_t features[8] = {0, 0, 0, 0, 0x40, 0, 0, 0};
      return send_complete(controller, opcode, 0, features, sizeof(features));
    }

  if (opcode == HCI_OP_READ_BUFFER_SIZE && packet[2] == 0)
    {
      /* 1021-byte ACL payloads, eight controller packets, no SCO pool. */
      const uint8_t size[] = {0xfd, 0x03, 0x00, 0x08, 0x00, 0x00, 0x00};
      return send_complete(controller, opcode, 0, size, sizeof(size));
    }

  if (opcode == HCI_OP_LE_READ_BUFFER_SIZE && packet[2] == 0)
    {
      const uint8_t size[] = {0xfb, 0x00, 0x08};
      return send_complete(controller, opcode, 0, size, sizeof(size));
    }

  if (opcode == HCI_OP_LE_READ_LOCAL_FEATURES && packet[2] == 0)
    {
      const uint8_t features[8] = {0};
      return send_complete(controller, opcode, 0, features, sizeof(features));
    }

  if (opcode == HCI_OP_LE_SET_ADV_PARAM && packet[2] == 15)
    {
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if ((opcode == HCI_OP_LE_SET_ADV_DATA ||
       opcode == HCI_OP_LE_SET_SCAN_RSP_DATA) && packet[2] == 32 &&
      packet[3] <= 31)
    {
      uint8_t *data = opcode == HCI_OP_LE_SET_ADV_DATA ?
        controller->advertising_data : controller->scan_response_data;
      uint8_t *data_length = opcode == HCI_OP_LE_SET_ADV_DATA ?
        &controller->advertising_data_length :
        &controller->scan_response_data_length;
      *data_length = packet[3];
      memcpy(data, packet + 4, *data_length);
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_LE_SET_ADV_ENABLE && packet[2] == 1 && packet[3] <= 1)
    {
      controller->advertising = packet[3] != 0;
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_LE_LTK_REQ_REPLY && packet[2] == 18 &&
      controller->connected && !controller->classic_connection &&
      controller->ltk_request_pending && packet[3] ==
      (uint8_t)controller->connection_handle && packet[4] ==
      (uint8_t)(controller->connection_handle >> 8))
    {
      if (memcmp(packet + 5, controller->expected_ltk, 16))
        {
          return -EKEYREJECTED;
        }
      controller->ltk_request_pending = false;
      const uint8_t handle[] = {
        (uint8_t)controller->connection_handle,
        (uint8_t)(controller->connection_handle >> 8)
      };
      int result = send_complete(controller, opcode, 0, handle, sizeof(handle));
      if (result)
        {
          return result;
        }
      const uint8_t encrypted[] = {
        H4_EVENT, 0x08, 4, 0,
        (uint8_t)controller->connection_handle,
        (uint8_t)(controller->connection_handle >> 8), 1
      };
      return controller->send(encrypted, sizeof(encrypted),
                              controller->context);
    }

  if (opcode == HCI_OP_WRITE_SCAN_ENABLE && packet[2] == 1 && packet[3] <= 3)
    {
      controller->classic_connectable = (packet[3] & 0x02) != 0;
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_READ_CLASS_OF_DEVICE && packet[2] == 0)
    {
      const uint8_t device_class[] = {0x00, 0x08, 0x00};
      return send_complete(controller, opcode, 0, device_class,
                           sizeof(device_class));
    }

  if (opcode == HCI_OP_WRITE_CURRENT_IAC_LAP && packet[2] >= 4 &&
      packet[3] >= 1 && packet[2] == (uint8_t)(1 + packet[3] * 3))
    {
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_ACCEPT_CONN_REQ && packet[2] == 7 &&
      controller->classic_connectable && !controller->connected &&
      !memcmp(packet + 3, controller->peer_address, 6))
    {
      int result = send_status(controller, opcode, 0);
      if (result)
        {
          return result;
        }
      controller->connection_handle = 1;
      controller->connected = true;
      controller->classic_connection = true;
      const uint8_t complete[] = {
        H4_EVENT, HCI_CONNECTION_COMPLETE, 11, 0, 1, 0,
        controller->peer_address[0], controller->peer_address[1],
        controller->peer_address[2], controller->peer_address[3],
        controller->peer_address[4], controller->peer_address[5],
        1, 0
      };
      return controller->send(complete, sizeof(complete), controller->context);
    }

  if (opcode == HCI_OP_READ_REMOTE_FEATURES && packet[2] == 2 &&
      controller->connected && controller->classic_connection)
    {
      int result = send_status(controller, opcode, 0);
      if (result)
        {
          return result;
        }
      const uint8_t features[] = {
        H4_EVENT, 0x0b, 11, 0,
        (uint8_t)controller->connection_handle,
        (uint8_t)(controller->connection_handle >> 8),
        0, 0, 0, 0, 0, 0, 0, 0
      };
      return controller->send(features, sizeof(features), controller->context);
    }

  if ((opcode == HCI_OP_SET_EVENT_MASK ||
       opcode == HCI_OP_LE_SET_EVENT_MASK) && packet[2] == 8)
    {
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_WRITE_LE_HOST_SUPPORT && packet[2] == 2)
    {
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (((opcode == HCI_OP_WRITE_SSP_MODE ||
        opcode == HCI_OP_WRITE_INQUIRY_MODE) && packet[2] == 1) ||
      ((opcode == HCI_OP_WRITE_PAGE_TIMEOUT ||
        opcode == HCI_OP_WRITE_DEFAULT_LINK_POLICY) && packet[2] == 2) ||
      (opcode == HCI_OP_WRITE_CLASS_OF_DEVICE && packet[2] == 3) ||
      (opcode == HCI_OP_WRITE_LOCAL_NAME && packet[2] == 248))
    {
      return send_complete(controller, opcode, 0, NULL, 0);
    }

  if (opcode == HCI_OP_READ_DEFAULT_LINK_POLICY && packet[2] == 0)
    {
      const uint8_t policy[] = {0x00, 0x00};
      return send_complete(controller, opcode, 0, policy, sizeof(policy));
    }

  return send_complete(controller, opcode, HCI_STATUS_UNKNOWN_COMMAND,
                       NULL, 0);
}

void brickwright_virtual_hci_acknowledge_vendor_commands(
  struct brickwright_virtual_hci *controller, bool enabled)
{
  if (controller)
    {
      controller->acknowledge_vendor_commands = enabled;
    }
}

void brickwright_virtual_hci_init(struct brickwright_virtual_hci *controller,
                                  const uint8_t address[6],
                                  brickwright_virtual_hci_send_cb send,
                                  void *context)
{
  memset(controller, 0, sizeof(*controller));
  memcpy(controller->address, address, sizeof(controller->address));
  controller->send = send;
  controller->context = context;
  brickwright_h4_init(&controller->h4, receive_command, controller);
}

int brickwright_virtual_hci_feed(struct brickwright_virtual_hci *controller,
                                 const void *data, size_t length)
{
  if (!controller || !controller->send)
    {
      return -EINVAL;
    }

  return brickwright_h4_feed(&controller->h4, data, length);
}

int brickwright_virtual_hci_connect(struct brickwright_virtual_hci *controller,
                                    const uint8_t peer_address[6])
{
  if (!controller || !controller->send || !peer_address ||
      !controller->advertising || controller->connected)
    {
      return -EINVAL;
    }
  controller->connection_handle = 1;
  controller->connected = true;
  controller->advertising = false;
  memcpy(controller->peer_address, peer_address,
         sizeof(controller->peer_address));
  const uint8_t frame[] = {
    H4_EVENT, HCI_LE_META_EVENT, 19, HCI_LE_CONNECTION_COMPLETE, 0,
    0x01, 0x00, 0x01, 0x00,
    peer_address[0], peer_address[1], peer_address[2], peer_address[3],
    peer_address[4], peer_address[5],
    0x18, 0x00, 0x00, 0x00, 0xf4, 0x01, 0x00
  };
  return controller->send(frame, sizeof(frame), controller->context);
}

int brickwright_virtual_hci_disconnect(struct brickwright_virtual_hci *controller,
                                       uint8_t reason)
{
  if (!controller || !controller->send || !controller->connected)
    {
      return -EINVAL;
    }
  const uint8_t frame[] = {
    H4_EVENT, HCI_DISCONNECTION_COMPLETE, 4, 0,
    (uint8_t)controller->connection_handle,
    (uint8_t)(controller->connection_handle >> 8), reason
  };
  controller->connected = false;
  controller->classic_connection = false;
  controller->ltk_request_pending = false;
  memset(controller->expected_ltk, 0, sizeof(controller->expected_ltk));
  return controller->send(frame, sizeof(frame), controller->context);
}

int brickwright_virtual_hci_send_acl(struct brickwright_virtual_hci *controller,
                                     const void *payload, size_t length)
{
  if (!controller || !controller->send || !controller->connected ||
      (!payload && length) || length > 1021)
    {
      return -EINVAL;
    }
  uint8_t frame[1026];
  frame[0] = H4_ACL;
  frame[1] = (uint8_t)controller->connection_handle;
  frame[2] = (uint8_t)((controller->connection_handle >> 8) | 0x20);
  frame[3] = (uint8_t)length;
  frame[4] = (uint8_t)(length >> 8);
  memcpy(frame + 5, payload, length);
  return controller->send(frame, length + 5, controller->context);
}

int brickwright_virtual_hci_request_ltk(
  struct brickwright_virtual_hci *controller, const uint8_t expected_ltk[16])
{
  if (!controller || !controller->send || !expected_ltk ||
      !controller->connected || controller->classic_connection ||
      controller->ltk_request_pending)
    {
      return -EINVAL;
    }
  memcpy(controller->expected_ltk, expected_ltk,
         sizeof(controller->expected_ltk));
  controller->ltk_request_pending = true;
  const uint8_t frame[] = {
    H4_EVENT, HCI_LE_META_EVENT, 13, 0x05,
    (uint8_t)controller->connection_handle,
    (uint8_t)(controller->connection_handle >> 8),
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0
  };
  int result = controller->send(frame, sizeof(frame), controller->context);
  if (result)
    {
      controller->ltk_request_pending = false;
    }
  return result;
}

int brickwright_virtual_hci_classic_connection_request(
  struct brickwright_virtual_hci *controller, const uint8_t peer_address[6])
{
  if (!controller || !controller->send || !peer_address ||
      !controller->classic_connectable || controller->connected)
    {
      return -EINVAL;
    }
  memcpy(controller->peer_address, peer_address,
         sizeof(controller->peer_address));
  const uint8_t frame[] = {
    H4_EVENT, HCI_CONNECTION_REQUEST, 10,
    peer_address[0], peer_address[1], peer_address[2],
    peer_address[3], peer_address[4], peer_address[5],
    0x00, 0x08, 0x00, 0x01
  };
  return controller->send(frame, sizeof(frame), controller->context);
}
