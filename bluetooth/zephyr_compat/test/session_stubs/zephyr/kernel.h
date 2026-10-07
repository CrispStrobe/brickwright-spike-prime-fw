/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026 Brickwright contributors */
#ifndef BW_SESSION_TEST_KERNEL_H
#define BW_SESSION_TEST_KERNEL_H
struct k_work { void (*handler)(struct k_work *); };
#define K_WORK_DEFINE(name, fn) struct k_work name = { .handler = fn }
static inline int k_work_submit(struct k_work *work)
{ work->handler(work); return 0; }
#endif
