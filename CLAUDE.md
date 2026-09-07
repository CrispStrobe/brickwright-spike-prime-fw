# Agent instructions

Read `SAFETY.md`, `PLAN.md`, `README.md`, and the contract documents named by
the selected plan task. `PLAN.md` is the unfinished queue; `HISTORY.md` records
accepted milestones.

## Workflow

- Fetch the target, then create a dedicated worktree and feature branch.
- Treat shared primary checkouts and upstream repositories as read-only.
- Preserve unrelated changes and pins. Push each accepted plan task separately.
- Use only approved permissive project/vendor source. Never add BTstack,
  GPL-family, AGPL, noncommercial, or unknown-license code.
- Treat Pybricks/PBIO as behavioral evidence unless an individual MIT file and
  its complete dependency/link closure are approved.
- Treat the TI service pack as opaque, byte-exact, separately licensed data.
  Never alter it, inspect vendor parameters, derive code from it, or relicense it.
- Keep Classic and BLE behind `protocol/hub-contract.schema.json`; preserve port
  generations, bounded resources, and disconnect-safe motor behavior.
- Do not bypass production functions to claim unchanged-image execution.

## Safety and documentation

Do not flash hardware, add actionable flashing instructions, or publish firmware
artifacts. Simulation cannot prove electrical, RF, thermal, charging, motor,
update, or recovery safety.

Maintained prose is English-only. `README.md` contains current capability and
usage; `PLAN.md` contains only pending ordered work and gates; `HISTORY.md`
contains accepted summaries. Contract documents state current normative behavior.
Avoid issue chronology, abandoned approaches, checkpoint diaries, and speculative
status. Preserve imported documentation and legal notices unchanged.

## Verification

Run focused tests plus:

```bash
python3 tools/check_live_docs.py
python3 tools/check_english_only.py
python3 tools/check_source_policy.py
python3 tools/check_safety_policy.py
python3 tools/check_workflow_security.py
python3 tools/test_source_policy.py
python3 tests/test_live_docs_policy.py
python3 tests/test_english_only_policy.py
mkdocs build --strict
```

Firmware changes also require the protected build, resource gate, relevant
host/ARM tests, and the Renode scenario named by `PLAN.md`.
