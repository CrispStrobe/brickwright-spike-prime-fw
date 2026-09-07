/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <pthread.h>
#include <time.h>
#include <zephyr/kernel.h>

struct item { void *next; int value; };
struct producer_context { struct k_sem *sem; struct k_fifo *fifo; struct item *item; };

static void *producer(void *opaque)
{
  struct producer_context *context = opaque;
  struct timespec delay = { .tv_nsec = 5 * 1000 * 1000 };
  nanosleep(&delay, 0);
  k_fifo_put(context->fifo, context->item);
  k_sem_give(context->sem);
  return 0;
}

int main(void)
{
  struct k_sem sem;
  struct k_fifo fifo;
  struct item first = { .value = 1 }, second = { .value = 2 };
  assert(k_sem_init(&sem, 0, 1) == 0);
  k_fifo_init(&fifo);
  k_fifo_put(&fifo, &first);
  k_fifo_put(&fifo, &second);
  assert(k_fifo_get(&fifo, K_NO_WAIT) == &first);
  assert(k_fifo_get(&fifo, K_NO_WAIT) == &second);
  assert(k_fifo_get(&fifo, K_NO_WAIT) == 0);
  assert(k_sem_take(&sem, K_NO_WAIT) == -EAGAIN);

  struct producer_context context = { .sem = &sem, .fifo = &fifo, .item = &first };
  pthread_t thread;
  assert(pthread_create(&thread, 0, producer, &context) == 0);
  assert(k_sem_take(&sem, 100) == 0);
  assert(k_fifo_get(&fifo, K_NO_WAIT) == &first);
  assert(pthread_join(thread, 0) == 0);
  k_sem_give(&sem);
  k_sem_give(&sem);
  assert(k_sem_count_get(&sem) == 1);
  k_sem_reset(&sem);
  assert(k_sem_count_get(&sem) == 0);
  assert(k_sem_take(&sem, 1) == -EAGAIN);
  return 0;
}
