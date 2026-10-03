/****************************************************************************
 * apps/imu/imu_main.c
 *
 * NuttX NSH builtin application for IMU sensor fusion.
 ****************************************************************************/

#include <nuttx/config.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <fcntl.h>
#include <poll.h>
#include <unistd.h>
#include <math.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>

#include <nuttx/sensors/sensor.h>

#include <arch/board/board_lsm6dsl.h>

#include "imu_types.h"
#include "imu_stationary.h"
#include "imu_fusion.h"
#include "imu_calibration.h"
#include "imu_timestamp.h"
#include "imu_service.h"

/****************************************************************************
 * Pre-processor Definitions
 ****************************************************************************/

#define IMU_CAL_PATH      "/data/imu_cal.bin"
#define IMU_DAEMON_NAME   "imu_daemon"
/* Keep stop responsive when the sensor stops delivering samples. */
#define IMU_POLL_TIMEOUT  20
#define IMU_ODR           833
#define IMU_MAX_AGE_US    UINT64_C(300000)

#define IMU_GRAVITY_MS2    9.80665f

#define IMU_FSR_IDX_UNKNOWN 0xFF

/* Issue #139: physical-scale tables, indexed by the driver enum value
 * the LSM6DSL driver embeds per-sample in struct sensor_imu.  Mirrors
 * boards/spike-prime-hub/src/lsm6dsl_uorb.c:124-154 (sparse for the
 * gyro / xl FSR enums — invalid idx slots return 0 and invalidate the
 * current publication until a valid sample arrives).
 *
 *   accel sensitivity: fsr_g * 1000 / 32768 mg/LSB -> mm/s^2 via 9.80665
 *   gyro  sensitivity: fsr_dps * 0.035 / 1000 dps/LSB (Table 3 headroom)
 */

static const uint16_t g_odr_hz_table[] =
    {0, 13, 26, 52, 104, 208, 416, 833, 1660, 3330, 6660};

static const uint8_t  g_fsr_xl_g_table[]    = {2, 16, 4, 8};
static const uint16_t g_fsr_gy_dps_table[]  =
    {250, 125, 500, 0, 1000, 0, 2000};

static inline float accel_lsb_to_mms2_from_idx(uint8_t idx)
{
  if (idx >= (sizeof(g_fsr_xl_g_table) / sizeof(g_fsr_xl_g_table[0])))
    {
      return 0.0f;
    }

  uint8_t fsr_g = g_fsr_xl_g_table[idx];
  return ((float)fsr_g * IMU_GRAVITY_MS2 * 1000.0f) / 32768.0f;
}

static inline float gyro_lsb_to_dps_from_idx(uint8_t idx)
{
  if (idx >= (sizeof(g_fsr_gy_dps_table) / sizeof(g_fsr_gy_dps_table[0])))
    {
      return 0.0f;
    }

  uint16_t fsr_dps = g_fsr_gy_dps_table[idx];
  return ((float)fsr_dps * 0.035f) / 1000.0f;
}

/****************************************************************************
 * Private Data
 ****************************************************************************/

static pthread_mutex_t g_daemon_lock = PTHREAD_MUTEX_INITIALIZER;
static bool g_daemon_running;
static bool g_daemon_starting;
static bool g_daemon_stop;

/****************************************************************************
 * Private Functions
 ****************************************************************************/

/* Issue #139: cached scale factors recomputed each time the per-sample
 * fsr_xl_idx / fsr_gy_idx changes.  The stationary callback consumes
 * raw int16 sums and needs `g_gyro_dps_per_lsb` to convert them back to
 * dps, so it must match the scale that produced the sums in the
 * current window.  Sample-loop callers reset the stationary state on
 * idx change to keep the window homogeneous.
 */

static float g_accel_mms2_per_lsb;
static float g_gyro_dps_per_lsb;

static bool daemon_should_stop(void)
{
  pthread_mutex_lock(&g_daemon_lock);
  bool stop = g_daemon_stop;
  pthread_mutex_unlock(&g_daemon_lock);
  return stop;
}

static bool daemon_is_running(void)
{
  pthread_mutex_lock(&g_daemon_lock);
  bool running = g_daemon_running;
  pthread_mutex_unlock(&g_daemon_lock);
  return running;
}

static void daemon_finished(void)
{
  pthread_mutex_lock(&g_daemon_lock);
  g_daemon_running = false;
  g_daemon_starting = false;
  g_daemon_stop = false;
  pthread_mutex_unlock(&g_daemon_lock);
}

