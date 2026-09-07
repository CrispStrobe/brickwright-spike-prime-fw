/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>
#include <brickwright/controller_lifecycle.h>
#include <brickwright/h4_netbuf.h>
#include <brickwright/h4_transport.h>
#include <brickwright/hci_driver.h>
#include <brickwright/virtual_hci.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/device.h>
#include <zephyr/drivers/bluetooth.h>
#include <zephyr/net_buf.h>
#include "../../ti_service_pack/ti_bts_loader.h"

#ifdef __NuttX__
#include <fcntl.h>
#include <nuttx/fs/ioctl.h>
#define BRICKWRIGHT_BTUART_SETBAUD _BLUETOOTHIOC(0x40)
#define BRICKWRIGHT_BTUART_CHIPRESET _BLUETOOTHIOC(0x41)
#endif

#define PHYSICAL_BOOT_BAUD 115200u
#define PHYSICAL_RECOVERIES 3u

__attribute__((weak)) int brickwright_hci_platform_power_cycle(const char *path)
{
#ifdef __NuttX__
  int fd = brickwright_h4_io_open(path, O_RDWR | O_NONBLOCK);
  if (fd < 0)
    {
      return -errno;
    }
  int result = brickwright_h4_io_ioctl(fd, BRICKWRIGHT_BTUART_CHIPRESET, 0);
  int saved = result < 0 ? errno : 0;
  (void)brickwright_h4_io_close(fd);
  return result < 0 ? -saved : 0;
#else
  (void)path;
  return -ENOSYS;
#endif
}

__attribute__((weak)) int brickwright_hci_platform_service_pack(
  const uint8_t **image, size_t *length)
{
  (void)image;
  (void)length;
  return -ENOENT;
}

__attribute__((weak)) int brickwright_hci_platform_set_serial(
  int fd, uint32_t baud, uint32_t flow_control)
{
#ifdef __NuttX__
  (void)flow_control;
  int result = brickwright_h4_io_ioctl(fd, BRICKWRIGHT_BTUART_SETBAUD,
                                       (unsigned long)baud);
  return result < 0 ? -errno : 0;
#else
  (void)fd;
  (void)baud;
  (void)flow_control;
  return -ENOSYS;
#endif
}

__attribute__((weak)) int brickwright_hci_platform_delay_ms(
  uint32_t duration_ms)
{
  struct timespec duration = {
    .tv_sec = duration_ms / 1000,
    .tv_nsec = (long)(duration_ms % 1000) * 1000000L
  };
  while (nanosleep(&duration, &duration) != 0)
    {
      if (errno != EINTR)
        {
          return -errno;
        }
    }
  return 0;
}

struct driver_state
{
  enum brickwright_hci_backend backend;
  const char *path;
  uint8_t address[6];
  bt_hci_recv_t receive;
  struct brickwright_h4_netbuf bridge;
  struct brickwright_h4_transport transport;
  struct brickwright_virtual_hci virtual_controller;
  struct brickwright_controller controller;
  pthread_t receive_thread;
  pthread_mutex_t physical_mutex;
  pthread_mutex_t virtual_mutex;
  pthread_cond_t virtual_changed;
  uint8_t virtual_frame[71];
  size_t virtual_length;
  bool open;
  bool stopping;
  unsigned int host_acl_generation;
  unsigned int virtual_enqueued_generation;
  unsigned int virtual_received_generation;
  uint8_t host_acl_queue[4][1025];
  size_t host_acl_lengths[4];
  unsigned int host_acl_completions[4];
  unsigned int host_acl_head;
  unsigned int host_acl_count;
  uint8_t init_event[260];
  size_t init_event_length;
};

static struct driver_state state = {
#ifdef __NuttX__
  .backend = BRICKWRIGHT_HCI_BACKEND_PHYSICAL,
#else
  .backend = BRICKWRIGHT_HCI_BACKEND_VIRTUAL,
#endif
  .path = "/dev/ttyBT",
  .transport = {.fd = -1},
  .virtual_mutex = PTHREAD_MUTEX_INITIALIZER,
  .virtual_changed = PTHREAD_COND_INITIALIZER,
  .physical_mutex = PTHREAD_MUTEX_INITIALIZER
};

static int deliver(struct net_buf *buffer, void *context)
{
  struct driver_state *driver = context;
  return driver->receive(&brickwright_hci_device, buffer);
}

static int collect_init_event(uint8_t type, const uint8_t *packet,
                              size_t length, void *context)
{
  struct driver_state *driver = context;
  if (type != BT_HCI_H4_EVT || length + 1 > sizeof(driver->init_event))
    {
      return -EPROTO;
    }
  driver->init_event[0] = type;
  memcpy(driver->init_event + 1, packet, length);
  driver->init_event_length = length + 1;
  return 0;
}

