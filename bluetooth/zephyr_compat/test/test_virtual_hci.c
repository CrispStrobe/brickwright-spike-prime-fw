/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <brickwright/virtual_hci.h>

static uint8_t output[256];
static size_t output_length;

static int send_frame(const uint8_t *frame, size_t length, void *context)
{
  assert(context == output);
  assert(output_length + length <= sizeof(output));
  memcpy(output + output_length, frame, length);
  output_length += length;
  return 0;
}

int main(void)
{
  const uint8_t address[6] = {0x06, 0x05, 0x04, 0x03, 0x02, 0x01};
  struct brickwright_virtual_hci controller;
  brickwright_virtual_hci_init(&controller, address, send_frame, output);

  const uint8_t vendor[] = {0x01, 0x05, 0xff, 0x01, 0xaa};
  assert(brickwright_virtual_hci_feed(&controller, vendor, sizeof(vendor)) == 0);
  assert(output[6] == 0x01);
  brickwright_virtual_hci_acknowledge_vendor_commands(&controller, true);
  assert(brickwright_virtual_hci_feed(&controller, vendor, sizeof(vendor)) == 0);
  assert(output[13] == 0x00);
  brickwright_virtual_hci_acknowledge_vendor_commands(&controller, false);
  output_length = 0;

  const uint8_t reset[] = {0x01, 0x03, 0x0c, 0x00};
  assert(brickwright_virtual_hci_feed(&controller, reset, 2) == 0);
  assert(output_length == 0);
  assert(brickwright_virtual_hci_feed(&controller, reset + 2, 2) == 0);
  const uint8_t reset_complete[] = {0x04, 0x0e, 0x04, 0x01,
                                    0x03, 0x0c, 0x00};
  assert(output_length == sizeof(reset_complete));
  assert(!memcmp(output, reset_complete, sizeof(reset_complete)));

  output_length = 0;
  const uint8_t commands[] = {
    0x01, 0x09, 0x10, 0x00,
    0x01, 0xff, 0x03, 0x00
  };
  assert(brickwright_virtual_hci_feed(&controller, commands,
                                      sizeof(commands)) == 0);
  const uint8_t expected[] = {
    0x04, 0x0e, 0x0a, 0x01, 0x09, 0x10, 0x00,
    0x06, 0x05, 0x04, 0x03, 0x02, 0x01,
    0x04, 0x0e, 0x04, 0x01, 0xff, 0x03, 0x01
  };
  assert(output_length == sizeof(expected));
  assert(!memcmp(output, expected, sizeof(expected)));

  output_length = 0;
  const uint8_t initialization[] = {
    0x01, 0x03, 0x10, 0x00,
    0x01, 0x01, 0x10, 0x00,
    0x01, 0x02, 0x20, 0x00,
    0x01, 0x01, 0x20, 0x08, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff
  };
  assert(brickwright_virtual_hci_feed(&controller, initialization,
                                      sizeof(initialization)) == 0);
  /* Features: 7-byte event prefix plus eight feature bytes. */
  assert(output[0] == 0x04 && output[2] == 12 && output[6] == 0);
  assert(output[11] == 0x40);
  /* Version response follows, then LE buffer size and event-mask success. */
  assert(output[15] == 0x04 && output[17] == 12 && output[21] == 0);
  assert(output[30] == 0x04 && output[32] == 7 && output[36] == 0);
  assert(output[40] == 0x04 && output[42] == 4 && output[46] == 0);

  output_length = 0;
  const uint8_t supported[] = {0x01, 0x02, 0x10, 0x00};
  assert(brickwright_virtual_hci_feed(&controller, supported,
                                      sizeof(supported)) == 0);
  assert(output_length == 71 && output[2] == 68 && output[6] == 0);
  for (size_t i = 7; i < output_length; ++i)
    {
      assert(output[i] == 0);
    }

  output_length = 0;
  const uint8_t classic_init[] = {
    0x01, 0x56, 0x0c, 0x01, 0x01,
    0x01, 0x45, 0x0c, 0x01, 0x02,
    0x01, 0x24, 0x0c, 0x03, 0x00, 0x08, 0x00,
    0x01, 0x18, 0x0c, 0x02, 0x00, 0x20,
    0x01, 0x0e, 0x08, 0x00
  };
  assert(brickwright_virtual_hci_feed(&controller, classic_init,
                                      sizeof(classic_init)) == 0);
  /* Four write completions and a read-policy completion. */
  assert(output_length == 37);
  assert(output[0] == 0x04 && output[6] == 0);
  assert(output[7] == 0x04 && output[13] == 0);
  assert(output[14] == 0x04 && output[20] == 0);
  assert(output[21] == 0x04 && output[27] == 0);
  assert(output[28] == 0x04 && output[30] == 6 && output[34] == 0);
  assert(output[35] == 0 && output[36] == 0);

  output_length = 0;
  uint8_t local_name[252] = {0x01, 0x13, 0x0c, 248};
  memcpy(local_name + 4, "Brickwright SPIKE", 17);
  assert(brickwright_virtual_hci_feed(&controller, local_name,
                                      sizeof(local_name)) == 0);
  assert(output_length == 7 && output[4] == 0x13 && output[5] == 0x0c &&
         output[6] == 0);

  output_length = 0;
  uint8_t advertising[55] = {
    0x01, 0x06, 0x20, 15, 0x20, 0x00, 0x40, 0x00, 0x03, 0x00,
    0x00, 0, 0, 0, 0, 0, 0, 0x07, 0x00,
    0x01, 0x08, 0x20, 32, 3, 0x02, 0x01, 0x06,
  };
  assert(brickwright_virtual_hci_feed(&controller, advertising,
                                      sizeof(advertising)) == 0);
  assert(controller.advertising_data_length == 3);
  assert(!memcmp(controller.advertising_data, advertising + 24, 3));
  const uint8_t enable[] = {0x01, 0x0a, 0x20, 0x01, 0x01};
  assert(brickwright_virtual_hci_feed(&controller, enable, sizeof(enable)) == 0);
  assert(controller.advertising);
  assert(output_length == 21);
  output_length = 0;
  const uint8_t peer[6] = {1, 2, 3, 4, 5, 6};
  assert(brickwright_virtual_hci_connect(&controller, peer) == 0);
  assert(controller.connected && !controller.advertising);
  assert(output_length == 22 && output[1] == 0x3e && output[3] == 0x01);
  output_length = 0;
  uint8_t expected_ltk[16] = {0};
  expected_ltk[15] = 0xa5;
  assert(brickwright_virtual_hci_request_ltk(&controller, expected_ltk) == 0);
  assert(controller.ltk_request_pending);
  assert(output_length == 16 && output[1] == 0x3e && output[3] == 0x05);
  output_length = 0;
  uint8_t ltk_reply[22] = {0x01, 0x1a, 0x20, 18, 1, 0};
  memcpy(ltk_reply + 6, expected_ltk, sizeof(expected_ltk));
  ltk_reply[21] ^= 1;
  assert(brickwright_virtual_hci_feed(&controller, ltk_reply,
                                      sizeof(ltk_reply)) == -EKEYREJECTED);
  assert(controller.ltk_request_pending && output_length == 0);
  ltk_reply[21] ^= 1;
  assert(brickwright_virtual_hci_feed(&controller, ltk_reply,
                                      sizeof(ltk_reply)) == 0);
  assert(!controller.ltk_request_pending);
  assert(output_length == 16 && output[1] == 0x0e && output[10] == 0x08 &&
         output[15] == 1);
  output_length = 0;
  assert(brickwright_virtual_hci_disconnect(&controller, 0x13) == 0);
  assert(!controller.connected);
  assert(output_length == 7 && output[1] == 0x05 && output[6] == 0x13);

  output_length = 0;
  const uint8_t page_scan[] = {0x01, 0x1a, 0x0c, 0x01, 0x02};
  assert(brickwright_virtual_hci_feed(&controller, page_scan,
                                      sizeof(page_scan)) == 0);
  assert(controller.classic_connectable);
  assert(brickwright_virtual_hci_classic_connection_request(&controller,
                                                             peer) == 0);
  const uint8_t accept[] = {
    0x01, 0x09, 0x04, 0x07, 1, 2, 3, 4, 5, 6, 0
  };
  assert(brickwright_virtual_hci_feed(&controller, accept, sizeof(accept)) == 0);
  assert(controller.connected && controller.classic_connection);
  assert(brickwright_virtual_hci_feed(NULL, commands, sizeof(commands)) ==
         -EINVAL);
  return 0;
}
