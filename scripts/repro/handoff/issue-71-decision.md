# Issue 71

`PollProvenance` in `window_change_detector.rs` is a private field. It was not compiled on this Linux host. `needs_restore` and `result_suffix` are the existing public methods. No regression was found that fails unless a new public field exists, so none was added.

| Caller decision | How it is decided today | Recommendation |
| --- | --- | --- |
| continue | `typed_choice("confirmed", "completed", passive_success=False)` returns `continue` | OTHER EXISTING SIGNAL |
| reobserve | `typed_choice("confirmed", "skipped", passive_success=False)` returns `observe` | OTHER EXISTING SIGNAL |
| stop | `typed_choice("refused", "skipped", passive_success=False)` returns `stop` | OTHER EXISTING SIGNAL |
| escalate | `WORKFLOW.md` line 121: escalation is advice, never an automatic retry | OTHER EXISTING SIGNAL |
| retry forbidden | `WORKFLOW.md` line 127 and `typed_choice` on `unverifiable` return `observe`, not another dispatch | OTHER EXISTING SIGNAL |
| tool text | `Changes.result_suffix` | OTHER EXISTING SIGNAL |
| restore | `Changes.needs_restore` | OTHER EXISTING SIGNAL |
| poll split | `PollProvenance` | NO PUBLIC FIELD |

Recommendation: NO PUBLIC FIELD.

There is no promotion dependency, because nothing is published. The macOS crate was not compiled here, so this is not a claim that the detector ran.
