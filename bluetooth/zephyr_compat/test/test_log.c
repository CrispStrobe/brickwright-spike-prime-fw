/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(bt_test);
static enum brickwright_log_level captured_level;
static char captured_module[32];
static char captured_message[256];
static bool debug_enabled;
bool brickwright_log_enabled(enum brickwright_log_level level, const char *module)
{
  (void)module;
  return level != BRICKWRIGHT_LOG_DEBUG || debug_enabled;
}
void brickwright_log_write(enum brickwright_log_level level, const char *module,
                           const char *message)
{
  captured_level = level;
  snprintf(captured_module, sizeof(captured_module), "%s", module);
  snprintf(captured_message, sizeof(captured_message), "%s", message);
}
int main(void)
{
  LOG_WRN("packet %u", 7U);
  assert(captured_level == BRICKWRIGHT_LOG_WARNING);
  assert(strcmp(captured_module, "bt_test") == 0);
  assert(strcmp(captured_message, "packet 7") == 0);
  const unsigned char bytes[] = {0x00, 0xab, 0xff};
  snprintf(captured_message, sizeof(captured_message), "unchanged");
  LOG_HEXDUMP_DBG(bytes, sizeof(bytes), "rx");
  assert(strcmp(captured_message, "unchanged") == 0);
  debug_enabled = true;
  LOG_HEXDUMP_DBG(bytes, sizeof(bytes), "rx");
  assert(captured_level == BRICKWRIGHT_LOG_DEBUG);
  assert(strcmp(captured_message, "rx 00 ab ff") == 0);
  assert(LOG_DBG_ENABLED());
  return 0;
}
