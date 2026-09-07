/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <brickwright/fd02_service.h>
#include <brickwright/classic_spp.h>
#include <brickwright/hci_driver.h>
#include <brickwright/hub_transport.h>
#include <brickwright/settings_store.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/classic/classic.h>
#include <zephyr/bluetooth/classic/rfcomm.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/iterable_sections.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci_types.h>
#include <zephyr/bluetooth/crypto.h>
#include <zephyr/device.h>
#include <zephyr/drivers/bluetooth.h>
#include "host/classic/sco_internal.h"

/* GNU start/stop symbols only exist for non-empty iterable sections. */
static const STRUCT_SECTION_ITERABLE(bt_sco_conn_cb,
                                     brickwright_empty_sco_conn_cb) = {0};
static const STRUCT_SECTION_ITERABLE(bt_sco_hci_cb,
                                     brickwright_empty_sco_hci_cb) = {0};

static struct k_sem connected;
static struct k_sem disconnected;
static struct k_sem fd02_received;
static struct k_sem spp_received;
static struct k_sem security_changed;
static struct k_sem setting_saved;
static uint8_t fd02_input[16];
static size_t fd02_input_length;
static uint8_t spp_input[16];
static size_t spp_input_length;
static struct bt_conn *active_connection;
static unsigned link_state_events;
static uint32_t ble_generation;
static uint32_t classic_generation;
static bt_security_t security_level;
static enum bt_security_err security_error;
static char saved_setting_key[128];
static uint8_t saved_setting[160];
static size_t saved_setting_length;

int brickwright_settings_store(const char *key, const void *value,
                               size_t length)
{
  assert(key != NULL && (value != NULL || length == 0));
  if (strncmp(key, "bt/keys/", 8)) return 0;
  assert(strlen(key) < sizeof(saved_setting_key));
  assert(length <= sizeof(saved_setting));
  strcpy(saved_setting_key, key);
  if (length) memcpy(saved_setting, value, length);
  saved_setting_length = length;
  if (length) k_sem_give(&setting_saved);
  return 0;
}

int brickwright_settings_remove(const char *key)
{
  if (!strcmp(key, saved_setting_key))
    {
      saved_setting_key[0] = '\0';
      saved_setting_length = 0;
    }
  return 0;
}

int brickwright_settings_visit(const char *subtree,
                               brickwright_settings_visit_cb visitor,
                               void *context)
{
  (void)subtree;
  (void)visitor;
  (void)context;
  return 0;
}

static void on_link_state(enum brickwright_hub_link link, bool is_connected,
                          uint32_t generation, void *context)
{
  (void)is_connected;
  assert(context == &connected);
  link_state_events++;
  if (link == BRICKWRIGHT_HUB_LINK_BLE) ble_generation = generation;
  else classic_generation = generation;
}

static int unused_physical_receive(const struct device *device,
                                   struct net_buf *buffer)
{
  (void)device;
  (void)buffer;
  assert(false);
  return -EIO;
}

static void on_fd02_receive(const uint8_t *data, size_t length, void *context)
{
  assert(context == &fd02_received);
  assert(length <= sizeof(fd02_input));
  memcpy(fd02_input, data, length);
  fd02_input_length = length;
  k_sem_give(&fd02_received);
}

static void on_spp_receive(const uint8_t *data, size_t length, void *context)
{
  assert(context == &spp_received);
  assert(length <= sizeof(spp_input));
  memcpy(spp_input, data, length);
  spp_input_length = length;
  k_sem_give(&spp_received);
}

static void on_hub_receive(enum brickwright_hub_link link,
                           const uint8_t *data, size_t length, void *context)
{
  assert(context == &connected);
  if (link == BRICKWRIGHT_HUB_LINK_BLE)
    {
      on_fd02_receive(data, length, &fd02_received);
    }
  else
    {
      assert(link == BRICKWRIGHT_HUB_LINK_CLASSIC);
      on_spp_receive(data, length, &spp_received);
    }
}

static uint8_t rfcomm_fcs(const uint8_t *data, size_t length)
{
  uint8_t fcs = 0xff;
  while (length--)
    {
      fcs ^= *data++;
      for (unsigned int bit = 0; bit < 8; ++bit)
        {
          fcs = (fcs & 1) ? (uint8_t)((fcs >> 1) ^ 0xe0) : (fcs >> 1);
        }
    }
  return (uint8_t)(0xff - fcs);
}

