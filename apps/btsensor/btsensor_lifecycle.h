/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_LIFECYCLE_H
#define BTSENSOR_LIFECYCLE_H

#include <stdbool.h>

#include "btsensor_transport.h"

struct btsensor_lifecycle_hooks
{
  btsensor_transport_receive_cb receive;
  btsensor_transport_state_cb state;
  void *receive_context;
  int (*services_start)(void *context);
  void (*services_stop)(void *context);
  void *services_context;
};

int btsensor_lifecycle_start(const struct btsensor_lifecycle_hooks *hooks);
int btsensor_lifecycle_stop(int timeout_ms);
bool btsensor_lifecycle_running(void);
int btsensor_lifecycle_pid(void);

#endif
