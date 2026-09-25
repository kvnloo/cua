# Issue 69

Owner: `task_accounting.outcome_time`, which returns `verified_outcome_ms` only.

```text
cold_setup_ms          (separate)
verified_outcome_ms    --> reported outcome
runner_lifetime_ms     (not the outcome)
named_span_ms          (coverage check only)
```

No double count: the report does not add runner lifetime to the outcome. The #4052 branches were not merged here.
