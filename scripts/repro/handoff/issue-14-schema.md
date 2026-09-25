# Issue 14 schema note

Recipe-local. The public Driver and MCP candidate contract is unchanged. `core.Candidate` still carries `id`, `description`, `tool`, `arguments`, `capture_id`, and `screenshot_reference`. The expectation is a separate object built by `compile_expectation` before dispatch.

| Candidate id | Compiled expectation |
| --- | --- |
| `type-verification-value` | `field_value_equals` for the caller token |
| `submit-form` | `fixture_submitted_equals` for the caller token |
| `visual-submit` | the same fixture expectation, and only when `capture_id` is present |
| `reobserve`, `abstain` | none |

`provider_cannot_replace` returns the compiled object. A provider id selection cannot supply a different token.

`accept_if_bound` calls `browser_revision.bind` before it returns the expectation. A stale ref raises and the expectation is not returned as success.

`second_child_allowed` returns false for `unknown` and `refuted`, so a failed postcondition does not start the next guarded child.

Python and TypeScript both read `scripts/repro/handoff/issue-40-fixture.json`. This note is for kvnloo/cua#5. No shared compiler was added upstream.

Wall time was not measured. Missing machine: this Linux host. The pinned driver session is not running (`cua-driver 0.28.2` is installed and the daemon is not running). No speedup is claimed.
