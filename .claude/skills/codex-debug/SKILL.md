---
name: codex-debug
description: Ask Codex to analyze a defect, rank root-cause hypotheses, propose checks, and identify relevant code.
---

# Codex defect analysis

## Select the target

- For an issue number, read the issue, reproduction, observations, and history.
- For free text, treat it as the symptom report.
- For a file path, start at that code and inspect its callers and dependencies.

## Procedure

1. Collect the exact symptom, reproduction rate, logs, configuration, relevant
   source, and recent changes.
2. Identify the likely layer: electrical/hardware, MCU peripheral, NuttX
   kernel, board driver, application, or test infrastructure.
3. Check equivalent Pybricks behavior and implementation when available.
4. Ask Codex for multiple hypotheses ranked by confidence, evidence locations,
   and a minimal discriminating experiment for each.
5. Report conclusions separately from unresolved hypotheses.

Always consider timing, interrupt priority, critical sections, DMA/CPU races,
USB CDC constraints, power state, and differences between isolated and batch
execution. For hardware-dependent claims, check STM32F413 capabilities in
RM0430 rather than inferring support from Kconfig or successful compilation.

The prompt must include the relevant code and logs, MCU and RTOS context, exact
expected and actual behavior, reproduction steps, and a request for ranked,
testable hypotheses with file and line references.
