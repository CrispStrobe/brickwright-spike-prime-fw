/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_sound.h"
#include <arch/board/board_sound.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

struct fake {
  int opens, writes, stops, closes, timer_starts, timer_stops;
  int open_result, write_result, timer_result;
  uint32_t delay;
  struct pcm_write_hdr_s header;
  btsensor_sound_timer_cb_t callback;
  void *callback_arg;
};
static int f_open(const char *path, int flags, void *ctx) {
  struct fake *f = ctx; (void)flags; assert(!strcmp(path, "/dev/pcm0"));
  f->opens++; return f->open_result ? f->open_result : 7;
}
static int f_write(int fd, const void *data, size_t length, void *ctx) {
  struct fake *f = ctx; assert(fd == 7); assert(length >= sizeof(f->header));
  memcpy(&f->header, data, sizeof(f->header)); f->writes++;
  return f->write_result ? f->write_result : (int)length;
}
static int f_ioctl(int fd, int cmd, unsigned long arg, void *ctx) {
  struct fake *f = ctx; assert(fd == 7 && cmd == TONEIOC_STOP && arg == 0);
  f->stops++; return 0;
}
static int f_close(int fd, void *ctx) {
  struct fake *f = ctx; assert(fd == 7); f->closes++; return 0;
}
static int f_timer_start(uint32_t delay, btsensor_sound_timer_cb_t cb,
                         void *arg, void *ctx) {
  struct fake *f = ctx; f->delay = delay; f->callback = cb;
  f->callback_arg = arg; f->timer_starts++; return f->timer_result;
}
static void f_timer_stop(void *ctx) { ((struct fake *)ctx)->timer_stops++; }

int main(void) {
  struct fake f = {0};
  struct btsensor_sound_io io = { f_open, f_write, f_ioctl, f_close,
                                  f_timer_start, f_timer_stop, &f };
  struct btsensor_modern_operation op = {
    .kind = BTSENSOR_MODERN_OP_SOUND_BEEP,
    .frequency_hz = 440, .duration_ms = 250
  };
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_CLASSIC,
                                           &op, &io) == 0);
  assert(f.opens == 1 && f.writes == 1 && f.timer_starts == 1);
  assert(f.delay == 250 && f.header.magic == PCM_WRITE_MAGIC);
  assert(f.header.sample_rate / f.header.sample_count == 440);
  assert(f.stops == 0 && f.closes == 0);
  f.callback(f.callback_arg);
  assert(f.stops == 1 && f.closes == 1);
  assert(f.delay == op.duration_ms);

  op.frequency_hz = 99;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_CLASSIC,
                                           &op, &io) == -ERANGE);
  op.frequency_hz = 440; op.duration_ms = 0;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_CLASSIC,
                                           &op, &io) == 0);
  assert(f.opens == 1);
  op.kind = BTSENSOR_MODERN_OP_SOUND_STOP;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_CLASSIC,
                                           &op, &io) == 0);
  btsensor_sound_reset_with_io(&io);

  /* External failures clean up synchronously.  The captured timer callback
   * provides virtual time for exact expiry/failsafe assertions. */
  memset(&f, 0, sizeof(f));
  op.kind = BTSENSOR_MODERN_OP_SOUND_BEEP;
  op.frequency_hz = 440; op.duration_ms = 25;
  f.open_result = -ENODEV;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_BLE,
                                           &op, &io) == -ENODEV);
  assert(f.closes == 0 && f.timer_starts == 0);
  f.open_result = 0; f.write_result = -EIO;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_BLE,
                                           &op, &io) == -EIO);
  assert(f.stops == 1 && f.closes == 1);
  f.write_result = 1;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_BLE,
                                           &op, &io) == -EIO);
  assert(f.stops == 2 && f.closes == 2);
  f.write_result = 0; f.timer_result = -ENOSPC;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_BLE,
                                           &op, &io) == -ENOSPC);
  assert(f.stops == 3 && f.closes == 3);
  f.timer_result = 0;
  assert(btsensor_sound_operation_with_io(BRICKWRIGHT_HUB_LINK_BLE,
                                           &op, &io) == 0);
  assert(f.timer_starts == 2 && f.delay == 25);
  btsensor_sound_link_state(BRICKWRIGHT_HUB_LINK_BLE, false);
  assert(f.stops == 4 && f.closes == 4);
  f.callback(f.callback_arg);
  assert(f.stops == 4 && f.closes == 4);
  puts("btsensor finite sound service: OK");
  return 0;
}
