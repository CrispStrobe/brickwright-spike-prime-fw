/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_DEVICE_H
#define BRICKWRIGHT_ZEPHYR_DEVICE_H

struct device
{
  const void *api;
  void *data;
};

extern const struct device brickwright_hci_device;

#ifndef __subsystem
#define __subsystem
#endif

#define DEVICE_API_GET(name, device) \
  ((const struct name##_driver_api *)((device)->api))

static inline int device_is_ready(const struct device *device)
{
  return device != 0 && device->api != 0;
}

#endif
