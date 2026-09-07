/* SPDX-License-Identifier: MIT */

#include "ti_bts_loader.h"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

struct fixture_transport
{
  uint8_t sent[32];
  size_t sent_length;
  uint8_t event[16];
  size_t event_length;
  uint32_t timeout_ms;
  uint32_t delay_ms;
};

static int send_command(void *context, const uint8_t *command, size_t length)
{
  struct fixture_transport *fixture = context;
  assert(length <= sizeof(fixture->sent));
  memcpy(fixture->sent, command, length);
  fixture->sent_length = length;
  return 0;
}

static int receive_event(void *context, uint8_t *event, size_t capacity,
                         size_t *length, uint32_t timeout_ms)
{
  struct fixture_transport *fixture = context;
  assert(fixture->event_length <= capacity);
  memcpy(event, fixture->event, fixture->event_length);
  *length = fixture->event_length;
  fixture->timeout_ms = timeout_ms;
  return 0;
}

static int delay_ms(void *context, uint32_t duration_ms)
{
  ((struct fixture_transport *)context)->delay_ms = duration_ms;
  return 0;
}

static void put_le16(uint8_t *output, uint16_t value)
{
  output[0] = (uint8_t)value;
  output[1] = (uint8_t)(value >> 8);
}

static void put_le32(uint8_t *output, uint32_t value)
{
  output[0] = (uint8_t)value;
  output[1] = (uint8_t)(value >> 8);
  output[2] = (uint8_t)(value >> 16);
  output[3] = (uint8_t)(value >> 24);
}

static size_t action(uint8_t *image, size_t offset, uint16_t type,
                     const uint8_t *payload, uint16_t payload_size)
{
  put_le16(image + offset, type);
  put_le16(image + offset + 2, payload_size);
  memcpy(image + offset + 4, payload, payload_size);
  return offset + 4u + payload_size;
}

static size_t command_script(uint8_t *image, const uint8_t *command,
                             size_t command_length)
{
  uint8_t wait[] = {0, 0, 0, 0, 0, 0, 0, 0};
  size_t size = 32;
  memset(image, 0, 128);
  memcpy(image, "BTSB", 4);
  size = action(image, size, TI_BTS_ACTION_SEND_COMMAND, command,
                (uint16_t)command_length);
  put_le32(wait, 5000);
  size = action(image, size, TI_BTS_ACTION_WAIT_EVENT, wait, sizeof(wait));
  return size;
}

static struct ti_bts_transport callbacks(struct fixture_transport *fixture)
{
  struct ti_bts_transport result = {
    .send_command = send_command,
    .receive_event = receive_event,
    .delay_ms = delay_ms,
    .context = fixture,
  };
  return result;
}

static void test_complete_and_byte_preservation(void)
{
  const uint8_t command[] = {0x01, 0x0c, 0xfd, 0x02, 0xaa, 0x55};
  uint8_t image[128];
  size_t image_size = command_script(image, command, sizeof(command));
  struct fixture_transport fixture = {
    .event = {0x04, 0x0e, 0x04, 0x01, 0x0c, 0xfd, 0x00},
    .event_length = 7,
  };
  struct ti_bts_transport transport = callbacks(&fixture);
  struct ti_bts_report report;

  assert(ti_bts_execute(image, image_size, &transport, &report) == TI_BTS_OK);
  assert(fixture.sent_length == sizeof(command));
  assert(memcmp(fixture.sent, command, sizeof(command)) == 0);
  assert(fixture.timeout_ms == 5000);
  assert(report.actions == 2 && report.commands == 1);
}

static void test_command_status(void)
{
  const uint8_t command[] = {0x01, 0x34, 0x12, 0x00};
  uint8_t image[128];
  size_t image_size = command_script(image, command, sizeof(command));
  struct fixture_transport fixture = {
    .event = {0x04, 0x0f, 0x04, 0x00, 0x01, 0x34, 0x12},
    .event_length = 7,
  };
  struct ti_bts_transport transport = callbacks(&fixture);
  assert(ti_bts_execute(image, image_size, &transport, NULL) == TI_BTS_OK);
}

static void test_rejections(void)
{
  const uint8_t command[] = {0x01, 0x34, 0x12, 0x00};
  uint8_t image[128];
  size_t image_size = command_script(image, command, sizeof(command));
  struct fixture_transport fixture = {
    .event = {0x04, 0x0e, 0x04, 0x01, 0x34, 0x12, 0x01},
    .event_length = 7,
  };
  struct ti_bts_transport transport = callbacks(&fixture);
  assert(ti_bts_execute(image, image_size, &transport, NULL) ==
         TI_BTS_ERROR_HCI);

  fixture.event[4] = 0x35;
  fixture.event[6] = 0;
  assert(ti_bts_execute(image, image_size, &transport, NULL) ==
         TI_BTS_ERROR_HCI);

  image[image_size - 1] = 1; /* WAIT expected-data size no longer fits. */
  assert(ti_bts_execute(image, image_size, &transport, NULL) ==
         TI_BTS_ERROR_FORMAT);
  assert(ti_bts_execute(image, image_size - 1, &transport, NULL) ==
         TI_BTS_ERROR_FORMAT);
}

static void test_delay_and_unsupported(void)
{
  uint8_t image[128] = {0};
  uint8_t delay[4];
  size_t image_size = 32;
  struct fixture_transport fixture = {0};
  struct ti_bts_transport transport = callbacks(&fixture);
  memcpy(image, "BTSB", 4);
  put_le32(delay, 17);
  image_size = action(image, image_size, TI_BTS_ACTION_DELAY, delay, 4);
  assert(ti_bts_execute(image, image_size, &transport, NULL) == TI_BTS_OK);
  assert(fixture.delay_ms == 17);

  transport.delay_ms = NULL;
  assert(ti_bts_execute(image, image_size, &transport, NULL) ==
         TI_BTS_ERROR_UNSUPPORTED);
  image[32] = TI_BTS_ACTION_RUN_SCRIPT;
  assert(ti_bts_execute(image, image_size, &transport, NULL) ==
         TI_BTS_ERROR_UNSUPPORTED);
}

int main(void)
{
  test_complete_and_byte_preservation();
  test_command_status();
  test_rejections();
  test_delay_and_unsupported();
  return 0;
}
