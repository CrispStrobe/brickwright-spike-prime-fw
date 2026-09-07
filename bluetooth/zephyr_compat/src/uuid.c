/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdio.h>
#include <zephyr/sys/uuid.h>

static int hex(char c)
{
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

int uuid_from_string(const char *text, struct uuid *uuid)
{
  static const unsigned breaks[] = {8, 13, 18, 23};
  unsigned source = 0, output = 0, next_break = 0;
  if (!text || !uuid) return -EINVAL;
  while (output < UUID_SIZE) {
    if (next_break < 4 && source == breaks[next_break]) {
      if (text[source++] != '-') return -EINVAL;
      ++next_break;
    }
    int high = hex(text[source++]);
    int low = hex(text[source++]);
    if (high < 0 || low < 0) return -EINVAL;
    uuid->val[output++] = (uint8_t)((high << 4) | low);
  }
  return text[source] == '\0' ? 0 : -EINVAL;
}

int uuid_to_string(const struct uuid *uuid, char text[UUID_STR_LEN])
{
  if (!uuid || !text) return -EINVAL;
  int result = snprintf(text, UUID_STR_LEN,
      "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
      uuid->val[0], uuid->val[1], uuid->val[2], uuid->val[3],
      uuid->val[4], uuid->val[5], uuid->val[6], uuid->val[7],
      uuid->val[8], uuid->val[9], uuid->val[10], uuid->val[11],
      uuid->val[12], uuid->val[13], uuid->val[14], uuid->val[15]);
  return result == UUID_STR_LEN - 1 ? 0 : -EINVAL;
}
