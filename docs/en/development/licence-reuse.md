# Firmware source reuse

The firmware uses adapted or referenced Pybricks source for motion control,
IMU processing and device protocols. This is acknowledged MIT/BSD-3-Clause
reuse, not a clean-room claim. Original Pybricks, LEGO and David Lechner
notices are retained. See `policy/pybricks-reuse.json` and `licenses/`.

The [broader source-origin review](../../project/source-origin-review.md)
found unresolved inherited Madgwick reference provenance, TI payloads in older
Git commits and older public branch tips without corrected grants. Current
source attribution and successful build/input checks do not clear those issues.

The embedded MicroPython selection and generated headers have a separate
pinned inventory. Its cited integer-width formula is replaced with the
recorded BSD-3-Clause component. CI and builds check these inventories.

Pybricks is not intrinsically required: implementations can be replaced while
preserving their interfaces and behaviour. Removing the present code without
a replacement would lose motor control, sensor discovery and IMU behaviour.
MicroPython LEGO_HUB_NO6 supplies a board/interpreter foundation, but its
default build includes BTstack and a TI initialization payload and does not
supply our full robotics API. A migration requires a separate implementation
and hardware validation.

Hardware images using the fetched TI service pack remain restricted;
simulation images exclude it. Source inventory is not whole-image clearance.


The configured simulation audit and redistribution notices are recorded in
`policy/simulation-firmware-inputs.json` and
`licenses/Simulation-Firmware-NOTICES.txt`. It covers the recorded profile,
source hashes, compiler runtime and linker-selected members; changed inputs
require review. GCC runtime components retain GPLv3 with the explicit GCC
Runtime Library Exception. Default builds use the simulation profile.
