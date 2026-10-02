/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_DEBUG_STACK_H
#define BRICKWRIGHT_ZEPHYR_DEBUG_STACK_H

#include <zephyr/kernel.h>

static inline void log_stack_usage(const struct k_thread *thread)
{
  ARG_UNUSED(thread);
}

#endif
