/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#ifndef BRICKWRIGHT_PROGRAM_SERVICE_H
#define BRICKWRIGHT_PROGRAM_SERVICE_H
#include "upload.h"
int bw_program_service_init(void);
int bw_program_service_stop(void);
int bw_program_service_request(uint32_t owner,const uint8_t *,size_t,uint8_t reply[20]);
int bw_program_service_poll(void);
int bw_program_service_motor(unsigned port,int32_t speed);
int bw_program_service_position(unsigned port,int32_t degrees,int32_t speed);
int bw_program_service_done(unsigned port);
int bw_program_service_sensor(unsigned predicate,int32_t *value);
int bw_python_execute(const char *source);
#endif