static void stationary_callback(const int32_t *gyro_sum,
                                const int32_t *accel_sum,
                                uint32_t num_samples)
{
  imu_fusion_stationary_update(gyro_sum, accel_sum, num_samples,
                               g_gyro_dps_per_lsb);
}

static int imu_daemon(int argc, char *argv[])
{
  (void)argc;
  (void)argv;
  struct pollfd fds[1];
  struct sensor_imu imu_data;
  int imu_fd;
  int ret;

  /* Open the combined IMU topic. */

  imu_fd = open("/dev/uorb/sensor_imu0", O_RDONLY | O_NONBLOCK);
  if (imu_fd < 0)
    {
      fprintf(stderr, "imu: cannot open sensor_imu0\n");
      daemon_finished();
      return -1;
    }

  /* Issue #139: scale factors are derived per-sample from idx fields,
   * so leave them at 0 and let the sample loop initialise on the first
   * frame.  The stationary thresholds also depend on the scale, so they
   * get re-applied via imu_stationary_set_thresholds() when idx changes.
   */

  g_accel_mms2_per_lsb = 0.0f;
  g_gyro_dps_per_lsb   = 0.0f;

  /* Initialize modules */

  imu_settings_t *settings = imu_calibration_get_settings();
  imu_calibration_init(settings);
  imu_calibration_load(IMU_CAL_PATH);
  imu_fusion_init();
  imu_fusion_set_settings(settings);
  imu_stationary_init(0.0f, 0.0f, IMU_ODR, stationary_callback);

  uint8_t cur_fsr_xl_idx = IMU_FSR_IDX_UNKNOWN;
  uint8_t cur_fsr_gy_idx = IMU_FSR_IDX_UNKNOWN;
  uint8_t cur_odr_idx = IMU_FSR_IDX_UNKNOWN;
  uint64_t previous_timestamp = 0;

  pthread_mutex_lock(&g_daemon_lock);
  g_daemon_running = true;
  g_daemon_starting = false;
  pthread_mutex_unlock(&g_daemon_lock);

  printf("imu: daemon started\n");

  /* Poll loop */

  while (!daemon_should_stop())
    {
      fds[0].fd = imu_fd;
      fds[0].events = POLLIN;

      ret = poll(fds, 1, IMU_POLL_TIMEOUT);
      if (ret < 0)
        {
          if (errno == EINTR)
            {
              continue;
            }

          break;
        }

      if (ret == 0)
        {
          continue;
        }

      if (fds[0].revents & (POLLERR | POLLHUP | POLLNVAL))
        {
          break;
        }

      if (!(fds[0].revents & POLLIN))
        {
          continue;
        }

      while (!daemon_should_stop() &&
             read(imu_fd, &imu_data, sizeof(imu_data)) ==
             sizeof(imu_data))
        {
          /* Issue #139: detect FSR change before any conversion or
           * stationary-window accumulation.  Recompute scale factors
           * and reset the stationary state so the new window starts
           * fresh under the new sensitivity.
           */

          struct timespec received_at;
          uint64_t source_timestamp = 0;
          if (clock_gettime(CLOCK_BOOTTIME, &received_at) < 0)
            {
              previous_timestamp = 0;
              imu_stationary_reset();
              (void)imu_fusion_update_timestamped(NULL, NULL, 0, 0);
              continue;
            }
          uint64_t now_us = (uint64_t)received_at.tv_sec * 1000000ULL +
                            (uint64_t)received_at.tv_nsec / 1000ULL;
          if (!imu_timestamp_expand(imu_data.timestamp, now_us, &source_timestamp))
            {
              previous_timestamp = 0;
              imu_stationary_reset();
              (void)imu_fusion_update_timestamped(NULL, NULL, 0, 0);
              continue;
            }

          float new_accel = accel_lsb_to_mms2_from_idx(imu_data.fsr_xl_idx);
          float new_gyro = gyro_lsb_to_dps_from_idx(imu_data.fsr_gy_idx);
          uint16_t odr = imu_data.odr_idx <
              sizeof(g_odr_hz_table) / sizeof(g_odr_hz_table[0]) ?
              g_odr_hz_table[imu_data.odr_idx] : 0;
          bool changed = imu_data.fsr_xl_idx != cur_fsr_xl_idx ||
                         imu_data.fsr_gy_idx != cur_fsr_gy_idx ||
                         imu_data.odr_idx != cur_odr_idx;

          /* ODR and scales belong to each sample. Never accumulate a
           * stationary window across source configuration changes. */
          if (changed)
            {
              cur_fsr_xl_idx = imu_data.fsr_xl_idx;
              cur_fsr_gy_idx = imu_data.fsr_gy_idx;
              cur_odr_idx = imu_data.odr_idx;
              previous_timestamp = 0;
              g_accel_mms2_per_lsb = new_accel;
              g_gyro_dps_per_lsb = new_gyro;
              if (new_accel > 0 && new_gyro > 0 && odr > 0)
                {
                  imu_stationary_init(
                      settings->gyro_stationary_threshold / new_gyro,
                      settings->accel_stationary_threshold / new_accel,
                      odr, stationary_callback);
                }
            }

          /* Reject stale input, stopped/unknown ODR, unknown scales and
           * discontinuous time. A gap over 300 ms is not integrated blindly;
           * the next valid frame starts with one nominal ODR interval. */
          if (odr == 0 || new_accel <= 0 || new_gyro <= 0 ||
              now_us - source_timestamp > IMU_MAX_AGE_US ||
              (previous_timestamp != 0 &&
               (source_timestamp <= previous_timestamp ||
                source_timestamp - previous_timestamp > IMU_MAX_AGE_US)))
            {
              previous_timestamp = 0;
              imu_stationary_reset();
              (void)imu_fusion_update_timestamped(NULL, NULL, 0, source_timestamp);
              continue;
            }

          float sample_time = previous_timestamp == 0 ? 1.0f / odr :
              (float)(source_timestamp - previous_timestamp) / 1000000.0f;
          previous_timestamp = source_timestamp;

          int16_t raw[6];
          raw[0] = imu_data.gx;
          raw[1] = imu_data.gy;
          raw[2] = imu_data.gz;
          raw[3] = imu_data.ax;
          raw[4] = imu_data.ay;
          raw[5] = imu_data.az;

          imu_stationary_update(raw);

          imu_xyz_t accel_mms2 =
          {
            .x = (float)imu_data.ax * g_accel_mms2_per_lsb,
            .y = (float)imu_data.ay * g_accel_mms2_per_lsb,
            .z = (float)imu_data.az * g_accel_mms2_per_lsb,
          };

          imu_xyz_t gyro_dps =
          {
            .x = (float)imu_data.gx * g_gyro_dps_per_lsb,
            .y = (float)imu_data.gy * g_gyro_dps_per_lsb,
            .z = (float)imu_data.gz * g_gyro_dps_per_lsb,
          };

          (void)imu_fusion_update_timestamped(&gyro_dps, &accel_mms2, sample_time,
                                               source_timestamp);
        }
    }

  close(imu_fd);

  /* Reset module state so status reports clean after stop */

  imu_stationary_reset();
  imu_fusion_init();

  daemon_finished();
  printf("imu: daemon stopped\n");
  return 0;
}

