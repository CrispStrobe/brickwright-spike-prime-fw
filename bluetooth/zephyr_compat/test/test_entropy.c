/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>

#include <brickwright/entropy.h>
#include <zephyr/bluetooth/crypto.h>

static int mode;
static unsigned int calls;

ssize_t brickwright_entropy_read(void *buffer, size_t length)
{
  ++calls;
  if (mode == 1 && calls == 1) {
    errno = EINTR;
    return -1;
  }
  if (mode == 2 && calls == 2) {
    errno = EIO;
    return -1;
  }
  size_t count = length > 3 ? 3 : length;
  memset(buffer, (int)(0x40 + calls), count);
  return (ssize_t)count;
}

int main(void)
{
  uint8_t data[8];

  assert(bt_rand(NULL, sizeof(data)) == -EINVAL);
  assert(bt_rand(data, 0) == -EINVAL);

  calls = 0;
  mode = 0;
  assert(bt_rand(data, sizeof(data)) == 0);
  assert(calls == 3);
  assert(data[0] == 0x41 && data[3] == 0x42 && data[6] == 0x43);

  calls = 0;
  mode = 1;
  assert(bt_rand(data, sizeof(data)) == 0);
  assert(calls == 4);

  memset(data, 0xaa, sizeof(data));
  calls = 0;
  mode = 2;
  assert(bt_rand(data, sizeof(data)) == -EIO);
  for (size_t i = 0; i < sizeof(data); ++i) assert(data[i] == 0);
  return 0;
}
