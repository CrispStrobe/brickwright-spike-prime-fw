/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_IRQ_H
#define BRICKWRIGHT_ZEPHYR_IRQ_H

#include <zephyr/kernel.h>

/* Zephyr uses irq_lock() to make short list operations atomic between the
 * HCI receive context and the work queues (conn.c takes TX contexts off
 * tx_complete). Here those are separate preemptive threads, so the lock must
 * exclude them: a process-wide recursive mutex (work.c). Code under
 * irq_lock() never blocks in Zephyr. */
unsigned int brickwright_irq_lock(void);
void brickwright_irq_unlock(unsigned int key);

static inline unsigned int irq_lock(void)
{
  return brickwright_irq_lock();
}

static inline void irq_unlock(unsigned int key)
{
  brickwright_irq_unlock(key);
}

#endif
