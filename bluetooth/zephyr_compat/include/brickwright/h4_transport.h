/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_H4_TRANSPORT_H
#define BRICKWRIGHT_H4_TRANSPORT_H
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <pthread.h>
#include <brickwright/ehcill.h>
#include <brickwright/h4.h>
struct brickwright_h4_transport {
  int fd;
  struct brickwright_h4 h4;
  struct brickwright_ehcill ehcill;
  pthread_mutex_t lock;
  int write_timeout_ms;
  int fault;
};
int brickwright_h4_transport_open(struct brickwright_h4_transport *transport,
                                  const char *path,
                                  brickwright_h4_packet_cb receive,
                                  void *context);
int brickwright_h4_transport_close(struct brickwright_h4_transport *transport);
int brickwright_h4_transport_receive(struct brickwright_h4_transport *transport,
                                     int timeout_ms);
int brickwright_h4_transport_send(struct brickwright_h4_transport *transport,
                                  const void *frame, size_t length,
                                  int timeout_ms);
int brickwright_h4_transport_ioctl(struct brickwright_h4_transport *transport,
                                   int request, unsigned long argument);
int brickwright_h4_transport_fault(struct brickwright_h4_transport *transport);
int brickwright_h4_io_open(const char *path, int flags);
int brickwright_h4_io_close(int fd);
ssize_t brickwright_h4_io_read(int fd, void *data, size_t length);
ssize_t brickwright_h4_io_write(int fd, const void *data, size_t length);
int brickwright_h4_io_poll(int fd, short events, int timeout_ms);
int brickwright_h4_io_ioctl(int fd, int request, unsigned long argument);
#endif
