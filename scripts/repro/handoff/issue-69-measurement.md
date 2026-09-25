# Issue 69

Ownership decision: downstream benchmark-only tooling in `task_accounting.py`. Do not add this report to trycua/cua#4052. That issue's warm-span head was not merged here, and the 4-arm battery was not run, so there is nothing new for #4052 to review.

Exact fields on `TrialClocks`:

```text
cold_setup_ms          separate; not the outcome
verified_outcome_ms    the only value outcome_time returns
runner_lifetime_ms     not added to the outcome
named_span_ms          coverage check only
```

`residual_ms` is `verified_outcome_ms - named_span_ms`. `phase0_spans_cover_outcome` is true only when `named_span_ms * 100 >= verified_outcome_ms * 90` and the outcome is positive.

No double count:

```text
cold_setup_ms
verified_outcome_ms  --> reported outcome
runner_lifetime_ms   --> not added
named_span_ms        --> subset check against verified_outcome_ms, not a second clock in the sum
```

`verify_state.elapsed_ms` stays verification-loop time (`expectation.rs` line 310), closed before the optional screenshot read. It is not `verified_outcome_ms` and it is not runner lifetime.

The >90% fixture-battery gate was not run. No trial milliseconds were invented. kvnloo/cua#10 stays open.
