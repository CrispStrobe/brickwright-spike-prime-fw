/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <brickwright/h4.h>
static unsigned int packets;
static int receive(uint8_t type, const uint8_t *packet, size_t length, void *context)
{
  const uint8_t *expected = context;
  assert(type == expected[0]);
  assert(length == expected[2]);
  assert(memcmp(packet, expected + 3, length) == 0);
  ++packets;
  return 0;
}
int main(void)
{
  const uint8_t expected[] = {0x04, 0, 4, 0x0e, 0x02, 0x01, 0x00};
  struct brickwright_h4 h4;
  brickwright_h4_init(&h4, receive, (void *)expected);
  const uint8_t part1[] = {0x04, 0x0e};
  const uint8_t part2[] = {0x02, 0x01, 0x00};
  assert(brickwright_h4_feed(&h4, part1, sizeof(part1)) == 0 && packets == 0);
  assert(brickwright_h4_feed(&h4, part2, sizeof(part2)) == 0 && packets == 1);
  const uint8_t two[] = {0x04, 0x0e, 0x02, 0x01, 0x00,
                         0x04, 0x0e, 0x02, 0x01, 0x00};
  assert(brickwright_h4_feed(&h4, two, sizeof(two)) == 0 && packets == 3);
  const uint8_t bad = 0xff;
  assert(brickwright_h4_feed(&h4, &bad, 1) == -EPROTO);
  const uint8_t huge[] = {0x02, 0, 0, 0xff, 0xff};
  assert(brickwright_h4_feed(&h4, huge, sizeof(huge)) == -EMSGSIZE);
  assert(brickwright_h4_feed(NULL, &bad, 1) == -EINVAL);
  return 0;
}
