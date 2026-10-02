/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Simulation-only Cortex-M4 arena demonstration. No physical I/O or radio.
 * All input is a bounded RAM mailbox, all output is computed by guest code.
 */
#include <stdint.h>
#define MAILBOX ((volatile struct arena_state *)0x20040000u)
struct arena_state {
    uint32_t signature, version, ticks, input_seq;
    int32_t distance, color, reflection, ambient, force, pressed, load_a, load_b;
    int32_t position_a, position_b, speed_a, speed_b, stalled_a, stalled_b;
    uint32_t output_seq;
    int32_t demand_a, demand_b;
};
static int32_t distance, pressed, load_a, load_b, color, reflection;
static uint32_t input_seq;
#include "program.h"
static int32_t approach(int32_t value, int32_t target) {
    int32_t abs_value = value < 0 ? -value : value;
    int32_t abs_target = target < 0 ? -target : target;
    int32_t rate = abs_target < abs_value || value * target < 0 ? 4 : 2;
    if(value < target) return target - value < rate ? target : value + rate;
    if(value > target) return value - target < rate ? target : value - rate;
    return value;
}
static int32_t position_speed(int32_t speed, int32_t remaining) {
    if(remaining <= 0) return 0;
    /* v^2/(2*4) millidegrees for 4000 deg/s^2 stopping. Integer square root
     * bounds stopping speed; the final encoder quantization is <= 4 mdeg. */
    uint32_t lo = 0, hi = (uint32_t)(speed < 0 ? -speed : speed);
    while(lo < hi) {
        uint32_t mid = (lo + hi + 1) / 2;
        if(mid * mid <= (uint32_t)remaining * 8u) lo = mid; else hi = mid - 1;
    }
    return speed < 0 ? -(int32_t)lo : (int32_t)lo;
}
void systick_handler(void) {
    volatile struct arena_state *state = MAILBOX;
    state->output_seq++;
    __asm volatile("dmb" ::: "memory");
    uint32_t seq = state->input_seq;
    if(!(seq & 1u) && seq != input_seq) {
        int32_t next_distance = state->distance, next_pressed = state->pressed;
        int32_t next_a = state->load_a, next_b = state->load_b;
        int32_t next_color = state->color, next_reflection = state->reflection;
        __asm volatile("dmb" ::: "memory");
        if(state->input_seq == seq) {
            distance = next_distance; pressed = next_pressed;
            load_a = next_a; load_b = next_b; color = next_color; reflection = next_reflection; input_seq = seq;
        }
    }
    int32_t demand = (state->ticks < 3600000u && !pressed && (distance < 0 || distance >= 250)) ? 300 : 0;
    program_tick(state);
    state->demand_a = program_seq || PROGRAM->sequence ? demands[0] : -demand;
    state->demand_b = program_seq || PROGRAM->sequence ? demands[1] : demand;
    state->stalled_a = state->demand_a && load_a >= 100;
    state->stalled_b = state->demand_b && load_b >= 100;
    int32_t target_a = state->demand_a, target_b = state->demand_b;
    if(moving_port >= 0) {
        int32_t current = moving_port ? state->position_b : state->position_a;
        int32_t remaining = demands[moving_port] > 0 ? position_target - current : current - position_target;
        if(moving_port) target_b = position_speed(target_b, remaining);
        else target_a = position_speed(target_a, remaining);
    }
    state->speed_a = state->stalled_a ? 0 : approach(state->speed_a, target_a * (100 - load_a) / 100);
    state->speed_b = state->stalled_b ? 0 : approach(state->speed_b, target_b * (100 - load_b) / 100);
    /* One degree/second for one millisecond is one millidegree. */
    state->position_a += state->speed_a;
    state->position_b += state->speed_b;
    if(moving_port >= 0) {
        volatile int32_t *position = moving_port ? &state->position_b : &state->position_a;
        volatile int32_t *speed = moving_port ? &state->speed_b : &state->speed_a;
        if((demands[moving_port] > 0 && *position >= position_target) ||
           (demands[moving_port] < 0 && *position <= position_target)) {
            *position = position_target; *speed = 0;
        }
    }
    state->ticks++;
    __asm volatile("dmb" ::: "memory");
    state->output_seq++;
}
static void halt(void) {for(;;) __asm volatile("wfi");}
extern uint32_t __bss_start__, __bss_end__;
void reset_handler(void) {
    for(uint32_t *p = &__bss_start__; p < &__bss_end__; ++p) *p = 0;
    program_seq = program_started = wait_until = 0;
    demands[0] = demands[1] = 0; moving_port = -1;
    distance = 1000; color = 255; reflection = 0;
    volatile struct arena_state *state = MAILBOX;
    for(uint32_t i = 0; i < sizeof(*state) / sizeof(uint32_t); ++i) ((volatile uint32_t *)state)[i] = 0;
    for(uint32_t i = 0; i < sizeof(*PROGRAM) / sizeof(uint32_t); ++i) ((volatile uint32_t *)PROGRAM)[i] = 0;
    PROGRAM->signature = BW_PROGRAM_SIGNATURE; PROGRAM->version = 1;
    state->version = 1;
    state->distance = 1000;
    state->color = 255;
    state->signature = 0x42574152u; /* BWAR, published after initialization. */
    /* Renode's declared timer frequency is 72 MHz; one interrupt per ms. */
    *(volatile uint32_t *)0xe000ed08u = 0x08008000u;
    *(volatile uint32_t *)0xe000e014u = 72000u - 1u;
    *(volatile uint32_t *)0xe000e018u = 0;
    *(volatile uint32_t *)0xe000e010u = 7;
    for(;;) __asm volatile("wfi");
}
__attribute__((section(".vectors"), used))
const uintptr_t vectors[16] = {(uintptr_t)0x20050000u, (uintptr_t)reset_handler,
    (uintptr_t)halt, (uintptr_t)halt, (uintptr_t)halt, (uintptr_t)halt,
    (uintptr_t)halt, 0, 0, 0, 0, (uintptr_t)halt, (uintptr_t)halt, 0,
    (uintptr_t)halt, (uintptr_t)systick_handler};
