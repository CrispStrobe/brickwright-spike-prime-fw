/* SPDX-License-Identifier: Apache-2.0 */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#ifdef __NuttX__
#include <syslog.h>
#endif
#include <brickwright/log.h>

__attribute__((weak)) bool brickwright_log_enabled(enum brickwright_log_level level,
                                                    const char *module)
{
  (void)module;
  return level >= BRICKWRIGHT_LOG_INFO;
}

__attribute__((weak)) void brickwright_log_write(enum brickwright_log_level level,
                                                  const char *module,
                                                  const char *message)
{
#ifdef __NuttX__
  static const int priorities[] = {LOG_DEBUG, LOG_INFO, LOG_WARNING, LOG_ERR};
  syslog(priorities[level], "%s: %s\n", module, message);
#else
  static const char names[] = {'D', 'I', 'W', 'E'};
  fprintf(stderr, "[%c] %s: %s\n", names[level], module, message);
#endif
}

void brickwright_log_emit(enum brickwright_log_level level, const char *module,
                          const char *format, ...)
{
  if (!brickwright_log_enabled(level, module)) return;
  char message[256];
  va_list arguments;
  va_start(arguments, format);
  vsnprintf(message, sizeof(message), format, arguments);
  va_end(arguments);
  brickwright_log_write(level, module, message);
}

void brickwright_log_hexdump(enum brickwright_log_level level, const char *module,
                             const void *data, size_t length, const char *message)
{
  if (!brickwright_log_enabled(level, module)) return;
  const uint8_t *bytes = data;
  char output[256];
  int used = snprintf(output, sizeof(output), "%s", message);
  if (used < 0) return;
  for (size_t i = 0; i < length && (size_t)used + 3 < sizeof(output); ++i)
    used += snprintf(output + used, sizeof(output) - (size_t)used, " %02x", bytes[i]);
  brickwright_log_write(level, module, output);
}
