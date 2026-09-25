# Issue 34

Audit: `TrialClocks` fields are `cold_setup_ms`, `verified_outcome_ms`, `runner_lifetime_ms`, and `named_span_ms`. All are integers. No window title, token, or screenshot is stored.

Recommended event schema: those four millisecond fields only.

Test: `test_task_accounting.py` uses only those integers.
