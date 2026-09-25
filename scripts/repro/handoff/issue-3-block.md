# Issue 3

Blocked. Missing trace on this Linux host: an instrumented accessibility walker count for `get_window_state`.

Asked for: exact-head logs and native traces for the six predicate cases, with the walker count, plus a verdict and platform coverage.

Not produced: walker counts, capture-versus-traversal latency, or a verdict.
Not invented: a claim that any platform honored `include_accessibility_tree`.

The call site that was locked, and is not that trace, is `observe(input.pid, input.window_id, false, true)` after `include_screenshot` in `expectation.rs`, checked by `test_verify_elapsed_order.py`.
