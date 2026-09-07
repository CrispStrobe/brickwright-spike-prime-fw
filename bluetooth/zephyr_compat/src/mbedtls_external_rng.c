/* SPDX-License-Identifier: Apache-2.0 */
#include <psa/crypto.h>
#include <psa/crypto_extra.h>
#include <brickwright/entropy.h>

psa_status_t mbedtls_psa_external_get_random(
    mbedtls_psa_external_random_context_t *context,
    uint8_t *output, size_t output_size, size_t *output_length)
{
  (void)context;
  if (brickwright_entropy_read(output, output_size) != 0)
    {
      *output_length = 0;
      return PSA_ERROR_HARDWARE_FAILURE;
    }
  *output_length = output_size;
  return PSA_SUCCESS;
}
