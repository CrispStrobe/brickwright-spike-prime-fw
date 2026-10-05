/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_classic.h"
#include "btsensor_font5.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>

#define CLASSIC_REPLY_MAX 192u
#define CLASSIC_PORT_COUNT 6u
#define CLASSIC_TIMED_MAX_MS 60000u
#define CLASSIC_ENCODER_POLL_MS 20u
#define CLASSIC_NO_PROGRESS_MS 1000u

static struct btsensor_classic_config g_config;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

struct pending_run
{
  uint64_t deadline_ms;
  uint64_t expires_ms, progress_ms;
  int32_t last_position;
  int64_t target_delta, displacement;
  int direction;
  bool degrees;
  uint32_t generation;
  uint32_t ownership_token;
  uint8_t end_state;
  char id[5];
  bool has_id;
  bool active;
};

static struct pending_run g_pending[CLASSIC_PORT_COUNT];
static uint32_t g_generation;

struct request
{
  const char *method;
  size_t method_length;
  const char *params;
  size_t params_length;
  char id[5];
  bool has_id;
};

void btsensor_classic_init(const struct btsensor_classic_config *config)
{
  pthread_mutex_lock(&g_lock);
  memset(g_pending, 0, sizeof(g_pending));
  if (config != NULL)
    g_config = *config;
  else
    memset(&g_config, 0, sizeof(g_config));
  pthread_mutex_unlock(&g_lock);
}

static bool exact(const char *value, size_t length, const char *literal)
{
  return strlen(literal) == length && !memcmp(value, literal, length);
}

static bool parse_request(const uint8_t *data, size_t length,
                          struct request *request)
{
  const char *text = (const char *)data;
  size_t pos = 0;
  size_t start;

  memset(request, 0, sizeof(*request));
  if (length < 15 || text[pos++] != '{') return false;
  if (length - pos >= 5 && !memcmp(text + pos, "\"i\":\"", 5))
    {
      pos += 5;
      if (length - pos < 10) return false;
      for (size_t i = 0; i < 4; i++)
        {
          char c = text[pos++];
          if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z')))
            return false;
          request->id[i] = c;
        }
      request->has_id = true;
      if (length - pos < 7) return false;
      if (memcmp(text + pos, "\",\"m\":\"", 7)) return false;
      pos += 7;
    }
  else
    {
      if (length - pos < 5 || memcmp(text + pos, "\"m\":\"", 5))
        return false;
      pos += 5;
    }

  start = pos;
  while (pos < length && text[pos] != '\"')
    {
      char c = text[pos++];
      if (!((c >= 'a' && c <= 'z') || c == '.' || c == '_')) return false;
    }
  if (pos == start || length - pos < 7 ||
      memcmp(text + pos, "\",\"p\":", 6)) return false;
  request->method = text + start;
  request->method_length = pos - start;
  pos += 6;
  request->params = text + pos;
  if (text[length - 1] != '}') return false;
  request->params_length = length - pos - 1;
  return request->params_length != 0;
}

static bool parse_integer(const char **cursor, const char *end,
                          int minimum, int maximum, int *value)
{
  const char *p = *cursor;
  int sign = 1;
  int result = 0;
  if (p < end && *p == '-') { sign = -1; p++; }
  if (p == end || *p < '0' || *p > '9') return false;
  if (*p == '0' && p + 1 < end && p[1] >= '0' && p[1] <= '9') return false;
  while (p < end && *p >= '0' && *p <= '9')
    {
      if (result > 1000000) return false;
      result = result * 10 + (*p++ - '0');
    }
  result *= sign;
  if (result < minimum || result > maximum) return false;
  *cursor = p;
  *value = result;
  return true;
}

static bool take(const char **cursor, const char *end, const char *literal)
{
  size_t n = strlen(literal);
  if ((size_t)(end - *cursor) < n || memcmp(*cursor, literal, n)) return false;
  *cursor += n;
  return true;
}

