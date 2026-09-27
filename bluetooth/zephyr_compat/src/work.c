/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/irq.h>

static pthread_mutex_t irq_lock_mutex;
static pthread_once_t irq_lock_once = PTHREAD_ONCE_INIT;

static void irq_lock_init(void)
{
  pthread_mutexattr_t attributes;
  pthread_mutexattr_init(&attributes);
  pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE);
  pthread_mutex_init(&irq_lock_mutex, &attributes);
  pthread_mutexattr_destroy(&attributes);
}

unsigned int brickwright_irq_lock(void)
{
  pthread_once(&irq_lock_once, irq_lock_init);
  pthread_mutex_lock(&irq_lock_mutex);
  return 0;
}

void brickwright_irq_unlock(unsigned int key)
{
  (void)key;
  pthread_mutex_unlock(&irq_lock_mutex);
}

struct k_work_q k_sys_work_q;
static pthread_once_t system_queue_once = PTHREAD_ONCE_INIT;
static struct k_work_q *thread_registry;
static pthread_mutex_t thread_registry_mutex = PTHREAD_MUTEX_INITIALIZER;

/* Which work queue, if any, the calling thread runs. Zephyr asks this through
 * k_current_get() (conn.c asserts tx notifications run on their queue).
 * pthread_self() cannot answer it on NuttX: it returns the TLS copy of the
 * thread ID, which is 0 on threads whose TLS carries none, so a worker and
 * another thread compare equal. Thread-specific keys are compiled out
 * (CONFIG_TLS_NELEM=0). Each worker therefore records where its stack is;
 * a caller whose own stack lies in that range is that worker. */
static size_t worker_stack_size(void)
{
  pthread_attr_t attributes;
  size_t size = 0;
  pthread_attr_init(&attributes);
  (void)pthread_attr_getstacksize(&attributes, &size);
  pthread_attr_destroy(&attributes);
  return size;
}

static void *worker_main(void *opaque)
{
  struct k_work_q *queue = opaque;
  volatile char anchor = 0;
  queue->stack_anchor = (uintptr_t)&anchor;
  for (;;) {
    struct k_work *work = k_fifo_get(&queue->fifo, K_FOREVER);
    pthread_mutex_lock(&work->mutex);
    work->pending = false;
    if (work->canceled) {
      work->canceled = false;
      pthread_cond_broadcast(&work->changed);
      pthread_mutex_unlock(&work->mutex);
      continue;
    }
    work->running = true;
    pthread_mutex_unlock(&work->mutex);
    work->handler(work);
    pthread_mutex_lock(&work->mutex);
    work->running = false;
    pthread_cond_broadcast(&work->changed);
    pthread_mutex_unlock(&work->mutex);
  }
  return 0;
}

void k_work_queue_init(struct k_work_q *queue)
{
  memset(queue, 0, sizeof(*queue));
  k_fifo_init(&queue->fifo);
}

void k_work_queue_start(struct k_work_q *queue, k_thread_stack_t *stack,
                        size_t stack_size, int priority,
                        const struct k_work_queue_config *config)
{
  (void)stack; (void)priority; (void)config;
  /* Zephyr hands each queue a statically sized stack; here the thread gets
   * its own, at least the requested size. The system queue carries the
   * application's receive path (btsensor's transmit pump keeps a full frame
   * on the stack), which overflowed the 2 KiB pthread default. */
  size_t size = stack_size;
  if (queue == &k_sys_work_q && size < CONFIG_BRICKWRIGHT_SYSTEM_WORKQUEUE_STACK_SIZE)
    size = CONFIG_BRICKWRIGHT_SYSTEM_WORKQUEUE_STACK_SIZE;
  if (size < worker_stack_size())
    size = worker_stack_size();
  pthread_attr_t attributes;
  pthread_attr_init(&attributes);
  (void)pthread_attr_setstacksize(&attributes, size);
  queue->stack_size = size;
  pthread_mutex_lock(&thread_registry_mutex);
  if (!queue->started &&
      pthread_create(&queue->thread, &attributes, worker_main, queue) == 0)
    {
      queue->started = true;
      queue->thread_registry_next = thread_registry;
      thread_registry = queue;
    }
  pthread_mutex_unlock(&thread_registry_mutex);
  pthread_attr_destroy(&attributes);
}

