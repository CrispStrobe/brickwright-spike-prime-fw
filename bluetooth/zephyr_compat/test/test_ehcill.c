/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <string.h>

#include <brickwright/ehcill.h>

static uint8_t written[64];
static size_t written_length;
static unsigned int packets;

static int write_bytes(const uint8_t *data, size_t length, void *context)
{
  assert(context == written);
  assert(written_length + length <= sizeof(written));
  memcpy(written + written_length, data, length);
  written_length += length;
  return 0;
}

static int receive(uint8_t type, const uint8_t *packet, size_t length,
                   void *context)
{
  assert(context == &packets);
  assert(type == 0x04 && length == 4);
  /* A control-byte value inside an H4 payload is data, not eHCILL. */
  assert(!memcmp(packet, (uint8_t[]){0x0e, 0x02, 0x30, 0x00}, 4));
  ++packets;
  return 0;
}

int main(void)
{
  struct brickwright_h4 h4;
  struct brickwright_ehcill ehcill;
  brickwright_h4_init(&h4, receive, &packets);
  brickwright_ehcill_init(&ehcill, &h4, write_bytes, written);
  assert(brickwright_ehcill_awake(&ehcill));

  /* H4 may be arbitrarily fragmented and adjacent to control octets. */
  const uint8_t first[] = {0x04, 0x0e};
  const uint8_t second[] = {0x02, 0x30, 0x00, BRICKWRIGHT_EHCILL_SLEEP_IND};
  assert(brickwright_ehcill_feed(&ehcill, first, sizeof(first)) == 0);
  assert(brickwright_ehcill_feed(&ehcill, second, sizeof(second)) == 0);
  assert(packets == 1 && !brickwright_ehcill_awake(&ehcill));
  assert(written_length == 1 && written[0] == BRICKWRIGHT_EHCILL_SLEEP_ACK);

  /* A sleeping controller is woken and the frame retained until its ACK. */
  const uint8_t command[] = {0x01, 0x03, 0x0c, 0x00};
  assert(brickwright_ehcill_send(&ehcill, command, sizeof(command)) == 0);
  assert(written[1] == BRICKWRIGHT_EHCILL_WAKE_IND);
  assert(brickwright_ehcill_send(&ehcill, command, sizeof(command)) == 0);
  uint8_t wake_ack = BRICKWRIGHT_EHCILL_WAKE_ACK;
  assert(brickwright_ehcill_feed(&ehcill, &wake_ack, 1) == 0);
  assert(brickwright_ehcill_awake(&ehcill));
  assert(written_length == 2 + 2 * sizeof(command));
  assert(!memcmp(written + 2, command, sizeof(command)));
  assert(!memcmp(written + 2 + sizeof(command), command, sizeof(command)));

  /* Controller-initiated wake is acknowledged, including a wake collision. */
  uint8_t sleep = BRICKWRIGHT_EHCILL_SLEEP_IND;
  uint8_t wake = BRICKWRIGHT_EHCILL_WAKE_IND;
  assert(brickwright_ehcill_feed(&ehcill, &sleep, 1) == 0);
  assert(brickwright_ehcill_feed(&ehcill, &wake, 1) == 0);
  assert(brickwright_ehcill_awake(&ehcill));
  assert(written[written_length - 1] == BRICKWRIGHT_EHCILL_WAKE_ACK);

  /* ACKs which cannot match a host request are rejected for recovery. */
  uint8_t sleep_ack = BRICKWRIGHT_EHCILL_SLEEP_ACK;
  assert(brickwright_ehcill_feed(&ehcill, &sleep_ack, 1) == -EPROTO);
  assert(brickwright_ehcill_awake(&ehcill));
  /* Delayed duplicate wake acknowledgements remain idempotent. */
  assert(brickwright_ehcill_feed(&ehcill, &wake_ack, 1) == 0);

  assert(brickwright_ehcill_feed(&ehcill, &sleep, 1) == 0);
  assert(brickwright_ehcill_send(&ehcill, command, sizeof(command)) == 0);
  assert(brickwright_ehcill_feed(&ehcill, &sleep, 1) == -EPROTO);
  assert(ehcill.state == BRICKWRIGHT_EHCILL_WAKING);
  brickwright_ehcill_abort(&ehcill);
  assert(ehcill.pending_length == 0 && !brickwright_ehcill_awake(&ehcill));
  assert(brickwright_ehcill_feed(NULL, &wake, 1) == -EINVAL);
  assert(brickwright_ehcill_send(&ehcill, NULL, 1) == -EINVAL);
  return 0;
}
