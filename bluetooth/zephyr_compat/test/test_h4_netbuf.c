/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <brickwright/h4.h>
#include <brickwright/h4_netbuf.h>
#include <zephyr/bluetooth/hci.h>
static unsigned int delivered;
static int deliver(struct net_buf *buffer, void *context)
{
  const uint8_t *expected = context;
  assert(buffer->len == 5);
  assert(buffer->data[0] == BT_HCI_H4_EVT);
  assert(!memcmp(buffer->data + 1, expected, 4));
  ++delivered;
  net_buf_unref(buffer);
  return 0;
}
int main(void)
{
  const uint8_t event[] = {0x0e, 0x02, 0x01, 0x00};
  struct brickwright_h4_netbuf bridge = {
    .receive = deliver, .context = (void *)event
  };
  struct brickwright_h4 h4;
  brickwright_h4_init(&h4, brickwright_h4_netbuf_receive, &bridge);
  const uint8_t frame[] = {BT_HCI_H4_EVT, 0x0e, 0x02, 0x01, 0x00};
  assert(brickwright_h4_feed(&h4, frame, sizeof(frame)) == 0);
  assert(delivered == 1);
  assert(brickwright_h4_netbuf_receive(BT_HCI_H4_SCO, event, sizeof(event),
                                       &bridge) == -ENOTSUP);
  assert(brickwright_h4_netbuf_receive(BT_HCI_H4_EVT, event, 1, &bridge) == -EPROTO);
  return 0;
}