static int init_send(void *context, const uint8_t *command, size_t length)
{
  struct driver_state *driver = context;
  return brickwright_h4_transport_send(&driver->transport, command, length,
                                       1000);
}

static int init_receive(void *context, uint8_t *event, size_t capacity,
                        size_t *length, uint32_t timeout_ms)
{
  struct driver_state *driver = context;
  driver->init_event_length = 0;
  while (!driver->init_event_length)
    {
      int result = brickwright_h4_transport_receive(&driver->transport,
                                                     (int)timeout_ms);
      if (result != 0)
        {
          return result;
        }
    }
  if (driver->init_event_length > capacity)
    {
      return -EMSGSIZE;
    }
  memcpy(event, driver->init_event, driver->init_event_length);
  *length = driver->init_event_length;
  return 0;
}

static int init_set_serial(void *context, uint32_t baud,
                           uint32_t flow_control)
{
  struct driver_state *driver = context;
  return brickwright_hci_platform_set_serial(driver->transport.fd, baud,
                                              flow_control);
}

static int init_delay(void *context, uint32_t duration_ms)
{
  (void)context;
  return brickwright_hci_platform_delay_ms(duration_ms);
}

static int physical_power_cycle(void *context)
{
  struct driver_state *driver = context;
  return brickwright_hci_platform_power_cycle(driver->path);
}

static int physical_open(void *context, uint32_t baud)
{
  struct driver_state *driver = context;
  (void)baud;
  int result = brickwright_h4_transport_open(&driver->transport, driver->path,
                                              collect_init_event, driver);
  if (result == 0)
    {
      brickwright_h4_init(&driver->transport.h4, collect_init_event, driver);
    }
  return result;
}

static int physical_load_firmware(void *context)
{
  struct driver_state *driver = context;
  const uint8_t *image = NULL;
  size_t length = 0;
  int result = brickwright_hci_platform_service_pack(&image, &length);
  if (result != 0 || !image || !length)
    {
      return result != 0 ? result : -ENOENT;
    }
  const struct ti_bts_transport transport = {
    .send_command = init_send,
    .receive_event = init_receive,
    .set_serial = init_set_serial,
    .delay_ms = init_delay,
    .context = driver
  };
  result = ti_bts_execute(image, length, &transport, NULL);
  return result == TI_BTS_OK ? 0 : -EIO;
}

static int physical_unused_baud(void *context, uint32_t baud)
{
  (void)context;
  (void)baud;
  /* BTS SERIAL actions own the paired controller/host baud transition. */
  return 0;
}

static int physical_start_host(void *context)
{
  struct driver_state *driver = context;
  brickwright_h4_init(&driver->transport.h4, brickwright_h4_netbuf_receive,
                      &driver->bridge);
  return 0;
}

static int physical_stop_host(void *context)
{
  (void)context;
  return 0;
}

static void physical_close(void *context)
{
  struct driver_state *driver = context;
  (void)brickwright_h4_transport_close(&driver->transport);
}

static const struct brickwright_controller_ops physical_ops = {
  .power_cycle = physical_power_cycle,
  .open = physical_open,
  .load_firmware = physical_load_firmware,
  .set_controller_baud = physical_unused_baud,
  .set_host_baud = physical_unused_baud,
  .start_host = physical_start_host,
  .stop_host = physical_stop_host,
  .close = physical_close
};

static int virtual_send(const uint8_t *frame, size_t length, void *context)
{
  struct driver_state *driver = context;
  if (length > sizeof(driver->virtual_frame))
    {
      return -EMSGSIZE;
    }
  pthread_mutex_lock(&driver->virtual_mutex);
  while (driver->virtual_length && !driver->stopping)
    {
      pthread_cond_wait(&driver->virtual_changed, &driver->virtual_mutex);
    }
  if (driver->stopping)
    {
      pthread_mutex_unlock(&driver->virtual_mutex);
      return -ESHUTDOWN;
    }
  memcpy(driver->virtual_frame, frame, length);
  driver->virtual_length = length;
  ++driver->virtual_enqueued_generation;
  pthread_cond_signal(&driver->virtual_changed);
  pthread_mutex_unlock(&driver->virtual_mutex);
  return 0;
}

