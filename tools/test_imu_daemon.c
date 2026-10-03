/* SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Christian Strobele
 * Execute the actual application with synthetic task/device boundaries.
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int fake_task_create(const char *, int, int,
                            int (*)(int, char **), char **);
static int fake_open(const char *, int, ...);
static int fake_close(int);
static ssize_t fake_read(int, void *, size_t);
static int fake_poll(struct pollfd *, nfds_t, int);
static int fake_clock_gettime(clockid_t, struct timespec *);
static int fake_printf(const char *, ...);

#define main imu_application_main
#define task_create fake_task_create
#define open fake_open
#define close fake_close
#define read fake_read
#define poll fake_poll
#define clock_gettime fake_clock_gettime
#define printf fake_printf
#include "../apps/imu/imu_main.c"
#undef main
#undef task_create
#undef open
#undef close
#undef read
#undef poll
#undef clock_gettime
#undef printf

enum scenario { STOP_PENDING, OPEN_FAIL, TASK_FAIL, INTERRUPTED, STOP_DRAIN,
                POLL_FAULT, LIVE_TIMING };
static enum scenario scenario;
static int create_count;
static int open_count;
static int close_count;
static int read_count;
static int poll_count;
static int (*pending_task)(int, char **);
static char printed[4096];
static size_t printed_size;
static uint64_t fake_now = 1000000;
static size_t sample_index;
static bool sample_pending;
/* The zero-gravity startup step fails inside the real fusion algorithm.
 * The older frame at a live ODR change must not seed the following interval. */
static const uint32_t timestamps[] =
  {989000, 999000, 1009000, 1019000, 1029000, 1039000, 1400000,
   1410000, 1420000, 1430000, 1430000, 1440000, 1435000,
   1450000, 1460000};
static const uint8_t odrs[] = {7, 7, 7, 4, 0, 4, 4, 4, 4, 4, 4, 4, 3, 3, 3};
static const uint8_t gyro_fsrs[] = {4, 4, 4, 4, 4, 4, 4, 4, 3, 4, 4, 4, 4, 4, 4};
static const bool valid_samples[] =
  {false, true, true, true, false, true, false, true, false, true, false,
   true, false, true, true};
static const float steps[] = {0, 1.0f / 833, .01f, 1.0f / 104, 0,
                             1.0f / 104, 0, 1.0f / 104, 0,
                             1.0f / 104, 0, 1.0f / 104, 0, 1.0f / 52, .01f};
static float integrated_time;
static unsigned valid_count;

static int fake_printf(const char *format, ...)
{
  va_list args;
  va_start(args, format);
  int n = vsnprintf(printed + printed_size,
                    sizeof(printed) - printed_size, format, args);
  va_end(args);
  assert(n >= 0 && (size_t)n < sizeof(printed) - printed_size);
  printed_size += (size_t)n;
  return n;
}

static int fake_task_create(const char *name, int priority, int stack,
                            int (*entry)(int, char **), char **argv)
{
  assert(strcmp(name, "imu_daemon") == 0);
  assert(priority > 0 && stack > 0 && argv == NULL);
  create_count++;
  if (scenario == TASK_FAIL)
    {
      errno = EAGAIN;
      return -1;
    }
  pending_task = entry;
  return 17;
}

static int fake_open(const char *path, int flags, ...)
{
  assert(strcmp(path, "/dev/uorb/sensor_imu0") == 0);
  assert(flags == (O_RDONLY | O_NONBLOCK));
  open_count++;
  if (scenario == OPEN_FAIL)
    {
      errno = ENODEV;
      return -1;
    }
  return 42;
}

static int fake_close(int fd)
{
  assert(fd == 42);
  close_count++;
  return 0;
}

static int fake_clock_gettime(clockid_t clock_id, struct timespec *out)
{
  assert(clock_id == CLOCK_BOOTTIME);
  out->tv_sec = fake_now / 1000000;
  out->tv_nsec = (fake_now % 1000000) * 1000;
  return 0;
}

static ssize_t fake_read(int fd, void *out, size_t len)
{
  assert(fd == 42 && len == sizeof(struct sensor_imu));
  read_count++;
  if (scenario == LIVE_TIMING && !sample_pending)
    {
      errno = EAGAIN;
      return -1;
    }
  if (scenario != LIVE_TIMING && read_count > 1)
    {
      assert(scenario != STOP_DRAIN);
      errno = EAGAIN;
      return -1;
    }
  struct sensor_imu sample = {0};
  sample.timestamp = 999990;
  sample.az = 16384;
  sample.gz = 500;
  sample.fsr_xl_idx = 0;
  sample.fsr_gy_idx = 4;
  sample.odr_idx = 7;
  if (scenario == LIVE_TIMING)
    {
      sample.timestamp = timestamps[sample_index];
      if (sample_index == 0) sample.az = 0;
      sample.odr_idx = odrs[sample_index];
      sample.fsr_gy_idx = gyro_fsrs[sample_index];
      fake_now = (uint64_t)sample.timestamp + 10;
      sample_pending = false;
    }
  memcpy(out, &sample, sizeof(sample));
  if (scenario == STOP_DRAIN)
    {
      cmd_stop();
    }
  return sizeof(sample);
}

