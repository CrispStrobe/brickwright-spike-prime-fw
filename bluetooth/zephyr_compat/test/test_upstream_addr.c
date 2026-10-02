/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <zephyr/bluetooth/addr.h>

int bt_rand(void *buffer, size_t length)
{
  memset(buffer, 0x55, length);
  return 0;
}

int main(void)
{
  bt_addr_t address;
  bt_addr_le_t le;

  assert(bt_addr_from_str("01:23:45:67:89:ab", &address) == 0);
  assert(address.val[0] == 0xab && address.val[5] == 0x01);
  assert(bt_addr_from_str("01-23-45-67-89-ab", &address) == -EINVAL);
  assert(bt_addr_le_from_str("01:23:45:67:89:ab", "random", &le) == 0);
  assert(le.type == BT_ADDR_LE_RANDOM);
  assert(bt_addr_le_create_static(&le) == 0);
  assert(BT_ADDR_IS_STATIC(&le.a));
  assert(bt_addr_le_create_nrpa(&le) == 0);
  assert(BT_ADDR_IS_NRPA(&le.a));
  return 0;
}
