/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "../service.h"
#include <assert.h>
#include "../python_output.h"
#include <errno.h>
#include <stdio.h>
static int polls,speed,delta;
int bw_program_service_poll(void) { return ++polls>1000 ? -ETIMEDOUT : 0; }
int bw_program_service_motor(unsigned port,int32_t value) { assert(port==0);speed=value;return 0; }
int bw_program_service_position(unsigned port,int32_t degrees,int32_t velocity) {
  assert(port==1 && velocity==500);delta=degrees;return 0;
}
int bw_program_service_done(unsigned port) { assert(port==1);return 1; }
int bw_program_service_sensor(unsigned predicate,int32_t *value) { assert(predicate==1);*value=200;return 0; }
int main(void) {
  const char *source="import brickwright as b\nvalues=[x*x for x in range(6)]\nassert sum(values)==55\nb.motor(b.A,400)\nb.position(b.B,-90,500)\nassert b.sensor(1)==200\nprint('embedded MicroPython calculation and robot API: PASS')\n";
  assert(!bw_python_execute(source));assert(speed==400 && delta==-90);
  assert(g_bw_python_output.length>0);
  assert(!bw_python_execute("print('x' * 10000)\n"));
  assert(g_bw_python_output.length==BW_PYTHON_OUTPUT_CAPACITY && g_bw_python_output.truncated);
  assert(!bw_python_execute("assert 1+1 == 2\n"));
  assert(g_bw_python_output.length==0 && !g_bw_python_output.truncated);
  polls=0;assert(bw_python_execute("while True:\n pass\n")<0);
  polls=0;assert(bw_python_execute("this is invalid syntax !")<0);
  puts("embedded MicroPython cancellation and syntax failure: PASS");return 0;
}
