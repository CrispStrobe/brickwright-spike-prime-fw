/* SPDX-License-Identifier: Apache-2.0 */
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <brickwright/settings_store.h>
#include <zephyr/settings/settings.h>

#define SETTINGS_ROOT "/mnt/flash/brickwright-settings"
#define SETTINGS_PATH_MAX 192
static struct settings_handler *handlers;

struct file_reader { int fd; };
static ssize_t read_file(void *context, void *data, size_t length)
{
  struct file_reader *reader = context;
  ssize_t result;
  do result = read(reader->fd, data, length); while (result < 0 && errno == EINTR);
  return result < 0 ? -errno : result;
}

static int visit_directory(const char *subtree, const char *relative,
                           brickwright_settings_visit_cb visitor, void *context)
{
  char directory_path[SETTINGS_PATH_MAX];
  int count = snprintf(directory_path, sizeof(directory_path), "%s%s%s",
                       SETTINGS_ROOT, *relative ? "/" : "", relative);
  if (count < 0 || (size_t)count >= sizeof(directory_path)) return -ENAMETOOLONG;
  DIR *directory = opendir(directory_path);
  if (!directory) return errno == ENOENT ? 0 : -errno;
  int result = 0;
  struct dirent *entry;
  while (!result && (entry = readdir(directory))) {
    if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
    char key[128];
    count = snprintf(key, sizeof(key), "%s%s%s", relative,
                     *relative ? "/" : "", entry->d_name);
    if (count < 0 || (size_t)count >= sizeof(key)) { result = -ENAMETOOLONG; break; }
    char path[SETTINGS_PATH_MAX];
    count = snprintf(path, sizeof(path), "%s/%s", SETTINGS_ROOT, key);
    if (count < 0 || (size_t)count >= sizeof(path)) { result = -ENAMETOOLONG; break; }
    struct stat status;
    if (stat(path, &status) < 0) { result = -errno; break; }
    if (S_ISDIR(status.st_mode)) {
      result = visit_directory(subtree, key, visitor, context);
    } else if (S_ISREG(status.st_mode)) {
      size_t subtree_length = subtree ? strlen(subtree) : 0;
      if (subtree_length && (strncmp(key, subtree, subtree_length) ||
          (key[subtree_length] && key[subtree_length] != '/'))) continue;
      int fd = open(path, O_RDONLY);
      if (fd < 0) { result = -errno; break; }
      struct file_reader reader = {.fd = fd};
      result = visitor(key, (size_t)status.st_size, read_file, &reader, context);
      close(fd);
    }
  }
  closedir(directory);
  return result;
}

__attribute__((weak)) int brickwright_settings_visit(
  const char *subtree, brickwright_settings_visit_cb visitor, void *context)
{
  return visit_directory(subtree, "", visitor, context);
}

static int valid_key(const char *key)
{
  if (!key || !*key || strlen(key) >= 128) return 0;
  int segment_has_character = 0;
  for (const unsigned char *p = (const unsigned char *)key; *p; ++p) {
    if (*p == '/') {
      if (!segment_has_character) return 0;
      segment_has_character = 0;
    } else if (isalnum(*p) || *p == '-' || *p == '_') {
      segment_has_character = 1;
    } else {
      return 0;
    }
  }
  return segment_has_character;
}

static int make_parents(char *path)
{
  for (char *p = path + 1; *p; ++p) {
    if (*p != '/') continue;
    *p = '\0';
    if (mkdir(path, 0700) < 0 && errno != EEXIST) { *p = '/'; return -errno; }
    *p = '/';
  }
  return 0;
}

