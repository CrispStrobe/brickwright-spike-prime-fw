/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <string.h>
#include <unistd.h>
#include <zephyr/kernel.h>
#include "long_wq.h"

struct context {
  struct k_work work;
  struct k_work_delayable delayed;
  struct k_sem completed;
  struct k_sem started;
  atomic_t calls;
  atomic_t resubmit_result;
};

static void run_slow(struct k_work *work)
{
  struct context *context = CONTAINER_OF(work, struct context, work);
  struct timespec delay = { .tv_nsec = 10 * 1000 * 1000 };
  k_sem_give(&context->started);
  nanosleep(&delay, 0);
  atomic_inc(&context->calls);
}

static void run(struct k_work *work)
{
  struct context *context = CONTAINER_OF(work, struct context, work);
  atomic_inc(&context->calls);
  k_sem_give(&context->completed);
}

static void run_delayed(struct k_work *work)
{
  struct k_work_delayable *delayed = k_work_delayable_from_work(work);
  struct context *context = CONTAINER_OF(delayed, struct context, delayed);
  atomic_inc(&context->calls);
  k_sem_give(&context->completed);
}

static void run_noop(struct k_work *work) { (void)work; }

static void run_and_resubmit(struct k_work *work)
{
  struct context *context = CONTAINER_OF(work, struct context, work);
  if (atomic_inc(&context->calls) == 0)
    atomic_set(&context->resubmit_result, k_work_submit(work));
  k_sem_give(&context->completed);
}

static k_tid_t seen_thread;
static struct k_sem seen_done;

static void record_current(struct k_work *work)
{
  (void)work;
  seen_thread = k_current_get();
  k_sem_give(&seen_done);
}

