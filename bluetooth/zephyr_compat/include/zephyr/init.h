/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_INIT_H
#define BRICKWRIGHT_ZEPHYR_INIT_H
#define POST_KERNEL 0
#define SYS_INIT(function, level, priority) \
  static void function##_constructor(void) __attribute__((constructor)); \
  static void function##_constructor(void) { (void)(level); (void)(priority); (void)function(); }
#endif
