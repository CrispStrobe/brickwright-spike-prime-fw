/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_TOOLCHAIN_H
#define BRICKWRIGHT_ZEPHYR_TOOLCHAIN_H
#define __aligned(value) __attribute__((aligned(value)))
#define __packed __attribute__((packed))
#define __noinit
#define __must_check __attribute__((warn_unused_result))
#define __fallthrough __attribute__((fallthrough))
#define __maybe_unused __attribute__((unused))
#define __deprecated __attribute__((deprecated))
#define __weak __attribute__((weak))
#define __unused __attribute__((unused))
#endif
