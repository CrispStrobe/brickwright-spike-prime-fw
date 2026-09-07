/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_modern.h"

#include <errno.h>
#include <string.h>

#define MSG_INFO_REQUEST                 0x00
#define MSG_INFO_RESPONSE                0x01
#define MSG_DEVICE_NOTIFICATION_REQUEST  0x28
#define MSG_DEVICE_NOTIFICATION_RESPONSE 0x29
#define MSG_TUNNEL                       0x32
#define MSG_DEVICE_NOTIFICATION          0x3c

static void put_le16(uint8_t *out, uint16_t value)
{
  out[0] = (uint8_t)value;
  out[1] = (uint8_t)(value >> 8);
}

static int send_info(struct btsensor_modern *service, bool high)
{
  uint8_t out[17] = { MSG_INFO_RESPONSE };
  out[1] = service->config.rpc_major;
  out[2] = service->config.rpc_minor;
  put_le16(out + 3, service->config.rpc_build);
  out[5] = service->config.firmware_major;
  out[6] = service->config.firmware_minor;
  put_le16(out + 7, service->config.firmware_build);
  put_le16(out + 9, BTSENSOR_MODERN_MAX_PACKET);
  put_le16(out + 11, BTSENSOR_MODERN_MAX_MESSAGE);
  put_le16(out + 13, BTSENSOR_MODERN_MAX_CHUNK);
  put_le16(out + 15, service->config.product_group_device);
  return service->send(out, sizeof(out), high, service->context);
}

/* The direct extension emits three fixed, whitespace-free JSON shapes.  Match
 * that exact grammar; everything else stays opaque and can never become a
 * physical operation here.  This is both smaller and stricter than embedding
 * a general JSON parser in the size-constrained target. */
struct byte_cursor { const uint8_t *p; const uint8_t *end; };

static bool take_literal(struct byte_cursor *c, const char *literal)
{
  size_t length = strlen(literal);
  if ((size_t)(c->end - c->p) < length || memcmp(c->p, literal, length))
    return false;
  c->p += length;
  return true;
}

static bool take_integer(struct byte_cursor *c, int *result)
{
  unsigned value = 0;
  bool negative = false;
  const uint8_t *start = c->p;
  if (c->p < c->end && *c->p == '-') { negative = true; c->p++; }
  if (c->p == c->end || *c->p < '0' || *c->p > '9') return false;
  do
    {
      value = value * 10u + (unsigned)(*c->p++ - '0');
      if (value > 100000u) return false;
    }
  while (c->p < c->end && *c->p >= '0' && *c->p <= '9');
  if ((size_t)(c->p - start) > 1 && start[negative] == '0') return false;
  *result = negative ? -(int)value : (int)value;
  return true;
}

