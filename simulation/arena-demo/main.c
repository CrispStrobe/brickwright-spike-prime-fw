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
static int32_t distance, pressed, load_a, load_b;
static uint32_t input_seq;
static int32_t approach(int32_t value, int32_t target) {
    int32_t rate = (target == 0) ? 4 : 2;
    if(value < target) return target - value < rate ? target : value + rate;
    if(value > target) return value - target < rate ? target : value - rate;
    return value;
}
void systick_handler(void) {
    volatile struct arena_state *state = MAILBOX;
    state->output_seq++;
    __asm volatile("dmb" ::: "memory");
    uint32_t seq = state->input_seq;
    if(!(seq & 1u) && seq != input_seq) {
        int32_t next_distance = state->distance, next_pressed = state->pressed;
        int32_t next_a = state->load_a, next_b = state->load_b;
        __asm volatile("dmb" ::: "memory");
        if(state->input_seq == seq) {
            distance = next_distance; pressed = next_pressed;
            load_a = next_a; load_b = next_b; input_seq = seq;
        }
    }
    int32_t demand = (state->ticks < 3600000u && !pressed && (distance < 0 || distance >= 250)) ? 300 : 0;
    state->demand_a = -demand;
    state->demand_b = demand;
    state->stalled_a = demand && load_a >= 100;
    state->stalled_b = demand && load_b >= 100;
    state->speed_a = state->stalled_a ? 0 : approach(state->speed_a, -demand * (100 - load_a) / 100);
    state->speed_b = state->stalled_b ? 0 : approach(state->speed_b, demand * (100 - load_b) / 100);
    /* One degree/second for one millisecond is one millidegree. */
    state->position_a += state->speed_a;
    state->position_b += state->speed_b;
    state->ticks++;
    __asm volatile("dmb" ::: "memory");
    state->output_seq++;
}
static void halt(void) {for(;;) __asm volatile("wfi");}
extern uint32_t __bss_start__, __bss_end__;
void reset_handler(void) {
    for(uint32_t *p = &__bss_start__; p < &__bss_end__; ++p) *p = 0;
    distance = 1000;
    volatile struct arena_state *state = MAILBOX;
    for(uint32_t i = 0; i < sizeof(*state) / sizeof(uint32_t); ++i) ((volatile uint32_t *)state)[i] = 0;
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
