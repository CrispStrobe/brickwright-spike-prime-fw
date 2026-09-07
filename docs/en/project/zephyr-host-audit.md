# Zephyr Bluetooth host source audit

## Decision

C4 uses the Zephyr Bluetooth host from release `v4.4.1`, peeled commit
`1f6485eca25431b5ff27ce9a754218c9e559bbbb`. The pin is immutable and the
selected upstream files carry `SPDX-License-Identifier: Apache-2.0`.

The machine-readable selection is `third_party/zephyr-host/manifest.json`.
C4.2 imports only that selection and its internal headers into
`third_party/zephyr-host/upstream`, with a SHA-256 lock file. The smallest
additional compatibility definitions are found by compile-driven dependency
tracing. Each subsequently added upstream file must be added to the manifest
and pass the source policy.

## Why this is viable, but not a drop-in library

Zephyr 4.4.1 still has experimental BR/EDR support. Enabling
`CONFIG_BT_CLASSIC` selects the shared connection, SMP, and dynamic L2CAP
machinery; `CONFIG_BT_RFCOMM` adds RFCOMM. Its Classic build graph supplies
BR/EDR GAP, BR connections, BR L2CAP, SDP, SSP, key storage, RFCOMM, and a SCO
translation unit. This covers the legacy SPP server needed by the Classic
extension.

The same host core supplies LE advertising, connections, ATT, GATT, SMP, key
storage, and settings for the modern FD02 service. Both transports share HCI,
buffers, connections, crypto, and persistent identity/key machinery.

It is not portable merely by compiling the listed `.c` files. The sources use
Zephyr `net_buf`, kernel objects, atomics, intrusive lists, iterable sections,
work queues/timers, settings, entropy, logging, device/HCI APIs, generated
configuration, and PSA Crypto. C4.2 therefore provides a deliberately narrow
NuttX compatibility layer instead of importing the Zephyr kernel.

## Selected boundary

The manifest selects 33 host/common/crypto translation units plus the H:4 UART
driver as the transport design source. H:4 framing is reused, but its Zephyr
device-tree/UART/thread plumbing is replaced by the existing NuttX UART driver.
The host receives and sends ordinary HCI command, event, and ACL packets through
a small driver interface. ISO is disabled.

The minimum target feature configuration is:

- host HCI with an external controller;
- broadcaster, observer, peripheral, and central GAP roles;
- LE connections, ATT, GATT server, SMP, Secure Connections, privacy, settings;
- Classic BR/EDR, BR L2CAP, SDP, SSP, RFCOMM;
- PSA Crypto backed only by an Apache-2.0 Mbed TLS pin;
- no Zephyr controller, Mesh, LE Audio, ISO, media/telephony profiles, shell, or
  monitor.

`sco.c` remains in the source set because Zephyr's current Classic CMake graph
compiles it unconditionally. SCO data paths stay unused. Removing it is allowed
only after the compile harness proves that doing so does not leave Classic host
references unresolved.

## Licence audit

The following were checked at the pinned commit:

- every selected `.c` file and required Zephyr Bluetooth public header declares
  Apache-2.0;
- Zephyr's root licence is Apache-2.0;
- no BTstack, TI payload, Zephyr controller, or media codec is selected;
- the host crypto implementation calls PSA Crypto; it does not make the crypto
  provider disappear from the dependency graph.

The crypto provider is intentionally a fail-closed open item. C4.2 must pin
Mbed TLS under Apache-2.0 before enabling SMP. TinyCrypt and any provider outside
the project's MIT/Apache-only rule are forbidden.

Apache-2.0 compatibility here is a source-policy result, not a claim that the
Bluetooth implementation is qualified or that use of Bluetooth trademarks is
licensed. Those questions remain C7.4.

## TI controller boundary

The selected Zephyr code is host software. It neither replaces nor reconstructs
the CC2564C service pack. On real SPIKE hardware, the controller still needs an
unmodified, separately installed, allowlisted TI service pack loaded as vendor HCI
commands. No TI bytes enter this source set or host-side simulation.

Zephyr's H:4 driver does not implement TI eHCILL. C5.2 remains a separate
NuttX-side power-management transport extension. C4 host tests use plain H:4 and
a virtual controller, so passing them is not evidence of CC2564C hardware
operation.

## Reproduction

```sh
git ls-remote https://github.com/zephyrproject-rtos/zephyr.git \
  'refs/tags/v4.4.1*'
git clone --depth 1 --branch v4.4.1 --filter=blob:none --sparse \
  https://github.com/zephyrproject-rtos/zephyr.git zephyr-4.4.1
git -C zephyr-4.4.1 rev-parse HEAD
git -C zephyr-4.4.1 grep 'SPDX-License-Identifier:' -- \
  subsys/bluetooth drivers/bluetooth/hci/h4.c include/zephyr/bluetooth
```

Expected peeled commit: `1f6485eca25431b5ff27ce9a754218c9e559bbbb`.

## C4.2 compile order

1. Import the pinned files with preserved notices and an automated upstream hash
   inventory. (Complete.)
2. Provide configuration and compiler-utility shims, then lists and atomics.
3. Implement `net_buf` pools and queues with allocation-failure tests.
4. Implement mutexes, semaphores, threads, work, delayed work, and timers.
5. Add logging, entropy, PSA/Mbed TLS, and persistent settings adapters.
6. Adapt H:4 to the NuttX UART seam without TI-specific behavior.
7. Compile one layer at a time and record every expanded dependency in the
   manifest rather than silently copying broader Zephyr subsystems.

The buffer boundary is now compiled both as host executables and as Cortex-M4
objects against pinned NuttX `a67efb31cf4f236e456882589b91862f04594528`.
That NuttX revision emits pre-existing `stdatomic.h` macro-redefinition warnings
with GCC 13.2, so the cross gate does not promote dependency-header warnings to
errors. Project compatibility code is still built with `-Wall -Wextra`, and the
host behavioral tests retain `-Werror`.
