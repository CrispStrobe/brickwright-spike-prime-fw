/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdint.h>
#include <zephyr/bluetooth/buf.h>
#include <zephyr/bluetooth/hci.h>

static enum bt_buf_type freed_mask;

static void on_freed(enum bt_buf_type mask)
{
  freed_mask = mask;
}

int main(void)
{
  bt_buf_rx_freed_cb_set(on_freed);
  struct net_buf *event = bt_buf_get_rx(BT_BUF_EVT, K_NO_WAIT);
  assert(event);
  assert(net_buf_pull_u8(event) == BT_HCI_H4_EVT);
  net_buf_add_u8(event, BT_HCI_EVT_VENDOR);
  net_buf_unref(event);
  assert((freed_mask & BT_BUF_EVT) != 0);

  struct net_buf *acl = bt_buf_get_rx(BT_BUF_ACL_IN, K_NO_WAIT);
  assert(acl);
  assert(net_buf_pull_u8(acl) == BT_HCI_H4_ACL);
  net_buf_unref(acl);
  assert((freed_mask & BT_BUF_ACL_IN) != 0);

  struct net_buf *sync = bt_buf_get_evt(BT_HCI_EVT_CMD_COMPLETE, false,
                                        K_NO_WAIT);
  assert(sync);
  assert(net_buf_pull_u8(sync) == BT_HCI_H4_EVT);
  net_buf_unref(sync);

  struct net_buf *discardable = bt_buf_get_evt(BT_HCI_EVT_LE_META_EVENT, true,
                                               K_NO_WAIT);
  assert(discardable);
  net_buf_unref(discardable);
  bt_buf_rx_freed_cb_set(NULL);
  return 0;
}
