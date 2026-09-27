/* SPDX-License-Identifier: MIT */
#ifndef BTSENSOR_FONT5_H
#define BTSENSOR_FONT5_H

#include <stdbool.h>
#include <stdint.h>

/* Five rows of a 5x5 glyph; bit 4 of each row is the leftmost column.
 * Covers space, 0-9, A-Z (lower case maps to upper case) and ! ? . , - + :
 * = / ' ". Returns false for other characters. */
bool btsensor_font5_glyph(char c, uint8_t rows[5]);

#endif
