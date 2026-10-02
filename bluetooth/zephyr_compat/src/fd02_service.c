/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <brickwright/fd02_service.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>

#define FD02_SERVICE_UUID \
  BT_UUID_DECLARE_128(BT_UUID_128_ENCODE(0x0000fd02, 0x0000, 0x1000, 0x8000, \
                                         0x00805f9b34fb))
#define FD02_RX_UUID \
  BT_UUID_DECLARE_128(BT_UUID_128_ENCODE(0x0000fd02, 0x0001, 0x1000, 0x8000, \
                                         0x00805f9b34fb))
#define FD02_TX_UUID \
  BT_UUID_DECLARE_128(BT_UUID_128_ENCODE(0x0000fd02, 0x0002, 0x1000, 0x8000, \
                                         0x00805f9b34fb))

static brickwright_fd02_receive_cb receive_callback;
static void *receive_context;

static ssize_t receive_write(struct bt_conn *connection,
                             const struct bt_gatt_attr *attribute,
                             const void *buffer, uint16_t length,
                             uint16_t offset, uint8_t flags)
{
  (void)connection;
  (void)attribute;
  (void)flags;
  if (offset != 0)
    {
      return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
  if (receive_callback)
    {
      receive_callback(buffer, length, receive_context);
    }
  return length;
}

BT_GATT_SERVICE_DEFINE(brickwright_fd02,
  BT_GATT_PRIMARY_SERVICE(FD02_SERVICE_UUID),
  BT_GATT_CHARACTERISTIC(FD02_RX_UUID,
    BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
    BT_GATT_PERM_WRITE, NULL, receive_write, NULL),
  BT_GATT_CHARACTERISTIC(FD02_TX_UUID, BT_GATT_CHRC_NOTIFY,
    BT_GATT_PERM_NONE, NULL, NULL, NULL),
  BT_GATT_CCC(NULL, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE)
);

void brickwright_fd02_set_receive(brickwright_fd02_receive_cb callback,
                                  void *context)
{
  receive_callback = callback;
  receive_context = context;
}

int brickwright_fd02_notify(struct bt_conn *connection, const void *data,
                            uint16_t length)
{
  if (!data && length)
    {
      return -EINVAL;
    }
  return bt_gatt_notify(connection, &attr_brickwright_fd02[4], data, length);
}

uint16_t brickwright_fd02_rx_handle(void)
{
  return bt_gatt_attr_get_handle(&attr_brickwright_fd02[2]);
}

uint16_t brickwright_fd02_tx_handle(void)
{
  return bt_gatt_attr_get_handle(&attr_brickwright_fd02[4]);
}

uint16_t brickwright_fd02_ccc_handle(void)
{
  return bt_gatt_attr_get_handle(&attr_brickwright_fd02[5]);
}