static void *receive_main(void *context)
{
  struct driver_state *driver = context;
  if (driver->backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      for (;;)
        {
          uint8_t frame[sizeof(driver->virtual_frame)];
          pthread_mutex_lock(&driver->virtual_mutex);
          while (!driver->virtual_length && !driver->stopping)
            {
              pthread_cond_wait(&driver->virtual_changed,
                                &driver->virtual_mutex);
            }
          if (driver->stopping)
            {
              pthread_mutex_unlock(&driver->virtual_mutex);
              break;
            }
          size_t length = driver->virtual_length;
          memcpy(frame, driver->virtual_frame, length);
          driver->virtual_length = 0;
          pthread_cond_signal(&driver->virtual_changed);
          pthread_mutex_unlock(&driver->virtual_mutex);
          (void)brickwright_h4_feed(&driver->transport.h4, frame, length);
          pthread_mutex_lock(&driver->virtual_mutex);
          ++driver->virtual_received_generation;
          pthread_cond_broadcast(&driver->virtual_changed);
          pthread_mutex_unlock(&driver->virtual_mutex);
        }
      return NULL;
    }
  while (!driver->stopping)
    {
      int result = brickwright_h4_transport_receive(&driver->transport, 100);
      int fault = brickwright_h4_transport_fault(&driver->transport);
      if (fault != 0 && !driver->stopping)
        {
          pthread_mutex_lock(&driver->physical_mutex);
          result = brickwright_controller_recover(&driver->controller);
          pthread_mutex_unlock(&driver->physical_mutex);
        }
      if (result != 0 && result != -ETIMEDOUT && result != -EAGAIN)
        {
          break;
        }
    }
  return NULL;
}

static int driver_open(const struct device *device, bt_hci_recv_t receive)
{
  (void)device;
  if (!receive || state.open)
    {
      return -EINVAL;
    }
  state.receive = receive;
  state.bridge.receive = deliver;
  state.bridge.context = &state;
  state.bridge.allocation_timeout = K_FOREVER;
  brickwright_h4_init(&state.transport.h4, brickwright_h4_netbuf_receive,
                      &state.bridge);
  state.transport.fd = -1;
  state.stopping = false;
  state.virtual_length = 0;
  state.host_acl_head = 0;
  state.host_acl_count = 0;
  if (state.backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      brickwright_virtual_hci_init(&state.virtual_controller, state.address,
                                   virtual_send, &state);
    }
  else
    {
      const struct brickwright_controller_config config = {
        .boot_baud = PHYSICAL_BOOT_BAUD,
        .operational_baud = PHYSICAL_BOOT_BAUD,
        .max_recoveries = PHYSICAL_RECOVERIES
      };
      int result = brickwright_controller_init(&state.controller, &config,
                                                &physical_ops, &state);
      if (result == 0)
        {
          result = brickwright_controller_start(&state.controller);
        }
      if (result != 0)
        {
          state.receive = NULL;
          return result;
        }
    }
  if (pthread_create(&state.receive_thread, NULL, receive_main, &state) != 0)
    {
      if (state.backend == BRICKWRIGHT_HCI_BACKEND_PHYSICAL)
        {
          (void)brickwright_controller_shutdown(&state.controller);
        }
      return -EIO;
    }
  state.open = true;
  return 0;
}

static int driver_close(const struct device *device)
{
  (void)device;
  if (!state.open)
    {
      return -EINVAL;
    }
  state.stopping = true;
  if (state.backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      pthread_mutex_lock(&state.virtual_mutex);
      pthread_cond_broadcast(&state.virtual_changed);
      pthread_mutex_unlock(&state.virtual_mutex);
    }
  pthread_join(state.receive_thread, NULL);
  if (state.backend == BRICKWRIGHT_HCI_BACKEND_PHYSICAL)
    {
      (void)brickwright_controller_shutdown(&state.controller);
    }
  state.open = false;
  state.receive = NULL;
  return 0;
}

static int driver_send(const struct device *device, struct net_buf *buffer)
{
  (void)device;
  if (!state.open || !buffer)
    {
      return -EINVAL;
    }
  int result = state.backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL ?
    brickwright_virtual_hci_feed(&state.virtual_controller, buffer->data,
                                 buffer->len) :
    0;
  if (state.backend == BRICKWRIGHT_HCI_BACKEND_PHYSICAL)
    {
      pthread_mutex_lock(&state.physical_mutex);
      result = state.controller.state == BRICKWRIGHT_CONTROLLER_READY ?
        brickwright_h4_transport_send(&state.transport, buffer->data,
                                      buffer->len, 1000) : -ENETDOWN;
      pthread_mutex_unlock(&state.physical_mutex);
    }
  if (result == 0 && state.backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL &&
      buffer->len && buffer->data[0] == BT_HCI_H4_ACL)
    {
      pthread_mutex_lock(&state.virtual_mutex);
      unsigned int tail = (state.host_acl_head + state.host_acl_count) % 4;
      if (state.host_acl_count == 4)
        {
          state.host_acl_head = (state.host_acl_head + 1) % 4;
          tail = (state.host_acl_head + state.host_acl_count - 1) % 4;
        }
      else
        {
          ++state.host_acl_count;
        }
      size_t acl_length = state.virtual_controller.host_acl_length;
      memcpy(state.host_acl_queue[tail], state.virtual_controller.host_acl,
             acl_length);
      state.host_acl_lengths[tail] = acl_length;
      state.host_acl_completions[tail] = state.virtual_enqueued_generation;
      ++state.host_acl_generation;
      pthread_cond_broadcast(&state.virtual_changed);
      pthread_mutex_unlock(&state.virtual_mutex);
    }
  if (result == 0)
    {
      net_buf_unref(buffer);
    }
  return result;
}

