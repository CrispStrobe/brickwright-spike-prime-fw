/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SETTINGS_H
#define BRICKWRIGHT_ZEPHYR_SETTINGS_H
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
typedef ssize_t (*settings_read_cb)(void *cb_arg, void *data, size_t len);
typedef int (*settings_load_direct_cb)(const char *key, size_t len,
                                       settings_read_cb read_cb, void *cb_arg,
                                       void *param);
struct settings_handler {
  const char *name;
  int (*h_get)(const char *key, char *value, int value_len_max);
  int (*h_set)(const char *key, size_t len_rd, settings_read_cb read_cb,
               void *cb_arg);
  int (*h_commit)(void);
  int (*h_export)(int (*export_func)(const char *, const void *, size_t));
  int cprio;
  struct settings_handler *next;
};
int settings_subsys_init(void);
int settings_register(struct settings_handler *handler);
int settings_save_one(const char *name, const void *value, size_t length);
int settings_delete(const char *name);
int settings_name_next(const char *name, const char **next);
bool settings_name_steq(const char *name, const char *key, const char **next);
int settings_load(void);
int settings_load_subtree(const char *subtree);
int settings_load_subtree_direct(const char *subtree,
                                 settings_load_direct_cb callback, void *param);
#define SETTINGS_STATIC_HANDLER_DEFINE_WITH_CPRIO(symbol, subtree, get, set, commit, export, priority) \
  static struct settings_handler settings_handler_##symbol = { \
    .name = (subtree), .h_get = (get), .h_set = (set), .h_commit = (commit), \
    .h_export = (export), .cprio = (priority) }; \
  static void __attribute__((constructor)) settings_register_##symbol(void) \
  { (void)settings_register(&settings_handler_##symbol); }
#define SETTINGS_STATIC_HANDLER_DEFINE(symbol, subtree, get, set, commit, export) \
  SETTINGS_STATIC_HANDLER_DEFINE_WITH_CPRIO(symbol, subtree, get, set, commit, export, 0)
#endif
