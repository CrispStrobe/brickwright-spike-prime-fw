/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_VIRTUAL_HCI_H
#define BRICKWRIGHT_VIRTUAL_HCI_H

#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>
#include <brickwright/h4.h>

typedef int (*brickwright_virtual_hci_send_cb)(const uint8_t *frame,
                                               size_t length, void *context);

struct brickwright_virtual_hci {
  struct brickwright_h4 h4;
  uint8_t address[6];
  brickwright_virtual_hci_send_cb send;
  void *context;
  bool advertising;
  uint8_t advertising_data[31];
  uint8_t advertising_data_length;
  uint8_t scan_response_data[31];
  uint8_t scan_response_data_length;
  bool connected;
  bool classic_connection;
  bool classic_connectable;
  bool acknowledge_vendor_commands;
  uint16_t connection_handle;
  uint8_t peer_address[6];
  uint8_t expected_ltk[16];
  bool ltk_request_pending;
  uint8_t host_acl[1025];
  size_t host_acl_length;
};

void brickwright_virtual_hci_init(struct brickwright_virtual_hci *controller,
                                  const uint8_t address[6],
                                  brickwright_virtual_hci_send_cb send,
                                  void *context);
void brickwright_virtual_hci_acknowledge_vendor_commands(
  struct brickwright_virtual_hci *controller, bool enabled);
int brickwright_virtual_hci_feed(struct brickwright_virtual_hci *controller,
                                 const void *data, size_t length);
int brickwright_virtual_hci_connect(struct brickwright_virtual_hci *controller,
                                    const uint8_t peer_address[6]);
int brickwright_virtual_hci_disconnect(struct brickwright_virtual_hci *controller,
                                       uint8_t reason);
int brickwright_virtual_hci_send_acl(struct brickwright_virtual_hci *controller,
                                     const void *payload, size_t length);
int brickwright_virtual_hci_request_ltk(
  struct brickwright_virtual_hci *controller, const uint8_t expected_ltk[16]);
int brickwright_virtual_hci_classic_connection_request(
  struct brickwright_virtual_hci *controller, const uint8_t peer_address[6]);

#endif
