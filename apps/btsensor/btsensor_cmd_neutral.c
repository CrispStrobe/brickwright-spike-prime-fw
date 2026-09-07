/* SPDX-License-Identifier: Apache-2.0 */
/* Legacy ASCII compatibility adapter over transport-neutral operations. */
#include "btsensor_cmd.h"
#include "btsensor_classic.h"
#include "btsensor_peripheral.h"
#include "btsensor_tx.h"
#include <ctype.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

struct stream {
  char line[BTSENSOR_CMD_MAX_LINE];
  size_t len;
  bool overflow;
};
static struct stream g_streams[2];
static const struct btsensor_peripheral_ops *g_ops;
#define BTSENSOR_CMD_REPLY_MAX 64u

void btsensor_cmd_set_peripheral_ops(
    const struct btsensor_peripheral_ops *ops) {
  g_ops = ops;
}
void btsensor_cmd_init(void) { memset(g_streams, 0, sizeof(g_streams)); }
void btsensor_cmd_reset_rx_buffer(void) {
  memset(g_streams, 0, sizeof(g_streams));
}

static void reply(enum brickwright_hub_link link, const char *s) {
  btsensor_tx_set_link(link, true);
  (void)btsensor_tx_enqueue_response(s);
}

static void reply_rc(enum brickwright_hub_link link, int rc, const char *what) {
  char s[BTSENSOR_CMD_REPLY_MAX];
  if (!rc)
    reply(link, "OK\n");
  else if (rc == -EBUSY)
    reply(link, "ERR busy\n");
  else if (rc == -EINVAL) {
    snprintf(s, sizeof(s), "ERR invalid %s\n", what);
    reply(link, s);
  } else {
    snprintf(s, sizeof(s), "ERR errno=%d\n", -rc);
    reply(link, s);
  }
}

static int number(const char *s, long min, long max, long *out) {
  char *end;
  long value;
  if (!s || !*s)
    return -EINVAL;
  errno = 0;
  value = strtol(s, &end, 10);
  if (errno == ERANGE || *end || value < min || value > max)
    return -EINVAL;
  *out = value;
  return 0;
}

static int unsigned_number(const char *s, uint32_t *out) {
  char *end;
  unsigned long long value;
  if (!s || !*s || *s == '-')
    return -EINVAL;
  errno = 0;
  value = strtoull(s, &end, 10);
  if (errno == ERANGE || *end || value > UINT32_MAX)
    return -EINVAL;
  *out = (uint32_t)value;
  return 0;
}

static int class_id(const char *s, uint8_t *out) {
  static const char *const names[] = {"color",   "ultrasonic", "force",
                                      "motor_m", "motor_r",    "motor_l"};
  long value;
  if (!s)
    return -EINVAL;
  for (uint8_t i = 0; i < BTSENSOR_PERIPHERAL_CLASS_COUNT; ++i)
    if (!strcasecmp(s, names[i])) {
      *out = i;
      return 0;
    }
  if (number(s, 0, BTSENSOR_PERIPHERAL_CLASS_COUNT - 1, &value))
    return -EINVAL;
  *out = (uint8_t)value;
  return 0;
}

static int hex_bytes(char **save, uint8_t *data, size_t cap) {
  size_t n = 0;
  char *s;
  while ((s = strtok_r(NULL, " ", save))) {
    size_t digits = strlen(s);
    if (!digits || (digits & 1u))
      return -EINVAL;
    for (size_t i = 0; i < digits; i += 2) {
      char pair[3] = {s[i], s[i + 1], 0};
      if (!isxdigit((unsigned char)pair[0]) ||
          !isxdigit((unsigned char)pair[1]))
        return -EINVAL;
      if (n == cap)
        return -E2BIG;
      data[n++] = (uint8_t)strtoul(pair, NULL, 16);
    }
  }
  return n ? (int)n : -EINVAL;
}

static int pwm_values(char **save, int16_t *values, size_t cap) {
  size_t n = 0;
  char *s;
  long value;
  while ((s = strtok_r(NULL, " ", save))) {
    if (n == cap)
      return -E2BIG;
    if (number(s, -10000, 10000, &value))
      return -EINVAL;
    values[n++] = (int16_t)value;
  }
  return n ? (int)n : -EINVAL;
}

static bool has_trailing_token(char **save) {
  return strtok_r(NULL, " ", save) != NULL;
}

