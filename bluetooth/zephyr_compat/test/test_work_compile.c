/* SPDX-License-Identifier: Apache-2.0 */
#include <zephyr/kernel.h>

static void handler(struct k_work *work) { (void)work; }

void brickwright_work_compile_probe(struct k_work *work,
                                    struct k_work_delayable *delayed)
{
  k_work_init(work, handler);
  k_work_init_delayable(delayed, handler);
  (void)k_work_submit(work);
  (void)k_work_schedule(delayed, K_MSEC(10));
  (void)k_work_cancel_delayable(delayed);
}
