# CUA current-upstream baseline preflight

Downstream Pomerado experiment support for [#161](https://github.com/kvnloo/cua/issues/161), the existing [draft #162](https://github.com/kvnloo/cua/pull/162), the [whole-task owner #10](https://github.com/kvnloo/cua/issues/10), and sole [promotion queue #74](https://github.com/kvnloo/cua/issues/74).

## Motivation

- Upstream [#4935](https://github.com/trycua/cua/pull/4935) merged the run_steps name (run_actions survives only as a hidden legacy alias).
- Upstream [#4936](https://github.com/trycua/cua/pull/4936) enables sandboxed run_script by default, subject to an operator-only opt-out.
- The older Python jev-use caller invokes individual Driver tools. A purported Pomerado speedup against *only* that caller could be a stale/strawman result. Match Pomerado against the **semantically eligible current batch/script route**, keeping the same starting state, user authorization, effects and independent outcome oracle.
- At the time of this audit, kvnloo/cua main is at 6e74bfadd82790312f0ab46ae7ed48027f8aca56 (October 8), preceding both October 10 upstream merges. This branch is downstream-only; an actual A/B still needs one pinned current upstream source-built Driver or released binary and independent verification. Do not silently compare different binaries, default configurations or permission policies.
- [Upstream #5897](https://github.com/trycua/cua/issues/5897) also reports Windows run_steps permission refusal on one release/config; a tool name in documentation does not establish that the selected runtime offers an executable path.

## Receipt fields and admission

For a REAL row in the existing Pomerado JSONL schema, additionally record:

- baseline_tool: exactly run_steps or run_script, on **both** A and B records
- In A records: advertised_driver_tools from the actual tools/list, observed_driver_tools from actual Driver invocation, and a unique nonempty redacted baseline_trace_evidence pointer
- For run_script A records: run_script_operator_enabled = true, supported by operator/config evidence
- Keep baseline_tool and driver_sha constant within one workflow/variant cohort. Put other baseline strategies in separate cohorts.
- Fail closed on old run_actions alias, unsupported or unobserved route, fallback, mixed binary, repeated trace identifier, script opt-out, synthetic evidence, or a driver_sha not equal to the independently confirmed build.

Run the existing Pomerado analyze_receipts.py and verify_plan_coverage.py checks in addition to the new baseline_gate.py. Example after independently confirming an actual current Driver SHA:

    python docs/experiments/pomerado-cua-2026-10-25/baseline_gate.py receipts.jsonl --expected-driver-sha "$ACTUAL_DRIVER_SHA"

Unit test command:

    python -m unittest discover -s docs/experiments/pomerado-cua-2026-10-25 -p 'test_baseline_gate.py' -v

## Claim boundary

This is a **receipt-shape fairness gate**, not a working batch/script runner, a mint, or a performance benchmark. The receipt rows and tool names can be fabricated; independently inspect actual Driver trace, exact source/binary provenance, permissions, Pomerado's separate consent, resets, and fixture-owned oracle/journal before accepting any REAL label. Do not claim a speedup from the 14 local UNIT tests (Python 3.13.5, 14/14 pass). No paid API call, CUA Driver E2E or remote Avrea/Boat run was performed by this change.

No new product dependency, Driver API, cache or action authority. Credit remains with the original CUA contributors and Pomerado AI, Inc.
