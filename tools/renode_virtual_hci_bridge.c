/* SPDX-License-Identifier: Apache-2.0 */
#include <brickwright/virtual_hci.h>

#include <errno.h>
#include <netdb.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

struct bridge {
  int fd;
  bool trace;
  uint8_t trace_command[4 + UINT8_MAX];
  size_t trace_command_length;
};

static void trace_bytes(const char *direction, const uint8_t *bytes,
                        size_t length)
{
  fprintf(stderr, "%s [%zu]", direction, length);
  for (size_t index = 0; index < length; ++index)
    {
      fprintf(stderr, " %02x", bytes[index]);
    }
  if (length >= 4 && bytes[0] == 0x01)
    {
      fprintf(stderr, " command=0x%02x%02x params=%u",
              bytes[2], bytes[1], bytes[3]);
    }
  else if (length >= 3 && bytes[0] == 0x04)
    {
      fprintf(stderr, " event=0x%02x params=%u", bytes[1], bytes[2]);
      if (bytes[1] == 0x0e && length >= 7)
        {
          fprintf(stderr, " opcode=0x%02x%02x status=0x%02x",
                  bytes[5], bytes[4], bytes[6]);
        }
      else if (bytes[1] == 0x0f && length >= 7)
        {
          fprintf(stderr, " opcode=0x%02x%02x status=0x%02x",
                  bytes[6], bytes[5], bytes[3]);
        }
    }
  fputc('\n', stderr);
  fflush(stderr);
}

static void trace_command_feed(struct bridge *bridge, const uint8_t *bytes,
                               size_t length)
{
  for (size_t index = 0; index < length; ++index)
    {
      if (bridge->trace_command_length == 0 && bytes[index] != 0x01)
        {
          fprintf(stderr, "uart -> controller: unexpected H4 type 0x%02x\n",
                  bytes[index]);
          continue;
        }
      bridge->trace_command[bridge->trace_command_length++] = bytes[index];
      if (bridge->trace_command_length >= 4 &&
          bridge->trace_command_length ==
            (size_t)4 + bridge->trace_command[3])
        {
          trace_bytes("uart -> controller", bridge->trace_command,
                      bridge->trace_command_length);
          bridge->trace_command_length = 0;
        }
    }
}

static int write_all(const uint8_t *bytes, size_t length, void *context)
{
  struct bridge *bridge = context;
  size_t offset = 0;
  while (offset < length)
    {
      ssize_t written = send(bridge->fd, bytes + offset, length - offset,
                             MSG_NOSIGNAL);
      if (written < 0 && errno == EINTR)
        continue;
      if (written <= 0)
        return -EIO;
      offset += (size_t)written;
    }
  if (bridge->trace)
    {
      trace_bytes("controller -> uart", bytes, length);
    }
  return 0;
}

static int connect_retry(const char *host, const char *service)
{
  struct addrinfo hints = {0};
  struct addrinfo *addresses = NULL;
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  int result = getaddrinfo(host, service, &hints, &addresses);
  if (result != 0)
    return -EINVAL;

  int fd = -1;
  for (unsigned attempt = 0; attempt < 100 && fd < 0; ++attempt)
    {
      for (struct addrinfo *address = addresses; address;
           address = address->ai_next)
        {
          fd = socket(address->ai_family, address->ai_socktype,
                      address->ai_protocol);
          if (fd >= 0 && connect(fd, address->ai_addr,
                                 address->ai_addrlen) == 0)
            break;
          if (fd >= 0)
            close(fd);
          fd = -1;
        }
      if (fd < 0)
        {
          const struct timespec delay = {.tv_nsec = 50000000};
          nanosleep(&delay, NULL);
        }
    }
  freeaddrinfo(addresses);
  return fd < 0 ? -ECONNREFUSED : fd;
}

static void usage(const char *program)
{
  fprintf(stderr, "Usage: %s [--trace] HOST PORT\n", program);
}

int main(int argc, char **argv)
{
  bool trace = false;
  int arg = 1;
  if (arg < argc && strcmp(argv[arg], "--trace") == 0)
    {
      trace = true;
      ++arg;
    }
  if (argc - arg != 2)
    {
      usage(argv[0]);
      return 2;
    }

  int fd = connect_retry(argv[arg], argv[arg + 1]);
  if (fd < 0)
    {
      fprintf(stderr, "virtual HCI: cannot connect to %s:%s\n",
              argv[arg], argv[arg + 1]);
      return 1;
    }

  struct bridge bridge = {.fd = fd, .trace = trace};
  struct brickwright_virtual_hci controller;
  const uint8_t address[6] = {0x06, 0x05, 0x04, 0x03, 0x02, 0x01};
  brickwright_virtual_hci_init(&controller, address, write_all, &bridge);
  brickwright_virtual_hci_acknowledge_vendor_commands(&controller, true);

  uint8_t buffer[1024];
  for (;;)
    {
      ssize_t length = recv(fd, buffer, sizeof(buffer), 0);
      if (length < 0 && errno == EINTR)
        continue;
      if (length == 0)
        break;
      if (length > 0 && trace)
        {
          trace_command_feed(&bridge, buffer, (size_t)length);
        }
      if (length < 0 || brickwright_virtual_hci_feed(
                            &controller, buffer, (size_t)length) != 0)
        {
          close(fd);
          return 1;
        }
    }
  close(fd);
  return 0;
}
