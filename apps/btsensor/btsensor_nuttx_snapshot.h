/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_NUTTX_SNAPSHOT_H
#define BTSENSOR_NUTTX_SNAPSHOT_H

#include "btsensor_modern_notify.h"

/* Injectable, allocation-free POSIX I/O seam.  Callbacks return -1 and set
 * errno on failure, exactly like open/ioctl/close.  Keeping the complete
 * transaction behind this interface makes error handling testable without
 * NuttX hardware.
 */
struct btsensor_snapshot_io
{
  int (*open_device)(const char *path, int flags);
  int (*device_ioctl)(int fd, int command, unsigned long argument);
  int (*close_device)(int fd);
};

int btsensor_nuttx_snapshot_read(
    struct btsensor_modern_snapshot *snapshot,
    const struct btsensor_snapshot_io *io);

#endif
