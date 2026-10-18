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

Loop structure (`bw_motor_step`), second revision. The first revision
overshot 13 % at 7.2 V and 20 % at 8.3 V.

1. The commanded speed is rate-limited to reach the rated 1110 °/s in 100 ms
   (11 100 °/s²) and to stop from it in 150 ms. Then it goes through a
   first-order reference model wm with τm = 50 ms.
2. Feed-forward `(wm + τ·dwm/dt)/K` makes the unloaded plant follow wm.
   There is no friction feed-forward. Feeding friction forward overdrives a
   motor with less friction, and overshoot is what it buys.
3. **Battery compensation.** The loop computes duty at 7.2 V and scales its
   output by 7200 mV / battery, as the identified motor models do. `device.c`
   reads `/dev/bat0` (`BATIOC_VOLTAGE`) at most every 500 ms while a motor is
   driven. A reading outside 5.5–9 V counts as no reading and the loop
   assumes 7.2 V. That covers a missing gauge and Renode's empty battery ADC
   channel. Without compensation, a full 8.3 V battery overdrives the
   feed-forward by 15 %. That alone is 7 % overshoot.
4. Speed is measured over 2 ticks (20 ms), a 50 °/s quantum instead of
   100 °/s.
5. A PI acts on wm − w with Kp = 8 duty per °/s. Lambda (IMC) tuning gives
   Kp = τ/(K(λ + Td)) with λ + Td = 63 ms. Ki = 55 duty per degree
   (Ti = 145 ms) keeps the loop overdamped up to four times the rotor inertia.
6. **The integral advances only while the reference model is steady**
   (|dwm/dt| ≤ 50 °/s²). A load heavier than the model lags the reference
   while it accelerates. An integral fed that lag has to give the angle back
   later, and that is overshoot. Instead, the lag closes under P and
   feed-forward, which cannot overshoot a first-order plant. The integral then
   removes the persistent part (friction, load, battery) from below.
7. The integral is held as an angle: model angle minus encoder angle, in mdeg.
   It is exact, so there is no steady-state error. Anti-windup: the integral
   freezes while the output is saturated in its direction, and it is bounded
   to full scale (±182°).

The cost is that angle lost while accelerating is not recovered. A 2 s run
at 300 °/s turns 581° on the bare host plant (ideal 600°): 4° from the ramp
and about 15° from the reference model. The first revision turned 598° and
gave the lag back as overshoot.

## Host evidence

`tests/hubprogram/speed_loop_test.c` (run by `tools/check_hubprogram.sh`)
closes the loop around `motor.c`. The plant is the DC model above,
integrated at 0.1 ms, with integer-degree encoder reports every 10 ms that
arrive one or two ticks late. The test passes the plant's voltage to
`bw_motor_supply`, as `device.c` does on a hub.

Overshoot is measured on the 50 ms mean of the true speed, which is what a
robot's travel shows. Steady state is the last 0.5 s of a 2 s run.

The grid covers 300 and 800 °/s × battery 7.2 / 8.3 V × 1, 2, 4× rotor
inertia × friction 0 / 0.018 N·m × reports 1 or 2 ticks late. Every case
asserts overshoot ≤ 3 % and steady error < 1 %. Rise to 90 % is asserted
below the old loop on the same plant: ≤ 0.15 / 0.25 / 0.40 s without
friction (old: 0.22 / 0.31 / 0.51 s), and ≤ 0.8 s with friction (the old loop
never got there; it settled 45 % low).

| 300 °/s, measured | Overshoot | 90 % rise |
|---|---|---|
| 7.2 V or 8.3 V, bare rotor | 2.1–2.8 % | 0.11–0.14 s |
| 2× inertia | 1.3–1.7 % | 0.18–0.20 s |
| 4× inertia | 2.9–3.0 % | 0.31–0.32 s |
| friction 0.018 N·m, 1–4× | 0.6–2.0 % | 0.63–0.67 s |

Other cases:
- −300 °/s behaves the same as +300 °/s.
- 100 °/s with friction: steady error −0.25 %, 90 % rise in 0.87 s.
- 2× inertia with friction plus a 0.02 N·m load: 0.8 % overshoot, 90 % rise in 0.83 s.
- 8.3 V with no battery reading: 7.4 % overshoot. This case is bounded at 10 %, not 3 %.
- Stall for 1 s, then release: the integral freezes while saturated. After release, speed peaks at 632 °/s and settles at 600 °/s.

`control_test.c` covers the battery path: scaling, the 500 ms sampling
period, and the fallback for an absent or zero reading.

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
