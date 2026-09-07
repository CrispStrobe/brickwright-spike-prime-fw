/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_KERNEL_H
#define BRICKWRIGHT_ZEPHYR_KERNEL_H
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>
#include <zephyr/sys/__assert.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/slist.h>
#include <zephyr/toolchain.h>
typedef int64_t k_timeout_t;
typedef int64_t k_timepoint_t;
typedef unsigned int k_spinlock_key_t;
struct k_lifo { void *head; pthread_mutex_t mutex; pthread_cond_t changed; };
struct k_spinlock { unsigned int state; };
struct k_heap { unsigned int unused; };
struct k_sem { unsigned int count; unsigned int limit; pthread_mutex_t mutex; pthread_cond_t changed; };
struct k_mutex { pthread_mutex_t mutex; };
struct k_condvar { pthread_cond_t condvar; };
struct k_mem_slab {
  uint8_t *buffer;
  bool *used;
  size_t block_size;
  size_t block_count;
  pthread_mutex_t mutex;
  pthread_cond_t changed;
};
struct k_fifo {
  void *head;
  void *tail;
  pthread_mutex_t mutex;
  pthread_cond_t changed;
  struct k_fifo *_queue;
};
struct k_work_q;
struct k_work {
  void *next;
  void (*handler)(struct k_work *work);
  pthread_mutex_t mutex;
  pthread_cond_t changed;
  struct k_work_q *queue;
  unsigned int generation;
  bool pending;
  bool running;
  bool canceled;
};
struct k_work_delayable {
  struct k_work work;
  int64_t deadline;
  struct k_work_q *queue;
};
struct k_work_sync { unsigned int unused; };
struct k_work_q {
  struct k_fifo fifo;
  pthread_t thread;
  bool started;
  struct k_work_q *thread_registry_next;
};
struct k_work_queue_config { const char *name; bool no_yield; bool essential; };
typedef uint8_t k_thread_stack_t;
typedef pthread_t *k_tid_t;
extern struct k_work_q k_sys_work_q;
#define K_WORK_QUEUED BIT(0)
#define K_WORK_DELAYED BIT(1)
#define K_MSEC(value) ((k_timeout_t)(value))
#define K_SECONDS(value) K_MSEC((value) * 1000)
#define K_THREAD_STACK_DEFINE(name, size) k_thread_stack_t name[size]
#define K_THREAD_STACK_SIZEOF(name) sizeof(name)
#define Z_WORK_INITIALIZER(handler_) \
  { .handler = (handler_), .mutex = PTHREAD_MUTEX_INITIALIZER, \
    .changed = PTHREAD_COND_INITIALIZER }
#define K_WORK_DEFINE(name, handler_) struct k_work name = Z_WORK_INITIALIZER(handler_)
#define K_WORK_DELAYABLE_DEFINE(name, handler_) \
  struct k_work_delayable name = { .work = Z_WORK_INITIALIZER(handler_) }
#define K_NO_WAIT ((k_timeout_t)0)
#define K_FOREVER ((k_timeout_t)-1)
#define K_SEM_MAX_LIMIT UINT_MAX
#define K_MEM_SLAB_DEFINE_STATIC(name, size, count, alignment) \
  static uint8_t name##_storage[(size) * (count)] \
    __attribute__((aligned(alignment))); \
  static bool name##_used[(count)]; \
  static struct k_mem_slab name = { \
    .buffer = name##_storage, .used = name##_used, .block_size = (size), \
    .block_count = (count), .mutex = PTHREAD_MUTEX_INITIALIZER, \
    .changed = PTHREAD_COND_INITIALIZER \
  }
#define Z_LIFO_INITIALIZER(object) \
  { .head = 0, .mutex = PTHREAD_MUTEX_INITIALIZER, .changed = PTHREAD_COND_INITIALIZER }
#define Z_FIFO_INITIALIZER(object) \
  { .head = 0, .tail = 0, .mutex = PTHREAD_MUTEX_INITIALIZER, \
    .changed = PTHREAD_COND_INITIALIZER, ._queue = &(object) }
