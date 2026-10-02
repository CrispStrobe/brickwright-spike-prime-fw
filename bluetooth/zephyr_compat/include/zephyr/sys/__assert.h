/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_ASSERT_H
#define BRICKWRIGHT_ZEPHYR_SYS_ASSERT_H
#include <assert.h>
#include <stdio.h>
#define __ASSERT(condition, message, ...) do { \
  if (!(condition)) { \
    fprintf(stderr, message "\n", ##__VA_ARGS__); \
    assert(condition); \
  } \
} while (0)
#define __ASSERT_NO_MSG(condition) assert(condition)
#endif
