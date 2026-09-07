/* SPDX-License-Identifier: MIT */

#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <brickwright/hci_driver.h>
#include "btsensor_ti_payload.h"

int main(void)
{
  size_t size = 99;
  const uint8_t *payload = btsensor_ti_payload(&size);
  const uint8_t *provided = (const uint8_t *)1;
  size_t provided_size = 99;
#ifdef EXPECT_LOCAL_PAYLOAD
  assert(payload != NULL && size >= 32);
  assert(memcmp(payload, "BTSB", 4) == 0);
  assert(brickwright_hci_platform_service_pack(&provided,
                                                &provided_size) == 0);
  assert(provided == payload && provided_size == size);
#else
  assert(payload == NULL && size == 0);
  assert(brickwright_hci_platform_service_pack(&provided,
                                                &provided_size) == -ENOENT);
  assert(provided == NULL && provided_size == 0);
#endif
  assert(brickwright_hci_platform_service_pack(NULL, &provided_size) ==
         -EINVAL);
  return 0;
}
