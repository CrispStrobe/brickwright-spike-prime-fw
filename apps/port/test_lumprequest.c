/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Host syscall doubles only; this is not protected guest execution.
 */
#include <assert.h>
#include <stdlib.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <arch/board/board_legoport.h>
#include <arch/board/board_lump.h>
static int request_open(const char *, int);
static int request_close(int);
static int request_ioctl(int, int, unsigned long);
#define open request_open
#define close request_close
#define ioctl request_ioctl
#include "lumpprobe.c"
#undef open
#undef close
#undef ioctl

static const char *scenario;
static unsigned opens, closes, calls;
static int request_open(const char *path, int flags)
{
  assert(!strcmp(path, "/dev/legoport5") && flags == O_RDONLY);
  assert(strcmp(scenario, "reject") != 0);
  assert(++opens == 1);
  if (!strcmp(scenario, "open-fail")) { errno = EBUSY; return -1; }
  return 42;
}
static int request_close(int fd)
{
  assert(fd == 42 && opens == 1 && ++closes == 1);
  if (!strcmp(scenario, "close-fail")) { errno = EIO; return -1; }
  return 0;
}
static int request_ioctl(int fd, int command, unsigned long argument)
{
  assert(fd == 42 && opens == 1 && closes == 0 && ++calls <= 6);
  assert(command == LEGOPORT_LUMP_POLL_DATA_SESSION || command == LEGOPORT_LUMP_POLL_DATA);
  const uintptr_t bad[] = {0, (uintptr_t)g_bw_lump_probe_readonly,
    UINT32_C(0x20000000), UINTPTR_MAX - 15, UINT32_C(0x20050000) - 36};
  for (unsigned i = 0; i < 5; i++)
    if (argument == bad[i])
      { errno = i == 0 ? EINVAL : EFAULT; return -1; }
  if (!strcmp(scenario, "data"))
    {
      if (command == LEGOPORT_LUMP_POLL_DATA_SESSION)
        {
          struct lump_data_session_frame_s *out = (void *)argument;
          memset(out, 0, sizeof(*out)); out->session = UINT64_C(0x1020304050607080);
          out->frame.mode = 2; out->frame.len = 4;
          memcpy(out->frame.data, "ABCD", 4);
        }
      else
        {
          struct lump_data_frame_s *out = (void *)argument;
          memset(out, 0, sizeof(*out)); out->mode = 3; out->len = 1; out->data[0] = 42;
        }
      return 0;
    }
  errno = EAGAIN; return -1;
}
int main(int argc, char **argv)
{
  assert(argc == 3); scenario = argv[2];
  const char *operation = !strcmp(argv[1], "<null>") ? NULL : argv[1];
  int result = bw_lump_request_run(operation);
  if (!strcmp(scenario, "reject")) assert(opens == 0 && calls == 0 && closes == 0);
  else if (!strcmp(scenario, "open-fail")) assert(opens == 1 && calls == 0 && closes == 0);
  else
    {
      assert(opens == 1 && closes == 1);
      assert(calls == (!strcmp(operation, "invalid-then-poll") ? 6u : 1u));
    }
  return result;
}
