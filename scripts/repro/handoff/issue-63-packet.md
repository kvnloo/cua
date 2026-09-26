# Issue 63

Latest comment: https://github.com/kvnloo/cua/issues/63#issuecomment-5841890086.

Measurement comment: https://github.com/kvnloo/cua/issues/63#issuecomment-5841776432.

That comment records head `fb7841be7c9d2ef666a5dd87be6ca78e2de5d254`. will-bogusz instrumented macOS Calculator, 205 AX nodes, 3 identical runs per row. Element plus screenshot went from 2 AX walks to 1. Window-only plus screenshot went from 1 AX walk to 0. The element control without a screenshot stayed at 1 AX walk. The final screenshot stayed one 460×816 PNG.

This host did not run that walk. Missing machine: Windows, for a UIA walker count. The Linux AT-SPI walker log from this host is still absent.

Fork call-site lock: `92b5035ea08b2126f947db0dfd8ecf829013d7b4`.

Test on this branch: `libs/cua-driver/examples/jev-use/python/tests/test_verify_elapsed_order.py`.

Source: `libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs`. `elapsed_ms` is assigned at line 310. The optional screenshot path then calls `observe(input.pid, input.window_id, false, true)` at line 329.

The measurement comment does not name that test file. The upstream pull request description was not updated from this branch.
