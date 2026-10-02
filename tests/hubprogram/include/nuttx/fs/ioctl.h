/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BW_TEST_IOCTL_H
#define BW_TEST_IOCTL_H
#include <sys/ioctl.h>
#undef _IOC
#define _IOC(base, nr) ((base) | (nr))
#endif
