/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_sound.h"
#include "btsensor_scheduler.h"

#include <arch/board/board_sound.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define PCM_DEV "/dev/pcm0"
#define TARGET_SR 50000u
#define PCM_MAX_SAMPLES 256u

struct pcm_blob
{
  struct pcm_write_hdr_s header;
  uint16_t samples[PCM_MAX_SAMPLES];
};

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static int g_fd = -1;
static enum brickwright_hub_link g_owner;
static struct btsensor_sound_io g_io;
static bool g_io_valid;
static struct btsensor_timer_s g_timer;

static bool same_io(const struct btsensor_sound_io *a,
                    const struct btsensor_sound_io *b)
{
  return a && b && a->open == b->open && a->write == b->write &&
         a->ioctl == b->ioctl && a->close == b->close &&
         a->timer_start == b->timer_start && a->timer_stop == b->timer_stop &&
         a->context == b->context;
}

static void close_locked(void)
{
  if (g_fd < 0 || !g_io_valid) return;
  (void)g_io.ioctl(g_fd, TONEIOC_STOP, 0, g_io.context);
  (void)g_io.close(g_fd, g_io.context);
  g_fd = -1;
}

static void timer_expired(void *arg)
{
  (void)arg;
  pthread_mutex_lock(&g_lock);
  close_locked();
  pthread_mutex_unlock(&g_lock);
}

static size_t build_square(struct pcm_blob *blob, uint16_t frequency)
{
  uint32_t count = TARGET_SR / frequency;
  if (count < 4) count = 4;
  if (count > PCM_MAX_SAMPLES) count = PCM_MAX_SAMPLES;
  count &= ~1u;
  for (uint32_t i = 0; i < count; i++)
    blob->samples[i] = i < count / 2 ? 0x0001u : 0xffffu;
  blob->header.magic = PCM_WRITE_MAGIC;
  blob->header.version = PCM_WRITE_VERSION;
  blob->header.hdr_size = sizeof(blob->header);
  blob->header.flags = 0;
  blob->header.sample_rate = frequency * count;
  blob->header.sample_count = count;
  return sizeof(blob->header) + count * sizeof(blob->samples[0]);
}

int btsensor_sound_operation_with_io(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation,
    const struct btsensor_sound_io *io)
{
  struct pcm_blob blob;
  size_t length;
  int rc = 0;
  if ((unsigned)link > BRICKWRIGHT_HUB_LINK_BLE || !operation || !io ||
      !io->open || !io->write || !io->ioctl || !io->close ||
      !io->timer_start || !io->timer_stop)
    return -EINVAL;
  if (operation->kind != BTSENSOR_MODERN_OP_SOUND_BEEP &&
      operation->kind != BTSENSOR_MODERN_OP_SOUND_STOP)
    return -ENOTSUP;
  if (operation->kind == BTSENSOR_MODERN_OP_SOUND_BEEP &&
      (operation->frequency_hz < 100 || operation->frequency_hz > 10000 ||
       operation->duration_ms > 60000))
    return -ERANGE;

  io->timer_stop(io->context);
  pthread_mutex_lock(&g_lock);
  if (g_io_valid && !same_io(&g_io, io)) close_locked();
  g_io = *io;
  g_io_valid = true;
  close_locked();
  if (operation->kind == BTSENSOR_MODERN_OP_SOUND_STOP ||
      operation->duration_ms == 0)
    goto out;
  length = build_square(&blob, operation->frequency_hz);
  g_fd = io->open(PCM_DEV, O_RDWR, io->context);
  if (g_fd < 0) { rc = g_fd; goto out; }
  rc = io->write(g_fd, &blob, length, io->context);
  if (rc < 0) { close_locked(); goto out; }
  if ((size_t)rc != length) { close_locked(); rc = -EIO; goto out; }
  g_owner = link;
  rc = io->timer_start(operation->duration_ms, timer_expired, NULL,
                       io->context);
  if (rc < 0) close_locked();
out:
  pthread_mutex_unlock(&g_lock);
  return rc;
}

static int prod_open(const char *path, int flags, void *context)
{ (void)context; int fd = open(path, flags); return fd < 0 ? -errno : fd; }
static int prod_write(int fd, const void *data, size_t length, void *context)
{ (void)context; ssize_t rc = write(fd, data, length); return rc < 0 ? -errno : (int)rc; }
static int prod_ioctl(int fd, int command, unsigned long argument, void *context)
{ (void)context; return ioctl(fd, command, argument) < 0 ? -errno : 0; }
static int prod_close(int fd, void *context)
{ (void)context; return close(fd) < 0 ? -errno : 0; }
static int prod_timer_start(uint32_t delay, btsensor_sound_timer_cb_t cb,
                            void *arg, void *context)
{ (void)context; return btsensor_scheduler_timer_start_once(&g_timer, delay, cb, arg); }
static void prod_timer_stop(void *context)
{ (void)context; btsensor_scheduler_timer_stop(&g_timer); }

static const struct btsensor_sound_io g_production_io =
  { prod_open, prod_write, prod_ioctl, prod_close,
    prod_timer_start, prod_timer_stop, NULL };

int btsensor_sound_operation(enum brickwright_hub_link link,
                             const struct btsensor_modern_operation *operation)
{ return btsensor_sound_operation_with_io(link, operation, &g_production_io); }

void btsensor_sound_link_state(enum brickwright_hub_link link, bool connected)
{
  if (connected) return;
  pthread_mutex_lock(&g_lock);
  /* Close while ownership is locked.  Calling the general shutdown after
   * unlocking would allow the other transport to replace the tone in between
   * and then have its newly-owned sound stopped by this stale disconnect. */
  if (g_fd >= 0 && g_owner == link) close_locked();
  pthread_mutex_unlock(&g_lock);
}

void btsensor_sound_reset_with_io(const struct btsensor_sound_io *io)
{
  if (!io) return;
  io->timer_stop(io->context);
  pthread_mutex_lock(&g_lock);
  if (g_io_valid && same_io(&g_io, io)) close_locked();
  pthread_mutex_unlock(&g_lock);
}

void btsensor_sound_shutdown(void)
{ btsensor_sound_reset_with_io(&g_production_io); }
