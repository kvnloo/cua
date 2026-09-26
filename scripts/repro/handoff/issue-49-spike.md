# Issue 49

Comparison: `scripts/repro/handoff/issue-49-comparison.json`, from `transfer_probe.comparison_rows`.

The five rows cover observation modality, one executable candidate, compiled postconditions, freshness, and guarded continuation. Each calls the shipped function. None of those concepts transferred: a second harness that used a plain dict would drop frozen arguments, compiled fixture ids, the browser ref generation, or the submit ref. That spike was deleted. Nothing else was deleted. No TypeSafe or Jev import was added.
