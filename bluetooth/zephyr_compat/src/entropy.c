/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <sys/random.h>

#include <brickwright/entropy.h>
#include <zephyr/bluetooth/crypto.h>

__attribute__((weak)) ssize_t brickwright_entropy_read(void *buffer, size_t length)
{
  return getrandom(buffer, length, GRND_RANDOM);
}

int bt_rand(void *buffer, size_t length)
{
  if (!buffer || !length) return -EINVAL;

  uint8_t *cursor = buffer;
  size_t remaining = length;
  while (remaining) {
    ssize_t count = brickwright_entropy_read(cursor, remaining);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0 || (size_t)count > remaining) {
      memset(buffer, 0, length);
      return -EIO;
    }
    cursor += count;
    remaining -= (size_t)count;
  }

  return 0;
}
