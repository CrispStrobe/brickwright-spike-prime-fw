/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "../service.h"
#include <assert.h>
#include "../python_output.h"
#include <errno.h>
#include <stdio.h>
static int polls,speed,delta,poll_error,motor_error;
static unsigned motors,positions;
int bw_program_service_poll(void) { return poll_error ? poll_error : ++polls>1000 ? -ETIMEDOUT : 0; }
int bw_program_service_motor(unsigned port,int32_t value) { assert(port<6);motors|=1u<<port;speed=value;return motor_error; }
int bw_program_service_position(unsigned port,int32_t degrees,int32_t velocity) {
  assert(port<6 && velocity>=1 && velocity<=1110);positions|=1u<<port;delta=degrees;return 0;
}
int bw_program_service_done(unsigned port) { assert(port<6);return 1; }
int bw_program_service_sensor(unsigned predicate,int32_t *value) { assert(predicate==1);*value=200;return 0; }
int main(void) {
  const char *source="import brickwright as b\nvalues=[x*x for x in range(6)]\nassert sum(values)==55\nb.motor(b.A,400)\nb.position(b.B,-90,500)\nassert b.sensor(1)==200\nprint('embedded MicroPython calculation and robot API: PASS')\n";
  assert(!bw_python_execute(source));assert(speed==400 && delta==-90);
  assert(g_bw_python_output.length>0);
  assert(!bw_python_execute("import brickwright as b\nfor port in range(2,6):\n b.motor(port,400)\n b.position(port,-90,500)\n"));
  assert(motors==61 && positions==62);
  /* Invalid integers must fail before truncation or reaching the service. */
  assert(!bw_python_execute("import brickwright as b\nfor port in (-1,6,4294967296,-4294967296):\n for operation in (b.motor,b.position):\n  try:\n   if operation == b.motor: operation(port,400)\n   else: operation(port,-90,500)\n  except (OSError,OverflowError): pass\n  else: raise AssertionError('invalid port accepted')\n"));
  assert(motors==61 && positions==62);
  /* This configuration has no arbitrary-precision integers. An unsupported
   * literal fails compilation before an argument guard can execute. */
  assert(bw_python_execute("18446744073709551616\n")<0);
  assert(motors==61 && positions==62);
  assert(!bw_python_execute("import brickwright as b\nfor value in (-1111,1111,4294967296,-4294967296):\n try: b.motor(0,value)\n except (OSError,OverflowError): pass\n else: raise AssertionError('invalid speed accepted')\nfor value in (-36001,36001,4294967296,-4294967296):\n try: b.position(1,value,500)\n except (OSError,OverflowError): pass\n else: raise AssertionError('invalid degrees accepted')\nfor value in (-1,0,1111,4294967296,-4294967296):\n try: b.position(1,90,value)\n except (OSError,OverflowError): pass\n else: raise AssertionError('invalid velocity accepted')\nb.motor(0,-1110)\nb.motor(0,1110)\nb.position(1,-36000,1)\nb.position(1,36000,1110)\n"));
  assert(speed==1110 && delta==36000);
  assert(!bw_python_execute("print('x' * 10000)\n"));
  assert(g_bw_python_output.length==BW_PYTHON_OUTPUT_CAPACITY && g_bw_python_output.truncated);
  assert(!bw_python_execute("assert 1+1 == 2\n"));
  assert(g_bw_python_output.length==0 && !g_bw_python_output.truncated);
  polls=0;assert(bw_python_execute("while True:\n pass\n")==-ETIMEDOUT);
  poll_error=-ECANCELED;assert(bw_python_execute("while True:\n pass\n")==-ECANCELED);poll_error=0;
  polls=0;motor_error=-ENODEV;
  assert(bw_python_execute("import brickwright as b\nb.motor(0,400)\n")==-ENODEV);motor_error=0;
  assert(bw_python_execute("raise OSError(5)\n")==-EIO);
  assert(bw_python_execute("raise OSError('invalid')\n")==-EINVAL);
  assert(bw_python_execute("raise OSError(-5)\n")==-EINVAL);
  assert(!bw_python_execute("assert 2+2 == 4\n"));
  polls=0;assert(bw_python_execute("this is invalid syntax !")<0);
  puts("embedded MicroPython cancellation and syntax failure: PASS");return 0;
}
