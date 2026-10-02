/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <brickwright/h4_transport.h>
__attribute__((weak)) int brickwright_h4_io_open(const char *path, int flags)
{ return open(path, flags); }
__attribute__((weak)) int brickwright_h4_io_close(int fd) { return close(fd); }
__attribute__((weak)) ssize_t brickwright_h4_io_read(int fd, void *data, size_t length)
{ return read(fd, data, length); }
__attribute__((weak)) ssize_t brickwright_h4_io_write(int fd, const void *data, size_t length)
{ return write(fd, data, length); }
__attribute__((weak)) int brickwright_h4_io_poll(int fd, short events, int timeout_ms)
{
  struct pollfd descriptor = {.fd = fd, .events = events};
  int result;
  do result = poll(&descriptor, 1, timeout_ms); while (result < 0 && errno == EINTR);
  if (result < 0) return -errno;
  if (!result) return -ETIMEDOUT;
  if (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) return -EIO;
  return descriptor.revents & events ? 0 : -EAGAIN;
}
__attribute__((weak)) int brickwright_h4_io_ioctl(int fd, int request,
                                                   unsigned long argument)
{ return ioctl(fd, request, argument); }

static int raw_write(const uint8_t *data, size_t length, void *context)
{
  struct brickwright_h4_transport *transport = context;
  while (length) {
    ssize_t count = brickwright_h4_io_write(transport->fd, data, length);
    if (count < 0 && errno == EINTR) continue;
    if (count < 0 && errno == EAGAIN) {
      int result = brickwright_h4_io_poll(transport->fd, POLLOUT,
                                           transport->write_timeout_ms);
      if (result) return result;
      continue;
    }
    if (count <= 0) return count < 0 ? -errno : -EIO;
    data += count;
    length -= (size_t)count;
  }
  return 0;
}

static int get_fault(struct brickwright_h4_transport *transport)
{
  pthread_mutex_lock(&transport->lock);
  int result = transport->fault;
  pthread_mutex_unlock(&transport->lock);
  return result;
}

static int latch_fault(struct brickwright_h4_transport *transport, int fault)
{
  pthread_mutex_lock(&transport->lock);
  if (!transport->fault)
    transport->fault = fault;
  int result = transport->fault;
  pthread_mutex_unlock(&transport->lock);
  return result;
}

int brickwright_h4_transport_open(struct brickwright_h4_transport *transport,
                                  const char *path,
                                  brickwright_h4_packet_cb receive, void *context)
{
  if (!transport || !path || !receive) return -EINVAL;
  transport->fd = brickwright_h4_io_open(path, O_RDWR | O_NONBLOCK);
  if (transport->fd < 0) return -errno;
  brickwright_h4_init(&transport->h4, receive, context);
  brickwright_ehcill_init(&transport->ehcill, &transport->h4, raw_write,
                          transport);
  transport->fault = 0;
  int mutex_result = pthread_mutex_init(&transport->lock, NULL);
  if (mutex_result != 0) {
    brickwright_h4_io_close(transport->fd);
    transport->fd = -1;
    return -mutex_result;
  }
  return 0;
}
int brickwright_h4_transport_close(struct brickwright_h4_transport *transport)
{
  if (!transport || transport->fd < 0) return -EINVAL;
  pthread_mutex_lock(&transport->lock);
  brickwright_ehcill_abort(&transport->ehcill);
  pthread_mutex_unlock(&transport->lock);
  int result = brickwright_h4_io_close(transport->fd);
  transport->fd = -1;
  pthread_mutex_destroy(&transport->lock);
  return result < 0 ? -errno : 0;
}
int brickwright_h4_transport_receive(struct brickwright_h4_transport *transport,
                                     int timeout_ms)
{
  if (!transport || transport->fd < 0) return -EINVAL;
  int fault = get_fault(transport);
  if (fault) return fault;
  int result = brickwright_h4_io_poll(transport->fd, POLLIN, timeout_ms);
  if (result) {
    pthread_mutex_lock(&transport->lock);
    bool waking = transport->ehcill.state == BRICKWRIGHT_EHCILL_WAKING;
    pthread_mutex_unlock(&transport->lock);
    if (result == -ETIMEDOUT && !waking)
      return result;
    if (result != -EAGAIN)
      return latch_fault(transport, result);
    return -EAGAIN;
  }
  uint8_t bytes[128];
  ssize_t count;
  do count = brickwright_h4_io_read(transport->fd, bytes, sizeof(bytes));
  while (count < 0 && errno == EINTR);
  if (count < 0) {
    result = errno == EAGAIN ? -EAGAIN : -errno;
    return result == -EAGAIN ? result : latch_fault(transport, result);
  }
  if (!count) return latch_fault(transport, -EPIPE);
  for (ssize_t index = 0; index < count; ++index) {
    bool control = !transport->h4.type &&
      bytes[index] >= BRICKWRIGHT_EHCILL_SLEEP_IND &&
      bytes[index] <= BRICKWRIGHT_EHCILL_WAKE_ACK;
    if (control) {
      pthread_mutex_lock(&transport->lock);
      transport->write_timeout_ms = timeout_ms;
    }
    int feed_result = brickwright_ehcill_feed(&transport->ehcill,
                                               &bytes[index], 1);
    if (control) {
      if (feed_result && !transport->fault)
        transport->fault = feed_result;
      pthread_mutex_unlock(&transport->lock);
    }
    if (feed_result) {
      return control ? feed_result : latch_fault(transport, feed_result);
    }
  }
  return 0;
}
int brickwright_h4_transport_send(struct brickwright_h4_transport *transport,
                                  const void *frame, size_t length, int timeout_ms)
{
  if (!transport || transport->fd < 0 || (!frame && length) || !length) return -EINVAL;
  pthread_mutex_lock(&transport->lock);
  if (transport->fault) {
    int fault = transport->fault;
    pthread_mutex_unlock(&transport->lock);
    return fault;
  }
  transport->write_timeout_ms = timeout_ms;
  int result = brickwright_ehcill_send(&transport->ehcill, frame, length);
  if (result != 0 && result != -ENOBUFS)
    transport->fault = result;
  pthread_mutex_unlock(&transport->lock);
  return result;
}

int brickwright_h4_transport_fault(struct brickwright_h4_transport *transport)
{
  return transport ? get_fault(transport) : -EINVAL;
}
int brickwright_h4_transport_ioctl(struct brickwright_h4_transport *transport,
                                   int request, unsigned long argument)
{
  if (!transport || transport->fd < 0) return -EINVAL;
  return brickwright_h4_io_ioctl(transport->fd, request, argument) < 0 ? -errno : 0;
}
