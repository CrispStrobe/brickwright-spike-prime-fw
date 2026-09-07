# Permissive SPIKE comparison projects

This note records what can be reused from two permissively licensed projects
without confusing an API simulator with a wire-protocol or radio simulator.

## `MGross21/spikeble`

- Repository inspected: <https://github.com/MGross21/spikeble>
- Commit inspected: `5139853d922c26cfb15bc4ed003ae65de02a7eaf`
- Declared licence: Apache-2.0.
- Useful material: independently implemented SPIKE 3 COBS/XOR framing,
  request/response message models, BLE transport sequencing, file upload,
  chunk transfer, and program-flow requests.
- Important finding: stored program execution uses `StartFileUploadRequest`,
  `TransferChunkRequest`, and `ProgramFlowRequest`. That supports the standard
  upload/run route; it does not disprove a LEGO-firmware tunnel receiver used
  for live commands.
- Reuse decision: use it as a protocol oracle and consider selectively porting
  attributable Apache-2.0 message definitions after line-level provenance
  review. Keep Brickwright's independent codec and shared fixtures as the
  conformance boundary.

## `rundhall/ESP-LEGO-SPIKE-Simulator`

- Repository inspected:
  <https://github.com/rundhall/ESP-LEGO-SPIKE-Simulator>
- Commit inspected: `dc83b895ff2aac5cf2fe576d0ba98426fea60827`
- Declared licence: MIT.
- Useful material: SPIKE 2-era Python API behaviour, device state models, and
  examples that can inform compatibility tests.
- Limitation: it is an ESP/desktop MicroPython API simulator, not a CC2564C,
  HCI, RFCOMM, Scratch Link, SPIKE 3 GATT, or byte-level protocol emulator.
- Reuse decision: mine test scenarios and API semantics selectively. Do not
  adopt it as the Brickwright transport architecture or add its Python runtime
  as a requirement for the bounded virtual hub.

## Architecture consequence

Brickwright will emulate at the application seams: a virtual FD02 GATT
peripheral for modern firmware and a virtual Scratch Link/RFCOMM session for
Classic firmware, both backed by the neutral `HubState`. It will not execute
the TI service pack, emulate TI silicon, or claim hardware validation from the
simulator. The physical CC2564C remains dependent on a separately installed,
hash-allowlisted, unmodified TI service pack.