static const struct bt_hci_driver_api driver_api = {
  .open = driver_open,
  .close = driver_close,
  .send = driver_send
};

const struct device brickwright_hci_device = {
  .api = &driver_api,
  .data = &state
};

int brickwright_hci_configure(enum brickwright_hci_backend backend,
                              const char *path, const uint8_t address[6])
{
  if (state.open ||
      (backend != BRICKWRIGHT_HCI_BACKEND_PHYSICAL &&
       backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL) ||
      (backend == BRICKWRIGHT_HCI_BACKEND_PHYSICAL && !path) ||
      (backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL && !address))
    {
      return -EINVAL;
    }
  state.backend = backend;
  if (path)
    {
      state.path = path;
    }
  if (address)
    {
      memcpy(state.address, address, sizeof(state.address));
    }
  return 0;
}

bool brickwright_hci_virtual_is_advertising(void)
{
  return state.backend == BRICKWRIGHT_HCI_BACKEND_VIRTUAL &&
         state.virtual_controller.advertising;
}

int brickwright_hci_virtual_connect(const uint8_t peer_address[6])
{
  if (!state.open || state.backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      return -ENODEV;
    }
  return brickwright_virtual_hci_connect(&state.virtual_controller,
                                         peer_address);
}

int brickwright_hci_virtual_disconnect(uint8_t reason)
{
  if (!state.open || state.backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      return -ENODEV;
    }
  return brickwright_virtual_hci_disconnect(&state.virtual_controller, reason);
}

int brickwright_hci_virtual_send_acl(const void *payload, size_t length)
{
  if (!state.open || state.backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      return -ENODEV;
    }
  return brickwright_virtual_hci_send_acl(&state.virtual_controller, payload,
                                          length);
}

int brickwright_hci_virtual_request_ltk(const uint8_t expected_ltk[16])
{
  if (!state.open || state.backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      return -ENODEV;
    }
  return brickwright_virtual_hci_request_ltk(&state.virtual_controller,
                                              expected_ltk);
}

int brickwright_hci_virtual_take_host_acl(void *buffer, size_t capacity,
                                          size_t *length, int timeout_ms)
{
  if (!buffer || !length || timeout_ms < 0 || !state.open ||
      state.backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      return -EINVAL;
    }
  pthread_mutex_lock(&state.virtual_mutex);
  unsigned int generation = state.host_acl_generation;
  if (!state.host_acl_count)
    {
      struct timespec deadline;
      clock_gettime(CLOCK_REALTIME, &deadline);
      deadline.tv_sec += timeout_ms / 1000;
      deadline.tv_nsec += (timeout_ms % 1000) * 1000000;
      if (deadline.tv_nsec >= 1000000000)
        {
          ++deadline.tv_sec;
          deadline.tv_nsec -= 1000000000;
        }
      while (generation == state.host_acl_generation)
        {
          int result = pthread_cond_timedwait(&state.virtual_changed,
                                              &state.virtual_mutex, &deadline);
          if (result == ETIMEDOUT)
            {
              pthread_mutex_unlock(&state.virtual_mutex);
              return -ETIMEDOUT;
            }
        }
    }
  unsigned int head = state.host_acl_head;
  size_t available = state.host_acl_lengths[head];
  if (available > capacity)
    {
      pthread_mutex_unlock(&state.virtual_mutex);
      return -EMSGSIZE;
    }
  memcpy(buffer, state.host_acl_queue[head], available);
  state.host_acl_head = (head + 1) % 4;
  --state.host_acl_count;
  *length = available;
  unsigned int completion = state.host_acl_completions[head];
  while (state.virtual_received_generation < completion)
    {
      pthread_cond_wait(&state.virtual_changed, &state.virtual_mutex);
    }
  pthread_mutex_unlock(&state.virtual_mutex);
  return 0;
}

int brickwright_hci_virtual_classic_connection_request(
  const uint8_t peer_address[6])
{
  if (!state.open || state.backend != BRICKWRIGHT_HCI_BACKEND_VIRTUAL)
    {
      return -ENODEV;
    }
  return brickwright_virtual_hci_classic_connection_request(
    &state.virtual_controller, peer_address);
}