int main(void)
{
  /* k_current_get() identifies the work queue a handler runs on, and no
   * other thread matches it (conn.c asserts tx notifications run on their
   * queue). */
  struct k_work identify;
  k_sem_init(&seen_done, 0, 1);
  k_work_init(&identify, record_current);
  assert(k_work_submit(&identify) == 1);
  assert(k_sem_take(&seen_done, 1000) == 0);
  assert(seen_thread == k_work_queue_thread_get(&k_sys_work_q));
  assert(k_current_get() != k_work_queue_thread_get(&k_sys_work_q));

  struct context context = {0};
  assert(k_sem_init(&context.completed, 0, 4) == 0);
  assert(k_sem_init(&context.started, 0, 1) == 0);
  k_work_init(&context.work, run);
  k_work_init_delayable(&context.delayed, run_delayed);

  assert(k_work_submit(&context.work) == 1);
  assert(k_sem_take(&context.completed, 100) == 0);
  assert(atomic_get(&context.calls) == 1);

  struct context resubmit = {0};
  assert(k_sem_init(&resubmit.completed, 0, 2) == 0);
  atomic_set(&resubmit.resubmit_result, -1);
  k_work_init(&resubmit.work, run_and_resubmit);
  assert(k_work_submit(&resubmit.work) == 1);
  assert(k_sem_take(&resubmit.completed, 100) == 0);
  assert(k_sem_take(&resubmit.completed, 100) == 0);
  assert(atomic_get(&resubmit.calls) == 2);
  assert(atomic_get(&resubmit.resubmit_result) == 1);

  assert(k_work_schedule(&context.delayed, K_MSEC(50)) == 1);
  assert(k_work_delayable_busy_get(&context.delayed) & K_WORK_DELAYED);
  assert(k_work_delayable_remaining_get(&context.delayed) > 0);
  assert(k_work_cancel_delayable(&context.delayed) == 1);
  assert(k_sem_take(&context.completed, K_MSEC(70)) == -EAGAIN);

  /* Sync cancellation owns the sleeping timer reference too.  Reinitialize
   * the same storage immediately after it returns; the canceled generation
   * must neither touch the replacement object nor invoke its handler. */
  struct context reusable = {0};
  assert(k_sem_init(&reusable.completed, 0, 1) == 0);
  k_work_init_delayable(&reusable.delayed, run_delayed);
  assert(k_work_schedule(&reusable.delayed, K_MSEC(200)) == 1);
  struct k_work_sync delayed_sync;
  assert(k_work_cancel_delayable_sync(&reusable.delayed, &delayed_sync) == 0);
  assert(pthread_mutex_destroy(&reusable.delayed.work.mutex) == 0);
  assert(pthread_cond_destroy(&reusable.delayed.work.changed) == 0);
  memset(&reusable.delayed, 0xa5, sizeof(reusable.delayed));
  k_work_init_delayable(&reusable.delayed, run_delayed);
  assert(k_work_schedule(&reusable.delayed, K_MSEC(1000)) == 1);
  assert(k_sem_take(&reusable.completed, K_MSEC(250)) == -EAGAIN);
  assert(atomic_get(&reusable.calls) == 0);
  assert(k_work_cancel_delayable_sync(&reusable.delayed, &delayed_sync) == 0);

  assert(k_work_reschedule(&context.delayed, K_MSEC(30)) == 1);
  assert(k_work_reschedule(&context.delayed, K_MSEC(5)) == 1);
  assert(k_sem_take(&context.completed, 100) == 0);
  assert(atomic_get(&context.calls) == 2);
  assert(k_work_delayable_remaining_get(&context.delayed) == 0);

  assert(bt_long_wq_submit(&context.work) == 1);
  assert(k_sem_take(&context.completed, 100) == 0);
  assert(atomic_get(&context.calls) == 3);

  struct k_work_sync sync;
  /* The handler signals before worker_main clears its running flag. */
  (void)k_work_flush(&context.work, &sync);
  k_work_init(&context.work, run_slow);
  assert(k_work_submit(&context.work) == 1);
  assert(k_sem_take(&context.started, 100) == 0);
  assert(k_work_cancel_sync(&context.work, &sync) == 0);
  assert(atomic_get(&context.calls) == 4);
  assert(!k_work_is_pending(&context.work));

  struct timespec prior_timer_wait = {.tv_nsec = 50 * 1000 * 1000};
  nanosleep(&prior_timer_wait, 0);
  struct k_work_delayable timers[CONFIG_BRICKWRIGHT_DELAYED_WORK_SLOTS + 1];
  for (size_t i = 0; i < ARRAY_SIZE(timers); ++i)
    k_work_init_delayable(&timers[i], run_noop);
  for (size_t i = 0; i < CONFIG_BRICKWRIGHT_DELAYED_WORK_SLOTS; ++i)
    assert(k_work_schedule(&timers[i], K_MSEC(200)) == 1);
  assert(k_work_schedule(&timers[CONFIG_BRICKWRIGHT_DELAYED_WORK_SLOTS],
                         K_MSEC(200)) == -ENOMEM);
  for (size_t i = 0; i < CONFIG_BRICKWRIGHT_DELAYED_WORK_SLOTS; ++i)
    assert(k_work_cancel_delayable(&timers[i]) == 1);
  struct timespec release_wait = {.tv_nsec = 250 * 1000 * 1000};
  nanosleep(&release_wait, 0);
  assert(k_work_schedule(&timers[0], K_MSEC(20)) == 1);
  assert(k_work_cancel_delayable(&timers[0]) == 1);

  /* Zephyr cancels and queries never-initialized (zero-filled) items, such
   * as the limited-advertising timeout on every peripheral connection. Their
   * mutex was never created; on NuttX a zero-filled one is locked. Model that
   * with a held mutex: the idle answer must not touch it. SIGALRM turns a
   * regression (a hang) into a failure. */
  struct k_work_delayable never_initialized;
  memset(&never_initialized, 0, sizeof(never_initialized));
  pthread_mutex_init(&never_initialized.work.mutex, 0);
  pthread_mutex_lock(&never_initialized.work.mutex);
  alarm(5);
  assert(k_work_cancel_delayable(&never_initialized) == 0);
  assert(k_work_cancel_delayable_sync(&never_initialized, &sync) == 0);
  assert(k_work_cancel(&never_initialized.work) == 0);
  assert(k_work_cancel_sync(&never_initialized.work, &sync) == 0);
  assert(!k_work_flush(&never_initialized.work, &sync));
  assert(!k_work_is_pending(&never_initialized.work));
  assert(k_work_delayable_busy_get(&never_initialized) == 0);
  alarm(0);
  pthread_mutex_unlock(&never_initialized.work.mutex);
  return 0;
}
