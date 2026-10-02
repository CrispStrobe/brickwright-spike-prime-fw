/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Simulation-only program ABI. No executable uploads or physical I/O. */
#ifndef BW_ARENA_PROGRAM_H
#define BW_ARENA_PROGRAM_H
#define BW_PROGRAM_MAX 256u
#define BW_PROGRAM_SIGNATURE 0x42575047u
struct program_state {
    uint32_t signature, version, sequence, count, status, pc, error;
    int32_t instructions[BW_PROGRAM_MAX][4];
};
#ifndef PROGRAM
#define PROGRAM ((volatile struct program_state *)0x20041000u)
#endif
static uint32_t program_seq, program_started, wait_until;
static int32_t demands[2], position_target;
static int32_t moving_port; /* reset_handler initializes this to -1 in RAM. */
static int predicate(int32_t sensor, int32_t threshold) {
    switch(sensor) {
    case 1: return distance >= 0 && distance < threshold;
    case 2: return distance >= 0 && distance > threshold;
    case 3: return pressed == threshold;
    case 4: return color == threshold;
    case 5: return reflection < threshold;
    case 6: return reflection > threshold;
    default: return 0;
    }
}
static void program_fault(uint32_t error) {
    PROGRAM->error = error; PROGRAM->status = 3;
    demands[0] = demands[1] = 0; moving_port = -1;
}
static void program_tick(volatile struct arena_state *state) {
    volatile struct program_state *p = PROGRAM;
    uint32_t seq = p->sequence;
    if(seq & 1u) { demands[0] = demands[1] = 0; return; }
    if(seq && seq != program_seq) {
        if(p->signature != BW_PROGRAM_SIGNATURE || p->version != 1 || !p->count || p->count > BW_PROGRAM_MAX) {
            program_fault(1); return;
        }
        program_seq = seq; p->status = 1; p->pc = p->error = 0;
        program_started = state->ticks; wait_until = 0;
        demands[0] = demands[1] = 0; moving_port = -1;
    }
    if(p->status != 1) return;
    if(state->ticks - program_started >= 120000u) { program_fault(2); return; }
    if(wait_until && state->ticks < wait_until) return;
    wait_until = 0;
    if(moving_port >= 0) {
        int32_t position = moving_port ? state->position_b : state->position_a;
        if((demands[moving_port] > 0 && position < position_target) ||
           (demands[moving_port] < 0 && position > position_target)) return;
        demands[moving_port] = 0; moving_port = -1;
    }
    /* Bounded work per tick: forever loops cannot monopolize the timer. */
    for(uint32_t work = 0; work < 32; ++work) {
        if(p->pc >= p->count) { program_fault(3); return; }
        int32_t op = p->instructions[p->pc][0], a = p->instructions[p->pc][1];
        int32_t b = p->instructions[p->pc][2], c = p->instructions[p->pc][3];
        switch(op) {
        case 0:
            if(a || b || c) { program_fault(4); return; }
            demands[0] = demands[1] = 0;
            /* Finish only once stopping has completed. */
            if(!state->speed_a && !state->speed_b) p->status = 2;
            return;
        case 1:
            if(a < 0 || a > 1 || b < -1110 || b > 1110 || c) { program_fault(4); return; }
            demands[a] = b; p->pc++; break;
        case 2:
            if(a < 0 || a > 120000 || b || c) { program_fault(4); return; }
            p->pc++; wait_until = state->ticks + (uint32_t)a;
            return;
        case 3:
        case 5:
            if(a < 1 || a > 6 || b < 0 || b > (a <= 2 ? 65535 : (a == 3 ? 1 : (a == 4 ? 255 : 100))) ||
               (op == 3 ? c != 0 : (c < 0 || (uint32_t)c >= p->count))) { program_fault(4); return; }
            if(op == 3 && !predicate(a, b)) return;
            p->pc = op == 5 && predicate(a, b) ? (uint32_t)c : p->pc + 1;
            break;
        case 4:
            if(a < 0 || (uint32_t)a >= p->count || b || c) { program_fault(4); return; }
            p->pc = (uint32_t)a; break;
        case 6:
            if(a < 0 || a > 1 || b < -36000 || b > 36000 || c <= 0 || c > 1110) { program_fault(4); return; }
            p->pc++;
            if(!b) break;
            moving_port = a;
            position_target = (a ? state->position_b : state->position_a) + b * 1000;
            demands[a] = b < 0 ? -c : c;
            return;
        default: program_fault(4); return;
        }
    }
}
#endif