static void sensor(enum brickwright_hub_link link, char *verb, char **save) {
  int rc;
  uint8_t cls;
  long mode;
  char *cls_s;
  char *mode_s;
  if (!verb) {
    reply(link, "ERR invalid SENSOR\n");
    return;
  }
  if (!strcasecmp(verb, "ON") || !strcasecmp(verb, "OFF")) {
    bool on = !strcasecmp(verb, "ON");
    if (has_trailing_token(save)) {
      reply(link, "ERR invalid SENSOR\n");
      return;
    }
    rc = g_ops && g_ops->set_sensor_enabled
             ? g_ops->set_sensor_enabled(g_ops->context, on)
             : -ENOTSUP;
    reply_rc(link, rc, on ? "SENSOR ON" : "SENSOR OFF");
    return;
  }
  if (strcasecmp(verb, "MODE") && strcasecmp(verb, "SEND") &&
      strcasecmp(verb, "PWM")) {
    char s[BTSENSOR_CMD_REPLY_MAX];
    snprintf(s, sizeof(s), "ERR invalid %s\n", verb);
    reply(link, s);
    return;
  }
  cls_s = strtok_r(NULL, " ", save);
  if (class_id(cls_s, &cls)) {
    reply(link, "ERR invalid class\n");
    return;
  }
  if (!strcasecmp(verb, "PWM")) {
    int16_t values[4];
    int n = pwm_values(save, values, 4);
    if (n < 0) {
      reply(link,
            n == -E2BIG ? "ERR too many channels\n" : "ERR invalid pwm\n");
      return;
    }
    rc = g_ops && g_ops->sensor_set_pwm
             ? g_ops->sensor_set_pwm(g_ops->context, link, cls, values,
                                     (size_t)n)
             : -ENOTSUP;
    reply_rc(link, rc, "SENSOR PWM");
    return;
  }
  mode_s = strtok_r(NULL, " ", save);
  if (number(mode_s, 0, 7, &mode)) {
    reply(link, "ERR invalid mode\n");
    return;
  }
  if (!strcasecmp(verb, "MODE")) {
    if (has_trailing_token(save)) {
      reply(link, "ERR invalid mode\n");
      return;
    }
    rc = g_ops && g_ops->sensor_select_mode
             ? g_ops->sensor_select_mode(g_ops->context, cls, (uint8_t)mode)
             : -ENOTSUP;
  } else if (!strcasecmp(verb, "SEND")) {
    uint8_t data[BTSENSOR_PERIPHERAL_PAYLOAD_MAX];
    int n = hex_bytes(save, data, sizeof(data));
    if (n < 0) {
      reply(link, n == -E2BIG ? "ERR payload too long\n" : "ERR invalid hex\n");
      return;
    }
    rc = g_ops && g_ops->sensor_send
             ? g_ops->sensor_send(g_ops->context, cls, (uint8_t)mode, data,
                                  (size_t)n)
             : -ENOTSUP;
  } else {
    char s[BTSENSOR_CMD_REPLY_MAX];
    snprintf(s, sizeof(s), "ERR invalid %s\n", verb);
    reply(link, s);
    return;
  }
  reply_rc(link, rc, !strcasecmp(verb, "MODE") ? "SENSOR MODE" : "SENSOR SEND");
}

