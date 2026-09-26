# Issue 35

Regression budget: do not add a CI wall-clock gate.

The checker is `regression_budget.semantic_path_ok`. A semantic success path has zero visual parses and zero model calls. `ci_may_gate_on_milliseconds` returns false.

Sample workflow: call `semantic_path_ok(WorkCounts(...))` from the unit test. A green unit run does not certify a latency change. No CI workflow file was added.

Controlled native benchmarks stay outside this checker. Missing machine: this Linux host, for a pinned driver session (`cua-driver 0.28.2` is installed and the daemon is not running).
