---
name: codex-review
description: Review plans and changes for design quality, STM32F413 feasibility, and shared hardware-resource conflicts.
---

# Codex design and implementation review

## Select the target

- `plan`: summarize the active plan and extract every peripheral, driver, and
  shared resource before review.
- Issue or pull request: collect its description, discussion, and diff.
- File path: inspect the file and related implementation.
- Other text: treat it as the proposed design.

## Required review dimensions

Review these dimensions independently; approval requires evidence for all that
apply:

1. **Design:** layering, API shape, NuttX conventions, concurrency, error
   handling, edge cases, and compatibility with intended Pybricks behavior.
2. **MCU feasibility:** verify the actual STM32F413 peripheral and register
   features in RM0430. A Kconfig option or successful compilation is not proof
   that the selected peripheral supports the feature.
3. **Resource conflicts:** check timers, DMA streams and channels, IRQ
   priorities, GPIO alternate functions, clocks, and resources reserved for
   future Pybricks-compatible functionality.

Use `docs/en/hardware/dma-irq.md` and `docs/en/hardware/pin-mapping.md` as the
resource ledgers. Compare the Pybricks choice for equivalent functionality and
understand why it was chosen before proposing a different NuttX mechanism.

Require feasibility evidence from a focused simulation or hardware test and
the reference manual. Respect `SAFETY.md`; this public derivative currently
permits simulation, not physical-hardware flashing.

## Result

List blocking findings, concerns, and evidence. For a plan review, update
`~/.claude/.plan-codex-reviewed` only after all three dimensions are acceptable.
Do not update the marker when a blocking item or unresolved feasibility concern
remains. A trivial-plan skip requires explicit user approval.