int imu_service_start(void)
{
  pthread_mutex_lock(&g_daemon_lock);
  if (g_daemon_stop)
    {
      pthread_mutex_unlock(&g_daemon_lock);
      return -EBUSY;
    }
  if (g_daemon_running || g_daemon_starting)
    {
      pthread_mutex_unlock(&g_daemon_lock);
      return 0;
    }

  /* Reserve the producer before task_create can schedule the child.  A
   * stop received during initialization belongs to this reservation and
   * must not be cleared by the child when it becomes running.
   */

  g_daemon_starting = true;
  g_daemon_stop = false;
  pthread_mutex_unlock(&g_daemon_lock);

  int pid = task_create(IMU_DAEMON_NAME, 100, 4096, imu_daemon, NULL);
  if (pid < 0)
    {
      int error = errno;
      daemon_finished();
      return -error;
    }
  return 0;
}

int imu_service_stop(void)
{
  pthread_mutex_lock(&g_daemon_lock);
  if (!g_daemon_running && !g_daemon_starting)
    {
      pthread_mutex_unlock(&g_daemon_lock);
      return 0;
    }

  g_daemon_stop = true;
  pthread_mutex_unlock(&g_daemon_lock);
  return 0;
}

void imu_service_status(bool *starting, bool *running, bool *stopping)
{
  pthread_mutex_lock(&g_daemon_lock);
  if (starting != NULL) *starting = g_daemon_starting;
  if (running != NULL) *running = g_daemon_running;
  if (stopping != NULL) *stopping = g_daemon_stop;
  pthread_mutex_unlock(&g_daemon_lock);
}

