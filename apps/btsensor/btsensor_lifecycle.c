/* SPDX-License-Identifier: Apache-2.0 */

#include <nuttx/config.h>

#include <errno.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

#include <nuttx/sched.h>

#include "btsensor_lifecycle.h"

#define BTSENSOR_DAEMON_NAME "btsensor_d"

#ifndef CONFIG_APP_BTSENSOR_PRIORITY
#  define CONFIG_APP_BTSENSOR_PRIORITY 100
#endif
#ifndef CONFIG_APP_BTSENSOR_STACKSIZE
#  define CONFIG_APP_BTSENSOR_STACKSIZE 4096
#endif

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static sem_t g_stop_request;
static sem_t g_stopped;
static bool g_semaphores_ready;
static bool g_running;
static int g_pid = -1;
static struct btsensor_lifecycle_hooks g_hooks;

static void deadline_after_ms(struct timespec *deadline, int timeout_ms)
{
  clock_gettime(CLOCK_REALTIME, deadline);
  deadline->tv_sec += timeout_ms / 1000;
  deadline->tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
  if (deadline->tv_nsec >= 1000000000L)
    {
      deadline->tv_sec++;
      deadline->tv_nsec -= 1000000000L;
    }
}

static __attribute__((noinline)) void daemon_wait_for_stop(void)
{
  while (sem_wait(&g_stop_request) < 0 && errno == EINTR)
    {
    }
}

#ifdef CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER
/* Stable Renode milestone: services and the HCI host are live when execution
 * reaches this function.  It has no side effects and is absent from hardware
 * builds so it cannot become a physical-firmware behavior dependency. */

__attribute__((noinline)) void brickwright_simulation_daemon_ready(void)
{
  __asm__ __volatile__("" ::: "memory");
}
#endif

static int daemon_main(int argc, char **argv)
{
  int ret = 0;
  bool services_started = false;
  bool transport_started = false;

  (void)argc;
  (void)argv;

  if (g_hooks.services_start)
    {
      ret = g_hooks.services_start(g_hooks.services_context);
      services_started = ret == 0;
    }

  if (ret == 0)
    {
      ret = btsensor_transport_start(g_hooks.receive,
                                     g_hooks.state,
                                     g_hooks.receive_context);
      transport_started = ret == 0;
    }

  if (ret == 0)
    {
#ifdef CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER
      brickwright_simulation_daemon_ready();
#endif
      daemon_wait_for_stop();
    }

  if (transport_started)
    {
      (void)btsensor_transport_stop();
    }

  if (services_started && g_hooks.services_stop)
    {
      g_hooks.services_stop(g_hooks.services_context);
    }

  pthread_mutex_lock(&g_lock);
  g_running = false;
  g_pid = -1;
  pthread_mutex_unlock(&g_lock);
  sem_post(&g_stopped);
  return ret;
}

int btsensor_lifecycle_start(const struct btsensor_lifecycle_hooks *hooks)
{
  int pid;

  if (!hooks || !hooks->receive)
    {
      return -EINVAL;
    }

  pthread_mutex_lock(&g_lock);
  if (g_running)
    {
      pthread_mutex_unlock(&g_lock);
      return -EALREADY;
    }

  if (!g_semaphores_ready)
    {
      if (sem_init(&g_stop_request, 0, 0) < 0 ||
          sem_init(&g_stopped, 0, 0) < 0)
        {
          pthread_mutex_unlock(&g_lock);
          return -errno;
        }

      g_semaphores_ready = true;
    }

  while (sem_trywait(&g_stop_request) == 0)
    {
    }
  while (sem_trywait(&g_stopped) == 0)
    {
    }

  g_hooks = *hooks;
  g_running = true;
  pid = task_create(BTSENSOR_DAEMON_NAME, CONFIG_APP_BTSENSOR_PRIORITY,
                    CONFIG_APP_BTSENSOR_STACKSIZE, daemon_main, NULL);
  if (pid < 0)
    {
      g_running = false;
      pthread_mutex_unlock(&g_lock);
      return -errno;
    }

  g_pid = pid;
  pthread_mutex_unlock(&g_lock);
  return pid;
}

int btsensor_lifecycle_stop(int timeout_ms)
{
  struct timespec deadline;

  pthread_mutex_lock(&g_lock);
  if (!g_running)
    {
      pthread_mutex_unlock(&g_lock);
      return -EALREADY;
    }
  pthread_mutex_unlock(&g_lock);

  sem_post(&g_stop_request);
  deadline_after_ms(&deadline, timeout_ms);
  while (sem_timedwait(&g_stopped, &deadline) < 0)
    {
      if (errno != EINTR)
        {
          return -errno;
        }
    }

  return 0;
}

bool btsensor_lifecycle_running(void)
{
  pthread_mutex_lock(&g_lock);
  bool running = g_running;
  pthread_mutex_unlock(&g_lock);
  return running;
}

int btsensor_lifecycle_pid(void)
{
  pthread_mutex_lock(&g_lock);
  int pid = g_pid;
  pthread_mutex_unlock(&g_lock);
  return pid;
}
