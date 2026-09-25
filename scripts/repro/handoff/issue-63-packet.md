# Issue 63

Verdict: KEEP DRAFT.

Upstream pin: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Fork evidence that contains the call-site lock: `92b5035ea08b2126f947db0dfd8ecf829013d7b4` on `test/rfc-fast-path-one-candidate-20260925`.

Test: `libs/cua-driver/examples/jev-use/python/tests/test_verify_elapsed_order.py`.

Source: `libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs`. `elapsed_ms` is assigned at line 310. The optional screenshot path then calls `observe(input.pid, input.window_id, false, true)` at line 329. The second flag is the screenshot. The third argument is `false`, so this call does not ask for elements.

Trace: none. The native walker counter was not captured on this Linux host. AX, UIA, and AT-SPI idle counts were not measured.

Limitation: the call site is not proof that those walkers stayed idle.

The upstream pull request description was not updated. `promotion-dag.json` marks 4164 `WAITING ON DOWNSTREAM EXPERIMENT`. This packet does not promote it.
