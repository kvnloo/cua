# Issue 64

Blocked. The exact-head outcome A/B for trycua/cua#4165 was not run.

Missing machine: this Linux host. The pinned outcome session is not running here (`cua-driver 0.28.2` is installed, the daemon is not running, and there are no top-level windows).

Missing on this Linux host: the pinned Driver, a Chromium fixture, and a model session. Installed binary: `cua-driver 0.28.2`. Daemon: not running. Top-level windows: none. See `scripts/repro/handoff/linux-host-probe.txt`. Pinned head: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Asked for that artifact, a pull-request description update, and a promotion verdict. Not produced. No helper was added. No verdict was issued. The unit rule in `test_lazy_vision.py` is not the A/B.

GitHub later closed the issue at https://github.com/kvnloo/cua/issues/64#issuecomment-5841479030. That comment points the remaining outcome evidence at trycua/cua#4196 and kvnloo/cua#2. This file still records that the A/B was not run.
