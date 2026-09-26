# Issue 47

Closed at https://github.com/kvnloo/cua/issues/47#issuecomment-5841889690.

The measurement is `scripts/repro/handoff/issue-47-history.json`, from `chooser_projection.history_report`. Accepted items keep `selected_id` and `outcome`. An extra field is rejected. `measured_success` is null. The proposal is `not justified`, so no shorter history is proposed.

The missing prerequisite for a live battery is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`, which is not an installed release. A debug build of that commit finished and printed `cua-driver 0.29.1`. `cua-driver status` then exited 1 because the daemon is not running, and `cua-driver doctor` returned no top-level windows. See `scripts/repro/handoff/pin-build.md`.