static bool parse_motor_start(const struct request *request,
                              struct btsensor_modern_operation *operation,
                              bool *stall)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int speed;
  if (!take(&p, end, "{\"port\":\"") || p == end || *p < 'A' || *p > 'F')
    return false;
  operation->port = (uint8_t)(*p++ - 'A');
  if (!take(&p, end, "\",\"speed\":") ||
      !parse_integer(&p, end, -100, 100, &speed) ||
      !take(&p, end, ",\"stall\":"))
    return false;
  if (take(&p, end, "true}"))
    *stall = true;
  else if (take(&p, end, "false}"))
    *stall = false;
  else
    return false;
  if (p != end) return false;
  operation->kind = BTSENSOR_MODERN_OP_MOTOR;
  operation->speed = (int8_t)speed;
  return true;
}

static bool parse_motor_stop(const struct request *request,
                             struct btsensor_modern_operation *operation)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int stop;
  if (!take(&p, end, "{\"port\":\"") || p == end || *p < 'A' || *p > 'F')
    return false;
  operation->port = (uint8_t)(*p++ - 'A');
  if (!take(&p, end, "\",\"stop\":") ||
      !parse_integer(&p, end, 0, 2, &stop) || !take(&p, end, "}") || p != end)
    return false;
  operation->kind = BTSENSOR_MODERN_OP_MOTOR;
  operation->speed = 0;
  operation->has_end_state = true;
  operation->end_state = (uint8_t)stop;
  return true;
}

static bool parse_motor_timed(const struct request *request,
                              struct btsensor_modern_operation *operation,
                              uint32_t *time_ms, uint8_t *end_state,
                              bool *stall)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int speed;
  int duration;
  int stop;
  if (!take(&p, end, "{\"port\":\"") || p == end || *p < 'A' || *p > 'F')
    return false;
  operation->port = (uint8_t)(*p++ - 'A');
  if (!take(&p, end, "\",\"speed\":") ||
      !parse_integer(&p, end, -100, 100, &speed) ||
      !take(&p, end, ",\"time\":") ||
      !parse_integer(&p, end, 0, CLASSIC_TIMED_MAX_MS, &duration) ||
      !take(&p, end, ",\"stop\":") ||
      !parse_integer(&p, end, 0, 2, &stop) ||
      !take(&p, end, ",\"stall\":"))
    return false;
  if (take(&p, end, "true}")) *stall = true;
  else if (take(&p, end, "false}")) *stall = false;
  else return false;
  if (p != end) return false;
  operation->kind = BTSENSOR_MODERN_OP_MOTOR;
  operation->speed = (int8_t)speed;
  *time_ms = (uint32_t)duration;
  *end_state = (uint8_t)stop;
  return true;
}

static bool parse_sound_beep(const struct request *request,
                             struct btsensor_modern_operation *operation)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int frequency;
  int duration;
  if (!take(&p, end, "{\"frequency\":") ||
      !parse_integer(&p, end, 100, 10000, &frequency) ||
      !take(&p, end, ",\"duration\":") ||
      !parse_integer(&p, end, 0, 60000, &duration) ||
      !take(&p, end, "}") || p != end)
    return false;
  operation->kind = BTSENSOR_MODERN_OP_SOUND_BEEP;
  operation->frequency_hz = (uint16_t)frequency;
  operation->duration_ms = (uint16_t)duration;
  return true;
}

static bool parse_display_set_pixel(
    const struct request *request,
    struct btsensor_modern_operation *operation)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int x;
  int y;
  int brightness;

  if (!take(&p, end, "{\"x\":") ||
      !parse_integer(&p, end, 0, 4, &x) ||
      !take(&p, end, ",\"y\":") ||
      !parse_integer(&p, end, 0, 4, &y) ||
      !take(&p, end, ",\"brightness\":") ||
      !parse_integer(&p, end, 0, 9, &brightness) ||
      !take(&p, end, "}") || p != end)
    return false;

  operation->kind = BTSENSOR_MODERN_OP_MATRIX5_PIXEL;
  operation->x = (uint8_t)x;
  operation->y = (uint8_t)y;
  /* The authoritative extension rounds percent onto the LEGO 0..9 display
   * scale.  Convert that level to the backend's 0..100 duty scale, with
   * nearest-integer rounding and exact endpoints. */
  operation->brightness = (uint8_t)((brightness * 100 + 4) / 9);
  return true;
}

/* {"text":"..."}: JSON string with the escapes JSON.stringify emits for
 * printable text (\" \\ \/ and \uXXXX). The first character is shown on
 * the 5x5 matrix; the 2.x hub scrolls longer text, which is not modelled. */
