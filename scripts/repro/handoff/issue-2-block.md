# Issue 2

Blocked. The outcome A/B was not run.

Missing on this Linux host: an exact-head Driver, a Chromium fixture, and a model session. `scripts/repro/handoff/linux-host-probe.txt` records installed `cua-driver 0.28.2`, exit 1 from `cua-driver status` (`Cua Driver daemon is not running`), and no top-level windows. The issues pin `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. That binary is not this host's installed driver.

Asked for under `scripts/repro/`: raw JSONL receipts, the exact command and environment, a summary table, and a promotion verdict for trycua/cua#4165.

Not produced: those receipts and that verdict.
Not invented: screenshot counts or wall times.

The admission rule that was unit-tested, and is not that A/B, is `lazy_vision.needs_visual_capture`.
