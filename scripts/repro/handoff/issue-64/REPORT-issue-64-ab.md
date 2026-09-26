# Issue #64 — exact-head outcome A/B artifact for #4165 lazy vision

Pinned head: `24aaf8d1965b3b7c1530cbb9d58758ec89472d92`
(upstream `main` merge of trycua/cua#4196, which salvaged #4165's lazy-parse
ordering and its candidate-invariance test — "Salvaged from #4165. The
lazy-parse ordering and its candidate-invariance test are adapted from
@kvnloo's PR." — #4196 body).

Raw artifact: `ab_artifact.json`. Reproduction harness: `ab_issue64.py`.
To re-run: `AB64_HEAD=<upstream checkout @24aaf8d19> AB64_STUBS=<dir with the
mcp import stub> python3 ab_issue64.py`. The harness's fake Driver, the
`exact-head` tree, and the `mcp` import stub all live next to the script.

## Arms

Arm A (`--visual-observation auto`): the #4165 lazy ordering — capture+parse
only when the page structure offers no executable candidate.
Arm B (`--visual-observation always`): pre-#4165 behaviour, restored through
the exact head's own flag — parse every step.

Both arms drive the exact head's `run.candidates_for_step`,
`run.observe_visual`, `core.build_candidates` and the mock chooser. The only
substitution is the Driver transport: this Linux host has no Driver daemon,
no browser, and no cua-perception extension, so a fake async Driver stands in
for the cua-driver MCP stdio transport. It serves the exact page-structure
snapshot refs the real driver produces, a `parse_visual_regions` payload that
passes the head's `parse_visual_regions` validation, and performs real form
submissions (HTTP POST `/submit`) against the real `fixture_server.py` from
the pinned head. The outcome oracle (`/state` submitted == token) is the
fixture server's own.

Fixture matrix: default fixture (semantic Submit ref) × visual fixture
(`--visual-fixture`: `role="presentation"` Submit, no DOM ref, visual path only).

## Results

| arm            | fixture | outcome  | steps | visual tool calls | per-step visual statuses |
|----------------|---------|----------|-------|-------------------|--------------------------|
| auto (A)       | default | verified | 2     | 0                 | skipped / skipped        |
| always (B)     | default | verified | 2     | 4                 | ok / ok                  |
| auto (A)       | visual  | verified | 2     | 2                 | skipped / ok             |
| always (B)     | visual  | verified | 2     | 4                 | ok / ok                  |

Visual tool calls = `get_window_state` + `parse_visual_regions` (2 per
observation). Both arms act through the same candidate IDs on both fixtures
(`type-verification-value` then `submit-form`; on the visual fixture the
submit rides the capture-bound visual click).

This is the outcome-level evidence #4165's own "Scope / caveat" section
demanded: "An interleaved fixture A/B should still report completed-task
outcome plus visual-observation count before promotion." Completed-task
outcome is invariant across arms (verified everywhere — the
candidate-invariance claim), and visual-observation count drops under the
lazy ordering (default fixture: 0 vs 2 observations; visual fixture: 1 vs 2).

## Environment gaps (honest)

- No real cua-driver, no browser, no perception extension on this host, so
  visual `ok` statuses come from a fake parse payload shaped to the head's
  exact schema. A desktop run with Driver ≥ 0.29.1 + the perception extension
  would be needed to prove the real visual-`ok` path end to end. That is
  #4196's stated known gap, not #4165's.
- Wall-clock latency is not claimed from this artifact: fake-driver round
  trips are microseconds; the real per-parse cost (3.6 s Linux / 8 s Windows
  CPU, per #4195/#4196) is upstream-reported, not measured here.

## Verdict

**#4165 is truly superseded; no separate qualification remains.**

- Its deliverable (lazy-parse ordering + candidate-invariance test) ships
  upstream inside merged #4196 (24aaf8d1965b3b7c1530cbb9d58758ec89472d92).
- The outcome-level evidence #4165 demanded now exists twice: this
  exact-head fixture-driven A/B, and #4196's CI Linux mock E2E at head
  `f416344c7` (default fixture: submitted via page-structure path,
  statuses `[skipped, skipped]`; visual fixture: `[skipped,
  not_installed × 3]`, no submission, `budget_exhausted`).
- The remaining unproven evidence — real visual-`ok` completed-task outcome
  with the perception extension, foreground escalation on a desktop, desktop
  matrix — is #4196's known-gap list, not a reason to keep qualifying the
  closed #4165. It attaches upstream to #4196 / its known gaps, and
  fork-side to kvnloo/cua#2 (which stays the live experiment handoff).
- Recommendation: close the #4165 promotion packet as superseded; keep #64
  open only until this artifact + verdict are filed, then close it too.
  No new work should target #4165's closed PR.

🤖 Generated with [Muse Spark](https://www.meta.ai) by Meta — authored with AI
assistance (Muse, Meta's Muse Spark) under the contributor's direction.
