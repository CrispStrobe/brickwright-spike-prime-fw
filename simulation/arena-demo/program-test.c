/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors */
#include <stdint.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint32_t memory[1031];
#define PROGRAM ((volatile struct program_state *)memory)
struct arena_state { uint32_t ticks; int32_t color, reflection, position_a, position_b, speed_a, speed_b; };
static int32_t distance, pressed, color, reflection;
#include "program.h"
static struct arena_state state;
static void load(const int32_t code[][4], uint32_t count) {
    memset(memory, 0, sizeof memory); memset(&state, 0, sizeof state);
    program_seq = program_started = wait_until = 0; moving_port = -1;
    demands[0] = demands[1] = 0; distance = 1000; pressed = 0;
    PROGRAM->signature = BW_PROGRAM_SIGNATURE; PROGRAM->version = 1; PROGRAM->sequence = 2; PROGRAM->count = count;
    memcpy((void *)PROGRAM->instructions, code, count * 16);
}
int main(void) {
    const int32_t timed[][4] = {{1,0,-300,0},{1,1,300,0},{2,10,0,0},{0,0,0,0}};
    load(timed,4); program_tick(&state); assert(demands[0]==-300 && demands[1]==300 && PROGRAM->status==1);
    state.ticks=9; program_tick(&state); assert(demands[1]==300);
    state.ticks=10; state.speed_b=100; program_tick(&state); assert(demands[1]==0 && PROGRAM->status==1);
    state.speed_b=0; program_tick(&state); assert(PROGRAM->status==2);
    const int32_t sensor[][4] = {{1,1,300,0},{3,1,250,0},{1,1,-300,0},{3,3,1,0},{0,0,0,0}};
    load(sensor,5); program_tick(&state); assert(demands[1]==300);
    distance=-1; program_tick(&state); assert(demands[1]==300);
    distance=249; program_tick(&state); assert(demands[1]==-300);
    pressed=1; program_tick(&state); assert(PROGRAM->status==2);
    const int32_t colors[][4] = {{3,4,9,0},{3,5,50,0},{0,0,0,0}};
    load(colors,3); color=10; reflection=100; program_tick(&state); assert(PROGRAM->pc==0);
    color=9; program_tick(&state); assert(PROGRAM->pc==1);
    reflection=49; program_tick(&state); assert(PROGRAM->status==2);
    const int32_t pos[][4] = {{6,1,-90,500},{0,0,0,0}};
    load(pos,2); program_tick(&state); assert(demands[1]==-500);
    state.position_b=-89999; program_tick(&state); assert(PROGRAM->status==1);
    state.position_b=-90000; program_tick(&state); assert(PROGRAM->status==2);
    const int32_t loop[][4] = {{4,0,0,0},{0,0,0,0}};
    load(loop,2); program_tick(&state); assert(PROGRAM->status==1);
    state.ticks=120000; program_tick(&state); assert(PROGRAM->status==3 && PROGRAM->error==2);
    const int32_t bad[][4] = {{4,3,0,0},{0,0,0,0}};
    load(bad,2); program_tick(&state); assert(PROGRAM->status==3 && PROGRAM->error==4 && !demands[0]);
    puts("PASS guest program timing, sensors, positioning, fairness, timeout and invalid branch");
}
