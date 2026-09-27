# Issue 28

Decision rows: `scripts/repro/handoff/issue-28-decisions.json`, from `old_driver_fallback.decision_rows`.

The shipped helper is `run.optional_visual_observation`. `supports_capture_bound_click` is the schema preflight for `click.capture_id`. `lazy_vision.needs_visual_capture` is the separate caller rule for a semantic candidate. No second helper was added. No new public Driver API was added.

The rows call that helper with an in-process fake session. A semantic executable candidate does not call it. Missing `parse_visual_regions`, or a click schema without `capture_id`, returns none and performs no call. A permission refusal returns none after one call and does not retry. A non-string `capture_id` returns none and does not call `parse_visual_regions`. When the visual path runs, `include_accessibility_tree` is false.

Fixture pin: upstream `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. Installed binary on this host: `cua-driver 0.28.2`, which is not that pin. This Linux host is present. The live current-driver versus older-driver session was not run, because the daemon is not running. The JSON rows set `live_driver` to `not used`.
