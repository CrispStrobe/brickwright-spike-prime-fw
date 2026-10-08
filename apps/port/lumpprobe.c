/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include <nuttx/config.h>
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
#include "lumpprobe.h"

#if !defined(CONFIG_BUILD_PROTECTED) || !defined(CONFIG_LEGO_LUMP) || \
    !defined(CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK)
#error "lumpprobe is only for explicit protected TI-free simulation"
#endif

volatile struct bw_lump_probe_result g_bw_lump_probe;
const uint8_t g_bw_lump_probe_readonly[48] = {0x42};
_Static_assert(sizeof(struct bw_lump_probe_result) == 32, "probe ABI");
_Static_assert(sizeof(struct lump_data_session_frame_s) == 48, "session ABI");
_Static_assert(offsetof(struct lump_data_session_frame_s, frame) == 8,
               "session frame offset");

static int finish(int fd, uint32_t failure, int result, int error)
{
  if (fd >= 0)
    {
      (void)close(fd);
    }
  g_bw_lump_probe.failure = failure;
  g_bw_lump_probe.result = result;
  g_bw_lump_probe.error = error;
  __sync_synchronize();
  g_bw_lump_probe.state = failure ? 3 : 2;
  return failure ? 1 : 0;
}

int bw_lump_probe_run(void)
{
  /* The boot script invokes this once. It does not start a daemon or reserve
   * a motor port; no requests, host pointers or commands are accepted.
   */
  g_bw_lump_probe.state = 1;
  g_bw_lump_probe.magic = UINT32_C(0x42574c50);
  g_bw_lump_probe.version = 1;
  g_bw_lump_probe.checks = 0;
  g_bw_lump_probe.failure = 0;
  g_bw_lump_probe.result = 0;
  g_bw_lump_probe.error = 0;
  g_bw_lump_probe.readonly_address = (uint32_t)(uintptr_t)g_bw_lump_probe_readonly;
  int fd = open("/dev/legoport5", O_RDONLY);
  if (fd < 0)
    {
      return finish(-1, 1, fd, errno);
    }

  struct legoport_info_s info;
  errno = 0;
  int result = ioctl(fd, LEGOPORT_GET_DEVICE_INFO, (unsigned long)&info);
  int error = errno;
  if (result != 0 || info.device_type != LEGOPORT_TYPE_NONE ||
      (info.flags & LEGOPORT_FLAG_CONNECTED))
    {
      return finish(fd, 2, result, error);
    }
  g_bw_lump_probe.checks |= 1u;

  /* Fixed board ABI test addresses. These are passed to the actual syscall,
   * never dereferenced by the probe. The last range has only 36 bytes left
   * in user RAM, so validation of the legacy size would wrongly admit it.
   */
  const uintptr_t invalid[] =
  {
    (uintptr_t)g_bw_lump_probe_readonly, UINT32_C(0x20000000),
    UINTPTR_MAX - 15, UINT32_C(0x20050000) - 36
  };
  errno = 0;
  result = ioctl(fd, LEGOPORT_LUMP_POLL_DATA_SESSION, 0ul);
  error = errno;
  if (result != -1 || error != EINVAL)
    {
      return finish(fd, 3, result, error);
    }
  g_bw_lump_probe.checks |= 1u << 1;
  for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++)
    {
      errno = 0;
      result = ioctl(fd, LEGOPORT_LUMP_POLL_DATA_SESSION,
                     (unsigned long)invalid[i]);
      error = errno;
      if (result != -1 || error != EFAULT)
        {
          return finish(fd, 4 + i, result, error);
        }
      g_bw_lump_probe.checks |= 1u << (2 + i);
    }

  struct lump_data_session_frame_s session, before;
  memset(&session, 0xa5, sizeof(session));
  before = session;
  errno = 0;
  result = ioctl(fd, LEGOPORT_LUMP_POLL_DATA_SESSION, (unsigned long)&session);
  error = errno;
  if (result != -1 || error != EAGAIN ||
      memcmp(&session, &before, sizeof(session)) != 0)
    {
      return finish(fd, 8, result, error);
    }
  g_bw_lump_probe.checks |= 1u << 6;

  struct lump_data_frame_s legacy, old;
  memset(&legacy, 0x5a, sizeof(legacy));
  old = legacy;
  errno = 0;
  result = ioctl(fd, LEGOPORT_LUMP_POLL_DATA, (unsigned long)&legacy);
  error = errno;
  if (result != -1 || error != EAGAIN ||
      memcmp(&legacy, &old, sizeof(legacy)) != 0)
    {
      return finish(fd, 9, result, error);
    }
  g_bw_lump_probe.checks |= 1u << 7;
  errno = 0;
  result = close(fd);
  error = errno;
  if (result != 0)
    {
      return finish(-1, 10, result, error);
    }
  g_bw_lump_probe.checks |= 1u << 8;
  return finish(-1, 0, 0, 0);
}