#define K_FIFO_DEFINE(name) struct k_fifo name = Z_FIFO_INITIALIZER(name)
#define Z_SEM_INITIALIZER(object, initial, maximum) \
  { .count = (initial), .limit = (maximum), .mutex = PTHREAD_MUTEX_INITIALIZER, \
    .changed = PTHREAD_COND_INITIALIZER }
#define K_SEM_DEFINE(name, initial, maximum) \
  struct k_sem name = Z_SEM_INITIALIZER(name, initial, maximum)
#define Z_MUTEX_INITIALIZER(object) { .mutex = PTHREAD_MUTEX_INITIALIZER }
#define Z_CONDVAR_INITIALIZER(object) { .condvar = PTHREAD_COND_INITIALIZER }
#define K_TIMEOUT_EQ(a, b) ((a) == (b))
#define K_HEAP_MEM_POOL_SIZE 0
static inline void k_lifo_put(struct k_lifo *lifo, void *item)
{
  pthread_mutex_lock(&lifo->mutex);
  *(void **)item = lifo->head;
  lifo->head = item;
  pthread_cond_signal(&lifo->changed);
  pthread_mutex_unlock(&lifo->mutex);
}
static inline void *k_lifo_get(struct k_lifo *lifo, k_timeout_t timeout)
{
  pthread_mutex_lock(&lifo->mutex);
  if (timeout == K_FOREVER) {
    while (!lifo->head) pthread_cond_wait(&lifo->changed, &lifo->mutex);
  } else if (timeout > 0 && !lifo->head) {
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += timeout / 1000;
    deadline.tv_nsec += (timeout % 1000) * 1000000;
    if (deadline.tv_nsec >= 1000000000) {
      ++deadline.tv_sec;
      deadline.tv_nsec -= 1000000000;
    }
    while (!lifo->head && pthread_cond_timedwait(&lifo->changed, &lifo->mutex,
                                                  &deadline) != ETIMEDOUT) { }
  }
  void *item = lifo->head;
  if (item) { lifo->head = *(void **)item; *(void **)item = 0; }
  pthread_mutex_unlock(&lifo->mutex);
  return item;
}
static inline void k_fifo_init(struct k_fifo *fifo)
{
  fifo->head = fifo->tail = 0;
  fifo->_queue = fifo;
  pthread_mutex_init(&fifo->mutex, 0);
  pthread_cond_init(&fifo->changed, 0);
}
static inline void k_queue_prepend(struct k_fifo **queue_handle, void *item)
{
  struct k_fifo *queue = *queue_handle;
  pthread_mutex_lock(&queue->mutex);
  *(void **)item = queue->head;
  queue->head = item;
  if (!queue->tail) queue->tail = item;
  pthread_cond_signal(&queue->changed);
  pthread_mutex_unlock(&queue->mutex);
}
static inline void k_fifo_put(struct k_fifo *fifo, void *item)
{
  *(void **)item = 0;
  pthread_mutex_lock(&fifo->mutex);
  if (fifo->tail) *(void **)fifo->tail = item; else fifo->head = item;
  fifo->tail = item;
  pthread_cond_signal(&fifo->changed);
  pthread_mutex_unlock(&fifo->mutex);
}
static inline void *k_fifo_get(struct k_fifo *fifo, k_timeout_t timeout)
{
  pthread_mutex_lock(&fifo->mutex);
  if (timeout == K_FOREVER) {
    while (!fifo->head) pthread_cond_wait(&fifo->changed, &fifo->mutex);
  } else if (timeout > 0 && !fifo->head) {
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += timeout / 1000;
    deadline.tv_nsec += (timeout % 1000) * 1000000;
    if (deadline.tv_nsec >= 1000000000) { ++deadline.tv_sec; deadline.tv_nsec -= 1000000000; }
    while (!fifo->head && pthread_cond_timedwait(&fifo->changed, &fifo->mutex,
                                                  &deadline) != ETIMEDOUT) { }
  }
  void *item = fifo->head;
  if (item) {
    fifo->head = *(void **)item;
    if (!fifo->head) fifo->tail = 0;
    *(void **)item = 0;
  }
  pthread_mutex_unlock(&fifo->mutex);
  return item;
}
static inline void *k_fifo_peek_head(struct k_fifo *fifo)
{
  return fifo->head;
}
static inline bool k_fifo_is_empty(struct k_fifo *fifo)
{
  return fifo->head == 0;
}
static inline int k_sem_init(struct k_sem *sem, unsigned int initial,
                             unsigned int limit)
{
  if (!limit || initial > limit) return -EINVAL;
  sem->count = initial; sem->limit = limit;
  pthread_mutex_init(&sem->mutex, 0);
  pthread_cond_init(&sem->changed, 0);
  return 0;
}
static inline void k_sem_give(struct k_sem *sem)
{
  pthread_mutex_lock(&sem->mutex);
  if (sem->count < sem->limit) ++sem->count;
  pthread_cond_signal(&sem->changed);
  pthread_mutex_unlock(&sem->mutex);
}
static inline int k_sem_take(struct k_sem *sem, k_timeout_t timeout)
{
  int result = 0;
  pthread_mutex_lock(&sem->mutex);
  if (timeout == K_FOREVER) {
    while (!sem->count) pthread_cond_wait(&sem->changed, &sem->mutex);
  } else if (timeout > 0 && !sem->count) {
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += timeout / 1000;
    deadline.tv_nsec += (timeout % 1000) * 1000000;
    if (deadline.tv_nsec >= 1000000000) { ++deadline.tv_sec; deadline.tv_nsec -= 1000000000; }
    while (!sem->count && result != ETIMEDOUT)
      result = pthread_cond_timedwait(&sem->changed, &sem->mutex, &deadline);
  }
  if (sem->count) { --sem->count; result = 0; } else result = -EAGAIN;
  pthread_mutex_unlock(&sem->mutex);
  return result;
}
static inline unsigned int k_sem_count_get(struct k_sem *sem)
{
  pthread_mutex_lock(&sem->mutex);
  unsigned int count = sem->count;
  pthread_mutex_unlock(&sem->mutex);
  return count;
}
static inline int k_mutex_lock(struct k_mutex *mutex, k_timeout_t timeout)
{
  (void)timeout;
  return pthread_mutex_lock(&mutex->mutex) == 0 ? 0 : -EIO;
}
static inline int k_mutex_init(struct k_mutex *mutex)
{
  return pthread_mutex_init(&mutex->mutex, 0) == 0 ? 0 : -EIO;
}
static inline void k_oops(void)
{
  abort();
}
static inline int k_mem_slab_alloc(struct k_mem_slab *slab, void **memory,
                                   k_timeout_t timeout)
{
  pthread_mutex_lock(&slab->mutex);
  for (;;)
    {
      for (size_t i = 0; i < slab->block_count; ++i)
        {
          if (!slab->used[i])
            {
              slab->used[i] = true;
              *memory = slab->buffer + i * slab->block_size;
              pthread_mutex_unlock(&slab->mutex);
              return 0;
            }
        }
      if (timeout != K_FOREVER)
        {
          pthread_mutex_unlock(&slab->mutex);
          return -ENOMEM;
        }
      pthread_cond_wait(&slab->changed, &slab->mutex);
    }
}
static inline void k_mem_slab_free(struct k_mem_slab *slab, void *memory)
{
  uintptr_t offset = (uintptr_t)((uint8_t *)memory - slab->buffer);
  pthread_mutex_lock(&slab->mutex);
  if (offset % slab->block_size == 0 &&
      offset / slab->block_size < slab->block_count)
    {
      slab->used[offset / slab->block_size] = false;
      pthread_cond_signal(&slab->changed);
    }
  pthread_mutex_unlock(&slab->mutex);
}
static inline int k_mutex_unlock(struct k_mutex *mutex)
{
  return pthread_mutex_unlock(&mutex->mutex) == 0 ? 0 : -EIO;
}
static inline int k_condvar_broadcast(struct k_condvar *condition)
{
  return pthread_cond_broadcast(&condition->condvar) == 0 ? 0 : -EIO;
}
static inline int k_condvar_wait(struct k_condvar *condition,
                                 struct k_mutex *mutex, k_timeout_t timeout)
{
  if (timeout == K_FOREVER)
    {
      return pthread_cond_wait(&condition->condvar, &mutex->mutex) == 0 ?
             0 : -EIO;
    }
  if (timeout == K_NO_WAIT)
    {
      return -EAGAIN;
    }
  struct timespec deadline;
  clock_gettime(CLOCK_REALTIME, &deadline);
  deadline.tv_sec += timeout / 1000;
  deadline.tv_nsec += (timeout % 1000) * 1000000;
  if (deadline.tv_nsec >= 1000000000)
    {
      ++deadline.tv_sec;
      deadline.tv_nsec -= 1000000000;
    }
  int result = pthread_cond_timedwait(&condition->condvar, &mutex->mutex,
                                      &deadline);
  return result == 0 ? 0 : result == ETIMEDOUT ? -EAGAIN : -EIO;
}
static inline void k_sem_reset(struct k_sem *sem)
{
  pthread_mutex_lock(&sem->mutex);
  sem->count = 0;
  pthread_mutex_unlock(&sem->mutex);
}
static inline k_spinlock_key_t k_spin_lock(struct k_spinlock *lock)
{
  while (__atomic_test_and_set(&lock->state, __ATOMIC_ACQUIRE)) { }
  return 0;
}
static inline void k_spin_unlock(struct k_spinlock *lock, k_spinlock_key_t key)
{
  (void)key;
  __atomic_clear(&lock->state, __ATOMIC_RELEASE);
}
static inline int64_t brickwright_now_ms(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}
static inline k_timepoint_t sys_timepoint_calc(k_timeout_t timeout)
{
  return timeout == K_FOREVER ? K_FOREVER : brickwright_now_ms() + timeout;
}
static inline k_timeout_t sys_timepoint_timeout(k_timepoint_t end)
{
  if (end == K_FOREVER) return K_FOREVER;
  int64_t remaining = end - brickwright_now_ms();
  return remaining > 0 ? remaining : K_NO_WAIT;
}
static inline void *k_heap_alloc(struct k_heap *heap, size_t size, k_timeout_t timeout)
{
  (void)heap; (void)timeout; return malloc(size);
}
static inline void *k_heap_aligned_alloc(struct k_heap *heap, size_t alignment,
                                         size_t size, k_timeout_t timeout)
{
  (void)heap; (void)timeout;
  void *result = 0;
  return posix_memalign(&result, alignment, size) == 0 ? result : 0;
}
static inline void k_heap_free(struct k_heap *heap, void *memory)
{
  (void)heap; free(memory);
}
static inline bool k_is_in_isr(void) { return false; }
static inline void k_sched_lock(void) { }
static inline void k_sched_unlock(void) { }

