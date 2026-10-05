/* SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Christian Strobele
 * Execute the actual application with synthetic task/device boundaries.
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <float.h>
#include <limits.h>
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

static char calibration_path[] = "/tmp/bw-imu-daemon-calibration-XXXXXX";
#define IMU_CAL_PATH calibration_path
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
                POLL_FAULT, LIVE_TIMING, STATIONARY_BIAS, STATIONARY_REOPEN, LIVE_BASE, LIVE_CALIBRATION };
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
static float stationary_heading;

/* All three compiled modules must observe the same synthetic monotonic clock,
 * rather than measuring real wall time while samples are supplied instantly. */
int clock_gettime(clockid_t clock_id, struct timespec *out)
{
  return fake_clock_gettime(clock_id, out);
}

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
  assert(clock_id == CLOCK_BOOTTIME || clock_id == CLOCK_MONOTONIC);
  out->tv_sec = fake_now / 1000000;
  out->tv_nsec = (fake_now % 1000000) * 1000;
  return 0;
}

static ssize_t fake_read(int fd, void *out, size_t len)
{
  assert(fd == 42 && len == sizeof(struct sensor_imu));
  read_count++;
  bool streaming = scenario == LIVE_TIMING || scenario == STATIONARY_BIAS ||
                   scenario == STATIONARY_REOPEN || scenario == LIVE_CALIBRATION;
  if (streaming && !sample_pending)
    {
      errno = EAGAIN;
      return -1;
    }
  if (!streaming && read_count > 1)
    {
      assert(scenario != STOP_DRAIN);
      errno = EAGAIN;
      return -1;
    }
  struct sensor_imu sample = {0};
  sample.timestamp = 999990;
  sample.az = 16384;
  sample.gz = 500;
  if (scenario == LIVE_BASE)
    {
      sample.ax = 1000; sample.ay = 2000;
      sample.gx = 20; sample.gy = -30; sample.gz = 40;
    }
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
  if (scenario == STATIONARY_BIAS || scenario == STATIONARY_REOPEN ||
      scenario == LIVE_CALIBRATION)
    {
      sample.timestamp = 1000000 + sample_index * 1000000 / 13;
      sample.odr_idx = 1;
      sample.gx = 20;
      sample.gy = -30;
      sample.gz = 40;
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

static void check_live_base(void)
{
  imu_fusion_snapshot_t physical, changed, preserved;
  imu_xyz_t front = {.y = 1}, top = {.z = 1};
  assert(imu_service_snapshot(&physical) == 0);
  assert(imu_service_set_base_axes(&front, &top) == 0);
  assert(imu_service_snapshot(&changed) == 0);
  assert(changed.sequence == physical.sequence);
  assert(changed.timestamp_us == physical.timestamp_us);
  assert(changed.ready == physical.ready && changed.up_side == physical.up_side);
  assert(memcmp(&changed.orientation, &physical.orientation,
                sizeof(changed.orientation)) == 0);
  assert(fabsf(changed.accel_mms2.x - physical.accel_mms2.y) < .0001f);
  assert(fabsf(changed.accel_mms2.y + physical.accel_mms2.x) < .0001f);
  assert(changed.accel_mms2.z == physical.accel_mms2.z);
  assert(fabsf(changed.gyro_dps.x - physical.gyro_dps.y) < .0001f);
  assert(fabsf(changed.gyro_dps.y + physical.gyro_dps.x) < .0001f);
  assert(changed.gyro_dps.z == physical.gyro_dps.z);
  assert(fabsf(changed.heading_1d) < .0001f);
  assert(fabsf(changed.heading_3d) < .0001f);

  imu_xyz_t invalid[] = {{.x = 0}, {.x = 2}, {.x = .5f}, {.x = NAN},
                         {.x = INFINITY}, {.x = 1, .y = 1}};
  assert(imu_service_set_base_axes(NULL, &top) == -EINVAL);
  assert(imu_service_set_base_axes(&front, NULL) == -EINVAL);
  assert(imu_service_set_base_axes(&front, &front) == -EINVAL);
  for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++)
    {
      assert(imu_service_set_base_axes(&invalid[i], &top) == -EINVAL);
      assert(imu_service_set_base_axes(&front, &invalid[i]) == -EINVAL);
    }
  assert(imu_service_snapshot(&preserved) == 0);
  assert(memcmp(&changed, &preserved, sizeof(changed)) == 0);
  assert(imu_service_stop() == 0);
  assert(imu_service_set_base_axes(&front, &top) == -EAGAIN);
}

static void load_live_threshold(float gyro_threshold)
{
  imu_settings_t settings;
  assert(imu_fusion_get_settings(&settings));
  settings.gyro_stationary_threshold = gyro_threshold;
  settings.flags |= IMU_FLAG_GYRO_THRESHOLD;
  assert(imu_calibration_save_copy(calibration_path, &settings) == 0);
  char *args[] = {"imu", "cal", "load"};
  assert(imu_application_main(3, args) == 0);
}

static int fake_poll(struct pollfd *fds, nfds_t count, int timeout)
{
  assert(count == 1 && fds[0].fd == 42 && timeout == IMU_POLL_TIMEOUT);
  poll_count++;
  assert(scenario != STOP_PENDING);
  if (scenario == LIVE_CALIBRATION)
    {
      if (poll_count > 1)
        {
          unsigned frames = sample_index + 1;
          imu_fusion_snapshot_t snapshot;
          if (frames == 140)
            {
              assert(imu_service_snapshot(&snapshot) == -EAGAIN);
              assert(!imu_stationary_is_stationary());
              load_live_threshold(2.0f);
            }
          else
            {
              assert(imu_service_snapshot(&snapshot) == 0);
              if (frames == 138)
                {
                  assert(snapshot.ready && imu_stationary_is_stationary());
                  load_live_threshold(0.0f);
                }
              else if (frames == 139)
                {
                  /* FSR/ODR stayed identical; loading a new threshold alone
                   * must restart the old stationary accumulation window. */
                  assert(!imu_stationary_is_stationary());
                  load_live_threshold(FLT_MAX);
                }
              else if (frames == 141)
                {
                  assert(!imu_stationary_is_stationary());
                  uint32_t revision = g_calibration_revision;
                  imu_settings_t before, after;
                  assert(imu_fusion_get_settings(&before));
                  assert(unlink(calibration_path) == 0);
                  char *args[] = {"imu", "cal", "load"};
                  assert(imu_application_main(3, args) == 1);
                  assert(g_calibration_revision == revision);
                  assert(imu_fusion_get_settings(&after));
                  assert(memcmp(&before, &after, sizeof(before)) == 0);
                }
            }
          sample_index++;
        }
      if (sample_index == 141)
        {
          assert(imu_service_stop() == 0);
          return 0;
        }
      sample_pending = true;
      fds[0].revents = POLLIN;
      return 1;
    }
  if (scenario == STATIONARY_BIAS || scenario == STATIONARY_REOPEN)
    {
      if (poll_count > 1)
        {
          unsigned frames = sample_index + 1;
          imu_fusion_snapshot_t snapshot;
          imu_settings_t settings;
          assert(imu_service_snapshot(&snapshot) == 0);
          assert(snapshot.sequence == frames);
          assert(imu_fusion_get_settings(&settings));
          if (frames < 125 + 13)
            {
              assert(!snapshot.ready);
              assert(!imu_stationary_is_stationary());
              assert(fabsf(snapshot.gyro_dps.x - .7f) < .00001f);
              assert(fabsf(snapshot.gyro_dps.y + 1.05f) < .00001f);
              assert(fabsf(snapshot.gyro_dps.z - 1.4f) < .00001f);
              stationary_heading = snapshot.heading_1d;
            }
          else
            {
              assert(snapshot.ready && imu_stationary_is_stationary());
              uint64_t restore = fake_now;
              fake_now += UINT64_C(600000000);
              assert(!imu_fusion_is_ready());
              fake_now = restore;
              assert(imu_fusion_is_ready());
              for (size_t i = 0; i < 3; i++)
                assert(fabsf(snapshot.gyro_dps.values[i]) < .00001f);
              assert(fabsf(snapshot.heading_1d - stationary_heading) < .00001f);
              assert(fabsf(imu_stationary_get_sample_time() - 1.0f / 13) < .00001f);
            }
          bool saved_initial_bias = frames >= 125 + 3 * 13;
          assert(!!(settings.flags & IMU_FLAG_GYRO_BIAS) == saved_initial_bias);
          if (saved_initial_bias)
            {
              assert(fabsf(settings.angular_velocity_bias_start.x - .7f) < .00001f);
              assert(fabsf(settings.angular_velocity_bias_start.y + 1.05f) < .00001f);
              assert(fabsf(settings.angular_velocity_bias_start.z - 1.4f) < .00001f);
            }
          sample_index++;
        }
      size_t count = scenario == STATIONARY_REOPEN ? 1 : 125 + 3 * 13;
      if (sample_index == count)
        {
          assert(imu_service_stop() == 0);
          return 0;
        }
      sample_pending = true;
      fds[0].revents = POLLIN;
      return 1;
    }
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
  if (scenario == LIVE_BASE && poll_count == 2)
    {
      check_live_base();
      return 0;
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

static void stationary_threshold_guards(void)
{
  const float invalid[] = {NAN, INFINITY, -INFINITY, -1.0f,
                           (float)INT16_MAX + 1.0f, FLT_MAX};
  assert(imu_stationary_init(7.5f, INT16_MAX, 13, NULL) == 0);
  float sample_time = imu_stationary_get_sample_time();
  for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++)
    {
      int result = i >= 4 ? -ERANGE : -EINVAL;
      assert(imu_stationary_init(invalid[i], 1, 104, NULL) == result);
      assert(imu_stationary_init(1, invalid[i], 104, NULL) == result);
      assert(imu_stationary_set_thresholds(invalid[i], 1) == result);
      assert(imu_stationary_set_thresholds(1, invalid[i]) == result);
      assert(imu_stationary_get_sample_time() == sample_time);
    }
  assert(imu_stationary_init(1, 1, 0, NULL) == -EINVAL);
  assert(imu_stationary_get_sample_time() == sample_time);
  assert(imu_stationary_init(0, 0, 104, NULL) == 0);
  assert(imu_stationary_set_thresholds(INT16_MAX, INT16_MAX) == 0);
}

int main(void)
{
  stationary_threshold_guards();
  int calibration_fd = mkstemp(calibration_path);
  assert(calibration_fd >= 0 && close(calibration_fd) == 0);
  assert(unlink(calibration_path) == 0);
  imu_xyz_t front = {.y = 1}, top = {.z = 1};
  assert(imu_service_set_base_axes(&front, &top) == -EAGAIN);
  reset(STOP_PENDING);
  cmd_start();
  assert(imu_service_set_base_axes(&front, &top) == -EAGAIN);
  cmd_start();
  assert(create_count == 1);
  cmd_status();
  assert(strstr(printed, "running:    no\nstarting:   yes\n"));
  cmd_stop();
  assert(imu_service_start() == -EBUSY);
  assert(imu_service_set_base_axes(&front, &top) == -EAGAIN);
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
  reset(STATIONARY_BIAS);
  assert(imu_service_start() == 0);
  assert(run_task() == 0);
  assert(sample_index == 164 && close_count == 1);
  assert(!imu_fusion_is_ready() && !imu_stationary_is_stationary());
  reset(STATIONARY_REOPEN);
  assert(imu_service_start() == 0);
  assert(run_task() == 0);
  assert(sample_index == 1 && close_count == 1);
  reset(LIVE_BASE);
  assert(imu_service_start() == 0);
  assert(run_task() == 0);
  assert(close_count == 1 && read_count == 2);
  assert(imu_service_set_base_axes(&front, &top) == -EAGAIN);
  reset(LIVE_CALIBRATION);
  assert(imu_service_start() == 0);
  assert(run_task() == 0);
  assert(sample_index == 141 && close_count == 1);
  puts("IMU daemon lifecycle, source timing, bias, reopen, base-axis and live calibration threshold checks passed");
  return 0;
}