static void peer_l2cap_send(uint16_t cid, const uint8_t *data, size_t length)
{
  uint8_t packet[80];
  assert(length + 4 <= sizeof(packet));
  packet[0] = (uint8_t)length;
  packet[1] = (uint8_t)(length >> 8);
  packet[2] = (uint8_t)cid;
  packet[3] = (uint8_t)(cid >> 8);
  memcpy(packet + 4, data, length);
  assert(brickwright_hci_virtual_send_acl(packet, length + 4) == 0);
}

static size_t peer_take_acl(uint8_t *packet, size_t capacity)
{
  size_t length = 0;
  assert(brickwright_hci_virtual_take_host_acl(packet, capacity, &length,
                                               5000) == 0);
  return length;
}

static size_t peer_take_signal(uint8_t *packet, size_t capacity,
                               uint8_t code, uint8_t identifier)
{
  for (unsigned int attempt = 0; attempt < 8; ++attempt)
    {
      const size_t length = peer_take_acl(packet, capacity);
      if (length >= 10 && packet[6] == 0x01 && packet[7] == 0x00 &&
          packet[8] == code &&
          (identifier == 0xff || packet[9] == identifier))
        {
          return length;
        }
    }
  assert(false);
  return 0;
}

static void xor_128(uint8_t output[16], const uint8_t left[16],
                    const uint8_t right[16])
{
  for (size_t i = 0; i < 16; ++i) output[i] = left[i] ^ right[i];
}

static void legacy_c1(const uint8_t random[16], const uint8_t preq[7],
                      const uint8_t pres[7], const uint8_t initiator[6],
                      const uint8_t responder[6], uint8_t output[16])
{
  const uint8_t tk[16] = {0};
  uint8_t p1[16] = {0};
  uint8_t p2[16] = {0};
  uint8_t temporary[16];
  /* Both addresses are public in the deterministic connection event. */
  memcpy(p1 + 2, preq, 7);
  memcpy(p1 + 9, pres, 7);
  memcpy(p2, responder, 6);
  memcpy(p2 + 6, initiator, 6);
  xor_128(temporary, random, p1);
  assert(bt_encrypt_le(tk, temporary, temporary) == 0);
  xor_128(temporary, temporary, p2);
  assert(bt_encrypt_le(tk, temporary, output) == 0);
}

static void legacy_s1(const uint8_t initiator_random[16],
                      const uint8_t responder_random[16], uint8_t stk[16])
{
  const uint8_t tk[16] = {0};
  memcpy(stk, initiator_random, 8);
  memcpy(stk + 8, responder_random, 8);
  assert(bt_encrypt_le(tk, stk, stk) == 0);
}

static void on_connected(struct bt_conn *connection, uint8_t error)
{
  assert(connection != NULL);
  assert(error == 0);
  active_connection = bt_conn_ref(connection);
  k_sem_give(&connected);
}

static void on_disconnected(struct bt_conn *connection, uint8_t reason)
{
  assert(connection != NULL);
  assert(reason == 0x13);
  bt_conn_unref(active_connection);
  active_connection = NULL;
  k_sem_give(&disconnected);
}


static void on_security_changed(struct bt_conn *connection,
                                bt_security_t level,
                                enum bt_security_err error)
{
  assert(connection == active_connection);
  security_level = level;
  security_error = error;
  k_sem_give(&security_changed);
}

BT_CONN_CB_DEFINE(connection_callbacks) = {
  .connected = on_connected,
  .disconnected = on_disconnected,
  .security_changed = on_security_changed,
};

