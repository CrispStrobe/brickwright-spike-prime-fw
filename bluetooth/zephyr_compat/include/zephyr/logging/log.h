/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_LOG_H
#define BRICKWRIGHT_ZEPHYR_LOG_H
#include <brickwright/log.h>
#define BRICKWRIGHT_LOG_STRINGIFY_(value) #value
#define BRICKWRIGHT_LOG_STRINGIFY(value) BRICKWRIGHT_LOG_STRINGIFY_(value)
#define LOG_MODULE_REGISTER(name, ...) \
  static const char *const brickwright_log_module __attribute__((unused)) = \
    BRICKWRIGHT_LOG_STRINGIFY(name)
#define LOG_MODULE_DECLARE(name, ...) \
  static const char *const brickwright_log_module __attribute__((unused)) = \
    BRICKWRIGHT_LOG_STRINGIFY(name)
#define LOG_DBG(...) \
  brickwright_log_emit(BRICKWRIGHT_LOG_DEBUG, brickwright_log_module, __VA_ARGS__)
#define LOG_INF(...) \
  brickwright_log_emit(BRICKWRIGHT_LOG_INFO, brickwright_log_module, __VA_ARGS__)
#define LOG_WRN(...) \
  brickwright_log_emit(BRICKWRIGHT_LOG_WARNING, brickwright_log_module, __VA_ARGS__)
#define LOG_ERR(...) \
  brickwright_log_emit(BRICKWRIGHT_LOG_ERROR, brickwright_log_module, __VA_ARGS__)
#define LOG_HEXDUMP_DBG(data, length, message) \
  brickwright_log_hexdump(BRICKWRIGHT_LOG_DEBUG, brickwright_log_module, \
                          (data), (length), (message))
#define LOG_DBG_ENABLED() true
#endif
