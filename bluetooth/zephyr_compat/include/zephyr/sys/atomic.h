/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_ATOMIC_H
#define BRICKWRIGHT_ZEPHYR_SYS_ATOMIC_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __NuttX__
#include <nuttx/atomic.h>
typedef int32_t atomic_val_t;
#ifdef atomic_set
#undef atomic_set
#endif
#else
typedef long atomic_t;
typedef long atomic_val_t;
#endif
typedef void *atomic_ptr_val_t;
typedef void *atomic_ptr_t;
#define ATOMIC_INIT(value) (value)
#define ATOMIC_BITS (sizeof(atomic_t) * 8U)
#define ATOMIC_BITMAP_SIZE(bit_count) \
  (((bit_count) + ATOMIC_BITS - 1U) / ATOMIC_BITS)
#define ATOMIC_DEFINE(name, bit_count) \
  atomic_t name[ATOMIC_BITMAP_SIZE(bit_count)]

static inline atomic_val_t atomic_get(const atomic_t *target)
{
  return __atomic_load_n(target, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_set(atomic_t *target, atomic_val_t value)
{
  return __atomic_exchange_n(target, value, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_clear(atomic_t *target)
{
  return atomic_set(target, 0);
}

static inline atomic_val_t atomic_add(atomic_t *target, atomic_val_t value)
{
  return __atomic_fetch_add(target, value, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_inc(atomic_t *target)
{
  return atomic_add(target, 1);
}

static inline atomic_val_t atomic_dec(atomic_t *target)
{
  return __atomic_fetch_sub(target, 1, __ATOMIC_SEQ_CST);
}

static inline bool atomic_cas(atomic_t *target, atomic_val_t old_value,
                              atomic_val_t new_value)
{
  return __atomic_compare_exchange_n(target, &old_value, new_value, false,
                                     __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

static inline bool atomic_test_bit(const atomic_t *target, int bit)
{
  return (atomic_get(target) & (1L << bit)) != 0;
}

static inline void atomic_set_bit(atomic_t *target, int bit)
{
  __atomic_fetch_or(target, 1L << bit, __ATOMIC_SEQ_CST);
}

static inline void atomic_clear_bit(atomic_t *target, int bit)
{
  __atomic_fetch_and(target, ~(1L << bit), __ATOMIC_SEQ_CST);
}

static inline void atomic_set_bit_to(atomic_t *target, int bit, bool value)
{
  if (value) atomic_set_bit(target, bit); else atomic_clear_bit(target, bit);
}

static inline bool atomic_test_and_set_bit(atomic_t *target, int bit)
{
  return (__atomic_fetch_or(target, 1L << bit, __ATOMIC_SEQ_CST) & (1L << bit)) != 0;
}

static inline bool atomic_test_and_clear_bit(atomic_t *target, int bit)
{
  return (__atomic_fetch_and(target, ~(1L << bit), __ATOMIC_SEQ_CST) & (1L << bit)) != 0;
}

static inline atomic_ptr_val_t atomic_ptr_get(const atomic_ptr_t *target)
{
  return __atomic_load_n(target, __ATOMIC_SEQ_CST);
}

static inline atomic_ptr_val_t atomic_ptr_set(atomic_ptr_t *target,
                                               atomic_ptr_val_t value)
{
  return __atomic_exchange_n(target, value, __ATOMIC_SEQ_CST);
}

static inline atomic_ptr_val_t atomic_ptr_clear(atomic_ptr_t *target)
{
  return atomic_ptr_set(target, 0);
}

static inline bool atomic_ptr_cas(atomic_ptr_t *target, atomic_ptr_val_t old_value,
                                  atomic_ptr_val_t new_value)
{
  return __atomic_compare_exchange_n(target, &old_value, new_value, false,
                                     __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

#endif
