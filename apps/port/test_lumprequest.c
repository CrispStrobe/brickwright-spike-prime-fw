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
static const char *expected_path = "/dev/legoport5";
static int request_open(const char *path, int flags)
{
  assert(!strcmp(path, expected_path) && flags == O_RDONLY);
  assert(strcmp(scenario, "reject") != 0);
  assert(++opens == 1);
  if (!strcmp(scenario, "observe-invalidated-reply"))
    assert(g_bw_lump_request_mailbox.reply_seq == 0);
  if (!strcmp(scenario, "open-no-errno")) return -1;
  if (!strcmp(scenario, "open-fail")) { errno = EBUSY; return -1; }
  return 42;
}
static int request_close(int fd)
{
  assert(fd == 42 && opens == 1 && ++closes == 1);
  if (!strcmp(scenario, "close-no-errno")) return -1;
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
  if (operation && (!strcmp(operation, "poll-e") || !strcmp(operation, "invalid-then-poll-e")))
    expected_path = "/dev/legoport4";
  int result = !strcmp(scenario, "startup") ? bw_lump_request_startup() : bw_lump_request_run(operation);
  if (!strcmp(scenario, "reject")) assert(opens == 0 && calls == 0 && closes == 0);
  else if (!strcmp(scenario, "open-fail")) assert(opens == 1 && calls == 0 && closes == 0);
  else
    {
      assert(opens == 1 && closes == 1);
      assert(calls == ((!strcmp(operation, "invalid-then-poll") || !strcmp(operation, "invalid-then-poll-e")) ? 6u : 1u));
    }
  if (!strcmp(scenario, "reject")) assert(g_bw_lump_request.state == 0);
  else
    {
      assert(g_bw_lump_request.magic == UINT32_C(0x42575251));
      assert(g_bw_lump_request.version == 1 && g_bw_lump_request.sequence == 1);
      assert(g_bw_lump_request.calls == calls);
      if (!strcmp(scenario, "open-fail"))
        assert(g_bw_lump_request.state == 3 && g_bw_lump_request.open_result == -1 &&
               g_bw_lump_request.open_error == EBUSY);
      else
        {
          assert(g_bw_lump_request.state == 2 && g_bw_lump_request.open_result == 42);
          assert(g_bw_lump_request.close_result == (!strcmp(scenario, "close-fail") ? -1 : 0));
          assert(g_bw_lump_request.close_error == (!strcmp(scenario, "close-fail") ? EIO : 0));
          for (unsigned i = 0; i < calls; i++)
            {
              const volatile struct bw_lump_request_record *r = &g_bw_lump_request.records[i];
              if ((!strcmp(operation, "invalid-then-poll") || !strcmp(operation, "invalid-then-poll-e")) && i < 5)
                assert(r->result == -1 && r->error == (i == 0 ? EINVAL : EFAULT) && r->length == 0);
              else if (!strcmp(operation, "poll") || !strcmp(operation, "poll-e") || !strcmp(operation, "legacy") || i == 5)
                {
                  assert(r->length == (!strcmp(operation, "legacy") ? 36u : 48u));
                  assert(r->result == (!strcmp(scenario, "data") ? 0 : -1));
                  assert(r->error == (!strcmp(scenario, "data") ? 0 : EAGAIN));
                  if (strcmp(scenario, "data"))
                    for (unsigned j = 0; j < r->length; j++) assert(r->bytes[j] == 0xa5);
                }
              else assert(r->result == -1 && r->length == 0);
            }
        }
    }
  return result;
}
