/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_UUID_H
#define BRICKWRIGHT_ZEPHYR_SYS_UUID_H

#include <stdint.h>

#define UUID_SIZE 16
#define UUID_STR_LEN 37
struct uuid { uint8_t val[UUID_SIZE]; };
int uuid_from_string(const char *text, struct uuid *uuid);
int uuid_to_string(const struct uuid *uuid, char text[UUID_STR_LEN]);

#endif
