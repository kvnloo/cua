# Issue 39

The live scan is `scripts/repro/handoff/issue-39-inventory.json`, produced by `extraction_inventory.inventory`. A production file counts only when it names the module and is not the module file. An independent harness is a production file outside `libs/cua-driver/examples/jev-use/`. This scan finds none.

| Abstraction | Call sites inside the example | Shared invariant | Differing invariant | Disposition |
| --- | --- | --- | --- | --- |
| deterministic fast path | `caller_route.py`, `task_battery.py` | one executable candidate | routing versus a task battery | recipe-local |
| compiled postconditions | the Python and TypeScript module files, plus their tests | one fixture | two languages, one recipe | recipe-local |
| guarded-run continuation | `run_length.py`, `handoff_emit.py` | the form-fill guard | a cap counter versus a receipt writer | recipe-local |
| candidate validation | `stale_batch.py` called from `handoff_emit.py` | re-resolve the next child | batch identity, not a postcondition | recipe-local |
| observation modality routing | `lazy_vision.py` called from `caller_route.py` | skip a visual capture only when a semantic candidate exists | not a second observer | recipe-local |
| settlement provenance | `window_change_detector.rs` | private `poll` field | not called from this example scan | recipe-local |
| revision invalidation | `browser_revision.py` called from `compiled_expectations.py` | ref plus generation | one browser rule | recipe-local |
| toggle expectations | `toggle_expectations.py` only | none shared | different predicates from the form compiler | recipe-local |
| toggle run | `toggle_run.py` only | none shared | boolean setting, not a submit ref | recipe-local |

No row is `extract now`. No refactor was performed.
