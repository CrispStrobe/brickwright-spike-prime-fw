/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <string.h>

#include <brickwright/h4_transport.h>

static uint8_t incoming;
static uint8_t outgoing[32];
static size_t outgoing_length;
static int poll_result;
static int read_error;
static int closes;

int brickwright_h4_io_open(const char *path, int flags)
{
  assert(!strcmp(path, "fault-test") && flags);
  return 9;
}

int brickwright_h4_io_close(int fd)
{
  assert(fd == 9);
  ++closes;
  return 0;
}

ssize_t brickwright_h4_io_read(int fd, void *data, size_t length)
{
  assert(fd == 9 && length);
  if (read_error) {
    errno = read_error;
    return -1;
  }
  *(uint8_t *)data = incoming;
  return 1;
}

ssize_t brickwright_h4_io_write(int fd, const void *data, size_t length)
{
  assert(fd == 9 && outgoing_length + length <= sizeof(outgoing));
  memcpy(outgoing + outgoing_length, data, length);
  outgoing_length += length;
  return (ssize_t)length;
}

int brickwright_h4_io_poll(int fd, short events, int timeout_ms)
{
  assert(fd == 9 && events && timeout_ms == 20);
  return poll_result;
}

int brickwright_h4_io_ioctl(int fd, int request, unsigned long argument)
{
  (void)fd; (void)request; (void)argument;
  return 0;
}

static int receive(uint8_t type, const uint8_t *packet, size_t length,
                   void *context)
{
  (void)type; (void)packet; (void)length; (void)context;
  assert(false);
  return 0;
}

static void open_transport(struct brickwright_h4_transport *transport)
{
  assert(brickwright_h4_transport_open(transport, "fault-test", receive,
                                       NULL) == 0);
  assert(brickwright_h4_transport_fault(transport) == 0);
}

static void enter_waking(struct brickwright_h4_transport *transport)
{
  const uint8_t command[] = {0x01, 0x03, 0x0c, 0x00};
  incoming = BRICKWRIGHT_EHCILL_SLEEP_IND;
  assert(brickwright_h4_transport_receive(transport, 20) == 0);
  assert(brickwright_h4_transport_send(transport, command, sizeof(command),
                                       20) == 0);
  assert(transport->ehcill.state == BRICKWRIGHT_EHCILL_WAKING);
}

int main(void)
{
  struct brickwright_h4_transport transport = {.fd = -1};

  /* Closing during a wake handshake discards retained traffic safely. */
  open_transport(&transport);
  enter_waking(&transport);
  assert(transport.ehcill.pending_length != 0);
  assert(brickwright_h4_transport_close(&transport) == 0);
  assert(transport.ehcill.pending_length == 0);

  /* A missing wake ACK becomes a sticky fault for lifecycle recovery. */
  outgoing_length = 0;
  open_transport(&transport);
  enter_waking(&transport);
  poll_result = -ETIMEDOUT;
  assert(brickwright_h4_transport_receive(&transport, 20) == -ETIMEDOUT);
  assert(brickwright_h4_transport_fault(&transport) == -ETIMEDOUT);
  assert(brickwright_h4_transport_receive(&transport, 20) == -ETIMEDOUT);
  assert(brickwright_h4_transport_close(&transport) == 0);

  /* Reopen is the explicit recovery boundary and clears the prior fault. */
  poll_result = 0;
  open_transport(&transport);
  read_error = EIO;
  assert(brickwright_h4_transport_receive(&transport, 20) == -EIO);
  assert(brickwright_h4_transport_fault(&transport) == -EIO);
  assert(brickwright_h4_transport_close(&transport) == 0);

  /* An impossible sleep ACK is a protocol fault, not H4 packet data. */
  read_error = 0;
  open_transport(&transport);
  incoming = BRICKWRIGHT_EHCILL_SLEEP_ACK;
  assert(brickwright_h4_transport_receive(&transport, 20) == -EPROTO);
  assert(brickwright_h4_transport_fault(&transport) == -EPROTO);
  assert(brickwright_h4_transport_close(&transport) == 0);

  /* A sleep request racing our wake request also signals recovery. */
  open_transport(&transport);
  enter_waking(&transport);
  incoming = BRICKWRIGHT_EHCILL_SLEEP_IND;
  assert(brickwright_h4_transport_receive(&transport, 20) == -EPROTO);
  assert(brickwright_h4_transport_close(&transport) == 0);
  assert(closes == 5);
  return 0;
}
