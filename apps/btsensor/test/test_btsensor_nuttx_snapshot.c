/* SPDX-License-Identifier: Apache-2.0 */

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "btsensor_nuttx_snapshot.h"
#include <arch/board/board_legosensor.h>
#include <nuttx/power/battery_ioctl.h>

static int g_open_result;
static int g_ioctl_result;
static int g_close_result;
static int g_capacity;
static int g_open_errno;
static int g_ioctl_errno;
static int g_close_errno;
static int g_open_count;
static int g_ioctl_count;
static int g_close_count;
static int g_sensor_open_result;
static int g_sensor_ioctl_result;
static struct lump_sample_s g_sensor_sample;

static int fake_open(const char *path, int flags)
{
  g_open_count++;
  if (strcmp(path, "/dev/uorb/sensor_ultrasonic") == 0)
    {
      assert(flags == (O_RDONLY | O_NONBLOCK));
      return g_sensor_open_result;
    }
  assert(strcmp(path, "/dev/bat0") == 0 && flags == O_RDONLY);
  errno = g_open_errno;
  return g_open_result;
}

static int fake_ioctl(int fd, int command, unsigned long argument)
{
  g_ioctl_count++;
  if (fd == g_sensor_open_result)
    {
      assert(command == LEGOSENSOR_GET_LATEST);
      if (g_sensor_ioctl_result == 0)
        {
          *(struct lump_sample_s *)argument = g_sensor_sample;
        }
      return g_sensor_ioctl_result;
    }
  assert(fd == g_open_result);
  assert(command == BATIOC_CAPACITY);
  if (g_ioctl_result == 0)
    {
      *(int *)argument = g_capacity;
    }
  errno = g_ioctl_errno;
  return g_ioctl_result;
}

static int fake_close(int fd)
{
  g_close_count++;
  assert(fd == g_open_result || fd == g_sensor_open_result);
  errno = g_close_errno;
  return g_close_result;
}

static const struct btsensor_snapshot_io g_io =
{
  .open_device = fake_open,
  .device_ioctl = fake_ioctl,
  .close_device = fake_close,
};

static void reset_fakes(void)
{
  g_open_result = 7;
  g_ioctl_result = 0;
  g_close_result = 0;
  g_capacity = 64;
  g_open_errno = g_ioctl_errno = g_close_errno = 0;
  g_open_count = g_ioctl_count = g_close_count = 0;
  g_sensor_open_result = -1;
  g_sensor_ioctl_result = -1;
  memset(&g_sensor_sample, 0, sizeof(g_sensor_sample));
}

static void test_success_is_battery_only(void)
{
  struct btsensor_modern_snapshot snapshot;
  memset(&snapshot, 0xa5, sizeof(snapshot));
  reset_fakes();
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == 0);
  assert(snapshot.battery_percent == 64);
  assert(snapshot.records_length == 0);
  assert(g_open_count == 2 && g_ioctl_count == 1 && g_close_count == 1);
}

static void test_distance_uses_non_destructive_latest_frame(void)
{
  struct btsensor_modern_snapshot snapshot;
  const uint8_t expected[] = {0x0d, 4, 0xff, 0xff};

  reset_fakes();
  g_sensor_open_result = 8;
  g_sensor_ioctl_result = 0;
  g_sensor_sample.port = 4;
  g_sensor_sample.type_id = 62;
  g_sensor_sample.mode_id = 0;
  g_sensor_sample.data_type = LUMP_DATA_INT16;
  g_sensor_sample.num_values = 1;
  g_sensor_sample.len = 2;
  g_sensor_sample.data.raw[0] = 0xff;
  g_sensor_sample.data.raw[1] = 0xff;

  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == 0);
  assert(snapshot.battery_percent == 64);
  assert(snapshot.records_length == sizeof(expected));
  assert(memcmp(snapshot.records, expected, sizeof(expected)) == 0);
  assert(g_open_count == 2 && g_ioctl_count == 2 && g_close_count == 2);
}

static void test_distance_rejects_unproven_shapes(void)
{
  struct btsensor_modern_snapshot snapshot;

  reset_fakes();
  g_sensor_open_result = 8;
  g_sensor_ioctl_result = 0;
  g_sensor_sample.port = 2;
  g_sensor_sample.type_id = 62;
  g_sensor_sample.mode_id = 2; /* SINGL is not part of the proven mapping. */
  g_sensor_sample.data_type = LUMP_DATA_INT16;
  g_sensor_sample.num_values = 1;
  g_sensor_sample.len = 2;
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == 0);
  assert(snapshot.records_length == 0);

  g_sensor_sample.mode_id = 0;
  g_sensor_sample.len = 1;
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == 0);
  assert(snapshot.records_length == 0);
}

static void test_failures_do_not_publish_partial_snapshot(void)
{
  struct btsensor_modern_snapshot before;
  struct btsensor_modern_snapshot snapshot;
  memset(&before, 0x5a, sizeof(before));

  reset_fakes();
  snapshot = before;
  g_open_result = -1;
  g_open_errno = ENOENT;
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == -ENOENT);
  assert(memcmp(&snapshot, &before, sizeof(snapshot)) == 0);
  assert(g_ioctl_count == 0 && g_close_count == 0);

  reset_fakes();
  snapshot = before;
  g_ioctl_result = -1;
  g_ioctl_errno = EIO;
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == -EIO);
  assert(memcmp(&snapshot, &before, sizeof(snapshot)) == 0);
  assert(g_close_count == 1);

  reset_fakes();
  snapshot = before;
  g_close_result = -1;
  g_close_errno = EINTR;
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == -EINTR);
  assert(memcmp(&snapshot, &before, sizeof(snapshot)) == 0);
}

static void test_rejects_invalid_capacity_and_arguments(void)
{
  struct btsensor_modern_snapshot before;
  struct btsensor_modern_snapshot snapshot;
  memset(&before, 0x3c, sizeof(before));

  reset_fakes();
  snapshot = before;
  g_capacity = 101;
  assert(btsensor_nuttx_snapshot_read(&snapshot, &g_io) == -ERANGE);
  assert(memcmp(&snapshot, &before, sizeof(snapshot)) == 0);

  assert(btsensor_nuttx_snapshot_read(NULL, &g_io) == -EINVAL);
  assert(btsensor_nuttx_snapshot_read(&snapshot, NULL) == -EINVAL);
}

int main(void)
{
  test_success_is_battery_only();
  test_distance_uses_non_destructive_latest_frame();
  test_distance_rejects_unproven_shapes();
  test_failures_do_not_publish_partial_snapshot();
  test_rejects_invalid_capacity_and_arguments();
  puts("btsensor NuttX snapshot tests passed");
  return 0;
}
