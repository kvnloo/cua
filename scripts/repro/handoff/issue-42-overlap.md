# Issue 42

Two readers of `issue-40-fixture.json`: `compiled_expectations.py` and `typescript/compiled_expectations.ts`.

Overlap: both compile `field_value_equals` and `fixture_submitted_equals`, and both ignore a provider replacement.

Verdict: remains recipe-local. One fixture does not justify a shared compiler.
