# Issue 49

Comparison: `scripts/repro/handoff/issue-49-comparison.json`, from `transfer_probe.comparison_rows`.

The shipped rule admits `only-action` when the other candidate is `reobserve`, and admits nothing when two candidates have tools. A second harness that used a plain dict would drop frozen arguments, so that spike was deleted. Nothing else was deleted. No TypeSafe or Jev import was added.