int imu_service_snapshot(imu_fusion_snapshot_t *out)
{
  if (out == NULL) return -EINVAL;
  memset(out, 0, sizeof(*out));
  pthread_mutex_lock(&g_daemon_lock);
  int result = -EAGAIN;
  if (g_daemon_running && !g_daemon_stop)
    {
      struct timespec now;
      if (clock_gettime(CLOCK_BOOTTIME, &now) < 0)
        result = -errno;
      else if (imu_fusion_get_snapshot(out,
                   (uint64_t)now.tv_sec * 1000000ULL + now.tv_nsec / 1000ULL,
                   IMU_MAX_AGE_US))
        result = 0;
    }
  pthread_mutex_unlock(&g_daemon_lock);
  return result;
}

static void cmd_start(void)
{
  int result = imu_service_start();
  if (result < 0) fprintf(stderr, "imu: start failed: %d\n", result);
}

static void cmd_stop(void)
{
  (void)imu_service_stop();
}

static void cmd_status(void)
{
  bool running, starting;
  imu_service_status(&starting, &running, NULL);
  printf("running:    %s\n", running ? "yes" : "no");
  printf("starting:   %s\n", starting ? "yes" : "no");
  printf("stationary: %s\n",
         imu_stationary_is_stationary() ? "yes" : "no");
  printf("ready:      %s\n", imu_fusion_is_ready() ? "yes" : "no");
}

static void cmd_accel(bool raw)
{
  imu_xyz_t v;
  imu_fusion_get_accel(&v, !raw);
  printf("accel: x=%.1f y=%.1f z=%.1f mm/s^2\n", v.x, v.y, v.z);
}

static void cmd_gyro(bool raw)
{
  imu_xyz_t v;
  imu_fusion_get_gyro(&v, !raw);
  printf("gyro: x=%.3f y=%.3f z=%.3f deg/s\n", v.x, v.y, v.z);
}

/* Dump live IMU samples for `duration_ms` straight from the uORB topic.
 * `which` selects accel ('a') or gyro ('g'); `raw` prints chip-frame
 * int16 LSB instead of physical units.  Timestamp is the driver's
 * ISR-captured CLOCK_BOOTTIME us low 32 bits (mod 2^32, ~71m35s wrap).
 *
 * The IMU daemon must be running so the sensor is activated and samples
 * are flowing on the topic.
 */

static void cmd_dump(char which, bool raw, uint32_t duration_ms)
{
  if (!daemon_is_running())
    {
      fprintf(stderr, "imu: daemon not running; run 'imu start' first\n");
      return;
    }

  int fd = open("/dev/uorb/sensor_imu0", O_RDONLY | O_NONBLOCK);
  if (fd < 0)
    {
      fprintf(stderr, "imu: cannot open sensor_imu0\n");
      return;
    }

  /* Issue #139: physical scale comes from each sample's embedded
   * fsr_*_idx, computed in the inner loop below; no fallback to a
   * fixed startup FSR is needed because driver samples always carry
   * a valid idx.
   */

  if (raw)
    {
      printf("# ts_us %s_x %s_y %s_z (raw int16)\n",
             which == 'a' ? "ax" : "gx",
             which == 'a' ? "ay" : "gy",
             which == 'a' ? "az" : "gz");
    }
  else
    {
      printf("# ts_us %s_x %s_y %s_z (%s)\n",
             which == 'a' ? "ax" : "gx",
             which == 'a' ? "ay" : "gy",
             which == 'a' ? "az" : "gz",
             which == 'a' ? "mm/s^2" : "deg/s");
    }

  struct timespec t0;
  clock_gettime(CLOCK_BOOTTIME, &t0);
  uint64_t deadline_us = (uint64_t)t0.tv_sec * 1000000ULL +
                         (uint64_t)t0.tv_nsec / 1000ULL +
                         (uint64_t)duration_ms * 1000ULL;

  uint32_t printed = 0;
  while (1)
    {
      struct timespec now;
      clock_gettime(CLOCK_BOOTTIME, &now);
      uint64_t now_us = (uint64_t)now.tv_sec * 1000000ULL +
                        (uint64_t)now.tv_nsec / 1000ULL;
      if (now_us >= deadline_us)
        {
          break;
        }

      struct pollfd pfd = { .fd = fd, .events = POLLIN };
      int remaining_ms = (int)((deadline_us - now_us) / 1000ULL);
      if (remaining_ms <= 0)
        {
          break;
        }

      int pret = poll(&pfd, 1, remaining_ms);
      if (pret <= 0)
        {
          continue;
        }

      struct sensor_imu s;
      while (read(fd, &s, sizeof(s)) == sizeof(s))
        {
          /* Issue #139: per-sample physical scale.  Each sample carries
           * its own FSR idx so a live SET mid-dump is reflected
           * immediately.  raw-mode bypasses conversion.
           */

          float a_scale =
              raw ? 0.0f : accel_lsb_to_mms2_from_idx(s.fsr_xl_idx);
          float g_scale =
              raw ? 0.0f : gyro_lsb_to_dps_from_idx(s.fsr_gy_idx);

          if (which == 'a')
            {
              if (raw)
                {
                  printf("%u %d %d %d\n", (unsigned)s.timestamp,
                         s.ax, s.ay, s.az);
                }
              else
                {
                  printf("%u %.3f %.3f %.3f\n", (unsigned)s.timestamp,
                         (double)((float)s.ax * a_scale),
                         (double)((float)s.ay * a_scale),
                         (double)((float)s.az * a_scale));
                }
            }
          else
            {
              if (raw)
                {
                  printf("%u %d %d %d\n", (unsigned)s.timestamp,
                         s.gx, s.gy, s.gz);
                }
              else
                {
                  printf("%u %.4f %.4f %.4f\n", (unsigned)s.timestamp,
                         (double)((float)s.gx * g_scale),
                         (double)((float)s.gy * g_scale),
                         (double)((float)s.gz * g_scale));
                }
            }

          printed++;

          /* Issue #139: gate the inner drain on the deadline.  Without
           * this, USB-CDC printf throughput can fall behind the 833 Hz
           * sample rate and the loop never sees an empty read.
           */

          clock_gettime(CLOCK_BOOTTIME, &now);
          now_us = (uint64_t)now.tv_sec * 1000000ULL +
                   (uint64_t)now.tv_nsec / 1000ULL;
          if (now_us >= deadline_us)
            {
              break;
            }
        }
    }

  close(fd);
  printf("# %u sample(s) over %u ms\n", (unsigned)printed,
         (unsigned)duration_ms);
}

