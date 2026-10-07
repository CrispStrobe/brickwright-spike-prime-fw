/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026 Brickwright contributors */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <brickwright/classic_spp.h>
#include <brickwright/fd02_service.h>
#include <brickwright/hub_transport.h>
#include <zephyr/bluetooth/conn.h>

/* Compile the actual adapter with neutral connection/notification boundaries.
 * Inclusion also permits a bounded synthetic exhaustion initial condition. */
#include "../src/hub_transport.c"

static struct bt_conn first = { .alive = true, .peer = 1 };
static struct bt_conn second = { .alive = true, .peer = 2 };
static bool reconnect_inside_notify;
static unsigned delivered[3], notifications;
static void connect_peer(struct bt_conn *connection)
{ brickwright_transport_connection_callbacks.connected(connection, 0); }
static void disconnect_peer(struct bt_conn *connection)
{
  connection->alive = false;
  brickwright_transport_connection_callbacks.disconnected(connection, 0);
}
int bt_conn_get_info(struct bt_conn *connection, struct bt_conn_info *info)
{
  assert(connection);
  *info = (struct bt_conn_info){ BT_CONN_TYPE_LE, BT_CONN_ROLE_PERIPHERAL };
  return 0;
}
struct bt_conn *bt_conn_ref(struct bt_conn *connection)
{ assert(connection); connection->refs++; return connection; }
void bt_conn_unref(struct bt_conn *connection)
{ assert(connection->refs > 0); connection->refs--; }
int brickwright_classic_spp_register(brickwright_classic_spp_receive_cb rx,
                                     brickwright_classic_spp_state_cb state, void *ctx)
{ (void)rx; (void)state; (void)ctx; return 0; }
void brickwright_classic_spp_set_sent_hook(void (*sent)(void)) { (void)sent; }
bool brickwright_classic_spp_is_connected(void) { return true; }
int brickwright_classic_spp_send(const void *data, size_t length)
{ (void)data; (void)length; return 0; }
void brickwright_fd02_set_receive(brickwright_fd02_receive_cb rx, void *ctx)
{ (void)rx; (void)ctx; }
int brickwright_fd02_notify(struct bt_conn *connection, const void *data, uint16_t length)
{
  notifications++;
  assert(length == 3 && !memcmp(data, "MSG", 3));
  assert(connection->refs == 2); /* adapter ownership plus final-send lease */
  if (reconnect_inside_notify)
    {
      reconnect_inside_notify = false;
      disconnect_peer(&first);
      assert(first.refs == 1); /* cannot recycle while this send holds its lease */
      connect_peer(&second);
      assert(connection == &first); /* never substitute the new global */
    }
  if (!connection->alive) return -ENOTCONN;
  delivered[connection->peer]++;
  return 0;
}

int main(void)
{
  uint64_t old = 99, fresh;
  assert(brickwright_hub_transport_capture_ble(NULL) == -EINVAL);
  assert(brickwright_hub_transport_capture_ble(&old) == -ENOTCONN && old == 0);
  connect_peer(&first);
  assert(brickwright_hub_transport_capture_ble(&old) == 0 && old);
  assert(brickwright_hub_transport_send_ble(old, "MSG", 3) == 0);
  assert(first.refs == 1 && delivered[1] == 1);
  reconnect_inside_notify = true;
  assert(brickwright_hub_transport_send_ble(old, "MSG", 3) == -ENOTCONN);
  assert(first.refs == 0 && second.refs == 1 && delivered[2] == 0);
  assert(brickwright_hub_transport_capture_ble(&fresh) == 0 && fresh != old);
  brickwright_transport_connection_callbacks.disconnected(&first, 0);
  uint64_t unchanged;
  assert(brickwright_hub_transport_capture_ble(&unchanged) == 0 && unchanged == fresh);
  brickwright_hub_transport_unregister();
  assert(brickwright_hub_transport_register(NULL, NULL, NULL) == 0);
  assert(brickwright_hub_transport_capture_ble(&unchanged) == 0 && unchanged == fresh);
  unsigned before = notifications;
  assert(brickwright_hub_transport_send_ble(old, "MSG", 3) == -ESTALE);
  assert(notifications == before && delivered[2] == 0);
  assert(brickwright_hub_transport_send_ble(fresh, "MSG", 3) == 0);
  assert(delivered[2] == 1 && second.refs == 1);
  assert(brickwright_hub_transport_send_ble(0, "MSG", 3) == -EINVAL);
  assert(brickwright_hub_transport_send_ble(fresh, NULL, 3) == -EINVAL);
  assert(brickwright_hub_transport_send_ble(fresh, "MSG", UINT16_MAX + 1u) == -EINVAL);
  disconnect_peer(&second);
  assert(second.refs == 0);
  last_le_identity = UINT64_MAX - 1;
  first.alive = true;
  connect_peer(&first);
  assert(brickwright_hub_transport_capture_ble(&fresh) == 0 && fresh == UINT64_MAX);
  disconnect_peer(&first);
  second.alive = true;
  connect_peer(&second);
  assert(brickwright_hub_transport_capture_ble(&fresh) == -EOVERFLOW && fresh == 0);
  assert(!brickwright_hub_transport_connected(BRICKWRIGHT_HUB_LINK_BLE));
  disconnect_peer(&second);
  assert(first.refs == 0 && second.refs == 0);
  puts("BLE concrete connection, stale admission, reentry, references and exhaustion passed");
  return 0;
}
