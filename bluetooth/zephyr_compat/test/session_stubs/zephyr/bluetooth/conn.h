/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026 Brickwright contributors */
#ifndef BW_SESSION_TEST_CONN_H
#define BW_SESSION_TEST_CONN_H
#include <stdint.h>
#include <stdbool.h>
#define BT_CONN_TYPE_LE 1
#define BT_CONN_ROLE_PERIPHERAL 1
struct bt_conn { int refs; bool alive; unsigned peer; };
struct bt_conn_info { unsigned type, role; };
struct bt_conn_cb {
  void (*connected)(struct bt_conn *, uint8_t);
  void (*disconnected)(struct bt_conn *, uint8_t);
  void (*recycled)(void);
};
#define BT_CONN_CB_DEFINE(name) struct bt_conn_cb name
int bt_conn_get_info(struct bt_conn *, struct bt_conn_info *);
struct bt_conn *bt_conn_ref(struct bt_conn *);
void bt_conn_unref(struct bt_conn *);
#endif
