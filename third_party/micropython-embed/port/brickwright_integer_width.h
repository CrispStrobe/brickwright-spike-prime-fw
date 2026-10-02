/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_INTEGER_WIDTH_H
#define BRICKWRIGHT_INTEGER_WIDTH_H

#include <limits.h>
#include <stdint.h>

/* For a constant m = 2^k - 1, 0 <= k <= 64, return k as an integer
 * constant expression under GCC/Clang. Inputs have no side effects.
 * Convert through uint64_t to retain the full unsigned 64-bit domain.
 * Set the low bit before clzll, ensuring its argument is never zero,
 * even in the unused branch of the zero case. This also lets Clang
 * accept the zero case as a constant expression in strict C99 mode.
 * Use the actual unsigned-long-long width, including on wider targets.
 */
#define MP_IMAX_BITS(m) \
    ((uint64_t)(m) == UINT64_C(0) ? 0 : \
        (int)(sizeof(unsigned long long) * CHAR_BIT - \
            __builtin_clzll((unsigned long long)((uint64_t)(m) | UINT64_C(1)))))

#endif
