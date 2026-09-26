# Issue 24

The structural table is `scripts/repro/handoff/issue-24-battery.json`. `live_success` is null and `wall_time_ms` is null.

This Linux host is present. It is not the missing machine. The missing prerequisite is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. A debug build printed `cua-driver 0.29.1`. The daemon is not running and doctor returned no top-level windows. See `scripts/repro/handoff/pin-build.md`. The live multi-task battery was not run.
