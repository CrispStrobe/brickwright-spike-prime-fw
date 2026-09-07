/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <brickwright/settings_store.h>
#include <zephyr/settings/settings.h>
static char saved_key[64];
static unsigned char saved_value[16];
static size_t saved_length;
static char removed_key[64];
static const unsigned char loaded_value[] = {9, 8, 7, 6};
static char loaded_name[32];
static unsigned char loaded_copy[8];
static int committed;
int brickwright_settings_store(const char *key, const void *value, size_t length)
{
  strcpy(saved_key, key);
  memcpy(saved_value, value, length);
  saved_length = length;
  return 0;
}
int brickwright_settings_remove(const char *key)
{
  strcpy(removed_key, key);
  return 0;
}
static ssize_t load_read(void *context, void *data, size_t length)
{
  size_t *offset = context;
  size_t available = sizeof(loaded_value) - *offset;
  if (length > available) length = available;
  memcpy(data, loaded_value + *offset, length);
  *offset += length;
  return (ssize_t)length;
}
int brickwright_settings_visit(const char *subtree,
                               brickwright_settings_visit_cb visitor,
                               void *context)
{
  assert(!subtree || strcmp(subtree, "bt") == 0);
  size_t offset = 0;
  return visitor("bt/name", sizeof(loaded_value), load_read, &offset, context);
}
static int set_value(const char *name, size_t length, settings_read_cb read_cb,
                     void *read_context)
{
  strcpy(loaded_name, name);
  assert(read_cb(read_context, loaded_copy, length) == (ssize_t)length);
  return 0;
}
static int commit_value(void) { ++committed; return 0; }
static int direct_value(const char *name, size_t length, settings_read_cb read_cb,
                        void *read_context, void *parameter)
{
  assert(strcmp(name, "name") == 0);
  assert(parameter == loaded_value);
  unsigned char copy[sizeof(loaded_value)];
  assert(read_cb(read_context, copy, length) == (ssize_t)length);
  assert(memcmp(copy, loaded_value, sizeof(copy)) == 0);
  return 0;
}
SETTINGS_STATIC_HANDLER_DEFINE(test_bt, "bt", NULL, set_value, commit_value, NULL);
int main(void)
{
  const char *next;
  assert(settings_name_next("bt/keys/device", &next) == 2);
  assert(strcmp(next, "keys/device") == 0);
  assert(settings_name_next(next, &next) == 4);
  assert(strcmp(next, "device") == 0);
  assert(settings_name_next(next, &next) == 6 && next == NULL);
  const unsigned char value[] = {1, 2, 3};
  assert(settings_save_one("bt/keys/device_1", value, sizeof(value)) == 0);
  assert(strcmp(saved_key, "bt/keys/device_1") == 0);
  assert(saved_length == sizeof(value) && memcmp(saved_value, value, sizeof(value)) == 0);
  assert(settings_delete("bt/keys/device_1") == 0);
  assert(strcmp(removed_key, "bt/keys/device_1") == 0);
  assert(settings_save_one("../escape", value, sizeof(value)) == -EINVAL);
  assert(settings_save_one("bt//empty", value, sizeof(value)) == -EINVAL);
  assert(settings_save_one("bt/key", NULL, 1) == -EINVAL);
  assert(settings_name_steq("bt/name", "bt", &next));
  assert(strcmp(next, "name") == 0);
  assert(!settings_name_steq("bt_other/name", "bt", &next));
  assert(settings_load_subtree("bt") == 0);
  assert(strcmp(loaded_name, "name") == 0);
  assert(memcmp(loaded_copy, loaded_value, sizeof(loaded_value)) == 0);
  assert(committed == 1);
  assert(settings_load_subtree_direct("bt", direct_value,
                                      (void *)loaded_value) == 0);
  return 0;
}
