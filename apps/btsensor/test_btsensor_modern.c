/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_modern.h"
#include "spike_codec.h"

#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

struct fixture
{
  uint8_t message[1100];
  size_t length;
  bool high;
  struct btsensor_modern_operation operation;
  uint8_t opaque[1100];
  unsigned operations;
  uint16_t interval;
};

static int capture_send(const uint8_t *message, size_t length, bool high,
                        void *context)
{
  struct fixture *f = context;
  assert(length <= sizeof(f->message));
  memcpy(f->message, message, length);
  f->length = length;
  f->high = high;
  return 0;
}

static int capture_operation(const struct btsensor_modern_operation *operation,
                             void *context)
{
  struct fixture *f = context;
  f->operation = *operation;
  if (operation->kind == BTSENSOR_MODERN_OP_TUNNEL_OPAQUE)
    {
      memcpy(f->opaque, operation->opaque, operation->opaque_length);
      f->operation.opaque = f->opaque;
    }
  f->operations++;
  return 0;
}

static int capture_interval(uint16_t interval, void *context)
{
  ((struct fixture *)context)->interval = interval;
  return 0;
}

static int feed_frame_message(const uint8_t *payload, size_t length, bool high,
                              void *context)
{
  return btsensor_modern_receive(context, payload, length, high);
}

static void tunnel(uint8_t *out, size_t *length, const char *text)
{
  size_t n = strlen(text);
  out[0] = 0x32;
  out[1] = (uint8_t)n;
  out[2] = (uint8_t)(n >> 8);
  memcpy(out + 3, text, n);
  *length = n + 3;
}

static void assert_opaque(struct btsensor_modern *service, struct fixture *f,
                          uint8_t *message, const char *text)
{
  size_t length;
  tunnel(message, &length, text);
  assert(btsensor_modern_receive(service, message, length, false) == 0);
  assert(f->operation.kind == BTSENSOR_MODERN_OP_TUNNEL_OPAQUE);
  assert(f->operation.opaque_length == strlen(text));
}

