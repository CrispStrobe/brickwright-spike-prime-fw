/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Probe self-controls only. All syscalls below are host doubles, not NuttX.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <arch/board/board_legoport.h>
#include <arch/board/board_lump.h>
static int probe_open(const char *, int);
static int probe_close(int);
static int probe_ioctl(int, int, unsigned long);
#define open probe_open
#define close probe_close
#define ioctl probe_ioctl
#include "lumpprobe.c"
#undef open
#undef close
#undef ioctl

static int mode, calls, closes;
static int probe_open(const char *name, int flags)
{
  assert(!strcmp(name, "/dev/legoport5") && flags == O_RDONLY);
  errno = ENODEV;
  return mode == 1 ? -1 : 42;
}
static int probe_close(int fd)
{
  assert(fd == 42);
  closes++;
  errno = EIO;
  return mode == 10 ? -1 : 0;
}
static int probe_ioctl(int fd, int command, unsigned long arg)
{
  assert(fd == 42);
  int step = ++calls + 1; /* steps 2..9 */
  if (step == 2)
    {
      assert(command == LEGOPORT_GET_DEVICE_INFO && arg);
      struct legoport_info_s *info = (void *)arg;
      memset(info, 0, sizeof(*info));
      if (mode == 11) info->flags = LEGOPORT_FLAG_CONNECTED;
      if (mode == 2) {errno = EIO; return -1;}
      return 0;
    }
  assert(command == (step == 9 ? LEGOPORT_LUMP_POLL_DATA :
                                 LEGOPORT_LUMP_POLL_DATA_SESSION));
  if (step == 3) assert(arg == 0);
  if (step == 4) assert(arg == (unsigned long)g_bw_lump_probe_readonly);
  if (step == 5) assert(arg == 0x20000000ul);
  if (step == 6) assert(arg == UINTPTR_MAX - 15);
  if (step == 7) assert(arg == 0x20050000ul - 36);
  if (mode == step) return 0; /* Incorrectly accepted/refused syscall. */
  if ((mode == 12 && step == 8) || (mode == 13 && step == 9))
    ((uint8_t *)arg)[0] ^= 1; /* Refusal must preserve every output byte. */
  errno = step == 3 ? EINVAL : step < 8 ? EFAULT : EAGAIN;
  return -1;
}

int main(void)
{
  for (mode = 0; mode <= 13; mode++)
    {
      calls = closes = 0;
      int result = bw_lump_probe_run();
      assert(g_bw_lump_probe.magic == UINT32_C(0x42574c50));
      assert(g_bw_lump_probe.version == 1);
      if (mode == 0)
        {
          assert(result == 0 && g_bw_lump_probe.state == 2);
          assert(g_bw_lump_probe.checks == 511 && calls == 8 && closes == 1);
          assert(!g_bw_lump_probe.failure && !g_bw_lump_probe.result &&
                 !g_bw_lump_probe.error);
        }
      else
        {
          int failure = mode < 11 ? mode : mode == 11 ? 2 : mode == 12 ? 8 : 9;
          assert(result == 1 && g_bw_lump_probe.state == 3);
          assert(g_bw_lump_probe.failure == (unsigned)failure);
          assert(closes == (mode == 1 ? 0 : 1));
          assert(calls == (failure == 1 ? 0 : failure == 10 ? 8 : failure - 1));
          assert(g_bw_lump_probe.checks != 511);
        }
    }
  return 0;
}
