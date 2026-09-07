/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_LOG_H
#define BRICKWRIGHT_LOG_H
#include <stdbool.h>
#include <stddef.h>
enum brickwright_log_level {
  BRICKWRIGHT_LOG_DEBUG,
  BRICKWRIGHT_LOG_INFO,
  BRICKWRIGHT_LOG_WARNING,
  BRICKWRIGHT_LOG_ERROR,
};
bool brickwright_log_enabled(enum brickwright_log_level level,
                             const char *module);
void brickwright_log_write(enum brickwright_log_level level, const char *module,
                           const char *message);
void brickwright_log_emit(enum brickwright_log_level level, const char *module,
                          const char *format, ...);
void brickwright_log_hexdump(enum brickwright_log_level level, const char *module,
                             const void *data, size_t length, const char *message);
#endif