static void start_system_queue(void)
{
  k_work_queue_init(&k_sys_work_q);
  k_work_queue_start(&k_sys_work_q, 0, 0, 0, 0);
}

void k_work_init(struct k_work *work, void (*handler)(struct k_work *work))
{
  memset(work, 0, sizeof(*work));
  work->handler = handler;
  pthread_mutex_init(&work->mutex, 0);
  pthread_cond_init(&work->changed, 0);
}

void k_work_init_delayable(struct k_work_delayable *work,
                           void (*handler)(struct k_work *work))
{
  memset(work, 0, sizeof(*work));
  k_work_init(&work->work, handler);
}

k_tid_t k_work_queue_thread_get(struct k_work_q *queue) { return &queue->thread; }
k_tid_t k_current_get(void)
{
  volatile char probe = 0;
  uintptr_t here = (uintptr_t)&probe;
  pthread_mutex_lock(&thread_registry_mutex);
  for (struct k_work_q *queue = thread_registry; queue;
       queue = queue->thread_registry_next)
    {
      if (queue->stack_anchor && here <= queue->stack_anchor &&
          queue->stack_anchor - here < queue->stack_size)
        {
          pthread_mutex_unlock(&thread_registry_mutex);
          return &queue->thread;
        }
    }
  pthread_mutex_unlock(&thread_registry_mutex);
  /* Non-worker callers only need an identity unequal to every work queue. */
  static pthread_t other_thread;
  return &other_thread;
}

int k_work_submit_to_queue(struct k_work_q *queue, struct k_work *work)
{
  if (!queue) queue = &k_sys_work_q;
  if (queue == &k_sys_work_q) pthread_once(&system_queue_once, start_system_queue);
  pthread_mutex_lock(&work->mutex);
  if (work->pending) { pthread_mutex_unlock(&work->mutex); return 0; }
  work->pending = true;
  work->canceled = false;
  work->queue = queue;
  pthread_mutex_unlock(&work->mutex);
  k_fifo_put(&queue->fifo, work);
  return 1;
}

int k_work_submit(struct k_work *work) { return k_work_submit_to_queue(&k_sys_work_q, work); }

struct delayed_request {
  struct k_work_delayable *work;
  struct k_work_q *queue;
  unsigned int generation;
  k_timeout_t delay;
  bool in_use;
  bool canceled;
};
static struct delayed_request delayed_requests[CONFIG_BRICKWRIGHT_DELAYED_WORK_SLOTS];
static pthread_mutex_t delayed_requests_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t delayed_requests_changed = PTHREAD_COND_INITIALIZER;

static struct delayed_request *delayed_request_allocate(void)
{
  pthread_mutex_lock(&delayed_requests_mutex);
  struct delayed_request *result = 0;
  for (size_t i = 0; i < ARRAY_SIZE(delayed_requests); ++i) {
    if (!delayed_requests[i].in_use) {
      delayed_requests[i].in_use = true;
      result = &delayed_requests[i];
      break;
    }
  }
  pthread_mutex_unlock(&delayed_requests_mutex);
  return result;
}

static void delayed_request_release(struct delayed_request *request)
{
  pthread_mutex_lock(&delayed_requests_mutex);
  memset(request, 0, sizeof(*request));
  pthread_cond_broadcast(&delayed_requests_changed);
  pthread_mutex_unlock(&delayed_requests_mutex);
}

static bool delayed_request_matches(const struct delayed_request *request,
                                    const struct k_work_delayable *work)
{
  return request->in_use && request->work == work;
}

