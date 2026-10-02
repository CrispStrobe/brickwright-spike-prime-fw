/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ENTROPY_H
#define BRICKWRIGHT_ENTROPY_H

#include <stddef.h>
#include <sys/types.h>

/* Board/simulator boundary. Implementations may return a short read. */
ssize_t brickwright_entropy_read(void *buffer, size_t length);

#endif
