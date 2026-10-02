/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_SETTINGS_STORE_H
#define BRICKWRIGHT_SETTINGS_STORE_H
#include <stddef.h>
#include <sys/types.h>
typedef ssize_t (*brickwright_settings_read_cb)(void *context, void *data,
                                                size_t length);
typedef int (*brickwright_settings_visit_cb)(const char *key, size_t length,
                                              brickwright_settings_read_cb read,
                                              void *read_context, void *context);
int brickwright_settings_store(const char *key, const void *value, size_t length);
int brickwright_settings_remove(const char *key);
int brickwright_settings_visit(const char *subtree,
                               brickwright_settings_visit_cb visitor,
                               void *context);
#endif