static void delayed_request_cancel(struct k_work_delayable *work, bool wait)
{
  pthread_mutex_lock(&delayed_requests_mutex);
  for (;;) {
    bool found = false;
    for (size_t i = 0; i < ARRAY_SIZE(delayed_requests); ++i) {
      if (delayed_request_matches(&delayed_requests[i], work)) {
        delayed_requests[i].canceled = true;
        found = true;
      }
    }
    pthread_cond_broadcast(&delayed_requests_changed);
    if (!wait || !found) break;
    pthread_cond_wait(&delayed_requests_changed, &delayed_requests_mutex);
  }
  pthread_mutex_unlock(&delayed_requests_mutex);
}

static void *delayed_main(void *opaque)
{
  struct delayed_request *request = opaque;
  struct timespec deadline;
  bool canceled;

  clock_gettime(CLOCK_REALTIME, &deadline);
  deadline.tv_sec += request->delay / 1000;
  deadline.tv_nsec += (request->delay % 1000) * 1000000;
  if (deadline.tv_nsec >= 1000000000) {
    ++deadline.tv_sec;
    deadline.tv_nsec -= 1000000000;
  }

  pthread_mutex_lock(&delayed_requests_mutex);
  while (!request->canceled &&
         pthread_cond_timedwait(&delayed_requests_changed,
                                &delayed_requests_mutex,
                                &deadline) != ETIMEDOUT) { }
  canceled = request->canceled;
  pthread_mutex_unlock(&delayed_requests_mutex);

  if (!canceled) {
    pthread_mutex_lock(&request->work->work.mutex);
    bool current = request->generation == request->work->work.generation;
    if (current) request->work->deadline = 0;
    pthread_mutex_unlock(&request->work->work.mutex);
    if (current)
      (void)k_work_submit_to_queue(request->queue, &request->work->work);
  }
  delayed_request_release(request);
  return 0;
}

static int schedule(struct k_work_q *queue, struct k_work_delayable *work,
                    k_timeout_t delay, bool replace)
{
  if (!queue) queue = &k_sys_work_q;
  pthread_mutex_lock(&work->work.mutex);
  if (!replace && work->deadline) { pthread_mutex_unlock(&work->work.mutex); return 0; }
  unsigned int generation = ++work->work.generation;
  work->queue = queue;
  work->deadline = delay == K_NO_WAIT ? 0 : brickwright_now_ms() + delay;
  pthread_mutex_unlock(&work->work.mutex);
  if (delay == K_NO_WAIT) return k_work_submit_to_queue(queue, &work->work);
  struct delayed_request *request = delayed_request_allocate();
  if (!request) goto fail;
  request->work = work;
  request->queue = queue;
  request->generation = generation;
  request->delay = delay;
  pthread_t timer;
  if (pthread_create(&timer, 0, delayed_main, request) != 0) {
    delayed_request_release(request);
    goto fail;
  }
  pthread_detach(timer);
  return 1;

fail:
  pthread_mutex_lock(&work->work.mutex);
  if (work->work.generation == generation) work->deadline = 0;
  pthread_mutex_unlock(&work->work.mutex);
  return -ENOMEM;
}

int k_work_schedule_for_queue(struct k_work_q *queue, struct k_work_delayable *work,
                              k_timeout_t delay) { return schedule(queue, work, delay, false); }
int k_work_schedule(struct k_work_delayable *work, k_timeout_t delay)
{ return k_work_schedule_for_queue(&k_sys_work_q, work, delay); }
int k_work_reschedule_for_queue(struct k_work_q *queue, struct k_work_delayable *work,
                                k_timeout_t delay) { return schedule(queue, work, delay, true); }
int k_work_reschedule(struct k_work_delayable *work, k_timeout_t delay)
{ return k_work_reschedule_for_queue(&k_sys_work_q, work, delay); }