static bool parse_display_text(const struct request *request,
                               struct btsensor_modern_operation *operation)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  char first = 0;
  bool have_first = false;
  uint8_t rows[5];
  if (!take(&p, end, "{\"text\":\"")) return false;
  while (p < end && *p != '"')
    {
      char c = *p++;
      if (c == '\\')
        {
          if (p == end) return false;
          c = *p++;
          if (c == 'u')
            {
              if (end - p < 4) return false;
              p += 4;
              c = '?';
            }
          else if (c != '"' && c != '\\' && c != '/') return false;
        }
      if (!have_first) { first = c; have_first = true; }
    }
  if (!take(&p, end, "\"}") || p != end) return false;
  memset(operation->frame, 0, sizeof(operation->frame));
  if (have_first)
    {
      if (!btsensor_font5_glyph(first, rows)) (void)btsensor_font5_glyph('?', rows);
      for (unsigned y = 0; y < 5; y++)
        for (unsigned x = 0; x < 5; x++)
          operation->frame[y * 5 + x] = (rows[y] >> (4 - x)) & 1 ? 100 : 0;
    }
  operation->kind = BTSENSOR_MODERN_OP_MATRIX5_FRAME;
  return true;
}

/* {"color":N}, N a LEGO colour index 0-10. */
static bool parse_center_button_lights(
    const struct request *request,
    struct btsensor_modern_operation *operation)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int color;
  if (!take(&p, end, "{\"color\":") ||
      !parse_integer(&p, end, 0, 10, &color) ||
      !take(&p, end, "}") || p != end)
    return false;
  operation->kind = BTSENSOR_MODERN_OP_STATUS_LIGHT;
  operation->color = (uint8_t)color;
  return true;
}

/* {"port":"A","speed":N,"degrees":N,"stop":N,"stall":bool} */
static bool parse_motor_degrees(const struct request *request,
                                struct btsensor_modern_operation *operation,
                                int32_t *angle, uint8_t *end_state, bool *stall)
{
  const char *p = request->params;
  const char *end = p + request->params_length;
  int speed;
  int degrees;
  int stop;
  if (!take(&p, end, "{\"port\":\"") || p == end || *p < 'A' || *p > 'F')
    return false;
  operation->port = (uint8_t)(*p++ - 'A');
  if (!take(&p, end, "\",\"speed\":") ||
      !parse_integer(&p, end, -100, 100, &speed) ||
      !take(&p, end, ",\"degrees\":") ||
      !parse_integer(&p, end, -1000000, 1000000, &degrees) ||
      !take(&p, end, ",\"stop\":") ||
      !parse_integer(&p, end, 0, 2, &stop) ||
      !take(&p, end, ",\"stall\":"))
    return false;
  if (take(&p, end, "true}")) *stall = true;
  else if (take(&p, end, "false}")) *stall = false;
  else return false;
  if (p != end) return false;
  *angle = degrees; *end_state = (uint8_t)stop;
  operation->kind = BTSENSOR_MODERN_OP_MOTOR;
  operation->speed = (int8_t)speed;
  return true;
}

static bool parse_legacy_sound(const uint8_t *line, size_t length,
                               struct btsensor_modern_operation *operation)
{
  const char *p = (const char *)line;
  const char *end = p + length;
  int frequency;
  int duration;
  if (take(&p, end, "import hub; hub.sound.stop()") && p == end)
    {
      operation->kind = BTSENSOR_MODERN_OP_SOUND_STOP;
      return true;
    }
  p = (const char *)line;
  if (!take(&p, end, "import hub; hub.sound.beep(") ||
      !parse_integer(&p, end, 100, 10000, &frequency) ||
      !take(&p, end, ", ") ||
      !parse_integer(&p, end, 0, 60000, &duration) ||
      !take(&p, end, ", hub.sound.SOUND_SIN)") || p != end)
    return false;
  operation->kind = BTSENSOR_MODERN_OP_SOUND_BEEP;
  operation->frequency_hz = (uint16_t)frequency;
  operation->duration_ms = (uint16_t)duration;
  return true;
}

static int send_text(enum brickwright_hub_link link, const char *text)
{
  if (!g_config.send) return -ENOTSUP;
  return g_config.send(link, (const uint8_t *)text, strlen(text),
                       g_config.context);
}

