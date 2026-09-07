/* SPDX-License-Identifier: Apache-2.0 */
#include "btsensor_modern_backend.h"

#include <arch/board/board_legoport.h>
#include <arch/board/board_lump.h>
#include <arch/board/board_rgbled.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define MATRIX_TYPE_ID 64u
#define MATRIX_PIXELS_MODE 2u
#define RGBLED_DEVPATH "/dev/rgbled0"

static const uint8_t g_matrix5_channels[5][5] =
{
  { 38, 36, 41, 46, 33 }, { 37, 28, 39, 47, 21 },
  { 24, 29, 31, 45, 23 }, { 26, 27, 32, 34, 22 },
  { 25, 40, 30, 35, 9 },
};

#define LPF2_TYPE_SPIKE_MEDIUM_MOTOR 48u
#define LPF2_TYPE_SPIKE_LARGE_MOTOR 49u

static int g_port_fds[BOARD_LEGOPORT_COUNT] =
{
  -1, -1, -1, -1, -1, -1,
};
static struct btsensor_modern_backend_io g_port_io;
static bool g_port_io_valid;
static bool g_commanded[2][BOARD_LEGOPORT_COUNT];
static uint32_t g_generation[2];
static uint32_t g_owner_token[BOARD_LEGOPORT_COUNT];
static uint32_t g_next_owner_token;
static pthread_mutex_t g_owner_lock = PTHREAD_MUTEX_INITIALIZER;

static int production_open(const char *path, int flags, void *context)
{
  int fd;
  (void)context;
  fd = open(path, flags);
  return fd < 0 ? -errno : fd;
}

static int production_ioctl(int fd, int command, unsigned long argument,
                            void *context)
{
  (void)context;
  return ioctl(fd, command, argument) < 0 ? -errno : 0;
}

static int production_close(int fd, void *context)
{
  (void)context;
  return close(fd) < 0 ? -errno : 0;
}

static bool same_io(const struct btsensor_modern_backend_io *a,
                    const struct btsensor_modern_backend_io *b)
{
  return a && b && a->open == b->open && a->ioctl == b->ioctl &&
         a->close == b->close && a->context == b->context;
}

static void close_all_ports(void)
{
  if (!g_port_io_valid) return;
  for (uint8_t port = 0; port < BOARD_LEGOPORT_COUNT; port++)
    if (g_port_fds[port] >= 0)
      {
        (void)g_port_io.ioctl(g_port_fds[port], LEGOPORT_PWM_COAST, 0,
                              g_port_io.context);
        (void)g_port_io.close(g_port_fds[port], g_port_io.context);
        g_port_fds[port] = -1;
      }
  g_port_io_valid = false;
}

static int port_open(uint8_t port,
                     const struct btsensor_modern_backend_io *io)
{
  char path[sizeof(BOARD_LEGOPORT_DEVPATH_FMT) + 2];

  if (g_port_io_valid && !same_io(&g_port_io, io)) close_all_ports();
  if (!g_port_io_valid)
    {
      g_port_io = *io;
      g_port_io_valid = true;
    }
  if (g_port_fds[port] >= 0) return g_port_fds[port];
  snprintf(path, sizeof(path), BOARD_LEGOPORT_DEVPATH_FMT, port);
  int fd = io->open(path, O_RDWR | O_NONBLOCK, io->context);
  if (fd >= 0) g_port_fds[port] = fd;
  return fd;
}

static bool passive_motor(uint8_t type)
{
  return type == LEGOPORT_TYPE_LPF2_MMOTOR ||
         type == LEGOPORT_TYPE_LPF2_TRAIN ||
         type == LEGOPORT_TYPE_LPF2_TURN ||
         type == LEGOPORT_TYPE_LPF2_POWER ||
         type == LEGOPORT_TYPE_LPF2_LMOTOR ||
         type == LEGOPORT_TYPE_LPF2_XMOTOR;
}