static void cmd_mag(void)
{
  struct sensor_mag mag_data;
  int fd;

  fd = open("/dev/uorb/sensor_mag0", O_RDONLY | O_NONBLOCK);
  if (fd < 0)
    {
      fprintf(stderr, "imu: cannot open sensor_mag0\n");
      return;
    }

  if (read(fd, &mag_data, sizeof(mag_data)) == sizeof(mag_data))
    {
      printf("mag: x=%.3f y=%.3f z=%.3f uT\n",
             mag_data.x, mag_data.y, mag_data.z);
    }
  else
    {
      printf("mag: no data\n");
    }

  close(fd);
}

static void cmd_heading(imu_heading_type_t type)
{
  float h = imu_fusion_get_heading(type);
  printf("heading: %.2f deg (%s)\n", h,
         type == IMU_HEADING_1D ? "1D" : "3D");
}

static void cmd_tilt(void)
{
  imu_xyz_t v;
  imu_fusion_get_tilt(&v);
  printf("tilt: x=%.4f y=%.4f z=%.4f\n", v.x, v.y, v.z);
}

static void cmd_upside(void)
{
  imu_side_t side = imu_fusion_get_up_side(true);
  const char *names[] =
  {
    "front", "left", "top", "back", "right", "bottom"
  };

  /* Map enum to index:
   * FRONT=0, LEFT=1, TOP=2, BACK=4, RIGHT=5, BOTTOM=6
   */

  int idx;
  switch (side)
    {
      case IMU_SIDE_FRONT:  idx = 0; break;
      case IMU_SIDE_LEFT:   idx = 1; break;
      case IMU_SIDE_TOP:    idx = 2; break;
      case IMU_SIDE_BACK:   idx = 3; break;
      case IMU_SIDE_RIGHT:  idx = 4; break;
      case IMU_SIDE_BOTTOM: idx = 5; break;
      default:              idx = 2; break;
    }

  printf("up side: %s\n", names[idx]);
}

static void cmd_orient(void)
{
  imu_matrix_3x3_t m;
  imu_fusion_get_orientation(&m);
  printf("orientation:\n");
  printf("  [%.4f %.4f %.4f]\n", m.m11, m.m12, m.m13);
  printf("  [%.4f %.4f %.4f]\n", m.m21, m.m22, m.m23);
  printf("  [%.4f %.4f %.4f]\n", m.m31, m.m32, m.m33);
}

