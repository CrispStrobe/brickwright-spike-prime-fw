/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_BYTEORDER_H
#define BRICKWRIGHT_ZEPHYR_SYS_BYTEORDER_H

#include <stdint.h>
#include <string.h>

static inline uint16_t sys_get_le16(const uint8_t *p) { return (uint16_t)p[0] | (uint16_t)p[1] << 8; }
static inline uint32_t sys_get_le24(const uint8_t *p) { return sys_get_le16(p) | (uint32_t)p[2] << 16; }
static inline uint32_t sys_get_le32(const uint8_t *p) { return sys_get_le16(p) | (uint32_t)sys_get_le16(p + 2) << 16; }
static inline uint64_t sys_get_le64(const uint8_t *p) { return sys_get_le32(p) | (uint64_t)sys_get_le32(p + 4) << 32; }
static inline uint16_t sys_get_be16(const uint8_t *p) { return (uint16_t)p[0] << 8 | p[1]; }
static inline uint32_t sys_get_be32(const uint8_t *p) { return (uint32_t)sys_get_be16(p) << 16 | sys_get_be16(p + 2); }
static inline void sys_put_le16(uint16_t v, uint8_t *p) { p[0] = v; p[1] = v >> 8; }
static inline void sys_put_le24(uint32_t v, uint8_t *p) { sys_put_le16(v, p); p[2] = v >> 16; }
static inline void sys_put_le32(uint32_t v, uint8_t *p) { sys_put_le16(v, p); sys_put_le16(v >> 16, p + 2); }
static inline void sys_put_le64(uint64_t v, uint8_t *p) { sys_put_le32(v, p); sys_put_le32(v >> 32, p + 4); }
static inline void sys_put_be16(uint16_t v, uint8_t *p) { p[0] = v >> 8; p[1] = v; }
static inline void sys_put_be24(uint32_t v, uint8_t *p) { p[0] = v >> 16; sys_put_be16(v, p + 1); }
static inline void sys_put_be32(uint32_t v, uint8_t *p) { sys_put_be16(v >> 16, p); sys_put_be16(v, p + 2); }
static inline void sys_put_le40(uint64_t v, uint8_t *p) { sys_put_le32(v, p); p[4] = v >> 32; }
static inline void sys_put_le48(uint64_t v, uint8_t *p) { sys_put_le32(v, p); sys_put_le16(v >> 32, p + 4); }
static inline void sys_put_be40(uint64_t v, uint8_t *p) { p[0] = v >> 32; sys_put_be32(v, p + 1); }
static inline void sys_put_be48(uint64_t v, uint8_t *p) { sys_put_be16(v >> 32, p); sys_put_be32(v, p + 2); }
static inline void sys_put_be64(uint64_t v, uint8_t *p) { sys_put_be32(v >> 32, p); sys_put_be32(v, p + 4); }

#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define sys_cpu_to_le16(v) ((uint16_t)(v))
#define sys_cpu_to_le32(v) ((uint32_t)(v))
#define sys_le16_to_cpu(v) ((uint16_t)(v))
#define sys_le32_to_cpu(v) ((uint32_t)(v))
#define sys_le24_to_cpu(v) ((uint32_t)(v) & UINT32_C(0xffffff))
#define sys_le40_to_cpu(v) ((uint64_t)(v) & UINT64_C(0xffffffffff))
#define sys_le48_to_cpu(v) ((uint64_t)(v) & UINT64_C(0xffffffffffff))
#define sys_le64_to_cpu(v) ((uint64_t)(v))
#define sys_cpu_to_be16(v) __builtin_bswap16((uint16_t)(v))
#define sys_be16_to_cpu(v) __builtin_bswap16((uint16_t)(v))
#define sys_be24_to_cpu(v) (__builtin_bswap32((uint32_t)(v)) >> 8)
#define sys_be32_to_cpu(v) __builtin_bswap32((uint32_t)(v))
#define sys_be40_to_cpu(v) (__builtin_bswap64((uint64_t)(v)) >> 24)
#define sys_be48_to_cpu(v) (__builtin_bswap64((uint64_t)(v)) >> 16)
#define sys_be64_to_cpu(v) __builtin_bswap64((uint64_t)(v))
#else
#error "Brickwright SPIKE currently supports only little-endian NuttX targets"
#define sys_cpu_to_le16(v) __builtin_bswap16((uint16_t)(v))
#define sys_cpu_to_le32(v) __builtin_bswap32((uint32_t)(v))
#define sys_le16_to_cpu(v) __builtin_bswap16((uint16_t)(v))
#define sys_le32_to_cpu(v) __builtin_bswap32((uint32_t)(v))
#define sys_cpu_to_be16(v) ((uint16_t)(v))
#define sys_be16_to_cpu(v) ((uint16_t)(v))
#define sys_be32_to_cpu(v) ((uint32_t)(v))
#endif

static inline void sys_memcpy_swap(void *dst, const void *src, size_t length)
{
  const uint8_t *in = src;
  uint8_t *out = dst;
  for (size_t i = 0; i < length; ++i) out[i] = in[length - 1 - i];
}

static inline void sys_mem_swap(void *data, size_t length)
{
  uint8_t *bytes = data;
  for (size_t i = 0; i < length / 2; ++i)
    {
      uint8_t temporary = bytes[i];
      bytes[i] = bytes[length - 1 - i];
      bytes[length - 1 - i] = temporary;
    }
}

#define UNALIGNED_GET(pointer) ({ __typeof__(*(pointer)) _value; memcpy(&_value, (pointer), sizeof(_value)); _value; })

#endif