static int fake_poll(struct pollfd *fds, nfds_t count, int timeout)
{
  assert(count == 1 && fds[0].fd == 42 && timeout == IMU_POLL_TIMEOUT);
  poll_count++;
  assert(scenario != STOP_PENDING);
  if (scenario == LIVE_TIMING)
    {
      if (poll_count > 1)
        {
          imu_fusion_snapshot_t snapshot;
          integrated_time += steps[sample_index];
          if (valid_samples[sample_index])
            {
              valid_count++;
              assert(imu_service_snapshot(&snapshot) == 0);
              assert(snapshot.sequence == valid_count);
              assert(snapshot.timestamp_us == timestamps[sample_index]);
              assert(fabsf(snapshot.heading_1d + 17.5f * integrated_time) < .001f);
              assert(fabsf(imu_stationary_get_sample_time() -
                           1.0f / g_odr_hz_table[odrs[sample_index]]) < .000001f);
              uint64_t restore = fake_now;
              fake_now = snapshot.timestamp_us + IMU_MAX_AGE_US + 1;
              memset(&snapshot, 0xff, sizeof(snapshot));
              assert(imu_service_snapshot(&snapshot) == -EAGAIN);
              assert(!snapshot.valid && snapshot.timestamp_us == 0);
              fake_now = restore;
            }
          else
            {
              memset(&snapshot, 0xff, sizeof(snapshot));
              assert(imu_service_snapshot(&snapshot) == -EAGAIN);
              assert(!snapshot.valid && snapshot.timestamp_us == 0);
            }
          sample_index++;
        }
      if (sample_index == sizeof(odrs))
        {
          imu_fusion_snapshot_t snapshot;
          assert(imu_service_stop() == 0);
          assert(imu_service_start() == -EBUSY);
          assert(imu_service_snapshot(&snapshot) == -EAGAIN);
          return 0;
        }
      sample_pending = true;
      fds[0].revents = POLLIN;
      return 1;
    }
  if (scenario == POLL_FAULT)
    {
      fds[0].revents = POLLHUP;
      return 1;
    }
  if (scenario == INTERRUPTED && poll_count == 1)
    {
      errno = EINTR;
      return -1;
    }
  if (scenario == INTERRUPTED && poll_count == 3)
    {
      imu_fusion_snapshot_t snapshot;
      assert(imu_fusion_get_snapshot(&snapshot, 1000000, 1000));
      assert(snapshot.valid && snapshot.sequence == 1);
      assert(fabsf(snapshot.accel_mms2.z - IMU_STANDARD_GRAVITY) < .01f);
      assert(fabsf(snapshot.gyro_dps.z - 17.5f) < .001f);
      cmd_stop();
      return 0;
    }
  fds[0].revents = POLLIN;
  return 1;
}

static void reset(enum scenario next)
{
  assert(!g_daemon_running);
  scenario = next;
  create_count = open_count = close_count = read_count = poll_count = 0;
  pending_task = NULL;
  printed_size = 0;
  printed[0] = '\0';
  fake_now = 1000000;
  sample_index = 0;
  sample_pending = false;
  integrated_time = 0;
  valid_count = 0;
}

static int run_task(void)
{
  assert(pending_task != NULL);
  int (*entry)(int, char **) = pending_task;
  pending_task = NULL;
  int result = entry(0, NULL);
  assert(!g_daemon_running);
  cmd_status();
  assert(strstr(printed, "running:    no\nstarting:   no\n"));
  assert(isfinite(imu_stationary_get_sample_time()));
  return result;
}

static void *start_thread(void *unused)
{
  (void)unused;
  cmd_start();
  return NULL;
}

int main(void)
{
  reset(STOP_PENDING);
  cmd_start();
  cmd_start();
  assert(create_count == 1);
  cmd_status();
  assert(strstr(printed, "running:    no\nstarting:   yes\n"));
  cmd_stop();
  assert(imu_service_start() == -EBUSY);
  bool starting, running, stopping;
  imu_service_status(&starting, &running, &stopping);
  assert(starting && !running && stopping);
  imu_fusion_snapshot_t unavailable;
  memset(&unavailable, 0xff, sizeof(unavailable));
  assert(imu_service_snapshot(&unavailable) == -EAGAIN);
  assert(!unavailable.valid && unavailable.timestamp_us == 0);
  assert(imu_service_snapshot(NULL) == -EINVAL);
  assert(run_task() == 0);
  assert(open_count == 1 && close_count == 1 && poll_count == 0);

  /* A simultaneous second caller must also see the start reservation. */
  reset(STOP_PENDING);
  pthread_t first, second;
  assert(pthread_create(&first, NULL, start_thread, NULL) == 0);
  assert(pthread_create(&second, NULL, start_thread, NULL) == 0);
  assert(pthread_join(first, NULL) == 0);
  assert(pthread_join(second, NULL) == 0);
  assert(create_count == 1);
  cmd_stop();
  assert(run_task() == 0);

  reset(TASK_FAIL);
  assert(imu_service_start() == -EAGAIN);
  assert(create_count == 1 && !g_daemon_running);
  cmd_status();
  assert(strstr(printed, "running:    no\nstarting:   no\n"));
  reset(OPEN_FAIL);
  cmd_start();
  assert(run_task() == -1 && close_count == 0);

  reset(INTERRUPTED);
  cmd_start();
  assert(run_task() == 0);
  assert(poll_count == 3 && read_count == 2 && close_count == 1);

  reset(STOP_DRAIN);
  cmd_start();
  assert(run_task() == 0);
  assert(read_count == 1 && close_count == 1);

  reset(POLL_FAULT);
  cmd_start();
  assert(run_task() == 0);
  assert(poll_count == 1 && read_count == 0 && close_count == 1);
  reset(LIVE_TIMING);
  assert(imu_service_start() == 0);
  assert(imu_service_start() == 0);
  assert(run_task() == 0);
  assert(valid_count == 9 && close_count == 1);
  assert(imu_service_stop() == 0);
  puts("IMU daemon lifecycle, freshness and source timing checks passed");
  return 0;
}