static int validate_motor(int fd,
                          const struct btsensor_modern_backend_io *io)
{
  struct legoport_info_s port_info;
  struct legoport_pwm_status_s pwm;
  int rc;

  memset(&port_info, 0, sizeof(port_info));
  rc = io->ioctl(fd, LEGOPORT_GET_DEVICE_INFO,
                 (unsigned long)&port_info, io->context);
  if (rc < 0) return rc;
  if (!(port_info.flags & LEGOPORT_FLAG_CONNECTED)) return -ENODEV;
  if (!passive_motor(port_info.device_type))
    {
      struct lump_device_info_s lump;
      if (!(port_info.flags & LEGOPORT_FLAG_IS_UART)) return -ENODEV;
      memset(&lump, 0, sizeof(lump));
      rc = io->ioctl(fd, LEGOPORT_LUMP_GET_INFO, (unsigned long)&lump,
                     io->context);
      if (rc < 0) return rc;
      if (lump.type_id != LPF2_TYPE_SPIKE_MEDIUM_MOTOR &&
          lump.type_id != LPF2_TYPE_SPIKE_LARGE_MOTOR) return -ENODEV;
    }
  memset(&pwm, 0, sizeof(pwm));
  rc = io->ioctl(fd, LEGOPORT_PWM_GET_STATUS, (unsigned long)&pwm,
                 io->context);
  if (rc < 0) return rc;
  return (pwm.flags & LEGOPORT_PWM_FLAG_PINNED) ? -EBUSY : 0;
}

static int motor_operation(const struct btsensor_modern_operation *operation,
                           const struct btsensor_modern_backend_io *io)
{
  int fd;
  int rc;

  if (operation->port >= BOARD_LEGOPORT_COUNT ||
      operation->speed < -100 || operation->speed > 100)
    return -ERANGE;
  if (operation->speed != 0 && operation->has_end_state)
    return -EINVAL;
  if (operation->has_end_state && operation->end_state > 2)
    return -ERANGE;
  if (operation->has_end_state && operation->end_state == 2)
    return -ENOTSUP; /* HOLD needs position feedback and a servo owner. */

  fd = port_open(operation->port, io);
  if (fd < 0) return fd;
  rc = validate_motor(fd, io);
  if (rc < 0) return rc;
  if (operation->speed != 0 || !operation->has_end_state)
    return io->ioctl(fd, LEGOPORT_PWM_SET_DUTY,
                     (unsigned long)(int16_t)(operation->speed * 100),
                     io->context);
  return io->ioctl(fd, operation->end_state == 0 ? LEGOPORT_PWM_COAST
                                                  : LEGOPORT_PWM_BRAKE,
                   0, io->context);
}

static int matrix_operation(const struct btsensor_modern_operation *operation,
                            const struct btsensor_modern_backend_io *io)
{
  struct lump_device_info_s info;
  struct legoport_lump_send_arg_s send;
  int fd;
  int rc;

  if (operation->port >= BOARD_LEGOPORT_COUNT) return -ERANGE;
  for (size_t i = 0; i < sizeof(operation->pixels); i++)
    {
      unsigned brightness = operation->pixels[i] >> 4;
      unsigned color = operation->pixels[i] & 0x0f;
      if (brightness > 10 || color > 10) return -ERANGE;
    }

  fd = port_open(operation->port, io);
  if (fd < 0) return fd;

  memset(&info, 0, sizeof(info));
  rc = io->ioctl(fd, LEGOPORT_LUMP_GET_INFO, (unsigned long)&info,
                 io->context);
  if (rc < 0) return rc;
  if (info.type_id != MATRIX_TYPE_ID) return -ENODEV;
  if (info.num_modes <= MATRIX_PIXELS_MODE ||
      !info.modes[MATRIX_PIXELS_MODE].writable ||
      info.modes[MATRIX_PIXELS_MODE].num_values != 9 ||
      info.modes[MATRIX_PIXELS_MODE].data_type != LUMP_DATA_INT8)
    return -ENOTSUP;

  memset(&send, 0, sizeof(send));
  send.mode = MATRIX_PIXELS_MODE;
  send.len = sizeof(operation->pixels);
  memcpy(send.data, operation->pixels, sizeof(operation->pixels));
  rc = io->ioctl(fd, LEGOPORT_LUMP_SEND, (unsigned long)&send, io->context);
  return rc;
}

void btsensor_modern_backend_reset_with_io(
    const struct btsensor_modern_backend_io *io)
{
  if (io && g_port_io_valid && same_io(&g_port_io, io)) close_all_ports();
}

