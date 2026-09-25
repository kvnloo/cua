# Issue 41

Candidate envelope, unchanged: `id`, `description`, `tool`, `arguments`, optional `capture_id`, optional `screenshot_reference`.

The fast path and guarded run read `id` and `tool`. They do not add an authority token. No public Driver API was added.

Fixture: the `Candidate(...)` constructions in `test_deterministic_fast_path.py` and `test_guarded_run.py`.
