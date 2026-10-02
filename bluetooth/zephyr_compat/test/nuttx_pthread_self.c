/* SPDX-License-Identifier: Apache-2.0 */
/* Models NuttX for the host work-queue tests. NuttX's pthread_self() returns
 * the thread ID cached in thread-local storage (libs/libc/sched/
 * task_gettid.c), and on the Bluetooth work-queue threads that value is 0,
 * so every such thread (and any other thread whose TLS carries no ID) reports
 * the same identity. Compiling work.c with -Dpthread_self=nuttx_pthread_self
 * makes that failure reproducible off-target. */
#include <pthread.h>

pthread_t nuttx_pthread_self(void);

pthread_t nuttx_pthread_self(void)
{
  return (pthread_t)0;
}