static void send_result(enum brickwright_hub_link link,
                        const struct request *request, int result)
{
  char reply[64];
  if (!request->has_id) return;
  if (result == 0)
    snprintf(reply, sizeof(reply), "{\"i\":\"%s\",\"r\":null}\r\n",
             request->id);
  else
    snprintf(reply, sizeof(reply),
             "{\"i\":\"%s\",\"e\":{\"code\":%d}}\r\n",
             request->id, result);
  (void)send_text(link, reply);
}

static void send_pending_result(const struct pending_run *pending, int result)
{
  struct request request;
  memset(&request, 0, sizeof(request));
  request.has_id = pending->has_id;
  memcpy(request.id, pending->id, sizeof(request.id));
  send_result(BRICKWRIGHT_HUB_LINK_CLASSIC, &request, result);
}

static int arm_next_locked(void)
{
  uint64_t now;
  uint64_t earliest = UINT64_MAX;
  uint32_t delay;
  if (!g_config.now || !g_config.timer_start) return -ENOTSUP;
  now = g_config.now(g_config.context);
  for (unsigned port = 0; port < CLASSIC_PORT_COUNT; port++)
    if (g_pending[port].active && g_pending[port].deadline_ms < earliest)
      earliest = g_pending[port].deadline_ms;
  if (earliest == UINT64_MAX) return 0;
  delay = earliest <= now ? 1u :
          earliest - now > UINT32_MAX ? UINT32_MAX :
          (uint32_t)(earliest - now);
  return g_config.timer_start(delay, g_config.context);
}

static bool port_pending(uint8_t port)
{
  bool active;
  pthread_mutex_lock(&g_lock);
  active = g_pending[port].active;
  pthread_mutex_unlock(&g_lock);
  return active;
}

static void abort_failed_runs(const struct pending_run *failed, int error)
{
  for (unsigned port = 0; port < CLASSIC_PORT_COUNT; port++)
    if (failed[port].active) {
      int stop_rc = g_config.end_owned(BRICKWRIGHT_HUB_LINK_CLASSIC, (uint8_t)port,
                                       failed[port].ownership_token, 1, g_config.context);
      send_pending_result(&failed[port], stop_rc < 0 ? stop_rc : error);
    }
}

static void cancel_port(uint8_t port)
{
  struct pending_run canceled, failed[CLASSIC_PORT_COUNT];
  bool had_pending;
  memset(failed, 0, sizeof(failed));
  pthread_mutex_lock(&g_lock);
  canceled = g_pending[port];
  had_pending = canceled.active;
  g_pending[port].active = false;
  pthread_mutex_unlock(&g_lock);
  if (!had_pending) return;
  if (g_config.timer_stop) g_config.timer_stop(g_config.context);
  pthread_mutex_lock(&g_lock);
  int arm_rc = arm_next_locked();
  if (arm_rc < 0) {
    memcpy(failed, g_pending, sizeof(failed));
    memset(g_pending, 0, sizeof(g_pending));
  }
  pthread_mutex_unlock(&g_lock);
  /* An explicit stop safely completes the older run; resolving its request
   * avoids triggering the extension's MicroPython fallback after the motor
   * has already been stopped. */
  send_pending_result(&canceled, 0);
  abort_failed_runs(failed, arm_rc);
}

