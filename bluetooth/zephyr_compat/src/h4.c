/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <string.h>
#include <brickwright/h4.h>

static uint8_t header_length(uint8_t type)
{
  switch (type) {
    case 0x01: return 3; /* Command */
    case 0x04: return 2; /* Event */
    case 0x02: return 4; /* ACL */
    case 0x03: return 3; /* SCO */
    default: return 0;
  }
}
static size_t payload_length(const struct brickwright_h4 *h4)
{
  if (h4->type == 0x01) return h4->packet[2];
  if (h4->type == 0x04) return h4->packet[1];
  if (h4->type == 0x02) return h4->packet[2] | ((size_t)h4->packet[3] << 8);
  return h4->packet[2];
}
static void reset(struct brickwright_h4 *h4)
{
  h4->type = 0;
  h4->header_length = 0;
  h4->used = 0;
  h4->expected = 0;
}
void brickwright_h4_init(struct brickwright_h4 *h4,
                         brickwright_h4_packet_cb receive, void *context)
{
  memset(h4, 0, sizeof(*h4));
  h4->receive = receive;
  h4->context = context;
}
int brickwright_h4_feed(struct brickwright_h4 *h4, const void *data, size_t length)
{
  if (!h4 || (!data && length) || !h4->receive) return -EINVAL;
  const uint8_t *bytes = data;
  for (size_t i = 0; i < length; ++i) {
    if (!h4->type) {
      h4->header_length = header_length(bytes[i]);
      if (!h4->header_length) return -EPROTO;
      h4->type = bytes[i];
      continue;
    }
    h4->packet[h4->used++] = bytes[i];
    if (!h4->expected && h4->used == h4->header_length) {
      h4->expected = h4->header_length + payload_length(h4);
      if (h4->expected > sizeof(h4->packet)) { reset(h4); return -EMSGSIZE; }
    }
    if (h4->expected && h4->used == h4->expected) {
      int result = h4->receive(h4->type, h4->packet, h4->used, h4->context);
      reset(h4);
      if (result) return result;
    }
  }
  return 0;
}
