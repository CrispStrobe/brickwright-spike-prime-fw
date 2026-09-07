# Simulation-only safety status

This firmware is a work in progress. It is currently approved only for
instruction-level execution in the Brickwright Renode simulator.

Do not flash or install builds from this repository on a physical LEGO SPIKE
Prime hub. Passing unit tests, CI builds, protocol fixtures, or Renode boot
milestones does not establish electrical or functional safety on real silicon.
The simulator does not validate USB electrical behaviour, battery charging,
power switching, flash-update recovery, motor current and torque limits,
thermal behaviour, RF behaviour, Bluetooth qualification, or all physical
timing and interrupt interactions.

Physical installation remains blocked until maintainers explicitly record all
of the following in `PLAN.md`:

- controlled bring-up on sacrificial hardware with current-limited power;
- verified safe states for every motor and external port across boot, reset,
  crash, disconnect, watchdog, and brownout;
- battery/charger, USB, storage, update, rollback, and recovery testing;
- CC2564C initialization and repeated power-cycle tests using the exact
  redistributed TI service pack;
- Classic and BLE interoperability tests on supported host platforms;
- fault injection and long-duration soak testing;
- a reviewed release decision that removes the simulation-only restriction.

No firmware binary is published by CI or as a GitHub release while this gate is
open. Source availability is not an assertion that a hardware image is safe.
