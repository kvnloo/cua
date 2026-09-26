# kvnloo/cua#22 — what `verify_state.elapsed_ms` covers

In `libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs`, `elapsed_ms` is assigned from `started.elapsed()` after the predicate sample loop and before the optional `include_screenshot` observation.

Recommendation: keep the field as verification-loop time. Do not move the boundary. Screenshot work stays outside that number so a timing report cannot hide it. No semantic change in this commit. The order is locked by `test_verify_elapsed_order.py`.
