# Issue 63

Verdict: KEEP DRAFT.

SHA: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Test: `libs/cua-driver/examples/jev-use/python/tests/test_verify_elapsed_order.py` locks `observe(input.pid, input.window_id, false, true)` after `include_screenshot`.

Trace: none. The native walker counter was not captured on this Linux host.

Limitation: the call site is not proof that AX, UIA, or AT-SPI stayed idle.

The upstream pull request description was not updated. Status in `promotion-dag.json` is WAITING ON DOWNSTREAM EXPERIMENT.
