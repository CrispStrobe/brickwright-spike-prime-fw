/* SPDX-License-Identifier: Apache-2.0 */
#include <zephyr/kernel.h>

void brickwright_sync_compile_probe(struct k_sem *sem, struct k_fifo *fifo,
                                    void *item)
{
  (void)k_sem_init(sem, 0, 1);
  k_sem_give(sem);
  (void)k_sem_take(sem, K_NO_WAIT);
  k_fifo_init(fifo);
  k_fifo_put(fifo, item);
  (void)k_fifo_get(fifo, K_NO_WAIT);
}
