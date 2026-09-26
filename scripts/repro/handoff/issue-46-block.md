# Issue 46

Open. The required artifact is a projection A/B. It was not run.

This Linux host is present. It is not the missing machine.

https://github.com/kvnloo/cua/issues/46#issuecomment-5841889526.

The measurement is `scripts/repro/handoff/issue-46-projection.json`, from `chooser_projection.projection_report`. The shipped request keeps `id` and `description`. Tool arguments stay local. Receipts are `not produced`. Recommendation: smallest safe chooser state is id and description.

The missing prerequisite for an A/B receipt is pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`, which is not an installed release. A debug build of that commit finished and printed `cua-driver 0.29.1`. `cua-driver status` then exited 1 because the daemon is not running, and `cua-driver doctor` returned no top-level windows. See `scripts/repro/handoff/pin-build.md`. Receipts stay `not produced`.
