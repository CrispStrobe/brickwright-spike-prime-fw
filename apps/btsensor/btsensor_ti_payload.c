/* SPDX-License-Identifier: MIT */

#include "btsensor_ti_payload.h"
#include <errno.h>

#if defined(__has_include)
#  if __has_include("ti_bts_local_payload.h")
#    include "ti_bts_local_payload.h"
#    define BTSENSOR_HAS_LOCAL_TI_PAYLOAD 1
#  endif
#endif

const uint8_t *btsensor_ti_payload(size_t *size)
{
#ifdef BTSENSOR_HAS_LOCAL_TI_PAYLOAD
  if (size != NULL)
    {
      *size = brickwright_local_ti_bts_image_size;
    }
  return brickwright_local_ti_bts_image;
#else
  if (size != NULL)
    {
      *size = 0;
    }
  return NULL;
#endif
}

/* Strong application-side implementation of the physical driver's weak
 * provider. The driver remains payload-free when this application is absent. */
int brickwright_hci_platform_service_pack(const uint8_t **image,
                                           size_t *length)
{
  if (image == NULL || length == NULL)
    {
      return -EINVAL;
    }
  *image = btsensor_ti_payload(length);
  return *image != NULL && *length != 0 ? 0 : -ENOENT;
}
