/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <string.h>
#include <brickwright/classic_spp.h>
#include <zephyr/bluetooth/classic/rfcomm.h>
#include <zephyr/bluetooth/classic/sdp.h>

#define SPP_MTU 256
NET_BUF_POOL_FIXED_DEFINE(spp_tx_pool, 2, BT_RFCOMM_BUF_SIZE(SPP_MTU),
                          CONFIG_BT_CONN_TX_USER_DATA_SIZE, NULL);

static brickwright_classic_spp_receive_cb receive_callback;
static void *receive_context;
static brickwright_classic_spp_state_cb state_callback;
static bool registered;
static bool connected;

static void dlc_connected(struct bt_rfcomm_dlc *dlc)
{
  (void)dlc;
  connected = true;
  if (state_callback) state_callback(true, receive_context);
}

static void dlc_disconnected(struct bt_rfcomm_dlc *dlc)
{
  (void)dlc;
  connected = false;
  if (state_callback) state_callback(false, receive_context);
}

static void dlc_receive(struct bt_rfcomm_dlc *dlc, struct net_buf *buffer)
{
  (void)dlc;
  if (receive_callback)
    {
      receive_callback(buffer->data, buffer->len, receive_context);
    }
}

static struct bt_rfcomm_dlc_ops dlc_ops = {
  .connected = dlc_connected,
  .disconnected = dlc_disconnected,
  .recv = dlc_receive,
};

static struct bt_rfcomm_dlc spp_dlc = {
  .ops = &dlc_ops,
  .mtu = SPP_MTU,
};

static int server_accept(struct bt_conn *connection,
                         struct bt_rfcomm_server *server,
                         struct bt_rfcomm_dlc **dlc)
{
  (void)connection;
  (void)server;
  if (spp_dlc.session)
    {
      return -ENOMEM;
    }
  *dlc = &spp_dlc;
  return 0;
}

static struct bt_rfcomm_server spp_server = {
  .channel = BT_RFCOMM_CHAN_SPP,
  .accept = server_accept,
};

static struct bt_sdp_attribute spp_attributes[] = {
  BT_SDP_NEW_SERVICE,
  BT_SDP_LIST(BT_SDP_ATTR_SVCLASS_ID_LIST,
    BT_SDP_TYPE_SIZE_VAR(BT_SDP_SEQ8, 3),
    BT_SDP_DATA_ELEM_LIST(
      { BT_SDP_TYPE_SIZE(BT_SDP_UUID16),
        BT_SDP_ARRAY_16(BT_SDP_SERIAL_PORT_SVCLASS) },
    )),
  BT_SDP_LIST(BT_SDP_ATTR_PROTO_DESC_LIST,
    BT_SDP_TYPE_SIZE_VAR(BT_SDP_SEQ8, 12),
    BT_SDP_DATA_ELEM_LIST(
      { BT_SDP_TYPE_SIZE_VAR(BT_SDP_SEQ8, 3),
        BT_SDP_DATA_ELEM_LIST(
          { BT_SDP_TYPE_SIZE(BT_SDP_UUID16),
            BT_SDP_ARRAY_16(BT_SDP_PROTO_L2CAP) },
        ) },
      { BT_SDP_TYPE_SIZE_VAR(BT_SDP_SEQ8, 5),
        BT_SDP_DATA_ELEM_LIST(
          { BT_SDP_TYPE_SIZE(BT_SDP_UUID16),
            BT_SDP_ARRAY_16(BT_SDP_PROTO_RFCOMM) },
          { BT_SDP_TYPE_SIZE(BT_SDP_UINT8),
            BT_SDP_ARRAY_8(BT_RFCOMM_CHAN_SPP) },
        ) },
    )),
  BT_SDP_LIST(BT_SDP_ATTR_PROFILE_DESC_LIST,
    BT_SDP_TYPE_SIZE_VAR(BT_SDP_SEQ8, 8),
    BT_SDP_DATA_ELEM_LIST(
      { BT_SDP_TYPE_SIZE_VAR(BT_SDP_SEQ8, 6),
        BT_SDP_DATA_ELEM_LIST(
          { BT_SDP_TYPE_SIZE(BT_SDP_UUID16),
            BT_SDP_ARRAY_16(BT_SDP_SERIAL_PORT_SVCLASS) },
          { BT_SDP_TYPE_SIZE(BT_SDP_UINT16), BT_SDP_ARRAY_16(0x0102) },
        ) },
    )),
  BT_SDP_SERVICE_NAME("Brickwright SPIKE Serial Port"),
};

static struct bt_sdp_record spp_record = BT_SDP_RECORD(spp_attributes);

int brickwright_classic_spp_register(brickwright_classic_spp_receive_cb receive,
                                     brickwright_classic_spp_state_cb state,
                                     void *context)
{
  receive_callback = receive;
  state_callback = state;
  receive_context = context;
  if (registered)
    {
      return 0;
    }
  int result = bt_rfcomm_server_register(&spp_server);
  if (result)
    {
      return result;
    }
  result = bt_sdp_register_service(&spp_record);
  if (result)
    {
      (void)bt_rfcomm_server_unregister(&spp_server);
      return result;
    }
  registered = true;
  return 0;
}

int brickwright_classic_spp_send(const void *data, size_t length)
{
  if (!connected || (!data && length) || length > SPP_MTU)
    {
      return -EINVAL;
    }
  struct net_buf *buffer = bt_rfcomm_create_pdu(&spp_tx_pool);
  if (!buffer)
    {
      return -ENOMEM;
    }
  net_buf_add_mem(buffer, data, length);
  int result = bt_rfcomm_dlc_send(&spp_dlc, buffer);
  if (result < 0)
    {
      net_buf_unref(buffer);
    }
  return result;
}

bool brickwright_classic_spp_is_connected(void)
{
  return connected;
}

uint8_t brickwright_classic_spp_channel(void)
{
  return spp_server.channel;
}
