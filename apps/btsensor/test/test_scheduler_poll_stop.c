/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright (c) 2026 Brickwright contributors */
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdbool.h>
#include <time.h>
#include <unistd.h>
#include "btsensor_scheduler.h"

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static int watched_fd = -1;
static bool entered, release_poll, stopping, stopped;
static struct btsensor_watch_s watch;

/* Compiled only into the scheduler under test. Hold a real watched poll
 * round until the test releases it, reproducing a retained file reference. */
int controlled_poll(struct pollfd *fds, nfds_t count, int timeout)
{
  pthread_mutex_lock(&lock);
  for (nfds_t i = 1; i < count; i++)
    if (fds[i].fd == watched_fd && !release_poll)
      {
        entered = true;
        pthread_cond_broadcast(&changed);
        while (!release_poll) pthread_cond_wait(&changed, &lock);
      }
  pthread_mutex_unlock(&lock);
  return poll(fds, count, timeout);
}

static void on_read(int fd, void *arg)
{
  (void)fd;
  (void)arg;
  assert(!"stopped watch dispatched");
}

static void *stop_watch(void *arg)
{
  (void)arg;
  pthread_mutex_lock(&lock);
  stopping = true;
  pthread_cond_broadcast(&changed);
  pthread_mutex_unlock(&lock);
  btsensor_scheduler_watch_stop(&watch);
  pthread_mutex_lock(&lock);
  stopped = true;
  pthread_cond_broadcast(&changed);
  pthread_mutex_unlock(&lock);
  return NULL;
}

int main(void)
{
  int pipefd[2];
  pthread_t stopper;
  assert(pipe(pipefd) == 0);
  watched_fd = pipefd[0];
  assert(btsensor_scheduler_acquire() == 0);
  assert(btsensor_scheduler_watch_start(&watch, watched_fd, on_read, NULL) == 0);
  pthread_mutex_lock(&lock);
  while (!entered) pthread_cond_wait(&changed, &lock);
  pthread_mutex_unlock(&lock);
  assert(pthread_create(&stopper, NULL, stop_watch, NULL) == 0);
  pthread_mutex_lock(&lock);
  while (!stopping) pthread_cond_wait(&changed, &lock);
  struct timespec deadline;
  assert(clock_gettime(CLOCK_REALTIME, &deadline) == 0);
  deadline.tv_nsec += 100000000;
  if (deadline.tv_nsec >= 1000000000) { deadline.tv_sec++; deadline.tv_nsec -= 1000000000; }
  int rc = 0;
  while (!stopped && rc == 0) rc = pthread_cond_timedwait(&changed, &lock, &deadline);
  assert(rc == ETIMEDOUT && !stopped);
  release_poll = true;
  pthread_cond_broadcast(&changed);
  pthread_mutex_unlock(&lock);
  assert(pthread_join(stopper, NULL) == 0);
  assert(stopped);
  close(pipefd[0]);
  close(pipefd[1]);
  btsensor_scheduler_release();
  return 0;
}
