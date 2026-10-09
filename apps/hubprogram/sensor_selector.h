/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_SENSOR_SELECTOR_H
#define BRICKWRIGHT_SENSOR_SELECTOR_H
/* Additive explicit distance tokens; legacy predicates 1..6 retain their ABI.
 * Token = 0x100 + (zero-based A..F port << 3) + distance predicate 1 or 2.
 */
static inline unsigned bw_sensor_predicate(unsigned selector)
{
  unsigned port, predicate;
  if (selector >= 1 && selector <= 6) return selector;
  if (selector < 0x100) return 0;
  port = (selector - 0x100) >> 3;
  predicate = (selector - 0x100) & 7;
  return port < 6 && (predicate == 1 || predicate == 2) ? predicate : 0;
}
#endif
