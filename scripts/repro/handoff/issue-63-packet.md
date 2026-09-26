# Issue 63

Verdict withheld. The promotion packet requires a native walker trace from this host, and that trace was not recorded here.

Upstream pin: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Fork evidence that contains the call-site lock: `92b5035ea08b2126f947db0dfd8ecf829013d7b4` on `test/rfc-fast-path-one-candidate-20260925`.

Cited macOS Calculator comment, not a walk this Linux host ran: head `fb7841be7c9d2ef666a5dd87be6ca78e2de5d254`. Element plus screenshot went from 2 AX walks to 1. Window-only plus screenshot went from 1 to 0. The element control without a screenshot stayed 1 to 1. The screenshot size in that comment is 460×816.

Test: `libs/cua-driver/examples/jev-use/python/tests/test_verify_elapsed_order.py`.

Source: `libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs`. `elapsed_ms` is assigned at line 310. The optional screenshot path then calls `observe(input.pid, input.window_id, false, true)` at line 329. The second flag is the screenshot. The third argument is `false`, so this call does not ask for elements.

Trace: none. Missing machines: macOS for an AX walker count, and Windows for a UIA walker count. Missing on this Linux host: an exact-head AT-SPI walker log.

Limitation: the call site and the cited comment are not a walker log from this host.

The upstream pull request description was not updated from this branch.