static int matrix5_operation(const struct btsensor_modern_operation *operation,
                             const struct btsensor_modern_backend_io *io)
{
  struct rgbled_duty_s duty;
  int fd = io->open(RGBLED_DEVPATH, O_RDWR, io->context);
  int rc = 0;
  if (fd < 0) return fd;

  if (operation->kind == BTSENSOR_MODERN_OP_MATRIX5_PIXEL)
    {
      if (operation->x > 4 || operation->y > 4 ||
          operation->brightness > 100)
        rc = -ERANGE;
      if (rc == 0)
        {
          duty.channel = g_matrix5_channels[operation->y][operation->x];
          duty.value = (uint16_t)(((uint32_t)operation->brightness * 65535u) /
                                  100u);
          rc = io->ioctl(fd, RGBLEDIOC_SETDUTY, (unsigned long)&duty,
                         io->context);
        }
    }
  else
    {
      for (unsigned y = 0; y < 5 && rc == 0; y++)
        for (unsigned x = 0; x < 5 && rc == 0; x++)
          {
            duty.channel = g_matrix5_channels[y][x];
            duty.value = 0;
            rc = io->ioctl(fd, RGBLEDIOC_SETDUTY, (unsigned long)&duty,
                           io->context);
          }
    }
  int close_rc = io->close(fd, io->context);
  return rc < 0 ? rc : close_rc;
}

int btsensor_modern_backend_operation_with_io(
    const struct btsensor_modern_operation *operation,
    const struct btsensor_modern_backend_io *io)
{
  if (!operation || !io || !io->open || !io->ioctl || !io->close)
    return -EINVAL;
  switch (operation->kind)
    {
      case BTSENSOR_MODERN_OP_MOTOR:
        return motor_operation(operation, io);
      case BTSENSOR_MODERN_OP_MATRIX3:
        return matrix_operation(operation, io);
      case BTSENSOR_MODERN_OP_MATRIX5_PIXEL:
      case BTSENSOR_MODERN_OP_MATRIX5_CLEAR:
        return matrix5_operation(operation, io);
      case BTSENSOR_MODERN_OP_TUNNEL_OPAQUE:
      default:
        /* Opaque tunnel bytes, including Python source, are data only. */
        return -ENOTSUP;
    }
}

int btsensor_modern_backend_operation(
    const struct btsensor_modern_operation *operation)
{
  return btsensor_modern_backend_operation_for_link(BRICKWRIGHT_HUB_LINK_BLE,
                                                     operation);
}

int btsensor_modern_backend_operation_for_link(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation)
{
  return btsensor_modern_backend_operation_for_link_tagged(link, operation,
                                                            NULL);
}

static void set_motor_owner_locked(enum brickwright_hub_link link,
                                   uint8_t port, bool running,
                                   uint32_t *ownership_token)
{
  for (unsigned other = 0; other < 2; other++)
    {
      g_commanded[other][port] = false;
    }
  g_owner_token[port] = 0;
  if (running)
    {
      if (++g_next_owner_token == 0) ++g_next_owner_token;
      g_commanded[link][port] = true;
      g_owner_token[port] = g_next_owner_token;
      if (ownership_token) *ownership_token = g_next_owner_token;
    }
  else if (ownership_token)
    *ownership_token = 0;
}

int btsensor_modern_backend_operation_for_link_tagged(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation,
    uint32_t *ownership_token)
{
  const struct btsensor_modern_backend_io io =
    {
      .open = production_open,
      .ioctl = production_ioctl,
      .close = production_close,
      .context = NULL,
    };
  if ((unsigned)link > BRICKWRIGHT_HUB_LINK_BLE) return -EINVAL;
  pthread_mutex_lock(&g_owner_lock);
  int rc = btsensor_modern_backend_operation_with_io(operation, &io);
  if (rc == 0 && operation && operation->kind == BTSENSOR_MODERN_OP_MOTOR)
    set_motor_owner_locked(link, operation->port, operation->speed != 0,
                           ownership_token);
  pthread_mutex_unlock(&g_owner_lock);
  return rc;
}