int main(void)
{
  struct fixture f = {0};
  struct btsensor_modern service;
  const struct btsensor_modern_config config = {
    .rpc_major = 1, .rpc_minor = 4, .rpc_build = 0x1234,
    .firmware_major = 0, .firmware_minor = 1, .firmware_build = 7,
    .product_group_device = 0x0080,
  };
  btsensor_modern_init(&service, &config, capture_send, capture_operation,
                        capture_interval, &f);

  const uint8_t info[] = {0};
  assert(btsensor_modern_receive(&service, info, sizeof(info), true) == 0);
  const uint8_t expected_info[] = {
    1, 1, 4, 0x34, 0x12, 0, 1, 7, 0,
    20, 0, 0, 4, 0, 2, 0x80, 0,
  };
  assert(f.high && f.length == sizeof(expected_info));
  assert(memcmp(f.message, expected_info, sizeof(expected_info)) == 0);

  const uint8_t subscribe[] = {0x28, 100, 0};
  assert(btsensor_modern_receive(&service, subscribe, sizeof(subscribe),
                                  false) == 0);
  assert(f.interval == 100 && service.notification_interval_ms == 100);
  assert(f.length == 2 && f.message[0] == 0x29 && f.message[1] == 0);

  const uint8_t records[] = {0, 81, 0x0d, 2, 0xff, 0xff};
  assert(btsensor_modern_notify(&service, records, sizeof(records), false) == 0);
  assert(f.length == sizeof(records) + 3 && f.message[0] == 0x3c);
  assert(f.message[1] == sizeof(records) && f.message[2] == 0);
  assert(memcmp(f.message + 3, records, sizeof(records)) == 0);
  const uint8_t bad_record[] = {0x0d, 6, 0, 0};
  assert(btsensor_modern_notify(&service, bad_record, sizeof(bad_record),
                                 false) == -ERANGE);
  assert(btsensor_modern_notify(&service, records, sizeof(records) - 1,
                                 false) == -EPROTO);

  uint8_t message[1100];
  size_t length;
  tunnel(message, &length,
         "{\"m\":\"motor\",\"p\":{\"port\":5,\"speed\":-75}}" );
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MOTOR);
  assert(f.operation.port == 5 && f.operation.speed == -75);
  assert(!f.operation.has_end_state);

  tunnel(message, &length,
         "{\"m\":\"motor\",\"p\":{\"port\":0,\"speed\":0,\"end_state\":2}}" );
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MOTOR);
  assert(f.operation.has_end_state && f.operation.end_state == 2);

  tunnel(message, &length,
         "{\"m\":\"display_3x3\",\"p\":{\"port\":2,\"data\":[0,0,0,0,153,0,0,0,0]}}" );
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MATRIX3);
  assert(f.operation.port == 2 && f.operation.pixels[4] == 153);

  /* Exact current-firmware streaming strings emitted by the authoritative
   * extension become finite operations, never interpreted Python. */
  tunnel(message, &length,
         "import motor\nfrom hub import port\nmotor.run(port.F, -750)");
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MOTOR);
  assert(f.operation.port == 5 && f.operation.speed == -75);
  assert(!f.operation.has_end_state);

  tunnel(message, &length,
         "import motor\nfrom hub import port\nmotor.stop(port.A)");
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MOTOR);
  assert(f.operation.port == 0 && f.operation.speed == 0);
  assert(f.operation.has_end_state && f.operation.end_state == 0);

  tunnel(message, &length,
         "from hub import light_matrix\nlight_matrix.set_pixel(4, 3, 100)");
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MATRIX5_PIXEL);
  assert(f.operation.x == 4 && f.operation.y == 3 &&
         f.operation.brightness == 100);

  tunnel(message, &length,
         "from hub import light_matrix\nlight_matrix.clear()");
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MATRIX5_CLEAR);

  tunnel(message, &length,
         "from hub import sound\nsound.beep(440, 250, 100)");
  assert(btsensor_modern_receive(&service, message, length, false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_SOUND_BEEP);
  assert(f.operation.frequency_hz == 440 && f.operation.duration_ms == 250);

  /* Method-like text and fields below the expected object levels must never
   * become physical operations. Unknown and duplicate fields fail closed to
   * the opaque tunnel handler. */
  assert_opaque(&service, &f, message,
                "{\"note\":\"\\\"m\\\":\\\"motor\\\"\",\"p\":{\"port\":0,\"speed\":99}}");
  assert_opaque(&service, &f, message,
                "{\"wrapper\":{\"m\":\"motor\",\"p\":{\"port\":0,\"speed\":99}}}");
  assert_opaque(&service, &f, message,
                "{\"m\":\"motor\",\"p\":{\"nested\":{\"port\":0,\"speed\":99}}}");
  assert_opaque(&service, &f, message,
                "{\"m\":\"motor\",\"m\":\"motor\",\"p\":{\"port\":0,\"speed\":99}}");
  assert_opaque(&service, &f, message,
                "{\"m\":\"motor\",\"p\":{\"port\":0,\"speed\":99,\"extra\":1}}");
  assert_opaque(&service, &f, message,
                "{\"m\":\"motor\",\"p\":{\"port\":0,\"speed\":99,}}");
  assert_opaque(&service, &f, message,
                "{\"m\":\"motor\",\"p\":{\"port\":0,\"speed\":99},}");

  assert_opaque(&service, &f, message,
                " { \"p\" : { \"speed\" : 25, \"port\" : 1 }, \"m\" : \"motor\" } " );

  /* Near misses and injection suffixes remain inert opaque bytes. */
  assert_opaque(&service, &f, message,
                "import motor\nfrom hub import port\nmotor.run(port.A, 750)\nprint('x')");
  assert_opaque(&service, &f, message,
                "import motor\nfrom hub import port\nmotor.run(port.A, 751)");
  assert_opaque(&service, &f, message,
                "import motor\nfrom hub import port\nmotor.stop(port.A, port.B)");
  assert_opaque(&service, &f, message,
                "from hub import light_matrix\nlight_matrix.clear();print('x')");
  assert_opaque(&service, &f, message,
                "from hub import light_matrix\nlight_matrix.set_pixel(1,1,100)");
  assert_opaque(&service, &f, message,
                "from hub import light_matrix\nlight_matrix.show_image(1)");
  assert_opaque(&service, &f, message,
                "from hub import sound\nsound.beep(440,250,100)");
  assert_opaque(&service, &f, message,
                "from hub import sound\nsound.beep(440, 250, 99)");

  tunnel(message, &length,
         "from hub import sound\nsound.beep(99, 250, 100)");
  assert(btsensor_modern_receive(&service, message, length, false) == -ERANGE);

  tunnel(message, &length,
         "from hub import light_matrix\nlight_matrix.set_pixel(5, 0, 100)");
  assert(btsensor_modern_receive(&service, message, length, false) == -ERANGE);

  const uint8_t python[] = "from hub import port";
  message[0] = 0x32;
  message[1] = sizeof(python) - 1;
  message[2] = 0;
  memcpy(message + 3, python, sizeof(python) - 1);
  assert(btsensor_modern_receive(&service, message, sizeof(python) + 2,
                                  false) == 0);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_TUNNEL_OPAQUE);
  assert(f.operation.opaque_length == sizeof(python) - 1);
  assert(memcmp(f.operation.opaque, python, sizeof(python) - 1) == 0);

  tunnel(message, &length,
         "{\"m\":\"motor\",\"p\":{\"port\":6,\"speed\":10}}" );
  assert(btsensor_modern_receive(&service, message, length, false) == -ERANGE);
  message[1]++;
  assert(btsensor_modern_receive(&service, message, length, false) == -EPROTO);

  /* Prove a fragmented high-priority COBS frame reaches this dispatcher and
   * that the response retains the priority tag. */
  uint8_t frame[64];
  size_t frame_length;
  struct bw_spike_stream stream = {0};
  assert(bw_spike_pack(info, sizeof(info), true, frame, sizeof(frame),
                        &frame_length) == BW_CODEC_OK);
  assert(bw_spike_stream_feed(&stream, frame, 2, feed_frame_message,
                               &service) == BW_CODEC_OK);
  assert(bw_spike_stream_feed(&stream, frame + 2, frame_length - 2,
                               feed_frame_message, &service) == BW_CODEC_OK);
  assert(f.high && f.message[0] == 1);

  puts("modern BLE service: all tests passed");
  return 0;
}
