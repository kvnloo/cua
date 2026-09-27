# Issue 34

Allowlist: `task_accounting.event_schema`. Projection: `task_accounting.project_event`.

The schema fields are the dataclass fields, each an int: `cold_setup_ms`, `verified_outcome_ms`, `runner_lifetime_ms`, `named_span_ms`.

Forbidden keys, which `project_event` drops: `window_title`, `token`, `screenshot`, `ocr_text`, `prompt`, `credential`.

`test_open_packets.py` feeds `SECRET-MARKER` in those forbidden keys and checks the projected JSON does not contain it.

`run.py` `write_event` still records the fixture token on the outcome event. That call is the existing runner, and this audit does not change it. The recommended RFC event schema is the four integer clocks only.
