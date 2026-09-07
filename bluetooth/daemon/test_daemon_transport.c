/* SPDX-License-Identifier: Apache-2.0 */
#include "daemon_transport.h"
#include <brickwright/hub_transport.h>
#include <assert.h>
#include <string.h>
static brickwright_hub_receive_cb receive_callback;
static void *receive_context;
static enum brickwright_hub_link sent_link;
static uint8_t sent[1100];
static size_t sent_length;
int brickwright_hub_transport_register(brickwright_hub_receive_cb callback,
                                       brickwright_hub_link_state_cb state,
                                       void *context)
{
  (void)state;
  receive_callback = callback; receive_context = context; return 0;
}
void brickwright_hub_transport_unregister(void) {}
int brickwright_hub_transport_send(enum brickwright_hub_link link,
                                   const void *data, size_t length)
{
  sent_link = link; memcpy(sent, data, length); sent_length = length; return 0;
}
bool brickwright_hub_transport_connected(enum brickwright_hub_link link)
{
  (void)link; return true;
}
static int messages;
static int on_message(enum brickwright_protocol_kind kind, const uint8_t *data,
                      size_t length, bool high, void *context)
{
  assert(context == &messages);
  assert(kind == BRICKWRIGHT_PROTOCOL_BLE_MESSAGE);
  assert(high && length == 2 && data[0] == 0x28 && data[1] == 0x64);
  ++messages; return 0;
}
int main(void)
{
  assert(brickwright_daemon_transport_init(on_message, &messages) == 0);
  const uint8_t payload[] = {0x28, 0x64};
  assert(brickwright_daemon_transport_send(BRICKWRIGHT_PROTOCOL_BLE_MESSAGE,
                                            payload, sizeof(payload), true) == 0);
  assert(sent_link == BRICKWRIGHT_HUB_LINK_BLE && sent_length > sizeof(payload));
  receive_callback(BRICKWRIGHT_HUB_LINK_BLE, sent, 2, receive_context);
  receive_callback(BRICKWRIGHT_HUB_LINK_BLE, sent + 2, sent_length - 2,
                   receive_context);
  assert(messages == 1);
  assert(brickwright_daemon_transport_send(BRICKWRIGHT_PROTOCOL_CLASSIC_RECORD,
                                            "{}", 2, false) == 0);
  assert(sent_link == BRICKWRIGHT_HUB_LINK_CLASSIC && sent_length == 4);
  assert(!memcmp(sent, "{}\r\n", 4));
  return 0;
}
