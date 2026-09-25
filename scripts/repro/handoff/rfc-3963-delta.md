# Speed RFC delta against current CUA

Downstream draft only. This file does not edit trycua/cua#3963.

| Idea in the broad RFC | Current owner | What this branch did | Still required |
| --- | --- | --- | --- |
| Skip visual work when semantic state is enough | jev-use caller | `lazy_vision.py`, not called by `run.py` | live A/B for #4165 |
| One executable candidate before the model | jev-use caller | `deterministic_fast_path.py`, not called by `run.py` | live trial for #4 |
| Bounded guarded run | jev-use caller | `guarded_run.py` | fixture receipts for #5 |
| Length 2–4 as a constant | none | not adopted; `run_length.py` | none for the deletion |
| Stale later batch child | #2794 / #3494 | `stale_batch.py` is caller-side only | app-state trace |
| Passive rows | #3904 | readable, not actionable | macOS Calculator |
| Walk budget | `WalkBudget` | no second budget | slow-tree timings |
| verify_state screenshot | `expectation.rs` | call site asks for no elements | native walker count |
| elapsed_ms | `expectation.rs` | closed before the screenshot read | none on this branch |
| Conditional observation | none | shadow probe refuses to skip | macOS, Windows, and a false-negative census |
| Public settlement field | none | `PollProvenance` stays internal | macOS compile |
| Cancellation service | existing request-id owner | order test only | RFC approval |
| Provider policy inside #3961 | provider adapter | no policy file was added there | none |

Deleted abstractions: a universal shadow store, a second verifier, a shared postcondition compiler, a shared guarded-run type, and a hard-coded run length of 4.
