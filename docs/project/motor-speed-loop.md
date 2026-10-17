# Motor speed loop and ISET timer gating

Simulation-only firmware; see [SAFETY.md](https://github.com/CrispStrobe/brickwright-spike-prime-fw/blob/main/SAFETY.md).
Neither change has been run on a physical hub.

## Why the speed loop changed

The Robot Lab ran the protected NuttX firmware in Renode, in lockstep with a
physics DC-motor model of the SPIKE medium motor (Brickwright Lite branch
`lane/simlab-next3-20261018`, `docs/ROBOT-LAB-SPIKE-EMULATION.md` §7).
Commanded to 300 °/s for 2 s, the motors settled at about 290 °/s and turned
563.5°, against 610.6° on the Scratch route. The old loop in
`apps/hubprogram/motor.c` computed

    duty = ref·10000/1110 + 3·(ref − w) + (Σ (ref − w)·dt[ms]) / 1000

The integral term was about 10 duty units per (°/s·s), so the time constant
was about 10 s and the loop behaved as P-only (Kp = 3). The 2000 °/s² ramp
also cost 22.5° at every start.

## Plant and derivation

The gains come from the real motor. They are not fitted to any simulator,
and the arena's controller tuning stays separate.

| Quantity | Value | Source |
|---|---|---|
| No-load speed w0 at 7.2 V | 1055 °/s (18.41 rad/s) | DC fit to measured data (Philo, motorcomp) |
| Stall torque Ts at 7.2 V | 0.104 N·m | same fit |
| Reflected inertia J | 3.0e-4 kg·m² | Pybricks `model_technic_m_angular` (`d_torque_d_acceleration` = 16163, scaled per `observer.c`) |
| Coulomb friction | 0.018 N·m (no-load current 0.1 A at R = 10.6 Ω) / 0.021 N·m (Pybricks `torque_friction`) | both sources |
| Mechanical time constant τ | J·w0/Ts = 53 ms | derived |
| PWM | TIM1/3/4, PSC 7, ARR 1000 → 12 kHz; CCR = duty/10 → full scale 1000/1001 | `stm32_legoport_pwm.c` |
| Duty → speed gain K | 1055/10010 = 0.1054 (°/s)/duty | derived |
| Control period T | 10 ms (service worker) | `service.c` |
| Speed measurement | backward difference of integer-degree LUMP positions over 10 ms → 100 °/s quantum; effective delay Td ≈ 20 ms | `device.c` |

Loop structure (`bw_motor_step`):

1. The commanded speed is rate-limited to reach the rated 1110 °/s in 100 ms
   (11 100 °/s²) and to stop from it in 150 ms (7 400 °/s²). Then it goes
   through a first-order reference model wm with τm = 35 ms.
2. The feed-forward is `(wm + τ·dwm/dt)/K` plus half of the Coulomb friction
   (700 duty). The friction term fades in over the first 50 °/s.
3. A PI acts on wm − w. It uses lambda (IMC) tuning for `K·e^(−Td·s)/(τs + 1)`:
   Kp = τ/(K(λ + Td)). With λ = 64 ms, Kp = 6 duty per °/s, so the 100 °/s
   quantum gives about 600 duty of jitter (≈ 5 % of full scale). Ti is λ = 64 ms
   rather than τ, giving Ki = 94 duty per degree. This keeps a load four times
   the rotor inertia from ringing.
4. The integral is held as an angle (model angle − encoder angle, in mdeg).
   It is exact over any number of ticks, so there is no steady-state speed
   error and two wheels commanded alike turn alike. The feedback compares
   against the model from one tick earlier, which matches the measurement
   delay, so the start transient does not wind up the integral.
5. Anti-windup: the integral does not advance while the output is saturated
   in the direction that advance would push it. It is also bounded so that
   its own term never exceeds full scale (±106°).

Only half of the friction is fed forward because the measured value varies
by unit, wear and temperature, and over-compensation causes overshoot. The
integral supplies the remainder.

## Host evidence

`tests/hubprogram/speed_loop_test.c` (part of `tools/check_hubprogram.sh`)
closes the loop around `motor.c` with the DC plant above. It integrates at
0.1 ms, quantizes the encoder to integer degrees every 10 ms, and computes the
same backward-difference speed as `device.c`. Measured with the current gains:

| Case | Steady error | Overshoot (20 ms mean) | Ripple | 90 % rise |
|---|---|---|---|---|
| 300 °/s, 7.2 V | +0.04 % | 13 % | 3.6 % | 0.07 s |
| −300 °/s, 7.2 V | +0.03 % | 12 % | 3.6 % | 0.07 s |
| 800 °/s, 7.2 V | −0.01 % | 4 % | 1.6 % | 0.11 s |
| 300 °/s, 8.3 V battery | −0.07 % | 20 % | 4.3 % | 0.06 s |
| 300 °/s, friction 0.018 N·m | −0.01 % | 3 % | 4.7 % | 0.17 s |
| 100 °/s, friction 0.018 N·m | +0.05 % | 6 % | 14 % | 0.33 s |
| 300 °/s, 2× inertia, friction + 0.02 N·m load | +0.03 % | 3 % | 2.3 % | 0.28 s |
| 300 °/s, 4× inertia, reports 20 ms late | −0.33 % | 21 % | 4.7 % | 0.22 s |

The bare motor turns 598° in 2 s at 300 °/s, against an ideal 600°. If the
shaft is held stalled for 1 s at 600 °/s, the duty saturates and the
integral stops advancing. After release, speed peaks at 706 °/s and settles
to 600 °/s.

## TIM5 (issue #54)

TIM5 CH1 on PA0 is the MP2639A charger's ISET PWM, inherited from Pybricks. It
runs at 96 MHz / 1000 = 96 kHz, and its duty sets the charge current limit.
The firmware used to start the counter at boot and leave it running, even
at duty 0 with the charger MODE pin disabled. The counter now runs only while
the duty is non-zero (USB present). At 0 % it is stopped with OC1 forced
inactive. The pin stays low, the same level PWM mode 1 with CCR = 0 produced.
A board with no USB attached, as in the Robot Lab, therefore runs no 96 kHz
timer. The frequency itself is unchanged, because the charger's ISET filter
was designed for it.

The other timers:

| Timer | Use | Rate |
|---|---|---|
| TIM1, TIM3, TIM4 | H-bridge PWM, ports A/B, E/F, C/D | 12 kHz, always counting; pins are GPIO while coasting/braking |
| TIM8 CH4 | CC2564C 32.768 kHz slow clock | free-running; needed only with the Bluetooth controller |
| TIM2 | ADC DMA trigger | 1 kHz |
| TIM6 | DAC sound sample clock | only while sound plays |
| TIM7 | CPU-load sampling (`SCHED_CPULOAD_EXTCLK`) | `CONFIG_SCHED_CPULOAD_TICKSPERSEC` |
| TIM9 | tickless OS timer | — |
| TIM12 CH2 | TLC5955 LED grayscale clock | 96 MHz / 11 ≈ 8.7 MHz (absent from the Renode profile in #54, so apparently not modelled as a ticking timer there) |