static void print_usage(void)
{
  printf("Usage: imu <command>\n");
  printf("Commands:\n");
  printf("  start        - start daemon\n");
  printf("  stop         - stop daemon\n");
  printf("  status       - print status\n");
  printf("  accel [raw] [ms] - print acceleration; with ms, dump samples\n");
  printf("  gyro  [raw] [ms] - print angular velocity; with ms, dump\n");
  printf("  mag          - print magnetic field\n");
  printf("  heading [1d|3d] - print heading\n");
  printf("  tilt         - print tilt vector\n");
  printf("  upside       - print which side is up\n");
  printf("  orient       - print rotation matrix\n");
  printf("  cal save     - save calibration\n");
  printf("  cal load     - load calibration\n");
  printf("  setbase      - set base orientation\n");
  printf("  resetheading - reset heading to 0\n");
}

/****************************************************************************
 * Public Functions
 ****************************************************************************/

int main(int argc, FAR char *argv[])
{
  if (argc < 2)
    {
      print_usage();
      return 0;
    }

  if (strcmp(argv[1], "start") == 0)
    {
      cmd_start();
    }
  else if (strcmp(argv[1], "stop") == 0)
    {
      cmd_stop();
    }
  else if (strcmp(argv[1], "status") == 0)
    {
      cmd_status();
    }
  else if (strcmp(argv[1], "accel") == 0)
    {
      bool raw = false;
      int dur_arg_idx = 2;
      if (argc > 2 && strcmp(argv[2], "raw") == 0)
        {
          raw = true;
          dur_arg_idx = 3;
        }

      if (argc > dur_arg_idx)
        {
          uint32_t ms = (uint32_t)strtoul(argv[dur_arg_idx], NULL, 10);
          cmd_dump('a', raw, ms);
        }
      else
        {
          cmd_accel(raw);
        }
    }
  else if (strcmp(argv[1], "gyro") == 0)
    {
      bool raw = false;
      int dur_arg_idx = 2;
      if (argc > 2 && strcmp(argv[2], "raw") == 0)
        {
          raw = true;
          dur_arg_idx = 3;
        }

      if (argc > dur_arg_idx)
        {
          uint32_t ms = (uint32_t)strtoul(argv[dur_arg_idx], NULL, 10);
          cmd_dump('g', raw, ms);
        }
      else
        {
          cmd_gyro(raw);
        }
    }
  else if (strcmp(argv[1], "mag") == 0)
    {
      cmd_mag();
    }
  else if (strcmp(argv[1], "heading") == 0)
    {
      imu_heading_type_t type = IMU_HEADING_3D;
      if (argc > 2 && strcmp(argv[2], "1d") == 0)
        {
          type = IMU_HEADING_1D;
        }

      cmd_heading(type);
    }
  else if (strcmp(argv[1], "tilt") == 0)
    {
      cmd_tilt();
    }
  else if (strcmp(argv[1], "upside") == 0)
    {
      cmd_upside();
    }
  else if (strcmp(argv[1], "orient") == 0)
    {
      cmd_orient();
    }
  else if (strcmp(argv[1], "cal") == 0)
    {
      if (argc < 3)
        {
          printf("Usage: imu cal <save|load>\n");
        }
      else if (strcmp(argv[2], "save") == 0)
        {
          imu_settings_t coherent_settings;
          if (imu_fusion_get_settings(&coherent_settings) &&
              imu_calibration_save_copy(IMU_CAL_PATH, &coherent_settings) == 0)
            {
              printf("calibration saved\n");
            }
          else
            {
              fprintf(stderr, "imu: save failed\n");
            }
        }
      else if (strcmp(argv[2], "load") == 0)
        {
          if (imu_calibration_load(IMU_CAL_PATH) == 0)
            {
              imu_fusion_set_settings(imu_calibration_get_settings());
              printf("calibration loaded\n");
            }
          else
            {
              fprintf(stderr, "imu: load failed\n");
            }
        }
    }
  else if (strcmp(argv[1], "setbase") == 0)
    {
      imu_xyz_t front = { .x = 1.0f, .y = 0.0f, .z = 0.0f };
      imu_xyz_t top   = { .x = 0.0f, .y = 0.0f, .z = 1.0f };
      imu_fusion_set_base_orientation(&front, &top);
      printf("base orientation set to identity\n");
    }
  else if (strcmp(argv[1], "resetheading") == 0)
    {
      imu_fusion_set_heading(0.0f);
      printf("heading reset\n");
    }
  else
    {
      print_usage();
      return 1;
    }

  return 0;
}