static void process(enum brickwright_hub_link link, char *line) {
  char *save = NULL, *cmd = strtok_r(line, " ", &save), *arg;
  char s[BTSENSOR_CMD_REPLY_MAX];
  int rc;
  long value;
  uint32_t index = 0;
  if (!cmd)
    return;
  if (!strcasecmp(cmd, "PING")) {
    reply(link, has_trailing_token(&save) ? "ERR invalid PING\n" : "OK PONG\n");
    return;
  }
  if (!strcmp(cmd, "IMU")) {
    arg = strtok_r(NULL, " ", &save);
    if (!arg) {
      reply(link, "ERR invalid IMU\n");
      return;
    }
    if (strcmp(arg, "ON") && strcmp(arg, "OFF")) {
      snprintf(s, sizeof(s), "ERR invalid %s\n", arg);
      reply(link, s);
      return;
    }
    if (has_trailing_token(&save)) {
      reply(link, "ERR invalid IMU\n");
      return;
    }
    rc = g_ops && g_ops->set_imu_enabled
             ? g_ops->set_imu_enabled(g_ops->context, !strcmp(arg, "ON"))
             : -ENOTSUP;
    reply_rc(link, rc, !strcmp(arg, "ON") ? "IMU ON" : "IMU OFF");
    return;
  }
  if (!strcmp(cmd, "SENSOR")) {
    sensor(link, strtok_r(NULL, " ", &save), &save);
    return;
  }
  if (!strcmp(cmd, "SET")) {
    char *what = strtok_r(NULL, " ", &save);
    uint32_t setting;
    arg = strtok_r(NULL, " ", &save);
    if (!what || !arg) {
      reply(link, "ERR invalid SET\n");
      return;
    }
    if (has_trailing_token(&save)) {
      reply(link, "ERR invalid SET\n");
      return;
    }
    if (unsigned_number(arg, &setting)) {
      reply(link, "ERR invalid value\n");
      return;
    }
    if (!strcmp(what, "ODR"))
      rc = g_ops && g_ops->set_imu_odr_hz
               ? g_ops->set_imu_odr_hz(g_ops->context, setting)
               : -ENOTSUP;
    else if (!strcmp(what, "ACCEL_FSR"))
      rc = g_ops && g_ops->set_accel_fsr
               ? g_ops->set_accel_fsr(g_ops->context, setting)
               : -ENOTSUP;
    else if (!strcmp(what, "GYRO_FSR"))
      rc = g_ops && g_ops->set_gyro_fsr
               ? g_ops->set_gyro_fsr(g_ops->context, setting)
               : -ENOTSUP;
    else {
      snprintf(s, sizeof(s), "ERR invalid %s\n", what);
      reply(link, s);
      return;
    }
    reply_rc(link, rc, what);
    return;
  }
  if (!strcmp(cmd, "GET")) {
    char *what = strtok_r(NULL, " ", &save);
    if (!what) {
      reply(link, "ERR invalid GET\n");
      return;
    }
    if (has_trailing_token(&save)) {
      reply(link, "ERR invalid GET\n");
      return;
    }
    if (!strcmp(what, "ODR"))
      rc = g_ops && g_ops->get_imu_odr_idx
               ? g_ops->get_imu_odr_idx(g_ops->context, &index)
               : -ENOTSUP;
    else if (!strcmp(what, "ACCEL_FSR"))
      rc = g_ops && g_ops->get_accel_fsr_idx
               ? g_ops->get_accel_fsr_idx(g_ops->context, &index)
               : -ENOTSUP;
    else if (!strcmp(what, "GYRO_FSR"))
      rc = g_ops && g_ops->get_gyro_fsr_idx
               ? g_ops->get_gyro_fsr_idx(g_ops->context, &index)
               : -ENOTSUP;
    else {
      snprintf(s, sizeof(s), "ERR invalid %s\n", what);
      reply(link, s);
      return;
    }
    if (rc < 0)
      snprintf(s, sizeof(s), "ERR errno=%d\n", -rc);
    else
      snprintf(s, sizeof(s), "OK %u\n", (unsigned)index);
    reply(link, s);
    return;
  }
  if (!strcasecmp(cmd, "_IMU_CAP")) {
    char *sub = strtok_r(NULL, " ", &save);
    if (!sub) {
      reply(link, "ERR invalid _IMU_CAP\n");
      return;
    }
    if (!strcasecmp(sub, "STOP")) {
      if (has_trailing_token(&save)) {
        reply(link, "ERR invalid _IMU_CAP\n");
        return;
      }
      rc = g_ops && g_ops->imu_capture_stop
               ? g_ops->imu_capture_stop(g_ops->context)
               : -ENOTSUP;
    } else if (!strcasecmp(sub, "START")) {
      arg = strtok_r(NULL, " ", &save);
      value = 0;
      if (arg && number(arg, 0, 86400, &value)) {
        reply(link, "ERR invalid duration\n");
        return;
      }
      if (has_trailing_token(&save)) {
        reply(link, "ERR invalid _IMU_CAP\n");
        return;
      }
      rc = g_ops && g_ops->imu_capture_start
               ? g_ops->imu_capture_start(g_ops->context, (uint32_t)value)
               : -ENOTSUP;
    } else {
      snprintf(s, sizeof(s), "ERR invalid _IMU_CAP %s\n", sub);
      reply(link, s);
      return;
    }
    reply_rc(link, rc,
             !strcasecmp(sub, "STOP") ? "_IMU_CAP STOP" : "_IMU_CAP START");
    return;
  }
  snprintf(s, sizeof(s), "ERR unknown %s\n", cmd);
  reply(link, s);
}

void btsensor_cmd_feed_link(enum brickwright_hub_link link, const uint8_t *data,
                            size_t length) {
  if ((link != BRICKWRIGHT_HUB_LINK_CLASSIC &&
       link != BRICKWRIGHT_HUB_LINK_BLE) ||
      (!data && length))
    return;
  struct stream *stream = &g_streams[link];
  for (size_t i = 0; i < length; ++i) {
    char c = (char)data[i];
    if (c == '\r' || c == '\n') {
      if (stream->overflow)
        reply(link, "ERR overflow\n");
      else if (stream->len) {
        stream->line[stream->len] = 0;
        if (!btsensor_classic_receive(link, (const uint8_t *)stream->line,
                                      stream->len))
          process(link, stream->line);
      }
      stream->len = 0;
      stream->overflow = false;
    } else if (stream->len + 1 < sizeof(stream->line))
      stream->line[stream->len++] = c;
    else
      stream->overflow = true;
  }
}

void btsensor_cmd_feed(const uint8_t *data, uint16_t length) {
  btsensor_cmd_feed_link(BRICKWRIGHT_HUB_LINK_CLASSIC, data, length);
}