__attribute__((weak)) int brickwright_settings_store(const char *key,
                                                       const void *value,
                                                       size_t length)
{
  char path[SETTINGS_PATH_MAX];
  char temporary[SETTINGS_PATH_MAX];
  int count = snprintf(path, sizeof(path), "%s/%s", SETTINGS_ROOT, key);
  if (count < 0 || (size_t)count >= sizeof(path)) return -ENAMETOOLONG;
  count = snprintf(temporary, sizeof(temporary), "%s.tmp", path);
  if (count < 0 || (size_t)count >= sizeof(temporary)) return -ENAMETOOLONG;
  int result = make_parents(path);
  if (result) return result;
  int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0) return -errno;
  const unsigned char *cursor = value;
  size_t remaining = length;
  while (remaining) {
    ssize_t written = write(fd, cursor, remaining);
    if (written < 0 && errno == EINTR) continue;
    if (written <= 0) { result = written < 0 ? -errno : -EIO; break; }
    cursor += written;
    remaining -= (size_t)written;
  }
  if (!result && fsync(fd) < 0) result = -errno;
  if (close(fd) < 0 && !result) result = -errno;
  if (!result && rename(temporary, path) < 0) result = -errno;
  if (result) unlink(temporary);
  return result;
}

__attribute__((weak)) int brickwright_settings_remove(const char *key)
{
  char path[SETTINGS_PATH_MAX];
  int count = snprintf(path, sizeof(path), "%s/%s", SETTINGS_ROOT, key);
  if (count < 0 || (size_t)count >= sizeof(path)) return -ENAMETOOLONG;
  if (unlink(path) < 0 && errno != ENOENT) return -errno;
  return 0;
}

int settings_subsys_init(void) { return 0; }
int settings_register(struct settings_handler *handler)
{
  if (!handler || !handler->name) return -EINVAL;
  struct settings_handler **position = &handlers;
  while (*position && (*position)->cprio <= handler->cprio)
    position = &(*position)->next;
  handler->next = *position;
  *position = handler;
  return 0;
}
int settings_save_one(const char *name, const void *value, size_t length)
{
  if (!valid_key(name) || (!value && length)) return -EINVAL;
  return brickwright_settings_store(name, value, length);
}
int settings_delete(const char *name)
{
  if (!valid_key(name)) return -EINVAL;
  return brickwright_settings_remove(name);
}
int settings_name_next(const char *name, const char **next)
{
  if (!name) { if (next) *next = NULL; return 0; }
  const char *separator = strchr(name, '/');
  if (next) *next = separator && separator[1] ? separator + 1 : NULL;
  if (separator) return (int)(separator - name);
  return (int)strlen(name);
}
bool settings_name_steq(const char *name, const char *key, const char **next)
{
  if (!name || !key) return false;
  size_t length = strlen(key);
  if (strncmp(name, key, length) || (name[length] && name[length] != '/')) return false;
  if (next) *next = name[length] == '/' ? name + length + 1 : NULL;
  return true;
}

struct load_context {
  const char *subtree;
  settings_load_direct_cb direct;
  void *param;
};
static int dispatch_setting(const char *key, size_t length,
                            brickwright_settings_read_cb read_cb,
                            void *read_context, void *opaque)
{
  struct load_context *context = opaque;
  if (context->direct) {
    const char *relative = key;
    if (context->subtree && *context->subtree &&
        !settings_name_steq(key, context->subtree, &relative)) return 0;
    return context->direct(relative, length, (settings_read_cb)read_cb,
                           read_context, context->param);
  }
  for (struct settings_handler *handler = handlers; handler; handler = handler->next) {
    const char *relative;
    if (handler->h_set && settings_name_steq(key, handler->name, &relative))
      return handler->h_set(relative, length, (settings_read_cb)read_cb, read_context);
  }
  return 0;
}
int settings_load_subtree_direct(const char *subtree,
                                 settings_load_direct_cb callback, void *param)
{
  if (!callback || (subtree && *subtree && !valid_key(subtree))) return -EINVAL;
  struct load_context context = {
    .subtree = subtree, .direct = callback, .param = param
  };
  return brickwright_settings_visit(subtree, dispatch_setting, &context);
}
int settings_load_subtree(const char *subtree)
{
  if (subtree && *subtree && !valid_key(subtree)) return -EINVAL;
  struct load_context context = {0};
  int result = brickwright_settings_visit(subtree, dispatch_setting, &context);
  if (result) return result;
  for (struct settings_handler *handler = handlers; handler; handler = handler->next)
    if (handler->h_commit) {
      result = handler->h_commit();
      if (result) return result;
    }
  return 0;
}
int settings_load(void) { return settings_load_subtree(NULL); }
