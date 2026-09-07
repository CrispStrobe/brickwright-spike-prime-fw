/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_ITERABLE_SECTIONS_H
#define BRICKWRIGHT_ZEPHYR_ITERABLE_SECTIONS_H
#define STRUCT_SECTION_ITERABLE(type, name) \
  struct type name __attribute__((section(#type), used, aligned(__alignof__(struct type))))
#define STRUCT_SECTION_START_EXTERN(type) extern struct type __start_##type[]
#define STRUCT_SECTION_END_EXTERN(type) extern struct type __stop_##type[]
#define TYPE_SECTION_START(type) \
  ({ extern struct type __start_##type[]; __start_##type; })
#define TYPE_SECTION_END(type) \
  ({ extern struct type __stop_##type[]; __stop_##type; })
#define STRUCT_SECTION_GET(type, index, destination) \
  (*(destination) = &__start_##type[(index)])
#define STRUCT_SECTION_FOREACH(type, iterator) \
  for (struct type *(iterator) = TYPE_SECTION_START(type); \
       (iterator) < TYPE_SECTION_END(type); ++(iterator))
#endif