void k_work_init(struct k_work *work, void (*handler)(struct k_work *work));
void k_work_init_delayable(struct k_work_delayable *work,
                           void (*handler)(struct k_work *work));
void k_work_queue_init(struct k_work_q *queue);
void k_work_queue_start(struct k_work_q *queue, k_thread_stack_t *stack,
                        size_t stack_size, int priority,
                        const struct k_work_queue_config *config);
k_tid_t k_work_queue_thread_get(struct k_work_q *queue);
k_tid_t k_current_get(void);
int k_work_submit(struct k_work *work);
int k_work_submit_to_queue(struct k_work_q *queue, struct k_work *work);
int k_work_schedule(struct k_work_delayable *work, k_timeout_t delay);
int k_work_schedule_for_queue(struct k_work_q *queue,
                              struct k_work_delayable *work, k_timeout_t delay);
int k_work_reschedule(struct k_work_delayable *work, k_timeout_t delay);
int k_work_reschedule_for_queue(struct k_work_q *queue,
                                struct k_work_delayable *work, k_timeout_t delay);
int k_work_cancel(struct k_work *work);
int k_work_cancel_sync(struct k_work *work, struct k_work_sync *sync);
bool k_work_flush(struct k_work *work, struct k_work_sync *sync);
int k_work_cancel_delayable(struct k_work_delayable *work);
int k_work_cancel_delayable_sync(struct k_work_delayable *work,
                                 struct k_work_sync *sync);
bool k_work_is_pending(const struct k_work *work);
unsigned int k_work_delayable_busy_get(const struct k_work_delayable *work);
k_timeout_t k_work_delayable_remaining_get(const struct k_work_delayable *work);
struct k_work_delayable *k_work_delayable_from_work(struct k_work *work);
#endif
