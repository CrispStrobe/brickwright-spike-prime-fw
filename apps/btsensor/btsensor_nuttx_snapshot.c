/* SPDX-License-Identifier: Apache-2.0 */

#include <nuttx/config.h>
#include <nuttx/power/battery_ioctl.h>

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <arch/board/board_legosensor.h>

#include "btsensor_nuttx_snapshot.h"

#define BTSENSOR_BATTERY_PATH "/dev/bat0"
#define BTSENSOR_ULTRASONIC_PATH "/dev/uorb/sensor_ultrasonic"

#define BTSENSOR_RECORD_DISTANCE 0x0d
#define BTSENSOR_LPF2_ULTRASONIC 62

static int snapshot_open(const char *path, int flags)
{
  return open(path, flags);
}

static int snapshot_ioctl(int fd, int command, unsigned long argument)
{
  return ioctl(fd, command, argument);
}

static int snapshot_close(int fd)
{
  return close(fd);
}

static const struct btsensor_snapshot_io g_snapshot_io =
{
  .open_device = snapshot_open,
  .device_ioctl = snapshot_ioctl,
  .close_device = snapshot_close,
};

int btsensor_nuttx_snapshot_read(
    struct btsensor_modern_snapshot *snapshot,
    const struct btsensor_snapshot_io *io)
{
  struct btsensor_modern_snapshot next;
  int capacity;
  int fd;
  int saved_errno;
  struct lump_sample_s sample;
  int sensor_fd;

  if (snapshot == NULL || io == NULL || io->open_device == NULL ||
      io->device_ioctl == NULL || io->close_device == NULL)
    {
      return -EINVAL;
    }

  fd = io->open_device(BTSENSOR_BATTERY_PATH, O_RDONLY);
  if (fd < 0)
    {
      return errno == 0 ? -EIO : -errno;
    }

  capacity = 0;
  if (io->device_ioctl(fd, BATIOC_CAPACITY,
                       (unsigned long)&capacity) < 0)
    {
      saved_errno = errno == 0 ? EIO : errno;
      (void)io->close_device(fd);
      return -saved_errno;
    }

  if (io->close_device(fd) < 0)
    {
      return errno == 0 ? -EIO : -errno;
    }

  if (capacity < 0 || capacity > 100)
    {
      return -ERANGE;
    }

  /* Evidence for this conversion is local and exact:
   * boards/spike-prime-hub/src/stm32_battery_gauge.c::
   * spike_gauge_capacity returns an integer percentage through
   * BATIOC_CAPACITY. btsensor_modern_notify.c publishes that value as the
   * type-0 battery record.  No sensor/IMU record is emitted: their current
   * APIs are destructive stream drains, not coherent snapshot APIs.
   */
  memset(&next, 0, sizeof(next));
  next.battery_percent = (uint8_t)capacity;

  /* DISTL/DISTS expose the exact signed millimetre value required by the
   * published 0x0d record in one LUMP frame.  Other modern records combine
   * fields from multiple mutually-exclusive modes (motor/color/force), so
   * publishing them here would require guessed or temporally incoherent
   * values.  GET_LATEST does not advance any existing uORB reader.
   */

  sensor_fd = io->open_device(BTSENSOR_ULTRASONIC_PATH,
                              O_RDONLY | O_NONBLOCK);
  if (sensor_fd >= 0)
    {
      memset(&sample, 0, sizeof(sample));
      if (io->device_ioctl(sensor_fd, LEGOSENSOR_GET_LATEST,
                           (unsigned long)&sample) == 0 &&
          sample.port < 6 &&
          sample.type_id == BTSENSOR_LPF2_ULTRASONIC &&
          (sample.mode_id == 0 || sample.mode_id == 1) &&
          sample.data_type == LUMP_DATA_INT16 &&
          sample.num_values == 1 && sample.len >= 2)
        {
          next.records[0] = BTSENSOR_RECORD_DISTANCE;
          next.records[1] = sample.port;
          next.records[2] = sample.data.raw[0];
          next.records[3] = sample.data.raw[1];
          next.records_length = 4;
        }

      (void)io->close_device(sensor_fd);
    }

  *snapshot = next;
  return 0;
}

int btsensor_hub_snapshot(struct btsensor_modern_snapshot *snapshot)
{
  return btsensor_nuttx_snapshot_read(snapshot, &g_snapshot_io);
}
