/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <string.h>

#include <brickwright/ehcill.h>

static int write_control(struct brickwright_ehcill *ehcill, uint8_t control)
{
  return ehcill->write(&control, 1, ehcill->context);
}

static int wake(struct brickwright_ehcill *ehcill)
{
  if (!ehcill->pending_length) {
    ehcill->state = BRICKWRIGHT_EHCILL_AWAKE;
    return 0;
  }
  int result = ehcill->write(ehcill->pending, ehcill->pending_length,
                             ehcill->context);
  if (!result) {
    ehcill->pending_length = 0;
    ehcill->state = BRICKWRIGHT_EHCILL_AWAKE;
  }
  return result;
}

void brickwright_ehcill_init(struct brickwright_ehcill *ehcill,
                             struct brickwright_h4 *h4,
                             brickwright_ehcill_write_cb write,
                             void *context)
{
  memset(ehcill, 0, sizeof(*ehcill));
  ehcill->state = BRICKWRIGHT_EHCILL_AWAKE;
  ehcill->h4 = h4;
  ehcill->write = write;
  ehcill->context = context;
}

int brickwright_ehcill_feed(struct brickwright_ehcill *ehcill,
                            const void *data, size_t length)
{
  if (!ehcill || (!data && length) || !ehcill->h4 || !ehcill->write)
    return -EINVAL;
  const uint8_t *bytes = data;
  for (size_t index = 0; index < length; ++index) {
    uint8_t value = bytes[index];
    if (!ehcill->h4->type && value >= BRICKWRIGHT_EHCILL_SLEEP_IND &&
        value <= BRICKWRIGHT_EHCILL_WAKE_ACK) {
      int result = 0;
      switch (value) {
      case BRICKWRIGHT_EHCILL_SLEEP_IND:
        if (ehcill->state == BRICKWRIGHT_EHCILL_WAKING)
          return -EPROTO;
        result = write_control(ehcill, BRICKWRIGHT_EHCILL_SLEEP_ACK);
        if (!result)
          ehcill->state = BRICKWRIGHT_EHCILL_ASLEEP;
        break;
      case BRICKWRIGHT_EHCILL_SLEEP_ACK:
        /* This host never initiates sleep, so an ACK cannot match a request. */
        return -EPROTO;
      case BRICKWRIGHT_EHCILL_WAKE_IND:
        result = write_control(ehcill, BRICKWRIGHT_EHCILL_WAKE_ACK);
        if (!result)
          result = wake(ehcill);
        break;
      case BRICKWRIGHT_EHCILL_WAKE_ACK:
        if (ehcill->state == BRICKWRIGHT_EHCILL_AWAKE)
          break; /* A delayed duplicate ACK is harmless. */
        if (ehcill->state != BRICKWRIGHT_EHCILL_WAKING)
          return -EPROTO;
        result = wake(ehcill);
        break;
      }
      if (result)
        return result;
      continue;
    }
    int result = brickwright_h4_feed(ehcill->h4, &value, 1);
    if (result)
      return result;
  }
  return 0;
}

int brickwright_ehcill_send(struct brickwright_ehcill *ehcill,
                            const void *frame, size_t length)
{
  if (!ehcill || (!frame && length) || !length || !ehcill->write)
    return -EINVAL;
  if (ehcill->state == BRICKWRIGHT_EHCILL_AWAKE)
    return ehcill->write(frame, length, ehcill->context);
  if (length > sizeof(ehcill->pending) - ehcill->pending_length)
    return -ENOBUFS;
  memcpy(ehcill->pending + ehcill->pending_length, frame, length);
  ehcill->pending_length += length;
  if (ehcill->state == BRICKWRIGHT_EHCILL_ASLEEP) {
    int result = write_control(ehcill, BRICKWRIGHT_EHCILL_WAKE_IND);
    if (result) {
      ehcill->pending_length -= length;
      return result;
    }
    ehcill->state = BRICKWRIGHT_EHCILL_WAKING;
  }
  return 0;
}

bool brickwright_ehcill_awake(const struct brickwright_ehcill *ehcill)
{
  return ehcill && ehcill->state == BRICKWRIGHT_EHCILL_AWAKE;
}

void brickwright_ehcill_abort(struct brickwright_ehcill *ehcill)
{
  if (!ehcill)
    return;
  ehcill->pending_length = 0;
  ehcill->state = BRICKWRIGHT_EHCILL_ASLEEP;
}
