/* SPDX-License-Identifier: Apache-2.0 */
#include <stddef.h>
#include <zephyr/bluetooth/crypto.h>

int mbedtls_hardware_poll(void *context, unsigned char *output, size_t length,
                          size_t *output_length)
{
  (void)context;
  if (output_length)
    {
      *output_length = 0;
    }
  if (!output || !output_length || bt_rand(output, length) != 0)
    {
      return -1;
    }
  *output_length = length;
  return 0;
}
