# Issue 35

Regression budget: do not add a CI wall-clock gate.

Layer 1, hard CI counters: `model_calls`, `observation_calls`, `visual_parses`, `actions`, `unnecessary_producer_calls`. The checker is `regression_budget.semantic_path_ok`. A semantic success path has zero visual parses and zero model calls. `metric_layer` returns `hard CI counter` for those names.

`structural_ax_walks(include_elements=False)` is 0. `include_elements=True` is 1. That is the structural counter for a screenshot-only verifier, not a measured walk. The call-site lock is `test_verify_elapsed_order.py`.

`decisions_deleted_when_admitted(2, admitted)` is 1 when `admit_guarded_run` returns a plan. It is none when the run is not admitted.

Layer 2, controlled native benchmarks, stays an evidence artifact. `metric_layer("wall_clock_ms")` returns `evidence artifact`. `ci_may_gate_on_milliseconds` returns false. This Linux host is present. The pinned driver session is not running (`cua-driver 0.28.2` is installed and the daemon is not running), so layer 2 timings were not recorded.

Layer 3, broad trend telemetry, was not added. No CI workflow file was added. A green unit run does not certify a latency change.
