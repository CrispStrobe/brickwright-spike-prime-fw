/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BTSENSOR_NUTTX_PERIPHERAL_H
#define BTSENSOR_NUTTX_PERIPHERAL_H

/* Initialise the sampler/emitter services and install their neutral command
 * operations.  start/stop are idempotent and run on the daemon owner thread. */
int btsensor_nuttx_peripheral_start(void);
void btsensor_nuttx_peripheral_stop(void);

#endif