static int dispatch_tunnel(struct btsensor_modern *service,
                           const uint8_t *payload, size_t length)
{
  struct btsensor_modern_operation op = {0};
  struct byte_cursor c = { payload, payload + length };
  int value;

  if (!service->operation) return -ENOTSUP;
  if (length > BTSENSOR_MODERN_MAX_MESSAGE) return -EMSGSIZE;
  if (take_literal(&c, "{\"m\":\"motor\",\"p\":{\"port\":"))
    {
      if (!take_integer(&c, &value)) goto opaque;
      if (value < 0 || value > 5) return -ERANGE;
      op.kind = BTSENSOR_MODERN_OP_MOTOR;
      op.port = (uint8_t)value;
      if (!take_literal(&c, ",\"speed\":") || !take_integer(&c, &value))
        goto opaque;
      if (value < -100 || value > 100) return -ERANGE;
      op.speed = (int8_t)value;
      if (take_literal(&c, ",\"end_state\":"))
        {
          if (!take_integer(&c, &value)) goto opaque;
          if (value < 0 || value > 2) return -ERANGE;
          op.has_end_state = true;
          op.end_state = (uint8_t)value;
        }
      if (!take_literal(&c, "}}") || c.p != c.end) goto opaque;
    }
  else if (take_literal(&c,
            "{\"m\":\"display_3x3\",\"p\":{\"port\":"))
    {
      if (!take_integer(&c, &value)) goto opaque;
      if (value < 0 || value > 5) return -ERANGE;
      op.kind = BTSENSOR_MODERN_OP_MATRIX3;
      op.port = (uint8_t)value;
      if (!take_literal(&c, ",\"data\":[")) goto opaque;
      for (unsigned i = 0; i < 9; i++)
        {
          if (!take_integer(&c, &value)) goto opaque;
          if (value < 0 || value > 255) return -ERANGE;
          op.pixels[i] = (uint8_t)value;
          if (i != 8 && !take_literal(&c, ",")) goto opaque;
        }
      if (!take_literal(&c, "]}}") || c.p != c.end) goto opaque;
    }
  /* Current-firmware streaming blocks in legospikeprime_ble.js send these
   * exact Python strings.  They are recognized as a finite wire grammar;
   * no Python is parsed or executed.  Velocity 750 maps exactly to the
   * backend's 75 percent PWM command. */
  else if (take_literal(&c,
            "import motor\nfrom hub import port\nmotor.run(port."))
    {
      if (c.p == c.end || *c.p < 'A' || *c.p > 'F') goto opaque;
      op.kind = BTSENSOR_MODERN_OP_MOTOR;
      op.port = (uint8_t)(*c.p++ - 'A');
      if (take_literal(&c, ", 750)")) op.speed = 75;
      else if (take_literal(&c, ", -750)")) op.speed = -75;
      else goto opaque;
      if (c.p != c.end) goto opaque;
    }
  else if (take_literal(&c,
            "import motor\nfrom hub import port\nmotor.stop(port."))
    {
      if (c.p == c.end || *c.p < 'A' || *c.p > 'F') goto opaque;
      op.kind = BTSENSOR_MODERN_OP_MOTOR;
      op.port = (uint8_t)(*c.p++ - 'A');
      op.has_end_state = true;
      op.end_state = 0; /* The target's proven non-powered stop is coast. */
      if (!take_literal(&c, ")") || c.p != c.end) goto opaque;
    }
  else if (take_literal(&c,
            "from hub import light_matrix\nlight_matrix.set_pixel("))
    {
      op.kind = BTSENSOR_MODERN_OP_MATRIX5_PIXEL;
      if (!take_integer(&c, &value)) goto opaque;
      if (value < 0 || value > 4) return -ERANGE;
      op.x = (uint8_t)value;
      if (!take_literal(&c, ", ") || !take_integer(&c, &value)) goto opaque;
      if (value < 0 || value > 4) return -ERANGE;
      op.y = (uint8_t)value;
      if (!take_literal(&c, ", ") || !take_integer(&c, &value)) goto opaque;
      if (value < 0 || value > 100) return -ERANGE;
      op.brightness = (uint8_t)value;
      if (!take_literal(&c, ")") || c.p != c.end) goto opaque;
    }
  else if (take_literal(&c,
            "from hub import light_matrix\nlight_matrix.clear()") &&
           c.p == c.end)
    op.kind = BTSENSOR_MODERN_OP_MATRIX5_CLEAR;
  else if (take_literal(&c, "from hub import sound\nsound.beep("))
    {
      op.kind = BTSENSOR_MODERN_OP_SOUND_BEEP;
      if (!take_integer(&c, &value)) goto opaque;
      if (value < 100 || value > 10000) return -ERANGE;
      op.frequency_hz = (uint16_t)value;
      if (!take_literal(&c, ", ") || !take_integer(&c, &value)) goto opaque;
      if (value < 0 || value > 60000) return -ERANGE;
      op.duration_ms = (uint16_t)value;
      if (!take_literal(&c, ", 100)") || c.p != c.end) goto opaque;
    }
  else
    {
opaque:
      op.kind = BTSENSOR_MODERN_OP_TUNNEL_OPAQUE;
      op.opaque = payload;
      op.opaque_length = length;
    }
  return service->operation(&op, service->context);
}

