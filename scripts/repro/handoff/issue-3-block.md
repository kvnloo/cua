# Issue 3

Blocked. The walker trace was not captured.

Missing machines: macOS for an AX walker count, and Windows for a UIA walker count.

Missing on this Linux host: an exact-head AT-SPI walker log for the six predicate cases. `scripts/repro/handoff/linux-host-probe.txt` records `cua-driver 0.28.2`, a daemon that is not running, no top-level windows, and an AT-SPI bus with no window to walk. The pinned head is `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Not produced: walker counts, capture-versus-traversal latency, or a promotion verdict.
Not invented: a claim that any platform honored `include_accessibility_tree`.

The call site that was locked, and is not that trace, is `observe(input.pid, input.window_id, false, true)` after `include_screenshot` in `expectation.rs`, checked by `test_verify_elapsed_order.py`.
