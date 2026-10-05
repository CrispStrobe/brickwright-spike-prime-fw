/* SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Christian Strobele
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "imu_calibration.h"

static int fail_write, fail_sync, fail_close, fail_rename;
static int interrupt_write, interrupt_read, short_io;
static unsigned writes, syncs, renames;
static ssize_t injected_write(int fd, const void *buf, size_t n)
{
  writes++;
  if (interrupt_write) { interrupt_write = 0; errno = EINTR; return -1; }
  if (fail_write) {
    if (fail_write == 2) return 0;
    errno = ENOSPC; return -1;
  }
  return write(fd, buf, short_io && n > 3 ? 3 : n);
}
static ssize_t injected_read(int fd, void *buf, size_t n)
{
  if (interrupt_read) { interrupt_read = 0; errno = EINTR; return -1; }
  return read(fd, buf, short_io && n > 3 ? 3 : n);
}
static int injected_fsync(int fd)
{
  syncs++;
  if (fail_sync) { errno = EIO; return -1; }
  return fsync(fd);
}
static int injected_close(int fd)
{
  int result = close(fd);
  if (fail_close) { errno = EIO; return -1; }
  return result;
}
static int injected_rename(const char *a, const char *b)
{
  renames++;
  assert(syncs > 0);
  if (fail_rename) { errno = EACCES; return -1; }
  return rename(a, b);
}
#define write injected_write
#define read injected_read
#define fsync injected_fsync
#define close injected_close
#define rename injected_rename
#include "../apps/imu/imu_calibration.c"
#undef write
#undef read
#undef fsync
#undef close
#undef rename

static void raw_record(const char *path, const imu_settings_t *s, size_t n,
                       int append)
{
  int fd = open(path, O_WRONLY | O_TRUNC);
  unsigned char extra = 7;
  assert(fd >= 0 && write(fd, s, n) == (ssize_t)n);
  if (append) assert(write(fd, &extra, 1) == 1);
  assert(close(fd) == 0);
}
static void expect_record(const char *path, const imu_settings_t *s)
{
  imu_settings_t got;
  int fd = open(path, O_RDONLY);
  struct stat st;
  assert(fd >= 0 && fstat(fd, &st) == 0 && st.st_size == sizeof(got));
  assert(read(fd, &got, sizeof(got)) == sizeof(got));
  assert(close(fd) == 0 && memcmp(&got, s, sizeof(got)) == 0);
}
int main(void)
{
  char directory[] = "/tmp/bw-imu-persistence-XXXXXX";
  int temporary_fd;
  char path[128];
  imu_settings_t first = {0}, next, invalid;
  temporary_fd = mkstemp(directory);
  assert(temporary_fd >= 0 && close(temporary_fd) == 0);
  assert(unlink(directory) == 0 && mkdir(directory, 0700) == 0);
  assert(snprintf(path, sizeof(path), "%s/calibration", directory) > 0);
  imu_calibration_set_defaults(&first);
  next = first; next.angular_velocity_bias_start.x = 2.5f;
  next.flags |= IMU_FLAG_GYRO_BIAS;
  assert(imu_calibration_save_copy(path, &first) == 0);
  expect_record(path, &first);
  struct stat st; assert(stat(path, &st) == 0 && (st.st_mode & 0777) == 0600);

  for (unsigned failure = 0; failure < 5; failure++) {
    fail_write = failure == 0 ? 1 : failure == 1 ? 2 : 0;
    fail_sync = failure == 2; fail_close = failure == 3;
    fail_rename = failure == 4;
    assert(imu_calibration_save_copy(path, &next) == -1);
    assert(errno == (failure == 0 ? ENOSPC : failure == 4 ? EACCES : EIO));
    fail_write = fail_sync = fail_close = fail_rename = 0;
    expect_record(path, &first);
  }
  short_io = interrupt_write = interrupt_read = 1;
  assert(imu_calibration_save_copy(path, &next) == 0 && writes > 10);
  assert(imu_calibration_load(path) == 0);
  assert(memcmp(imu_calibration_get_settings(), &next, sizeof(next)) == 0);
  short_io = 0;

  /* Malformed records must not replace the already active calibration. */
  for (unsigned failure = 0; failure < 7; failure++) {
    invalid = first;
    if (failure == 2) invalid.gravity_pos.x = NAN;
    if (failure == 3) invalid.angular_velocity_scale.z = 0;
    if (failure == 4) invalid.flags = UINT32_MAX;
    if (failure == 5) invalid.gyro_stationary_threshold = -1;
    if (failure == 6) invalid.angular_velocity_bias_start.y = INFINITY;
    raw_record(path, &invalid, failure == 0 ? sizeof(invalid)-1 : sizeof(invalid),
               failure == 1);
    errno = 0;
    assert(imu_calibration_load(path) == -1 && errno == EBADMSG);
    assert(memcmp(imu_calibration_get_settings(), &next, sizeof(next)) == 0);
    if (failure >= 2) {
      assert(imu_calibration_save_copy(path, &invalid) == -1 && errno == EINVAL);
    }
  }
  assert(imu_calibration_load(NULL) == -1 && errno == EINVAL);
  assert(imu_calibration_load("") == -1 && errno == EINVAL);
  assert(imu_calibration_save_copy(path, &next) == 0);
  assert(unlink(path) == 0);
  /* No failed-save temporary files may be left behind. */
  assert(rmdir(directory) == 0);
  puts("IMU persistence: atomic replacement, failed-write isolation, exact/valid loads PASS");
  return 0;
}