void btsensor_modern_init(struct btsensor_modern *service,
                          const struct btsensor_modern_config *config,
                          btsensor_modern_send_t send,
                          btsensor_modern_operation_t operation,
                          btsensor_modern_interval_t set_interval,
                          void *context)
{
  memset(service, 0, sizeof(*service));
  if (config) service->config = *config;
  service->send = send;
  service->operation = operation;
  service->set_interval = set_interval;
  service->context = context;
}

int btsensor_modern_receive(struct btsensor_modern *service,
                            const uint8_t *message, size_t length,
                            bool high_priority)
{
  if (!service || !service->send || !message || length == 0)
    return -EINVAL;
  if (length > BTSENSOR_MODERN_MAX_MESSAGE) return -EMSGSIZE;
  switch (message[0])
    {
      case MSG_INFO_REQUEST:
        if (length != 1) return -EPROTO;
        return send_info(service, high_priority);
      case MSG_DEVICE_NOTIFICATION_REQUEST:
        {
          uint8_t response[2] = { MSG_DEVICE_NOTIFICATION_RESPONSE, 0 };
          int rc;
          if (length != 3) return -EPROTO;
          uint16_t interval = (uint16_t)message[1] |
                              ((uint16_t)message[2] << 8);
          rc = service->set_interval ?
               service->set_interval(interval, service->context) : 0;
          response[1] = rc < 0 ? 1 : 0;
          if (rc >= 0)
            __atomic_store_n(&service->notification_interval_ms, interval,
                             __ATOMIC_RELEASE);
          return service->send(response, sizeof(response), high_priority,
                               service->context);
        }
      case MSG_TUNNEL:
        if (length < 3) return -EPROTO;
        {
          size_t payload_length = (size_t)message[1] |
                                  ((size_t)message[2] << 8);
          if (payload_length != length - 3) return -EPROTO;
          return dispatch_tunnel(service, message + 3, payload_length);
        }
      default:
        return -ENOTSUP;
    }
}

int btsensor_modern_notify(struct btsensor_modern *service,
                           const uint8_t *records, size_t length,
                           bool high_priority)
{
  uint8_t *message;
  size_t offset = 0;
  if (!service || !service->send || (!records && length) ||
      length > BTSENSOR_MODERN_MAX_NOTIFICATION_RECORDS) return -EINVAL;
  message = service->notification_message;
  if (__atomic_load_n(&service->notification_interval_ms,
                      __ATOMIC_ACQUIRE) == 0) return -EAGAIN;

  /* Validate the whole record set before emitting any of it. This follows
   * the published layouts and avoids the extensions' partial-update bugs. */
  while (offset < length)
    {
      size_t record_length;
      switch (records[offset])
        {
          case 0x00: record_length = 2; break;  /* battery */
          case 0x01: record_length = 21; break; /* IMU */
          case 0x02: record_length = 26; break; /* 5x5 display */
          case 0x0a: record_length = 12; break; /* motor */
          case 0x0b: record_length = 4; break;  /* force */
          case 0x0c: record_length = 9; break;  /* color */
          case 0x0d: record_length = 4; break;  /* distance */
          case 0x0e: record_length = 11; break; /* 3x3 matrix */
          default: return -EPROTO;
        }
      if (record_length > length - offset) return -EPROTO;
      if (records[offset] == 0x00 && records[offset + 1] > 100)
        return -ERANGE;
      if (records[offset] >= 0x0a && records[offset] <= 0x0e &&
          records[offset + 1] > 5)
        return -ERANGE;
      offset += record_length;
    }
  message[0] = MSG_DEVICE_NOTIFICATION;
  put_le16(message + 1, (uint16_t)length);
  memcpy(message + 3, records, length);
  return service->send(message, length + 3, high_priority, service->context);
}
