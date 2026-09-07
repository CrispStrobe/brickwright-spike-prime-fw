/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <brickwright/h4_transport.h>
static const uint8_t incoming[] = {0x04, 0x0e, 0x02, 0x01, 0x00};
static uint8_t outgoing[8];
static size_t outgoing_length;
static int writes;
static int received;
static int reads;
int brickwright_h4_io_open(const char *path, int flags)
{ assert(strcmp(path, "virtual") == 0 && flags); return 7; }
int brickwright_h4_io_close(int fd) { assert(fd == 7); return 0; }
ssize_t brickwright_h4_io_read(int fd, void *data, size_t length)
{
  assert(fd == 7);
  ++reads;
  if (reads == 1) {
    assert(length >= sizeof(incoming));
    memcpy(data, incoming, sizeof(incoming));
    return sizeof(incoming);
  }
  assert(length >= 1 && reads <= 3);
  *(uint8_t *)data = reads == 2 ? BRICKWRIGHT_EHCILL_SLEEP_IND :
                                 BRICKWRIGHT_EHCILL_WAKE_ACK;
  return 1;
}
ssize_t brickwright_h4_io_write(int fd, const void *data, size_t length)
{
  assert(fd == 7);
  ++writes;
  if (writes == 1) { errno = EINTR; return -1; }
  size_t count = length > 2 ? 2 : length;
  memcpy(outgoing + outgoing_length, data, count);
  outgoing_length += count;
  return (ssize_t)count;
}
int brickwright_h4_io_poll(int fd, short events, int timeout_ms)
{ assert(fd == 7 && events && timeout_ms == 25); return 0; }
int brickwright_h4_io_ioctl(int fd, int request, unsigned long argument)
{ assert(fd == 7 && request == 42 && argument == 115200); return 0; }
static int receive(uint8_t type, const uint8_t *packet, size_t length, void *context)
{ assert(type == 0x04 && length == 4 && packet[0] == 0x0e && context == incoming); ++received; return 0; }
int main(void)
{
  struct brickwright_h4_transport transport = {.fd = -1};
  assert(brickwright_h4_transport_open(&transport, "virtual", receive,
                                       (void *)incoming) == 0);
  assert(brickwright_h4_transport_receive(&transport, 25) == 0 && received == 1);
  assert(brickwright_h4_transport_receive(&transport, 25) == 0);
  assert(outgoing_length == 1 && outgoing[0] == BRICKWRIGHT_EHCILL_SLEEP_ACK);
  const uint8_t frame[] = {0x01, 0x03, 0x0c, 0x00};
  assert(brickwright_h4_transport_send(&transport, frame, sizeof(frame), 25) == 0);
  assert(outgoing_length == 2 && outgoing[1] == BRICKWRIGHT_EHCILL_WAKE_IND);
  assert(brickwright_h4_transport_receive(&transport, 25) == 0);
  assert(outgoing_length == 2 + sizeof(frame));
  assert(!memcmp(outgoing + 2, frame, sizeof(frame)));
  assert(brickwright_h4_transport_ioctl(&transport, 42, 115200) == 0);
  assert(brickwright_h4_transport_close(&transport) == 0 && transport.fd == -1);
  return 0;
}