int btsensor_modern_backend_end_motor_if_owned(
    enum brickwright_hub_link link, uint8_t port, uint32_t ownership_token,
    uint8_t end_state)
{
  const struct btsensor_modern_backend_io io =
    { production_open, production_ioctl, production_close, NULL };
  struct btsensor_modern_operation stop =
    { .kind = BTSENSOR_MODERN_OP_MOTOR, .port = port, .speed = 0,
      .has_end_state = true, .end_state = end_state };
  int rc;
  if ((unsigned)link > BRICKWRIGHT_HUB_LINK_BLE ||
      port >= BOARD_LEGOPORT_COUNT || ownership_token == 0)
    return -EINVAL;
  pthread_mutex_lock(&g_owner_lock);
  if (!g_commanded[link][port] ||
      g_owner_token[port] != ownership_token)
    rc = -ESTALE;
  else
    {
      rc = btsensor_modern_backend_operation_with_io(&stop, &io);
      if (rc == 0) set_motor_owner_locked(link, port, false, NULL);
    }
  pthread_mutex_unlock(&g_owner_lock);
  return rc;
}

static void stop_owned_locked(enum brickwright_hub_link link)
{
  const struct btsensor_modern_backend_io io =
    { production_open, production_ioctl, production_close, NULL };
  for (uint8_t port = 0; port < BOARD_LEGOPORT_COUNT; port++)
    if (g_commanded[link][port])
      {
        struct btsensor_modern_operation stop =
          { .kind = BTSENSOR_MODERN_OP_MOTOR, .port = port, .speed = 0,
            .has_end_state = true, .end_state = 0 };
        g_commanded[link][port] = false; /* exactly once, even on I/O error */
        g_owner_token[port] = 0;
        (void)btsensor_modern_backend_operation_with_io(&stop, &io);
      }
}

void btsensor_modern_backend_link_state(enum brickwright_hub_link link,
                                        bool connected, uint32_t generation)
{
  if ((unsigned)link > BRICKWRIGHT_HUB_LINK_BLE) return;
  pthread_mutex_lock(&g_owner_lock);
  if (connected)
    {
      /* Never transfer actuator ownership to a reconnect. If its connect
       * overtakes the old disconnect callback, stop the old generation now. */
      if (g_generation[link] != 0 && g_generation[link] != generation)
        stop_owned_locked(link);
      g_generation[link] = generation;
      pthread_mutex_unlock(&g_owner_lock);
      return;
    }
  if (g_generation[link] == generation) stop_owned_locked(link);
  pthread_mutex_unlock(&g_owner_lock);
}

void btsensor_modern_backend_shutdown(void)
{
  bool stopped[BOARD_LEGOPORT_COUNT] = { false };
  pthread_mutex_lock(&g_owner_lock);
  for (unsigned link = 0; link < 2; link++)
    for (uint8_t port = 0; port < BOARD_LEGOPORT_COUNT; port++)
      if (g_commanded[link][port])
        {
          if (!stopped[port])
            {
              struct btsensor_modern_operation stop =
                { .kind = BTSENSOR_MODERN_OP_MOTOR, .port = port,
                  .has_end_state = true, .end_state = 0 };
              const struct btsensor_modern_backend_io stop_io =
                { production_open, production_ioctl, production_close, NULL };
              (void)btsensor_modern_backend_operation_with_io(&stop, &stop_io);
              stopped[port] = true;
            }
          g_commanded[link][port] = false;
          g_owner_token[port] = 0;
        }
  const struct btsensor_modern_backend_io io =
    {
      .open = production_open, .ioctl = production_ioctl,
      .close = production_close, .context = NULL,
    };
  btsensor_modern_backend_reset_with_io(&io);
  pthread_mutex_unlock(&g_owner_lock);
}
void btsensor_modern_backend_set_motor_owner(enum brickwright_hub_link link,
                                             uint8_t port, bool running)
{
  if ((unsigned)link > BRICKWRIGHT_HUB_LINK_BLE ||
      port >= BOARD_LEGOPORT_COUNT) return;
  pthread_mutex_lock(&g_owner_lock);
  /* The last successful command defines the physical actuator state.  A
   * stop clears any former owner; a nonzero command transfers ownership. */
  set_motor_owner_locked(link, port, running, NULL);
  pthread_mutex_unlock(&g_owner_lock);
}
