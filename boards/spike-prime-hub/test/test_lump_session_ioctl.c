/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#define _GNU_SOURCE
#include <assert.h>
#include <sys/mman.h>
#include <stdio.h>
#include "lump_data_queue.h"
#include "stm32_legoport_chardev.c"

static struct lump_data_queue_s queue;
static unsigned polls;
int lump_pop_data_session_frame(int port, struct lump_data_session_frame_s *out)
{
  assert(port == 2); polls++;
  return lump_data_queue_pop(&queue, out);
}
int lump_pop_data_frame(int port, struct lump_data_frame_s *out)
{
  struct lump_data_session_frame_s snap;
  int rc = lump_pop_data_session_frame(port, &snap);
  if (rc == 0) *out = snap.frame;
  return rc;
}

int main(void)
{
  /* Never replace host mappings: this Linux fixture fails if occupied. */
  void *mapping = mmap((void *)BOARD_USRAM_START,
                      BOARD_USRAM_END - BOARD_USRAM_START + 4096,
                      PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
  assert(mapping == (void *)BOARD_USRAM_START);
  struct legoport_chardev_s priv = {.port = 2};
  struct inode inode = {.i_private = &priv};
  struct file file = {.f_inode = &inode};
  assert(lump_data_queue_begin(&queue) == 0);
  struct lump_data_frame_s sample = {.mode = 2, .len = 4, .data = {1, 2, 3, 4}};
  assert(lump_data_queue_push(&queue, &sample) == 0);
  const unsigned long bad[] = {
    1, BOARD_USRAM_START - 1, BOARD_USRAM_END, BOARD_UFLASH_START,
    UINTPTR_MAX - 7, BOARD_USRAM_END - sizeof(struct lump_data_frame_s)
  };
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, 0) == -EINVAL);
  for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++)
    assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, bad[i]) == -EFAULT);
  assert(polls == 0); /* Even a legacy-sized range cannot consume a frame. */
  unsigned long address = BOARD_USRAM_END - sizeof(struct lump_data_session_frame_s);
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, address) == 0);
  struct lump_data_session_frame_s *out = (void *)address;
  assert(polls == 1 && out->session == 1 && out->reserved == 0);
  assert(memcmp(&out->frame, &sample, sizeof(sample)) == 0);
  struct lump_data_session_frame_s before = *out;
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, address) == -EAGAIN);
  assert(memcmp(out, &before, sizeof(before)) == 0);
  assert(lump_data_queue_push(&queue, &sample) == 0);
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA, BOARD_USRAM_START) == 0);
  assert(memcmp(mapping, &sample, sizeof(sample)) == 0);
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, address) == -EAGAIN);
  assert(lump_data_queue_push(&queue, &sample) == 0);
  lump_data_queue_invalidate(&queue);
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, address) == -EAGAIN);
  assert(lump_data_queue_begin(&queue) == 0);
  sample.data[0] = 9;
  assert(lump_data_queue_push(&queue, &sample) == 0);
  assert(legoport_cdev_ioctl(&file, LEGOPORT_LUMP_POLL_DATA_SESSION, address) == 0);
  assert(out->session == 2 && out->frame.data[0] == 9);
  assert(legoport_cdev_ioctl(&file, -1, address) == -ENOTTY);
  assert(munmap(mapping, BOARD_USRAM_END - BOARD_USRAM_START + 4096) == 0);
  puts("Actual protected session ioctl: PASS (host OS/driver boundaries stubbed)");
}
