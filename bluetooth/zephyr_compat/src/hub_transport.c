/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdbool.h>
#include <brickwright/classic_spp.h>
#include <brickwright/fd02_service.h>
#include <brickwright/hub_transport.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>

static brickwright_hub_receive_cb receive_callback;
static void *receive_context;
static brickwright_hub_link_state_cb state_callback;
static struct bt_conn *le_connection;
static uint32_t generations[2];
static void (*writable_hook)(enum brickwright_hub_link link);
static void (*advertising_stopped_hook)(void);
static void (*advertising_restart_hook)(void);

static void advertising_restart(struct k_work *work)
{
  (void)work;
  if (advertising_restart_hook)
    {
      advertising_restart_hook();
    }
}

static K_WORK_DEFINE(advertising_restart_work, advertising_restart);

static void receive_classic(const uint8_t *data, size_t length, void *context)
{
  (void)context;
  if (receive_callback)
    {
      receive_callback(BRICKWRIGHT_HUB_LINK_CLASSIC, data, length,
                       receive_context);
    }
}

static void receive_ble(const uint8_t *data, size_t length, void *context)
{
  (void)context;
  if (receive_callback)
    {
      receive_callback(BRICKWRIGHT_HUB_LINK_BLE, data, length,
                       receive_context);
    }
}

static void state_classic(bool connected, void *context)
{
  (void)context;
  if (connected) generations[BRICKWRIGHT_HUB_LINK_CLASSIC]++;
  if (state_callback)
    state_callback(BRICKWRIGHT_HUB_LINK_CLASSIC, connected,
                   generations[BRICKWRIGHT_HUB_LINK_CLASSIC], receive_context);
}

static void transport_connected(struct bt_conn *connection, uint8_t error)
{
  struct bt_conn_info info;
  if (!error && bt_conn_get_info(connection, &info) == 0 &&
      info.type == BT_CONN_TYPE_LE && !le_connection)
    {
      if (info.role == BT_CONN_ROLE_PERIPHERAL && advertising_stopped_hook)
        {
          advertising_stopped_hook();
        }
      le_connection = bt_conn_ref(connection);
      generations[BRICKWRIGHT_HUB_LINK_BLE]++;
      if (state_callback)
        state_callback(BRICKWRIGHT_HUB_LINK_BLE, true,
                       generations[BRICKWRIGHT_HUB_LINK_BLE], receive_context);
    }
}

static void transport_disconnected(struct bt_conn *connection, uint8_t reason)
{
  (void)reason;
  if (connection == le_connection)
    {
      bt_conn_unref(le_connection);
      le_connection = NULL;
      if (state_callback)
        state_callback(BRICKWRIGHT_HUB_LINK_BLE, false,
                       generations[BRICKWRIGHT_HUB_LINK_BLE], receive_context);
    }
}

static void transport_recycled(void)
{
  if (advertising_restart_hook)
    {
      (void)k_work_submit(&advertising_restart_work);
    }
}

BT_CONN_CB_DEFINE(brickwright_transport_connection_callbacks) = {
  .connected = transport_connected,
  .disconnected = transport_disconnected,
  .recycled = transport_recycled,
};

static void classic_sent(void)
{
  if (writable_hook) writable_hook(BRICKWRIGHT_HUB_LINK_CLASSIC);
}

void brickwright_hub_transport_set_writable_hook(
  void (*writable)(enum brickwright_hub_link link))
{
  writable_hook = writable;
  brickwright_classic_spp_set_sent_hook(writable ? classic_sent : NULL);
}

void brickwright_hub_transport_set_advertising_hooks(
  void (*advertising_stopped)(void), void (*advertising_restart)(void))
{
  advertising_stopped_hook = advertising_stopped;
  advertising_restart_hook = advertising_restart;
}

int brickwright_hub_transport_register(brickwright_hub_receive_cb receive,
                                       brickwright_hub_link_state_cb state,
                                       void *context)
{
  receive_callback = receive;
  state_callback = state;
  receive_context = context;
  brickwright_fd02_set_receive(receive_ble, NULL);
  int rc = brickwright_classic_spp_register(receive_classic, state_classic,
                                             NULL);
  if (rc < 0) brickwright_hub_transport_unregister();
  return rc;
}

void brickwright_hub_transport_unregister(void)
{
  receive_callback = NULL;
  state_callback = NULL;
  receive_context = NULL;
  brickwright_fd02_set_receive(NULL, NULL);
}

int brickwright_hub_transport_send(enum brickwright_hub_link link,
                                   const void *data, size_t length)
{
  if ((!data && length) || length > UINT16_MAX)
    {
      return -EINVAL;
    }
  if (link == BRICKWRIGHT_HUB_LINK_CLASSIC)
    {
      return brickwright_classic_spp_send(data, length);
    }
  if (link == BRICKWRIGHT_HUB_LINK_BLE)
    {
      return le_connection ?
        brickwright_fd02_notify(le_connection, data, (uint16_t)length) :
        -ENOTCONN;
    }
  return -EINVAL;
}

bool brickwright_hub_transport_connected(enum brickwright_hub_link link)
{
  if (link == BRICKWRIGHT_HUB_LINK_CLASSIC)
    {
      return brickwright_classic_spp_is_connected();
    }
  return link == BRICKWRIGHT_HUB_LINK_BLE && le_connection != NULL;
}
