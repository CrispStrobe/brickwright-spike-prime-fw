/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#include <zephyr/bluetooth/uuid.h>

int main(void)
{
  struct bt_uuid_any uuid;
  char text[BT_UUID_STR_LEN];

  assert(bt_uuid_from_str("fd02", &uuid) == 0);
  assert(uuid.uuid.type == BT_UUID_TYPE_16);
  assert(BT_UUID_16(&uuid.uuid)->val == 0xfd02);
  bt_uuid_to_str(&uuid.uuid, text, sizeof(text));
  assert(strcmp(text, "fd02") == 0);

  assert(bt_uuid_from_str("0000fd02-0000-1000-8000-00805f9b34fb", &uuid) == 0);
  assert(uuid.uuid.type == BT_UUID_TYPE_128);
  bt_uuid_to_str(&uuid.uuid, text, sizeof(text));
  assert(strcmp(text, "0000fd02-0000-1000-8000-00805f9b34fb") == 0);
  return 0;
}
