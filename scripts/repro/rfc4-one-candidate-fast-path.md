# kvnloo/cua#4 — one executable candidate

Downstream experiment. The default jev-use chooser is unchanged.

## Predicate

`single_executable_candidate` admits a candidate only when the set contains exactly one candidate that has a Driver tool and is not `reobserve` or `abstain`.

## What this commit does not claim

Live interleaved trials are not in this commit. No promotion verdict is issued.

The unit test `test_rule_acts_when_a_chooser_would_reobserve` records the authority the rule removes: one executable candidate is admitted even when a chooser would reobserve. That case has to be measured on the fixture before any promotion.

## Run

```bash
python -m unittest libs/cua-driver/examples/jev-use/python/tests/test_deterministic_fast_path.py
```

Pinned upstream main for the wave: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.