static int start_timed(enum brickwright_hub_link link,
                       const struct request *request,
                       const struct btsensor_modern_operation *operation,
                       uint32_t time_ms, uint8_t end_state)
{
  struct btsensor_modern_operation stop = {0};
  int rc;
  if (!g_config.tagged_operation || !g_config.end_owned || !g_config.now ||
      !g_config.timer_start || !g_config.timer_stop) return -ENOTSUP;
  if (end_state == 2) return -ENOTSUP;
  if (time_ms == 0)
    {
      stop.kind = BTSENSOR_MODERN_OP_MOTOR;
      stop.port = operation->port;
      stop.has_end_state = true;
      stop.end_state = end_state;
      int stop_rc = g_config.operation ? g_config.operation(link, &stop, g_config.context) : -ENOTSUP;
      if (stop_rc == 0) cancel_port(operation->port);
      return stop_rc;
    }
  pthread_mutex_lock(&g_lock);
  if (g_pending[operation->port].active)
    {
      pthread_mutex_unlock(&g_lock);
      return -EBUSY;
    }
  if (g_config.now(g_config.context) > UINT64_MAX - time_ms) {
    pthread_mutex_unlock(&g_lock); return -EOVERFLOW;
  }
  uint32_t ownership_token = 0;
  rc = g_config.tagged_operation(link, operation, &ownership_token,
                                 g_config.context);
  if (rc == 0)
    {
      struct pending_run *pending = &g_pending[operation->port];
      memset(pending, 0, sizeof(*pending));
      pending->deadline_ms = g_config.now(g_config.context) + time_ms;
      pending->generation = ++g_generation;
      pending->ownership_token = ownership_token;
      pending->end_state = end_state;
      pending->has_id = request->has_id;
      memcpy(pending->id, request->id, sizeof(pending->id));
      pending->active = true;
      rc = arm_next_locked();
      if (rc < 0)
        {
          pending->active = false;
          (void)g_config.end_owned(link, operation->port, ownership_token,
                                   end_state, g_config.context);
        }
    }
  pthread_mutex_unlock(&g_lock);
  return rc;
}

static int start_degrees(enum brickwright_hub_link link,
                         const struct request *request,
                         struct btsensor_modern_operation *operation,
                         int32_t angle, uint8_t end_state)
{
  int32_t baseline;
  int rc;
  if (!g_config.encoder || !g_config.tagged_operation || !g_config.end_owned ||
      !g_config.now || !g_config.timer_start || !g_config.timer_stop)
    return -ENOTSUP;
  if (end_state == 2) return -ENOTSUP;
  if (angle == 0) return start_timed(link, request, operation, 0, end_state);
  if (operation->speed == 0) return -EINVAL;
  pthread_mutex_lock(&g_lock);
  if (g_pending[operation->port].active) {
    pthread_mutex_unlock(&g_lock); return -EBUSY;
  }
  if (g_config.now(g_config.context) > UINT64_MAX - CLASSIC_TIMED_MAX_MS) {
    pthread_mutex_unlock(&g_lock); return -EOVERFLOW;
  }
  rc = g_config.encoder(operation->port, &baseline, g_config.context);
  if (rc == 0) {
    uint32_t token = 0;
    if (angle < 0) operation->speed = -operation->speed;
    rc = g_config.tagged_operation(link, operation, &token, g_config.context);
    if (rc == 0) {
      uint64_t now = g_config.now(g_config.context);
      struct pending_run *p = &g_pending[operation->port];
      memset(p, 0, sizeof(*p));
      p->degrees = true; p->last_position = baseline;
      p->target_delta = angle < 0 ? -(int64_t)angle : angle;
      p->direction = operation->speed < 0 ? -1 : 1;
      p->expires_ms = now + CLASSIC_TIMED_MAX_MS;
      p->progress_ms = now; p->deadline_ms = now + CLASSIC_ENCODER_POLL_MS;
      p->ownership_token = token; p->generation = ++g_generation;
      p->has_id = request->has_id; memcpy(p->id, request->id, sizeof(p->id));
      p->end_state = end_state; p->active = true;
      rc = arm_next_locked();
      if (rc < 0) {
        p->active = false;
        (void)g_config.end_owned(link, operation->port, token, 1, g_config.context);
      }
    }
  }
  pthread_mutex_unlock(&g_lock);
  return rc;
}