int main(void)
{
  const uint8_t address[6] = {0x01, 0x02, 0x03, 0x04, 0x05, 0xc0};

  assert(k_sem_init(&setting_saved, 0, 1) == 0);
  assert(brickwright_hci_configure(BRICKWRIGHT_HCI_BACKEND_VIRTUAL, NULL,
                                   address) == 0);
  assert(bt_enable(NULL) == 0);
  assert(settings_load() == 0);
  assert(bt_is_ready());
  assert(k_sem_init(&connected, 0, 1) == 0);
  assert(k_sem_init(&disconnected, 0, 1) == 0);
  assert(k_sem_init(&fd02_received, 0, 1) == 0);
  assert(k_sem_init(&spp_received, 0, 1) == 0);
  assert(k_sem_init(&security_changed, 0, 1) == 0);
  assert(brickwright_hub_transport_register(on_hub_receive, on_link_state,
                                             &connected) == 0);
  assert(brickwright_classic_spp_channel() == BT_RFCOMM_CHAN_SPP);
  const struct bt_le_adv_param *advertising = BT_LE_ADV_PARAM(
    BT_LE_ADV_OPT_CONN | BT_LE_ADV_OPT_USE_IDENTITY,
    BT_GAP_ADV_FAST_INT_MIN_2, BT_GAP_ADV_FAST_INT_MAX_2, NULL);
  assert(bt_le_adv_start(advertising, NULL, 0, NULL, 0) == 0);
  assert(brickwright_hci_virtual_is_advertising());
  const uint8_t peer[6] = {0x06, 0x05, 0x04, 0x03, 0x02, 0xc1};
  assert(brickwright_hci_virtual_connect(peer) == 0);
  assert(k_sem_take(&connected, K_SECONDS(1)) == 0);
  assert(brickwright_hub_transport_connected(BRICKWRIGHT_HUB_LINK_BLE));
  assert(link_state_events == 1 && ble_generation == 1);
  assert(!brickwright_hci_virtual_is_advertising());
  const uint8_t pairing_request[7] = {
    0x01, 0x03, 0x00, 0x01, 0x10, 0x01, 0x00
  };
  uint8_t smp_packet[11] = {7, 0, 6, 0};
  memcpy(smp_packet + 4, pairing_request, sizeof(pairing_request));
  assert(brickwright_hci_virtual_send_acl(smp_packet, sizeof(smp_packet)) == 0);
  uint8_t host_acl[64];
  size_t host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length == 15 && host_acl[6] == 0x06 && host_acl[7] == 0x00);
  assert(host_acl[8] == 0x02);
  uint8_t pairing_response[7];
  memcpy(pairing_response, host_acl + 8, sizeof(pairing_response));
  assert((pairing_response[3] & 0x01) != 0);
  assert((pairing_response[5] & 0x01) != 0);
  const uint8_t peer_random[16] = {
    0x10, 0x32, 0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe,
    0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88
  };
  uint8_t peer_confirm[16];
  legacy_c1(peer_random, pairing_request, pairing_response, peer, address,
            peer_confirm);
  uint8_t confirm_packet[21] = {17, 0, 6, 0, 3};
  memcpy(confirm_packet + 5, peer_confirm, sizeof(peer_confirm));
  assert(brickwright_hci_virtual_send_acl(confirm_packet,
                                          sizeof(confirm_packet)) == 0);
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length == 25 && host_acl[6] == 0x06 && host_acl[8] == 0x03);
  uint8_t random_packet[21] = {17, 0, 6, 0, 4};
  memcpy(random_packet + 5, peer_random, sizeof(peer_random));
  assert(brickwright_hci_virtual_send_acl(random_packet,
                                          sizeof(random_packet)) == 0);
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length == 25 && host_acl[6] == 0x06 && host_acl[8] == 0x04);
  uint8_t stk[16];
  legacy_s1(peer_random, host_acl + 9, stk);
  assert(brickwright_hci_virtual_request_ltk(stk) == 0);
  assert(k_sem_take(&security_changed, K_SECONDS(1)) == 0);
  assert(security_error == BT_SECURITY_ERR_SUCCESS);
  assert(security_level == BT_SECURITY_L2);
  assert(bt_conn_get_security(active_connection) == BT_SECURITY_L2);
  const uint8_t peer_ltk[16] = {
    0xa0, 0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7,
    0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xad, 0xae, 0xaf
  };
  uint8_t encrypt_info[21] = {17, 0, 6, 0, 6};
  memcpy(encrypt_info + 5, peer_ltk, sizeof(peer_ltk));
  assert(brickwright_hci_virtual_send_acl(encrypt_info,
                                          sizeof(encrypt_info)) == 0);
  const uint8_t central_ident[] = {
    0x0b, 0x00, 0x06, 0x00, 0x07,
    0x34, 0x12, 1, 2, 3, 4, 5, 6, 7, 8
  };
  assert(brickwright_hci_virtual_send_acl(central_ident,
                                          sizeof(central_ident)) == 0);
  assert(k_sem_take(&setting_saved, K_SECONDS(1)) == 0);
  assert(saved_setting_length > 0);
  assert(!strncmp(saved_setting_key, "bt/keys/", 8));
  const uint8_t mtu_request[] = {0x03, 0x00, 0x04, 0x00, 0x02, 0x40, 0x00};
  assert(brickwright_hci_virtual_send_acl(mtu_request,
                                          sizeof(mtu_request)) == 0);
  host_acl_length = 0;
  assert(brickwright_hci_virtual_take_host_acl(host_acl, sizeof(host_acl),
                                               &host_acl_length, 5000) == 0);
  assert(host_acl_length >= 11);
  assert(host_acl[6] == 0x04 && host_acl[7] == 0x00);
  assert(host_acl[8] == 0x03);
  const uint16_t rx_handle = brickwright_fd02_rx_handle();
  assert(rx_handle != 0);
  const uint8_t write_command[] = {
    0x06, 0x00, 0x04, 0x00, 0x52,
    (uint8_t)rx_handle, (uint8_t)(rx_handle >> 8), 0x00, 0x7e, 0x02
  };
  assert(brickwright_hci_virtual_send_acl(write_command,
                                          sizeof(write_command)) == 0);
  assert(k_sem_take(&fd02_received, K_SECONDS(1)) == 0);
  const uint8_t expected_input[] = {0x00, 0x7e, 0x02};
  assert(fd02_input_length == sizeof(expected_input));
  assert(!memcmp(fd02_input, expected_input, sizeof(expected_input)));
  const uint16_t ccc_handle = brickwright_fd02_ccc_handle();
  const uint8_t enable_notifications[] = {
    0x05, 0x00, 0x04, 0x00, 0x12,
    (uint8_t)ccc_handle, (uint8_t)(ccc_handle >> 8), 0x01, 0x00
  };
  assert(brickwright_hci_virtual_send_acl(enable_notifications,
                                          sizeof(enable_notifications)) == 0);
  assert(brickwright_hci_virtual_take_host_acl(host_acl, sizeof(host_acl),
                                               &host_acl_length, 5000) == 0);
  assert(host_acl_length >= 9 && host_acl[8] == 0x13);
  const uint8_t notification[] = {0x01, 0x40, 0x00};
  assert(brickwright_hub_transport_send(BRICKWRIGHT_HUB_LINK_BLE, notification,
                                        sizeof(notification)) == 0);
  assert(brickwright_hci_virtual_take_host_acl(host_acl, sizeof(host_acl),
                                               &host_acl_length, 5000) == 0);
  const uint16_t tx_handle = brickwright_fd02_tx_handle();
  assert(host_acl_length >= 14 && host_acl[8] == 0x1b);
  assert(host_acl[9] == (uint8_t)tx_handle &&
         host_acl[10] == (uint8_t)(tx_handle >> 8));
  assert(!memcmp(host_acl + 11, notification, sizeof(notification)));
  assert(brickwright_hci_virtual_disconnect(0x13) == 0);
  assert(k_sem_take(&disconnected, K_SECONDS(1)) == 0);
  assert(!brickwright_hub_transport_connected(BRICKWRIGHT_HUB_LINK_BLE));
  assert(link_state_events == 2 && ble_generation == 1);
  assert(bt_br_set_connectable(true, NULL) == 0);
  assert(bt_br_set_discoverable(true, false) == 0);
  const uint8_t classic_peer[6] = {0x0c, 0x0b, 0x0a, 0x09, 0x08, 0x07};
  assert(brickwright_hci_virtual_classic_connection_request(classic_peer) == 0);
  assert(k_sem_take(&connected, K_SECONDS(1)) == 0);
  assert(active_connection != NULL);
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 14 && host_acl[6] == 0x01 && host_acl[7] == 0x00);
  assert(host_acl[8] == 0x0a);
  uint8_t info_response[] = {
    0x0b, host_acl[9], 0x08, 0x00, 0x02, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00
  };
  peer_l2cap_send(0x0001, info_response, sizeof(info_response));
  const uint8_t rfcomm_connection_request[] = {
    0x02, 0x22, 0x04, 0x00, 0x03, 0x00, 0x41, 0x00
  };
  peer_l2cap_send(0x0001, rfcomm_connection_request,
                  sizeof(rfcomm_connection_request));
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 20 && host_acl[8] == 0x03 && host_acl[9] == 0x22);
  const uint16_t host_cid = host_acl[12] | ((uint16_t)host_acl[13] << 8);
  assert(host_acl[14] == 0x41 && host_acl[15] == 0x00);
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 16 && host_acl[8] == 0x04);
  const uint8_t host_config_identifier = host_acl[9];
  const uint8_t peer_config_request[] = {
    0x04, 0x23, 0x04, 0x00,
    (uint8_t)host_cid, (uint8_t)(host_cid >> 8), 0x00, 0x00
  };
  peer_l2cap_send(0x0001, peer_config_request, sizeof(peer_config_request));
  const uint8_t peer_config_response[] = {
    0x05, host_config_identifier, 0x06, 0x00,
    0x41, 0x00, 0x00, 0x00, 0x00, 0x00
  };
  peer_l2cap_send(0x0001, peer_config_response, sizeof(peer_config_response));
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 18 && host_acl[8] == 0x05 && host_acl[9] == 0x23);
  uint8_t sabm_mux[] = {0x03, 0x3f, 0x01, 0};
  sabm_mux[3] = rfcomm_fcs(sabm_mux, 3);
  peer_l2cap_send(host_cid, sabm_mux, sizeof(sabm_mux));
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 12 && (host_acl[9] & 0xef) == 0x63);
  uint8_t sabm_dlc[] = {0x2f, 0x3f, 0x01, 0};
  sabm_dlc[3] = rfcomm_fcs(sabm_dlc, 3);
  peer_l2cap_send(host_cid, sabm_dlc, sizeof(sabm_dlc));
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 12 && (host_acl[9] & 0xef) == 0x63);
  assert(brickwright_classic_spp_is_connected());
  assert(brickwright_hub_transport_connected(BRICKWRIGHT_HUB_LINK_CLASSIC));
  assert(link_state_events == 3 && classic_generation == 1);
  uint8_t spp_frame[] = {0x2f, 0xef, 0x07, 'O', 'K', '\r', 0};
  spp_frame[6] = rfcomm_fcs(spp_frame, 2);
  peer_l2cap_send(host_cid, spp_frame, sizeof(spp_frame));
  assert(k_sem_take(&spp_received, K_SECONDS(1)) == 0);
  assert(spp_input_length == 3 && !memcmp(spp_input, "OK\r", 3));
  const uint8_t sdp_connection_request[] = {
    0x02, 0x24, 0x04, 0x00, 0x01, 0x00, 0x42, 0x00
  };
  peer_l2cap_send(0x0001, sdp_connection_request,
                  sizeof(sdp_connection_request));
  host_acl_length = peer_take_signal(host_acl, sizeof(host_acl), 0x03, 0x24);
  assert(host_acl_length >= 20 && host_acl[8] == 0x03 && host_acl[9] == 0x24);
  const uint16_t sdp_host_cid = host_acl[12] | ((uint16_t)host_acl[13] << 8);
  assert(host_acl[14] == 0x42 && host_acl[15] == 0x00);
  host_acl_length = peer_take_signal(host_acl, sizeof(host_acl), 0x04, 0xff);
  assert(host_acl_length >= 16 && host_acl[8] == 0x04);
  const uint8_t sdp_config_identifier = host_acl[9];
  const uint8_t sdp_peer_config_request[] = {
    0x04, 0x25, 0x04, 0x00,
    (uint8_t)sdp_host_cid, (uint8_t)(sdp_host_cid >> 8), 0x00, 0x00
  };
  peer_l2cap_send(0x0001, sdp_peer_config_request,
                  sizeof(sdp_peer_config_request));
  const uint8_t sdp_peer_config_response[] = {
    0x05, sdp_config_identifier, 0x06, 0x00,
    0x42, 0x00, 0x00, 0x00, 0x00, 0x00
  };
  peer_l2cap_send(0x0001, sdp_peer_config_response,
                  sizeof(sdp_peer_config_response));
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 18 && host_acl[8] == 0x05 && host_acl[9] == 0x25);
  const uint8_t serial_port_search[] = {
    0x02, 0x00, 0x01, 0x00, 0x08,
    0x35, 0x03, 0x19, 0x11, 0x01, 0x00, 0x01, 0x00
  };
  peer_l2cap_send(sdp_host_cid, serial_port_search,
                  sizeof(serial_port_search));
  host_acl_length = peer_take_acl(host_acl, sizeof(host_acl));
  assert(host_acl_length >= 18);
  assert(host_acl[6] == 0x42 && host_acl[7] == 0x00);
  assert(host_acl[8] == 0x03 && host_acl[9] == 0x00 && host_acl[10] == 0x01);
  assert(host_acl[13] == 0x00 && host_acl[14] == 0x01);
  brickwright_hub_transport_unregister();
  unsigned events_before_unregister_disconnect = link_state_events;
  assert(brickwright_hci_virtual_disconnect(0x13) == 0);
  assert(k_sem_take(&disconnected, K_SECONDS(1)) == 0);
  assert(link_state_events == events_before_unregister_disconnect);
  assert(brickwright_hci_configure(BRICKWRIGHT_HCI_BACKEND_PHYSICAL,
                                   "/dev/ttyBT", NULL) == -EINVAL);
  assert(bt_disable() == 0);
  assert(!bt_is_ready());
  assert(brickwright_hci_configure(BRICKWRIGHT_HCI_BACKEND_PHYSICAL,
                                   "/dev/ttyBT", NULL) == 0);
  const struct bt_hci_driver_api *physical_api = brickwright_hci_device.api;
  /* Public CI has neither a board reset provider nor restricted TI bytes. */
  assert(physical_api->open(&brickwright_hci_device,
                            unused_physical_receive) == -ENOSYS);
  return 0;
}
