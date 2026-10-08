/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include <nuttx/config.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
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
volatile struct bw_lump_request_result g_bw_lump_request;
volatile struct bw_lump_request_mailbox g_bw_lump_request_mailbox;
static uint32_t g_request_busy, g_mailbox_busy;
_Static_assert(sizeof(struct bw_lump_request_mailbox) == 32, "request mailbox ABI");
_Static_assert(sizeof(struct bw_lump_request_record) == 60, "request record ABI");
_Static_assert(sizeof(struct bw_lump_request_result) == 400, "request publication ABI");
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

/* Fixed simulation-only requests, not arbitrary ioctl numbers or pointers.
 * A batch keeps the exclusive descriptor until all refusals and its final poll
 * have completed. The reply records observations; it does not declare PASS.
 */
static void request_reply(const char *operation, unsigned step, int result,
                          int error, const void *bytes, size_t length, bool emit)
{
  volatile struct bw_lump_request_record *record =
    &g_bw_lump_request.records[step - 1];
  record->result = result;
  record->error = error;
  record->length = length;
  for (size_t i = 0; i < length; i++) record->bytes[i] = ((const uint8_t *)bytes)[i];
  g_bw_lump_request.calls = step;
  if (!emit) return;
  printf("BW_LUMP_REQUEST v=1 op=%s step=%u rc=%d errno=%d bytes=",
         operation, step, result, error);
  if (bytes)
    {
      const uint8_t *data = bytes;
      for (size_t i = 0; i < length; i++) printf("%02x", data[i]);
    }
  else printf("-");
  printf("\n");
}

static int request_run(const char *operation, bool emit, uint32_t *publication)
{
  static const char *const names[] =
    {"poll", "legacy", "null", "readonly", "kernel", "wrap",
     "legacy-tail", "invalid-then-poll"};
  unsigned selected = sizeof(names) / sizeof(names[0]);
  if (!operation) return -EINVAL;
  size_t length = 0;
  while (length < 32 && operation[length]) length++;
  if (length == 32) return -EINVAL;
  for (unsigned i = 0; i < sizeof(names) / sizeof(names[0]); i++)
    if (strcmp(operation, names[i]) == 0) { selected = i; break; }
  if (selected == sizeof(names) / sizeof(names[0])) return -EINVAL;

  if (__sync_lock_test_and_set(&g_request_busy, 1)) return -EBUSY;
  if (g_bw_lump_request.sequence == UINT32_MAX)
    {
      __sync_lock_release(&g_request_busy);
      return -EOVERFLOW;
    }
  uint32_t sequence = g_bw_lump_request.sequence + 1;
  /* Invalidate the old terminal snapshot before any aggregate field changes. */
  g_bw_lump_request.state = 1;
  __sync_synchronize();
  g_bw_lump_request = (struct bw_lump_request_result)
    {.magic = UINT32_C(0x42575251), .version = 1, .state = 1,
     .sequence = sequence, .selector = selected};
  __sync_synchronize();
  errno = 0;
  int fd = open("/dev/legoport5", O_RDONLY);
  int open_error = errno;
  g_bw_lump_request.open_result = fd;
  g_bw_lump_request.open_error = open_error;
  if (fd < 0)
    {
      int error = open_error;
      __sync_synchronize();
      g_bw_lump_request.state = 3;
      if (emit) printf("BW_LUMP_REQUEST_OPEN v=1 op=%s rc=-1 errno=%d\n", operation, error);
      if (publication) *publication = sequence;
      __sync_lock_release(&g_request_busy);
      return error ? -error : -EIO;
    }
  const uintptr_t invalid[] =
    {0, (uintptr_t)g_bw_lump_probe_readonly, UINT32_C(0x20000000),
     UINTPTR_MAX - 15, UINT32_C(0x20050000) - 36};
  unsigned calls = 0;
  if (selected >= 2)
    {
      unsigned first = selected == 7 ? 0 : selected - 2;
      unsigned end = selected == 7 ? 5 : first + 1;
      for (unsigned i = first; i < end; i++)
        {
          errno = 0;
          int result = ioctl(fd, LEGOPORT_LUMP_POLL_DATA_SESSION,
                             (unsigned long)invalid[i]);
          int error = errno;
          request_reply(operation, ++calls, result, error, NULL, 0, emit);
        }
    }
  if (selected < 2 || selected == 7)
    {
      union
      {
        struct lump_data_session_frame_s session;
        struct lump_data_frame_s legacy;
      } output;
      memset(&output, 0xa5, sizeof(output));
      bool legacy = selected == 1;
      void *buffer = legacy ? (void *)&output.legacy : (void *)&output.session;
      errno = 0;
      int result = ioctl(fd, legacy ? LEGOPORT_LUMP_POLL_DATA :
                                     LEGOPORT_LUMP_POLL_DATA_SESSION,
                         (unsigned long)buffer);
      int error = errno;
      request_reply(operation, ++calls, result, error, buffer,
                    legacy ? sizeof(output.legacy) : sizeof(output.session), emit);
    }
  errno = 0;
  int result = close(fd);
  int error = errno;
  g_bw_lump_request.close_result = result;
  g_bw_lump_request.close_error = error;
  __sync_synchronize();
  g_bw_lump_request.state = 2;
  if (emit) printf("BW_LUMP_REQUEST_END v=1 op=%s calls=%u close_rc=%d close_errno=%d\n",
         operation, calls, result, error);
  if (publication) *publication = sequence;
  __sync_lock_release(&g_request_busy);
  return result == 0 ? 0 : error ? -error : -EIO;
}

int bw_lump_request_run(const char *operation)
{
  return request_run(operation, true, NULL) == 0 ? 0 : 1;
}

int bw_lump_request_startup(void)
{
  /* USB CDC is not connected in the startup fixture. Never wait on stdout. */
  return request_run("invalid-then-poll", false, NULL) == 0 ? 0 : 1;
}

void bw_lump_request_mailbox_step(void)
{
  static const char *const names[] =
    {"poll", "legacy", "null", "readonly", "kernel", "wrap",
     "legacy-tail", "invalid-then-poll"};
  if (__sync_lock_test_and_set(&g_mailbox_busy, 1)) return;
  uint32_t seq = g_bw_lump_request_mailbox.request_seq;
  uint32_t previous = g_bw_lump_request_mailbox.reply_seq;
  if (!seq || seq <= previous) goto done;
  uint32_t magic = g_bw_lump_request_mailbox.request_magic;
  uint32_t version = g_bw_lump_request_mailbox.request_version;
  uint32_t selector = g_bw_lump_request_mailbox.request_selector;
  __sync_synchronize();
  if (seq != g_bw_lump_request_mailbox.request_seq) goto done;
  /* An old sequence must not attest fields being replaced by this request. */
  g_bw_lump_request_mailbox.reply_seq = 0;
  __sync_synchronize();
  int result = -EINVAL;
  uint32_t publication = 0;
  if (seq == previous + 1 &&
      magic == UINT32_C(0x42574c52) && version == 1 && selector < 8)
    {
      result = request_run(names[selector], false, &publication);
    }
  g_bw_lump_request_mailbox.reply_result = result;
  g_bw_lump_request_mailbox.reply_publication_seq = publication;
  g_bw_lump_request_mailbox.reply_selector = selector;
  __sync_synchronize();
  g_bw_lump_request_mailbox.reply_seq = seq;
done:
  __sync_lock_release(&g_mailbox_busy);
}
