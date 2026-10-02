/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_HCI_DRIVER_H
#define BRICKWRIGHT_HCI_DRIVER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum brickwright_hci_backend
{
  BRICKWRIGHT_HCI_BACKEND_PHYSICAL,
  BRICKWRIGHT_HCI_BACKEND_VIRTUAL
};

int brickwright_hci_configure(enum brickwright_hci_backend backend,
                              const char *path, const uint8_t address[6]);
bool brickwright_hci_virtual_is_advertising(void);
int brickwright_hci_virtual_connect(const uint8_t peer_address[6]);
int brickwright_hci_virtual_disconnect(uint8_t reason);
int brickwright_hci_virtual_send_acl(const void *payload, size_t length);
int brickwright_hci_virtual_request_ltk(const uint8_t expected_ltk[16]);
int brickwright_hci_virtual_take_host_acl(void *buffer, size_t capacity,
                                          size_t *length, int timeout_ms);
int brickwright_hci_virtual_classic_connection_request(
  const uint8_t peer_address[6]);

/* Private deployments provide these hooks without putting restricted
 * controller bytes in this repository.  The weak defaults fail closed. */
int brickwright_hci_platform_power_cycle(const char *path);
int brickwright_hci_platform_service_pack(const uint8_t **image,
                                          size_t *length);
int brickwright_hci_platform_set_serial(int fd, uint32_t baud,
                                        uint32_t flow_control);
int brickwright_hci_platform_delay_ms(uint32_t duration_ms);

#endif