/* Zephyr treats a zero-filled k_work or k_work_delayable as idle: the host
 * cancels, flushes, and queries work items (for example the limited
 * advertising timeout) that were never initialized. Here each item owns a
 * pthread mutex that k_work_init creates; a zero-filled pthread mutex is not
 * a valid unlocked mutex on NuttX, where locking it blocks forever. An item
 * with no handler was never initialized and cannot have been submitted, so
 * the query and cancel paths answer "idle" without touching its mutex. */
static bool work_uninitialized(const struct k_work *work)
{
  return work->handler == NULL;
}

int k_work_cancel(struct k_work *work)
{
  if (work_uninitialized(work)) return 0;
  pthread_mutex_lock(&work->mutex);
  ++work->generation;
  bool busy = work->pending || work->running;
  if (work->pending) work->canceled = true;
  pthread_mutex_unlock(&work->mutex);
  return busy ? -EBUSY : 0;
}

int k_work_cancel_sync(struct k_work *work, struct k_work_sync *sync)
{
  (void)sync;
  if (work_uninitialized(work)) return 0;
  (void)k_work_cancel(work);
  pthread_mutex_lock(&work->mutex);
  while (work->pending || work->running)
    pthread_cond_wait(&work->changed, &work->mutex);
  pthread_mutex_unlock(&work->mutex);
  return 0;
}

bool k_work_flush(struct k_work *work, struct k_work_sync *sync)
{
  (void)sync;
  if (work_uninitialized(work)) return false;
  pthread_mutex_lock(&work->mutex);
  bool busy = work->pending || work->running;
  while (work->pending || work->running)
    pthread_cond_wait(&work->changed, &work->mutex);
  pthread_mutex_unlock(&work->mutex);
  return busy;
}

int k_work_cancel_delayable(struct k_work_delayable *work)
{
  if (work_uninitialized(&work->work)) return 0;
  pthread_mutex_lock(&work->work.mutex);
  bool delayed = work->deadline != 0;
  work->deadline = 0;
  ++work->work.generation;
  pthread_mutex_unlock(&work->work.mutex);
  delayed_request_cancel(work, false);
  return delayed ? 1 : k_work_cancel(&work->work);
}

int k_work_cancel_delayable_sync(struct k_work_delayable *work, struct k_work_sync *sync)
{
  if (work_uninitialized(&work->work)) return 0;
  (void)k_work_cancel_delayable(work);
  delayed_request_cancel(work, true);
  return k_work_cancel_sync(&work->work, sync);
}

bool k_work_is_pending(const struct k_work *work)
{
  struct k_work *mutable_work = (struct k_work *)work;
  if (work_uninitialized(mutable_work)) return false;
  pthread_mutex_lock(&mutable_work->mutex);
  bool pending = mutable_work->pending || mutable_work->running;
  pthread_mutex_unlock(&mutable_work->mutex);
  return pending;
}
unsigned int k_work_delayable_busy_get(const struct k_work_delayable *work)
{
  struct k_work *mutable_work = (struct k_work *)&work->work;
  if (work_uninitialized(mutable_work)) return 0;
  pthread_mutex_lock(&mutable_work->mutex);
  unsigned int busy = (work->deadline ? K_WORK_DELAYED : 0) |
                      (mutable_work->pending || mutable_work->running ? K_WORK_QUEUED : 0);
  pthread_mutex_unlock(&mutable_work->mutex);
  return busy;
}
k_timeout_t k_work_delayable_remaining_get(const struct k_work_delayable *work)
{
  struct k_work *mutable_work = (struct k_work *)&work->work;
  pthread_mutex_lock(&mutable_work->mutex);
  int64_t remaining = work->deadline - brickwright_now_ms();
  pthread_mutex_unlock(&mutable_work->mutex);
  return remaining > 0 ? remaining : 0;
}
struct k_work_delayable *k_work_delayable_from_work(struct k_work *work)
{ return CONTAINER_OF(work, struct k_work_delayable, work); }
