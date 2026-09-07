/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_classic.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

struct fixture {
  struct btsensor_modern_operation operation;
  unsigned operations;
  char sent[8][192];
  unsigned sends;
  int operation_result;
  int snapshot_result;
  uint8_t battery;
  uint64_t now;
  uint32_t timer_delay;
  unsigned timer_starts;
  unsigned timer_stops;
  int timer_result;
  uint32_t next_token;
  uint32_t owner_token[6];
};
static bool receive(const char *text);
static int operation(enum brickwright_hub_link link,
                     const struct btsensor_modern_operation *value, void *ctx) {
  struct fixture *f = ctx;
  assert(link == BRICKWRIGHT_HUB_LINK_CLASSIC);
  f->operation = *value; f->operations++;
  if (value->kind == BTSENSOR_MODERN_OP_MOTOR && value->speed == 0)
    f->owner_token[value->port] = 0;
  return f->operation_result;
}
static int tagged_operation(enum brickwright_hub_link link,
                            const struct btsensor_modern_operation *value,
                            uint32_t *token, void *ctx) {
  struct fixture *f = ctx; int rc = operation(link, value, ctx);
  if (rc == 0) {
    *token = ++f->next_token;
    f->owner_token[value->port] = *token;
  }
  return rc;
}
static int end_owned(enum brickwright_hub_link link, uint8_t port,
                     uint32_t token, uint8_t end_state, void *ctx) {
  struct fixture *f = ctx;
  if (f->owner_token[port] != token) return -ESTALE;
  struct btsensor_modern_operation stop =
    { .kind = BTSENSOR_MODERN_OP_MOTOR, .port = port, .speed = 0,
      .has_end_state = true, .end_state = end_state };
  return operation(link, &stop, ctx);
}
static int snapshot(struct btsensor_modern_snapshot *value, void *ctx) {
  struct fixture *f = ctx;
  memset(value, 0, sizeof(*value)); value->battery_percent = f->battery;
  return f->snapshot_result;
}
static int send_data(enum brickwright_hub_link link, const uint8_t *data,
                     size_t length, void *ctx) {
  struct fixture *f = ctx;
  assert(link == BRICKWRIGHT_HUB_LINK_CLASSIC);
  assert(f->sends < 8 && length < sizeof(f->sent[0]));
  memcpy(f->sent[f->sends], data, length); f->sent[f->sends][length] = 0;
  f->sends++; return 0;
}
static uint64_t now_ms(void *ctx) { return ((struct fixture *)ctx)->now; }
static int timer_start(uint32_t delay, void *ctx) {
  struct fixture *f = ctx; f->timer_delay = delay; f->timer_starts++;
  return f->timer_result;
}
static void timer_stop(void *ctx) { ((struct fixture *)ctx)->timer_stops++; }
static void configure(struct fixture *f) {
  memset(f, 0, sizeof(*f)); f->battery = 73;
  const struct btsensor_classic_config config =
    { .operation = operation, .tagged_operation = tagged_operation,
      .end_owned = end_owned, .snapshot = snapshot, .send = send_data,
      .now = now_ms, .timer_start = timer_start, .timer_stop = timer_stop,
      .context = f };
  btsensor_classic_init(&config);
}
static void test_takeover_makes_completion_stale(void) {
  struct fixture f; configure(&f); f.now = 1;
  assert(receive("{\"i\":\"old1\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"E\",\"speed\":40,\"time\":10,\"stop\":1,\"stall\":false}}"));
  /* Models a BLE command atomically replacing the Classic owner token. */
  f.owner_token[4] = ++f.next_token;
  f.now = 11; btsensor_classic_timer_fired();
  assert(f.operations == 1); /* stale completion performed no physical stop */
  assert(!strcmp(f.sent[0], "{\"i\":\"old1\",\"e\":{\"code\":-116}}\r\n"));
}
static void test_timed_motor(void) {
  struct fixture f; configure(&f); f.now = 1000;
  assert(receive("{\"i\":\"t123\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"C\",\"speed\":-25,\"time\":500,\"stop\":1,\"stall\":false}}"));
  assert(f.operations == 1 && f.operation.port == 2 && f.operation.speed == -25);
  assert(f.sends == 0 && f.timer_starts == 1 && f.timer_delay == 500);
  assert(receive("{\"i\":\"busy\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"C\",\"speed\":20,\"time\":1,\"stop\":0,\"stall\":false}}"));
  assert(f.operations == 1 && !strcmp(f.sent[0], "{\"i\":\"busy\",\"e\":{\"code\":-16}}\r\n"));
  f.now = 1499; btsensor_classic_timer_fired();
  assert(f.operations == 1 && f.timer_delay == 1);
  f.now = 1500; btsensor_classic_timer_fired();
  assert(f.operations == 2 && f.operation.port == 2 && f.operation.speed == 0);
  assert(f.operation.has_end_state && f.operation.end_state == 1);
  assert(!strcmp(f.sent[1], "{\"i\":\"t123\",\"r\":null}\r\n"));

  configure(&f); f.now = 1;
  assert(receive("{\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"A\",\"speed\":100,\"time\":0,\"stop\":0,\"stall\":false}}"));
  assert(f.operations == 1 && f.operation.speed == 0 && f.operation.end_state == 0);
  assert(f.timer_starts == 0);

  configure(&f); f.now = 5; f.timer_result = -ENOSPC;
  assert(receive("{\"i\":\"full\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"B\",\"speed\":50,\"time\":10,\"stop\":0,\"stall\":false}}"));
  assert(f.operations == 2 && f.operation.speed == 0 && f.operation.has_end_state);
  assert(!strcmp(f.sent[0], "{\"i\":\"full\",\"e\":{\"code\":-28}}\r\n"));
}
static void test_timed_adversarial(void) {
  struct fixture f; configure(&f);
  assert(receive("{\"i\":\"hold\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"A\",\"speed\":1,\"time\":1,\"stop\":2,\"stall\":false}}"));
  assert(receive("{\"i\":\"stal\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"A\",\"speed\":1,\"time\":1,\"stop\":0,\"stall\":true}}"));
  assert(receive("{\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"A\",\"speed\":1,\"time\":60001,\"stop\":0,\"stall\":false}}"));
  assert(receive("{\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"A\",\"speed\":1,\"time\":1,\"stop\":0,\"stall\":false,}}"));
  assert(receive("{\"i\":\"degr\",\"m\":\"scratch.motor_run_for_degrees\",\"p\":{\"port\":\"A\",\"speed\":1,\"degrees\":90,\"stop\":0,\"stall\":false}}"));
  assert(f.operations == 0 && f.sends == 3);
  assert(strstr(f.sent[0], "-95") && strstr(f.sent[1], "-95") && strstr(f.sent[2], "-95"));
}
static void test_disconnect_cancels_timed(void) {
  struct fixture f; configure(&f); f.now = 10;
  assert(receive("{\"i\":\"gone\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"F\",\"speed\":10,\"time\":20,\"stop\":1,\"stall\":false}}"));
  btsensor_classic_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, false);
  assert(f.timer_stops >= 1); f.now = 100; btsensor_classic_timer_fired();
  assert(f.operations == 1 && f.sends == 0);
}
static void test_explicit_stop_cancels_timed(void) {
  struct fixture f; configure(&f); f.now = 10;
  assert(receive("{\"i\":\"wait\",\"m\":\"scratch.motor_run_timed\",\"p\":{\"port\":\"D\",\"speed\":10,\"time\":20,\"stop\":1,\"stall\":false}}"));
  assert(receive("{\"i\":\"stop\",\"m\":\"scratch.motor_stop\",\"p\":{\"port\":\"D\",\"stop\":0}}"));
  assert(f.operations == 2 && f.operation.speed == 0 && f.operation.end_state == 0);
  assert(!strcmp(f.sent[0], "{\"i\":\"wait\",\"r\":null}\r\n"));
  assert(!strcmp(f.sent[1], "{\"i\":\"stop\",\"r\":null}\r\n"));
  f.now = 100; btsensor_classic_timer_fired();
  assert(f.operations == 2 && f.sends == 2);
}
static bool receive(const char *text) {
  return btsensor_classic_receive(BRICKWRIGHT_HUB_LINK_CLASSIC,
                                  (const uint8_t *)text, strlen(text));
}
static void test_current_state(void) {
  struct fixture f; configure(&f);
  assert(receive("{\"m\":\"trigger_current_state\",\"p\":{}}"));
  assert(f.sends == 2);
  assert(!strcmp(f.sent[0],
      "{\"m\":0,\"p\":[[0,[]],[0,[]],[0,[]],[0,[]],[0,[]],[0,[]],[],[],[0,0,0]]}\r\n"));
  assert(!strcmp(f.sent[1], "{\"m\":2,\"p\":[0,73]}\r\n"));
  configure(&f); f.snapshot_result = -ENODATA;
  assert(receive("{\"i\":\"a1z9\",\"m\":\"trigger_current_state\",\"p\":{}}"));
  assert(f.sends == 1);
  assert(!strcmp(f.sent[0],
                 "{\"i\":\"a1z9\",\"e\":{\"code\":-61}}\r\n"));
}
static void test_motors(void) {
  struct fixture f; configure(&f);
  assert(receive("{\"m\":\"scratch.motor_start\",\"p\":{\"port\":\"F\",\"speed\":-100,\"stall\":false}}"));
  assert(f.operations == 1 && f.operation.kind == BTSENSOR_MODERN_OP_MOTOR);
  assert(f.operation.port == 5 && f.operation.speed == -100 && f.sends == 0);
  f.operation_result = -ENOTSUP;
  assert(receive("{\"i\":\"0abc\",\"m\":\"scratch.motor_stop\",\"p\":{\"port\":\"A\",\"stop\":1}}"));
  assert(f.operations == 2 && f.operation.port == 0 && f.operation.speed == 0);
  assert(f.operation.has_end_state && f.operation.end_state == 1);
  assert(!strcmp(f.sent[0], "{\"i\":\"0abc\",\"e\":{\"code\":-95}}\r\n"));
  assert(receive("{\"i\":\"zzzz\",\"m\":\"scratch.motor_start\",\"p\":{\"port\":\"A\",\"speed\":1,\"stall\":true}}"));
  assert(f.operations == 2);
  assert(!strcmp(f.sent[1], "{\"i\":\"zzzz\",\"e\":{\"code\":-95}}\r\n"));
}
static void test_sound(void) {
  struct fixture f; configure(&f);
  assert(receive("{\"i\":\"beep\",\"m\":\"scratch.sound_beep\",\"p\":{\"frequency\":440,\"duration\":250}}"));
  assert(f.operations == 1);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_SOUND_BEEP);
  assert(f.operation.frequency_hz == 440 && f.operation.duration_ms == 250);
  assert(!strcmp(f.sent[0], "{\"i\":\"beep\",\"r\":null}\r\n"));
  assert(receive("{\"m\":\"scratch.sound_beep\",\"p\":{\"duration\":250,\"frequency\":440}}"));
  assert(receive("{\"m\":\"scratch.sound_beep\",\"p\":{\"frequency\":99,\"duration\":250}}"));
  assert(f.operations == 1);
  assert(receive("import hub; hub.sound.beep(880, 125, hub.sound.SOUND_SIN)"));
  assert(f.operations == 2 && f.operation.frequency_hz == 880 &&
         f.operation.duration_ms == 125);
  assert(receive("import hub; hub.sound.stop()"));
  assert(f.operations == 3 && f.operation.kind == BTSENSOR_MODERN_OP_SOUND_STOP);
  assert(!receive("import hub; hub.sound.stop();print('x')"));
}
static void test_display(void) {
  struct fixture f; configure(&f);
  assert(receive("{\"i\":\"clr1\",\"m\":\"scratch.display_clear\",\"p\":{}}"));
  assert(f.operations == 1);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MATRIX5_CLEAR);
  assert(!strcmp(f.sent[0], "{\"i\":\"clr1\",\"r\":null}\r\n"));

  assert(receive("{\"i\":\"pix1\",\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":4,\"y\":3,\"brightness\":9}}"));
  assert(f.operations == 2);
  assert(f.operation.kind == BTSENSOR_MODERN_OP_MATRIX5_PIXEL);
  assert(f.operation.x == 4 && f.operation.y == 3);
  assert(f.operation.brightness == 100);
  assert(!strcmp(f.sent[1], "{\"i\":\"pix1\",\"r\":null}\r\n"));

  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":0,\"y\":0,\"brightness\":1}}"));
  assert(f.operations == 3 && f.operation.brightness == 11);
  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":2,\"y\":2,\"brightness\":0}}"));
  assert(f.operations == 4 && f.operation.brightness == 0);

  assert(receive("{\"m\":\"scratch.display_clear\",\"p\":{\"x\":0}}"));
  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":5,\"y\":0,\"brightness\":9}}"));
  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":0,\"y\":-1,\"brightness\":9}}"));
  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":0,\"y\":0,\"brightness\":10}}"));
  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"brightness\":9,\"x\":0,\"y\":0}}"));
  assert(receive("{\"m\":\"scratch.display_set_pixel\",\"p\":{\"x\":0,\"y\":0,\"brightness\":9,}}"));
  assert(f.operations == 4);

  /* A 25-channel display image cannot be committed atomically by the
   * current RGBLED interface and remains an explicit finite-op boundary. */
  assert(receive("{\"i\":\"img1\",\"m\":\"scratch.display_image\",\"p\":{\"image\":\"00000:00000:00900:00000:00000\"}}"));
  assert(f.operations == 4);
  assert(!strcmp(f.sent[2], "{\"i\":\"img1\",\"e\":{\"code\":-95}}\r\n"));
}
static void test_exact_rejection(void) {
  struct fixture f; configure(&f);
  assert(!receive("import hub; hub.port.A.motor.pwm(100)"));
  assert(!receive("{ \"m\":\"trigger_current_state\",\"p\":{}}"));
  assert(receive("{\"m\":\"trigger_current_state\",\"p\":{},\"x\":1}"));
  assert(receive("{\"m\":\"scratch.motor_start\",\"p\":{\"port\":\"A\",\"speed\":101,\"stall\":false}}"));
  assert(receive("{\"m\":\"scratch.motor_start\",\"p\":{\"port\":\"A\",\"speed\":01,\"stall\":false}}"));
  assert(receive("{\"m\":\"scratch.motor_start\",\"p\":{\"speed\":1,\"port\":\"A\",\"stall\":false}}"));
  assert(!receive("{\"i\":\"ABC!\",\"m\":\"scratch.motor_stop\",\"p\":{\"port\":\"A\",\"stop\":0}}"));
  assert(receive("{\"m\":\"scratch.motor_stop\",\"p\":{\"port\":\"G\",\"stop\":0}}"));
  assert(receive("{\"m\":\"scratch.motor_stop\",\"p\":{\"port\":\"A\",\"stop\":2,}}"));
  assert(f.operations == 0 && f.sends == 0);
}
static void test_unsupported_request_replies_for_fallback(void) {
  struct fixture f; configure(&f);
  assert(receive("{\"i\":\"a123\",\"m\":\"scratch.display_text\",\"p\":{\"text\":\"x\"}}"));
  assert(f.operations == 0 && f.sends == 1);
  assert(!strcmp(f.sent[0], "{\"i\":\"a123\",\"e\":{\"code\":-95}}\r\n"));
}
int main(void) {
  test_current_state(); test_motors(); test_sound(); test_display();
  test_exact_rejection();
  test_timed_motor(); test_timed_adversarial(); test_disconnect_cancels_timed();
  test_explicit_stop_cancels_timed();
  test_takeover_makes_completion_stale();
  test_unsupported_request_replies_for_fallback();
  btsensor_classic_init(NULL);
  puts("btsensor Classic JSON adapter tests: OK"); return 0;
}