void btsensor_classic_timer_fired(void)
{
  for (unsigned port = 0; port < CLASSIC_PORT_COUNT; port++)
    {
      struct pending_run completed;
      int rc;
      pthread_mutex_lock(&g_lock);
      if (!g_pending[port].active || !g_config.now ||
          g_pending[port].deadline_ms > g_config.now(g_config.context))
        {
          pthread_mutex_unlock(&g_lock);
          continue;
        }
      completed = g_pending[port];
      rc = 0;
      if (completed.degrees) {
        int32_t measured = completed.last_position;
        uint64_t now = g_config.now(g_config.context);
        rc = g_config.encoder((uint8_t)port, &measured, g_config.context);
        if (rc == -EAGAIN) rc = 0;
        if (!rc && measured != completed.last_position) {
          uint32_t raw_delta = (uint32_t)measured - (uint32_t)completed.last_position;
          /* INT32 counter wrap is modular. Exactly half a counter range has
           * no distinguishable direction and must not complete a move. */
          if (raw_delta == UINT32_C(0x80000000)) rc = -EOVERFLOW;
          else {
            int32_t delta = raw_delta <= INT32_MAX ? (int32_t)raw_delta : -(int32_t)(~raw_delta) - 1;
            g_pending[port].displacement += delta;
            g_pending[port].last_position = measured;
            g_pending[port].progress_ms = now;
          }
        }
        bool reached = g_pending[port].displacement * completed.direction >= completed.target_delta;
        if (!rc && !reached && now < completed.expires_ms &&
            now - g_pending[port].progress_ms < CLASSIC_NO_PROGRESS_MS) {
          g_pending[port].deadline_ms = now + CLASSIC_ENCODER_POLL_MS;
          pthread_mutex_unlock(&g_lock); continue;
        }
        if (!rc && !reached) rc = -ETIMEDOUT;
      }
      pthread_mutex_unlock(&g_lock);
      int motion_result = rc;
      rc = g_config.end_owned ?
           g_config.end_owned(BRICKWRIGHT_HUB_LINK_CLASSIC, (uint8_t)port,
                              completed.ownership_token,
                              (motion_result < 0 ? 1 : completed.end_state), g_config.context) :
           -ENOTSUP;
      if (rc == 0) rc = motion_result;
      pthread_mutex_lock(&g_lock);
      bool owned = false;
      if (g_pending[port].active &&
          g_pending[port].generation == completed.generation)
        {
          g_pending[port].active = false;
          owned = true;
        }
      pthread_mutex_unlock(&g_lock);
      if (owned) send_pending_result(&completed, rc);
    }
  struct pending_run failed[CLASSIC_PORT_COUNT];
  memset(failed, 0, sizeof(failed));
  pthread_mutex_lock(&g_lock);
  int arm_rc = arm_next_locked();
  if (arm_rc < 0) {
    memcpy(failed, g_pending, sizeof(failed));
    memset(g_pending, 0, sizeof(g_pending));
  }
  pthread_mutex_unlock(&g_lock);
  abort_failed_runs(failed, arm_rc);
}

void btsensor_classic_link_state(enum brickwright_hub_link link,
                                 bool connected)
{
  btsensor_classic_timer_stop_t timer_stop;
  void *context;
  struct pending_run canceled[CLASSIC_PORT_COUNT];
  if (link != BRICKWRIGHT_HUB_LINK_CLASSIC || connected) return;
  pthread_mutex_lock(&g_lock);
  timer_stop = g_config.timer_stop;
  context = g_config.context;
  memcpy(canceled, g_pending, sizeof(canceled));
  memset(g_pending, 0, sizeof(g_pending));
  pthread_mutex_unlock(&g_lock);
  if (timer_stop) timer_stop(context);
  for (unsigned port = 0; port < CLASSIC_PORT_COUNT; port++)
    if (canceled[port].active && g_config.end_owned)
      (void)g_config.end_owned(link, (uint8_t)port, canceled[port].ownership_token, 1, context);
}

static int send_current_state(enum brickwright_hub_link link)
{
  struct btsensor_modern_snapshot snapshot;
  char reply[CLASSIC_REPLY_MAX];
  int rc;
  if (!g_config.snapshot) return -ENOTSUP;
  memset(&snapshot, 0, sizeof(snapshot));
  rc = g_config.snapshot(&snapshot, g_config.context);
  if (rc < 0) return rc;
  if (snapshot.battery_percent > 100) return -ERANGE;
  /* Unknown ports are explicit. The snapshot API currently proves battery
   * only; inventing motor or sensor values would violate the hub contract. */
  rc = send_text(link,
      "{\"m\":0,\"p\":[[0,[]],[0,[]],[0,[]],[0,[]],[0,[]],[0,[]],[],[],[0,0,0]]}\r\n");
  if (rc < 0) return rc;
  snprintf(reply, sizeof(reply), "{\"m\":2,\"p\":[0,%u]}\r\n",
           (unsigned)snapshot.battery_percent);
  return send_text(link, reply);
}

