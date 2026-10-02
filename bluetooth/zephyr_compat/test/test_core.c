/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/crc.h>
#include <zephyr/sys/math_extras.h>
#include <zephyr/sys/slist.h>
#include <zephyr/sys/util.h>
#include <zephyr/sys/uuid.h>

struct item { int value; sys_snode_t node; };

int main(void)
{
  atomic_t flags = 0;
  assert(atomic_inc(&flags) == 0);
  assert(atomic_get(&flags) == 1);
  assert(!atomic_test_and_set_bit(&flags, 3));
  assert(atomic_test_bit(&flags, 3));
  assert(atomic_test_and_clear_bit(&flags, 3));
  assert(atomic_cas(&flags, 1, 7));

  int first = 1, second = 2;
  atomic_ptr_t pointer = &first;
  assert(atomic_ptr_cas(&pointer, &first, &second));
  assert(atomic_ptr_get(&pointer) == &second);

  sys_slist_t list = SYS_SLIST_STATIC_INIT(&list);
  struct item a = { .value = 1 }, b = { .value = 2 }, c = { .value = 3 };
  sys_slist_append(&list, &a.node);
  sys_slist_append(&list, &b.node);
  sys_slist_insert(&list, &a.node, &c.node);
  assert(sys_slist_peek_head(&list) == &a.node);
  assert(sys_slist_peek_tail(&list) == &b.node);
  assert(sys_slist_find_and_remove(&list, &c.node));
  assert(sys_slist_get(&list) == &a.node);
  assert(sys_slist_get(&list) == &b.node);
  assert(sys_slist_is_empty(&list));

  uint8_t bytes[8];
  sys_put_le64(UINT64_C(0x0123456789abcdef), bytes);
  assert(sys_get_le64(bytes) == UINT64_C(0x0123456789abcdef));
  sys_put_be32(UINT32_C(0x12345678), bytes);
  assert(sys_get_be32(bytes) == UINT32_C(0x12345678));
  const uint8_t forward[] = {1, 2, 3, 4, 5};
  uint8_t reversed[sizeof(forward)];
  sys_memcpy_swap(reversed, forward, sizeof(forward));
  assert(!memcmp(reversed, (uint8_t[]){5, 4, 3, 2, 1}, sizeof(reversed)));
  sys_mem_swap(reversed, sizeof(reversed));
  assert(!memcmp(reversed, forward, sizeof(forward)));

  char character = '\0';
  char decimal[4];
  assert(hex2char(0, &character) == 0 && character == '0');
  assert(hex2char(15, &character) == 0 && character == 'f');
  assert(hex2char(16, &character) == -EINVAL);
  assert(hex2char(1, NULL) == -EINVAL);
  assert(u8_to_dec(decimal, sizeof(decimal), 0) == 1);
  assert(strcmp(decimal, "0") == 0);
  assert(u8_to_dec(decimal, sizeof(decimal), 255) == 3);
  assert(strcmp(decimal, "255") == 0);
  assert(u8_to_dec(decimal, 3, 255) == -ENOMEM);
  assert(u8_to_dec(NULL, sizeof(decimal), 1) == -ENOMEM);

  const uint8_t same_a[] = {1, 2, 3, 4};
  const uint8_t same_b[] = {1, 2, 3, 4};
  const uint8_t different[] = {1, 2, 3, 5};
  assert(util_memeq(same_a, same_b, sizeof(same_a)));
  assert(!util_memeq(same_a, different, sizeof(same_a)));
  assert(util_memeq(same_a, different, 0));
  uint8_t xor_result[16];
  const uint8_t xor_first[16] = {0xff, 0x55};
  const uint8_t xor_second[16] = {0x0f, 0xaa};
  mem_xor_128(xor_result, xor_first, xor_second);
  assert(xor_result[0] == 0xf0 && xor_result[1] == 0xff);
  for (size_t i = 2; i < sizeof(xor_result); ++i)
    {
      assert(xor_result[i] == 0);
    }

  uint16_t sum = 0;
  assert(!u16_add_overflow(1, 2, &sum) && sum == 3);
  assert(u16_add_overflow(UINT16_MAX, 1, &sum) && sum == 0);
  const uint8_t crc_data[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  assert(crc16_reflect(0xa001, 0xffff, crc_data, sizeof(crc_data)) == 0x4b37);

  struct uuid uuid;
  char uuid_text[UUID_STR_LEN];
  assert(uuid_from_string("0000fd02-0000-1000-8000-00805f9b34fb", &uuid) == 0);
  assert(uuid_to_string(&uuid, uuid_text) == 0);
  assert(strcmp(uuid_text, "0000fd02-0000-1000-8000-00805f9b34fb") == 0);

  puts("Zephyr compatibility core: passed");
  return 0;
}
