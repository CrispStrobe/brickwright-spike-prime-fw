/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <brickwright/h4_netbuf.h>
#include <zephyr/bluetooth/buf.h>
#include <zephyr/bluetooth/hci.h>
int brickwright_h4_netbuf_receive(uint8_t type, const uint8_t *packet,
                                  size_t length, void *opaque)
{
  struct brickwright_h4_netbuf *bridge = opaque;
  if (!bridge || !bridge->receive || !packet || !length) return -EINVAL;
  struct net_buf *buffer;
  if (type == BT_HCI_H4_EVT) {
    if (length < sizeof(struct bt_hci_evt_hdr)) return -EPROTO;
    buffer = bt_buf_get_evt(packet[0], false, bridge->allocation_timeout);
  } else if (type == BT_HCI_H4_ACL) {
    if (length < sizeof(struct bt_hci_acl_hdr)) return -EPROTO;
    buffer = bt_buf_get_rx(BT_BUF_ACL_IN, bridge->allocation_timeout);
  } else {
    return -ENOTSUP;
  }
  if (!buffer) return -ENOMEM;
  if (net_buf_tailroom(buffer) < length) {
    net_buf_unref(buffer);
    return -EMSGSIZE;
  }
  net_buf_add_mem(buffer, packet, length);
  int result = bridge->receive(buffer, bridge->context);
  if (result) net_buf_unref(buffer);
  return result;
}
