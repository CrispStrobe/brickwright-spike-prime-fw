/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "py/runtime.h"
#include "py/builtin.h"
#include "py/compile.h"
#include "py/gc.h"
#include "py/stackctrl.h"
#include "port/micropython_embed.h"
#include "../service.h"
#include "../python_output.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
mp_import_stat_t mp_import_stat(const char *path) { (void)path;return MP_IMPORT_STAT_NO_EXIST; }
mp_lexer_t *mp_lexer_new_from_file(qstr path) { (void)path;mp_raise_OSError(ENOENT); }
static void check(int rc) { if(rc<0)mp_raise_OSError(-rc); }
void bw_python_poll(void) { check(bw_program_service_poll()); }
static uint64_t now_ms(void) {
  struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);
  return (uint64_t)ts.tv_sec*1000+(uint64_t)ts.tv_nsec/1000000;
}
static void pause_ms(void) { struct timespec ts={0,1000000};nanosleep(&ts,NULL);bw_python_poll(); }
static int32_t bounded_integer(mp_obj_t value,int32_t low,int32_t high) {
  mp_int_t integer=mp_obj_get_int(value);
  if(integer<low || integer>high)mp_raise_OSError(EINVAL);
  return (int32_t)integer;
}
static unsigned motor_port(mp_obj_t value) {
  return (unsigned)bounded_integer(value,0,BW_PROGRAM_PORT_COUNT-1);
}
static mp_obj_t motor(mp_obj_t port,mp_obj_t speed) {
  check(bw_program_service_motor(motor_port(port),bounded_integer(speed,-1110,1110)));return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(motor_obj,motor);
static mp_obj_t position(size_t n,const mp_obj_t *args) {
  unsigned port=motor_port(args[0]);int rc;
  (void)n;check(bw_program_service_position(port,bounded_integer(args[1],-36000,36000),bounded_integer(args[2],1,1110)));
  do {pause_ms();rc=bw_program_service_done(port);check(rc);} while(!rc);
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(position_obj,3,3,position);
static mp_obj_t sleep_ms(mp_obj_t duration) {
  mp_int_t ms=mp_obj_get_int(duration);uint64_t start;
  if(ms<0 || ms>120000)mp_raise_ValueError(MP_ERROR_TEXT("duration must be 0..120000 ms"));
  start=now_ms();do {pause_ms();}while(now_ms()-start<(uint64_t)ms);
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(sleep_obj,sleep_ms);
static mp_obj_t sensor(size_t n,const mp_obj_t *args) {
  unsigned selector;int32_t value;
  selector=(unsigned)bounded_integer(args[0],1,n==1 ? 6 : 2);
  if(n==2)selector=0x100+(motor_port(args[1])<<3)+selector;
  check(bw_program_service_sensor(selector,&value));return mp_obj_new_int(value);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(sensor_obj,1,2,sensor);
static const mp_rom_map_elem_t globals[] = {
  {MP_ROM_QSTR(MP_QSTR___name__),MP_ROM_QSTR(MP_QSTR_brickwright)},
  {MP_ROM_QSTR(MP_QSTR_motor),MP_ROM_PTR(&motor_obj)},
  {MP_ROM_QSTR(MP_QSTR_position),MP_ROM_PTR(&position_obj)},
  {MP_ROM_QSTR(MP_QSTR_sleep_ms),MP_ROM_PTR(&sleep_obj)},
  {MP_ROM_QSTR(MP_QSTR_sensor),MP_ROM_PTR(&sensor_obj)},
  {MP_ROM_QSTR(MP_QSTR_A),MP_ROM_INT(0)}, {MP_ROM_QSTR(MP_QSTR_B),MP_ROM_INT(1)},
  {MP_ROM_QSTR(MP_QSTR_C),MP_ROM_INT(2)}, {MP_ROM_QSTR(MP_QSTR_D),MP_ROM_INT(3)},
  {MP_ROM_QSTR(MP_QSTR_E),MP_ROM_INT(4)}, {MP_ROM_QSTR(MP_QSTR_F),MP_ROM_INT(5)},
};
static MP_DEFINE_CONST_DICT(globals_dict,globals);
const mp_obj_module_t brickwright_module={.base={&mp_type_module},.globals=(mp_obj_dict_t *)&globals_dict};
MP_REGISTER_MODULE(MP_QSTR_brickwright,brickwright_module);
int bw_python_execute(const char *source) {
  volatile int rc=0; volatile uintptr_t top=0; nlr_buf_t nlr;
  void *heap=malloc(32768);if(!heap)return -ENOMEM;
  bw_python_output_reset();
  mp_embed_init(heap,32768,(void *)&top);mp_stack_set_limit(12000);
  if(nlr_push(&nlr)==0) {
    mp_lexer_t *lexer=mp_lexer_new_from_str_len(MP_QSTR__lt_stdin_gt_,source,strlen(source),0);
    qstr name=lexer->source_name;
    mp_parse_tree_t tree=mp_parse(lexer,MP_PARSE_FILE_INPUT);
    mp_obj_t fn=mp_compile(&tree,name,true);mp_call_function_0(fn);nlr_pop();
  } else {
    mp_obj_t exception=MP_OBJ_FROM_PTR(nlr.ret_val);
    mp_int_t error;
    rc=-EINVAL;
    /* Keep device failures, cancellation and deadlines visible to STATUS.
     * The runtime error field is signed 16-bit; out-of-range OSError
     * values, syntax/runtime errors and malformed values remain EINVAL. */
    if(mp_obj_exception_match(exception,MP_OBJ_FROM_PTR(&mp_type_OSError)) &&
       mp_obj_get_int_maybe(mp_obj_exception_get_value(exception),&error) &&
       error>0 && error<=INT16_MAX)rc=-(int)error;
    mp_obj_print_exception(&mp_plat_print,exception);
  }
  mp_embed_deinit();free(heap);return rc;
}
