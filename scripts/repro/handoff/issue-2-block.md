# Issue 2

Blocked. The outcome A/B was not run.

This Linux host is present. It is not the missing machine.

Missing runtime on this host, recorded in `scripts/repro/handoff/linux-host-probe.txt`:

- The pinned driver `c5ee191c02b11448ffefcc38b78b064a87d8ef23` is not installed. The installed binary is `cua-driver 0.28.2`.
- `cua-driver status` exited 1. The daemon is not running.
- The display returned no top-level windows.
- No Chromium fixture was driven.
- No model session was run.

This is not a macOS census and not a Windows census.

Asked for under `scripts/repro/`: raw JSONL receipts, the exact command and environment, a summary table, and a promotion verdict for trycua/cua#4165.

Not produced: those receipts and that verdict.
Not invented: screenshot counts or wall times.

The admission rule that was unit-tested, and is not that A/B, is `lazy_vision.needs_visual_capture`.
