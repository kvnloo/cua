# Issue 3

Blocked. The deliverable asked for exact-head logs under `scripts/repro/` and platform coverage.

The macOS counts are cited, not re-run, in `scripts/repro/handoff/issue-3-macos-trace.md`. That citation is the comment https://github.com/trycua/cua/pull/4164#issuecomment-5840994846. It is not a log file produced on this host.

Missing machine: Windows, for a UIA walker count.

Missing on this Linux host: an exact-head AT-SPI walker log. `scripts/repro/handoff/linux-host-probe.txt` records `cua-driver 0.28.2`, a daemon that is not running, no top-level windows, and an AT-SPI bus with no window to walk. The issues pin `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

No promotion verdict is applied. The call-site lock in `test_verify_elapsed_order.py` is not the walker trace.
