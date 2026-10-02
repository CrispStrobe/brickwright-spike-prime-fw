/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_UTIL_H
#define BRICKWRIGHT_ZEPHYR_SYS_UTIL_H

#include <stddef.h>
#include <stdint.h>
#include <errno.h>

#ifndef BIT
#define BIT(n) (1UL << (n))
#endif
#ifndef BIT64
#define BIT64(n) (1ULL << (n))
#endif
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define min(a, b) MIN(a, b)
#define max(a, b) MAX(a, b)
#define ARG_UNUSED(arg) ((void)(arg))
#define CONTAINER_OF(ptr, type, member) \
  ((type *)((char *)(ptr) - offsetof(type, member)))
#define BUILD_ASSERT(condition, ...) _Static_assert(condition, #condition)
#define ROUND_UP(value, alignment) \
  (((value) + (alignment) - 1) / (alignment) * (alignment))
#define DIV_ROUND_UP(value, divisor) (((value) + (divisor) - 1) / (divisor))
#define IN_RANGE(value, minimum, maximum) \
  ((value) >= (minimum) && (value) <= (maximum))
#define FLEXIBLE_ARRAY_DECLARE(type, name) \
  struct { struct { } unused_##name; type name[]; }
#define BRICKWRIGHT_CONCAT_INNER(first, second) first##second
#define _CONCAT(first, second) BRICKWRIGHT_CONCAT_INNER(first, second)
#define ARRAY_FOR_EACH(array, index) \
  for (size_t index = 0; index < ARRAY_SIZE(array); ++index)
#define ARRAY_INDEX(array, pointer) ((size_t)((pointer) - (array)))
#define IS_ARRAY_ELEMENT(array, pointer) \
  ((pointer) >= &(array)[0] && (pointer) < &(array)[ARRAY_SIZE(array)])
#define POINTER_TO_UINT(pointer) ((uintptr_t)(pointer))
#define UINT_TO_POINTER(value) ((void *)(uintptr_t)(value))

static inline int util_memeq(const void *first, const void *second,
                             size_t length)
{
  const uint8_t *a = first;
  const uint8_t *b = second;
  uint8_t difference = 0;

  for (size_t i = 0; i < length; ++i)
    {
      difference |= a[i] ^ b[i];
    }

  return difference == 0;
}

static inline void mem_xor_128(uint8_t result[16], const uint8_t first[16],
                               const uint8_t second[16])
{
  for (size_t i = 0; i < 16; ++i)
    {
      result[i] = first[i] ^ second[i];
    }
}

size_t hex2bin(const char *hex, size_t hex_length, uint8_t *output,
               size_t output_length);

#define BRICKWRIGHT_DEBRACKET(...) __VA_ARGS__
#define BRICKWRIGHT_IF_ENABLED_0(code)
#define BRICKWRIGHT_IF_ENABLED_1(code) BRICKWRIGHT_DEBRACKET code
#define BRICKWRIGHT_IF_ENABLED_SELECT(value, code) BRICKWRIGHT_IF_ENABLED_##value(code)
#ifndef IF_ENABLED
#define IF_ENABLED(value, code) BRICKWRIGHT_IF_ENABLED_SELECT(value, code)
#endif

static inline int hex2char(uint8_t value, char *character)
{
  if (!character || value > 0x0f)
    {
      return -EINVAL;
    }

  *character = value < 10 ? (char)('0' + value) : (char)('a' + value - 10);
  return 0;
}

static inline int u8_to_dec(char *buffer, size_t length, uint8_t value)
{
  char digits[3];
  int count = 0;

  do
    {
      digits[count++] = (char)('0' + value % 10);
      value /= 10;
    }
  while (value);

  if (!buffer || length <= (size_t)count)
    {
      return -ENOMEM;
    }

  for (int i = 0; i < count; ++i)
    {
      buffer[i] = digits[count - i - 1];
    }

  buffer[count] = '\0';
  return count;
}
#define BRICKWRIGHT_STRINGIFY(value) #value
#define STRINGIFY(value) BRICKWRIGHT_STRINGIFY(value)

#endif