bool btsensor_classic_receive(enum brickwright_hub_link link,
                              const uint8_t *line, size_t length)
{
  struct btsensor_modern_operation operation;
  struct request request;
  bool stall = false;
  uint32_t time_ms;
  uint8_t end_state;
  int rc;
  if (link != BRICKWRIGHT_HUB_LINK_CLASSIC || (!line && length)) return false;
  memset(&operation, 0, sizeof(operation));
  if (parse_legacy_sound(line, length, &operation))
    {
      if (g_config.operation)
        (void)g_config.operation(link, &operation, g_config.context);
      return true;
    }
  if (!parse_request(line, length, &request)) return false;
  if (exact(request.method, request.method_length, "trigger_current_state") &&
      exact(request.params, request.params_length, "{}"))
    {
      rc = send_current_state(link);
      send_result(link, &request, rc);
      return true;
    }
  if (exact(request.method, request.method_length, "scratch.motor_start"))
    {
      if (!parse_motor_start(&request, &operation, &stall)) rc = -EINVAL;
      else if (stall) rc = -ENOTSUP;
      else if (port_pending(operation.port)) rc = -EBUSY;
      else if (!g_config.operation) rc = -ENOTSUP;
      else rc = g_config.operation(link, &operation, g_config.context);
    }
  else if (exact(request.method, request.method_length, "scratch.motor_stop"))
    {
      if (!parse_motor_stop(&request, &operation)) rc = -EINVAL;
      else if (!g_config.operation) rc = -ENOTSUP;
      else
        {
          rc = g_config.operation(link, &operation, g_config.context);
          if (rc == 0) cancel_port(operation.port);
        }
    }
  else if (exact(request.method, request.method_length,
                 "scratch.motor_run_timed"))
    {
      if (!parse_motor_timed(&request, &operation, &time_ms, &end_state,
                             &stall)) rc = -EINVAL;
      else if (stall) rc = -ENOTSUP;
      else rc = start_timed(link, &request, &operation, time_ms, end_state);
      /* A successful timed request resolves only after its end action. */
      if (rc == 0 && time_ms != 0) return true;
    }
  else if (exact(request.method, request.method_length, "scratch.sound_beep"))
    {
      if (!parse_sound_beep(&request, &operation)) rc = -EINVAL;
      else if (!g_config.operation) rc = -ENOTSUP;
      else rc = g_config.operation(link, &operation, g_config.context);
    }
  else if (exact(request.method, request.method_length,
                 "scratch.display_clear"))
    {
      if (!exact(request.params, request.params_length, "{}")) rc = -EINVAL;
      else if (!g_config.operation) rc = -ENOTSUP;
      else
        {
          operation.kind = BTSENSOR_MODERN_OP_MATRIX5_CLEAR;
          rc = g_config.operation(link, &operation, g_config.context);
        }
    }
  else if (exact(request.method, request.method_length,
                 "scratch.display_set_pixel"))
    {
      if (!parse_display_set_pixel(&request, &operation)) rc = -EINVAL;
      else if (!g_config.operation) rc = -ENOTSUP;
      else rc = g_config.operation(link, &operation, g_config.context);
    }
  else if (exact(request.method, request.method_length,
                 "scratch.display_text"))
    {
      if (!parse_display_text(&request, &operation)) rc = -EINVAL;
      else if (!g_config.operation) rc = -ENOTSUP;
      else rc = g_config.operation(link, &operation, g_config.context);
    }
  else if (exact(request.method, request.method_length,
                 "scratch.center_button_lights"))
    {
      if (!parse_center_button_lights(&request, &operation)) rc = -EINVAL;
      else if (!g_config.operation) rc = -ENOTSUP;
      else rc = g_config.operation(link, &operation, g_config.context);
    }
  else if (exact(request.method, request.method_length,
                 "scratch.motor_run_for_degrees"))
    {
      int32_t angle;
      if (!parse_motor_degrees(&request, &operation, &angle, &end_state, &stall)) rc = -EINVAL;
      else if (stall) rc = -ENOTSUP;
      else rc = start_degrees(link, &request, &operation, angle, end_state);
      if (rc == 0 && angle != 0) return true;
    }
  else
    {
      /* A syntactically valid request belongs to this adapter even when its
       * finite operation is not implemented.  Replying with the request ID
       * lets the repaired authoritative extension reject the command and
       * choose its compatibility fallback instead of waiting forever. */
      send_result(link, &request, -ENOTSUP);
      return true;
    }
  send_result(link, &request, rc);
  return true;
}
