/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Host formatter using the retained LittleFS public interface. LittleFS is
 * BSD-3-Clause, copyright its authors and Arm Limited; retain LICENSE.md.
 */
#include "lfs.h"
#include "simulation_littlefs_geometry.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Only these two superblocks may be written. All remaining partition bytes
 * are modeled as erased NOR, without allocating a complete flash image. */
static unsigned char prefix[2 * BW_LFS_BLOCK_SIZE];
static unsigned char read_cache[BW_LFS_CACHE_SIZE];
static unsigned char prog_cache[BW_LFS_CACHE_SIZE];
static unsigned char lookahead[BW_LFS_LOOKAHEAD_SIZE];
static int readonly;
static unsigned mutations;

static int valid_range(lfs_block_t block, lfs_off_t off, lfs_size_t size)
{
  return block < BW_LFS_BLOCK_COUNT && off <= BW_LFS_BLOCK_SIZE &&
         size <= BW_LFS_BLOCK_SIZE - off;
}

static int read_block(const struct lfs_config *cfg, lfs_block_t block,
                      lfs_off_t off, void *buffer, lfs_size_t size)
{
  (void)cfg;
  if (!valid_range(block, off, size)) return LFS_ERR_IO;
  if (block < 2) memcpy(buffer, prefix + block * BW_LFS_BLOCK_SIZE + off, size);
  else memset(buffer, 0xff, size);
  return 0;
}

static int prog_block(const struct lfs_config *cfg, lfs_block_t block,
                      lfs_off_t off, const void *buffer, lfs_size_t size)
{
  (void)cfg;
  if (readonly || block >= 2 || !valid_range(block, off, size)) return LFS_ERR_IO;
  unsigned char *target = prefix + block * BW_LFS_BLOCK_SIZE + off;
  const unsigned char *source = buffer;
  for (lfs_size_t i = 0; i < size; ++i)
    if ((target[i] & source[i]) != source[i]) return LFS_ERR_IO;
  for (lfs_size_t i = 0; i < size; ++i) target[i] &= source[i];
  ++mutations;
  return 0;
}

static int erase_block(const struct lfs_config *cfg, lfs_block_t block)
{
  (void)cfg;
  if (readonly || block >= 2) return LFS_ERR_IO;
  memset(prefix + block * BW_LFS_BLOCK_SIZE, 0xff, BW_LFS_BLOCK_SIZE);
  ++mutations;
  return 0;
}

static int sync_block(const struct lfs_config *cfg) { (void)cfg; return 0; }

static int number_matches(const char *text, unsigned long expected)
{
  char *end;
  errno = 0;
  unsigned long value = strtoul(text, &end, 10);
  return text[0] >= '0' && text[0] <= '9' && !errno && !*end && value == expected;
}

int main(int argc, char **argv)
{
  if (argc != 4 || !number_matches(argv[2], BW_LFS_BLOCK_SIZE) ||
      !number_matches(argv[3], BW_LFS_BLOCK_COUNT))
    {
      fprintf(stderr, "usage: formatter OUTPUT %u %u (partition geometry)\n",
              BW_LFS_BLOCK_SIZE, BW_LFS_BLOCK_COUNT);
      return 2;
    }
  const struct lfs_config cfg = {
    .read = read_block, .prog = prog_block, .erase = erase_block, .sync = sync_block,
    .read_size = BW_LFS_READ_SIZE, .prog_size = BW_LFS_PROG_SIZE,
    .block_size = BW_LFS_BLOCK_SIZE, .block_count = BW_LFS_BLOCK_COUNT,
    .block_cycles = BW_LFS_BLOCK_CYCLES, .cache_size = BW_LFS_CACHE_SIZE,
    .lookahead_size = BW_LFS_LOOKAHEAD_SIZE, .read_buffer = read_cache,
    .prog_buffer = prog_cache, .lookahead_buffer = lookahead,
    .name_max = BW_LFS_NAME_MAX, .file_max = BW_LFS_FILE_MAX,
    .attr_max = BW_LFS_ATTR_MAX
  };
  lfs_t fs;
  memset(prefix, 0xff, sizeof(prefix));
  if (lfs_format(&fs, &cfg)) return 3;
  unsigned formatted_mutations = mutations;
  readonly = 1;
  if (lfs_mount(&fs, &cfg)) return 4;
  lfs_dir_t dir;
  struct lfs_info info;
  int result;
  unsigned entries = 0;
  if (lfs_dir_open(&fs, &dir, "/")) return 5;
  while ((result = lfs_dir_read(&fs, &dir, &info)) > 0)
    {
      if (strcmp(info.name, ".") && strcmp(info.name, "..")) return 6;
      if (info.type != LFS_TYPE_DIR) return 6;
      ++entries;
    }
  if (result < 0 || entries != 2 || lfs_dir_close(&fs, &dir) ||
      lfs_fs_size(&fs) != 2 || lfs_unmount(&fs) ||
      mutations != formatted_mutations) return 7;
  /* Open output only after a read-only mount and empty-root verification. */
  FILE *output = fopen(argv[1], "wbx");
  if (!output) { perror(argv[1]); return 8; }
  int failed = fwrite(prefix, 1, sizeof(prefix), output) != sizeof(prefix);
  if (fclose(output)) failed = 1;
  if (failed) { remove(argv[1]); return 9; }
  printf("empty LittleFS: offset=%u prefix=%zu block_size=%u block_count=%u; read-only mount verified\n",
         BW_LFS_OFFSET, sizeof(prefix), BW_LFS_BLOCK_SIZE, BW_LFS_BLOCK_COUNT);
  return 0;
}
