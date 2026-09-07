/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <zephyr/net_buf.h>

int main(void)
{
  NET_BUF_SIMPLE_DEFINE(buffer, 32);
  struct net_buf_simple clone;
  const uint8_t payload[] = {0xaa, 0xbb, 0xcc};

  net_buf_simple_init(&buffer, 4);
  assert(net_buf_simple_headroom(&buffer) == 4);
  net_buf_simple_add_u8(&buffer, 0x12);
  net_buf_simple_add_le16(&buffer, 0x3456);
  net_buf_simple_add_be32(&buffer, UINT32_C(0x789abcde));
  net_buf_simple_add_mem(&buffer, payload, sizeof(payload));
  assert(buffer.len == 10);

  net_buf_simple_clone(&buffer, &clone);
  assert(net_buf_simple_pull_u8(&clone) == 0x12);
  assert(net_buf_simple_pull_le16(&clone) == 0x3456);
  assert(net_buf_simple_pull_be32(&clone) == UINT32_C(0x789abcde));
  assert(memcmp(net_buf_simple_pull_mem(&clone, sizeof(payload)), payload,
                sizeof(payload)) == 0);
  assert(clone.len == 0);
  assert(buffer.len == 10);

  net_buf_simple_reset(&buffer);
  assert(buffer.len == 0);
  assert(net_buf_simple_headroom(&buffer) == 0);
  net_buf_simple_add_be64(&buffer, UINT64_C(0x0123456789abcdef));
  assert(net_buf_simple_remove_be64(&buffer) == UINT64_C(0x0123456789abcdef));
  return 0;
}
