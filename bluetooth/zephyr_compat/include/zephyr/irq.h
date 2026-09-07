/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_IRQ_H
#define BRICKWRIGHT_ZEPHYR_IRQ_H

#include <zephyr/kernel.h>

static inline unsigned int irq_lock(void)
{
  k_sched_lock();
  return 0;
}

static inline void irq_unlock(unsigned int key)
{
  ARG_UNUSED(key);
  k_sched_unlock();
}

#endif
