/* SPDX-License-Identifier: Apache-2.0 */
#include <zephyr/sys/iterable_sections.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci_types.h>
#include "host/classic/sco_internal.h"

/* GNU start/stop symbols only exist for non-empty iterable sections. */
static const STRUCT_SECTION_ITERABLE(bt_sco_conn_cb,
                                     brickwright_empty_sco_conn_cb) = {0};
static const STRUCT_SECTION_ITERABLE(bt_sco_hci_cb,
                                     brickwright_empty_sco_hci_cb) = {0};
