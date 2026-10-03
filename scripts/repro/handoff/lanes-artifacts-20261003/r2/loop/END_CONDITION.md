# CUA RFC loop: empirical end condition (v1, 2026-10-01)

Source of truth for the goals: kvnloo/cua#73 (canonical state, final deliverable/acceptance), #93 (experiment specs, invariants), #10 (whole-task accounting), #74 (posting queue). This file turns their acceptance text into checkable criteria. The loop stops only when ALL of E1–E6 hold, confirmed by two independent judges, or when a stop rule fires (bottom).

## Reference task set (the "whole task")
- Browser, jev-use fixture, the #24-admitted classes: fill→submit, toggle→confirm, modal→act.
- Native, canonical GTK3 fixture: checkbox toggle, text entry (the R2-04 tasks).
- Whole-task verified time T = task start (first observation) → independent oracle confirms the outcome. It includes provider decisions, observations, actions, feedback, waits and verification reads.

## E1 — Disposition coverage
Every scheduled experiment has a terminal disposition backed by a fresh-verifier-accepted packet: R2-01…R2-10, the follow-ups the waves spawn, and the Linux-runnable owner rows #9, #16, #20, #36, #75, #78 and #105. Each packet carries the five mechanism requirements from #73: forced path, actual route/producer attribution, independent target-owned outcome, negative/fallback case, exact provenance. Terminal = KEEP / REVISE (with the revised claim measured) / KILL / BLOCKED. BLOCKED needs an exact external blocker: hardware (macOS, Windows, a real Hyprland seat), an owner decision, or paid budget. "Not attempted" is not terminal.

## E2 — Critical path exhausted
For each reference task, take the best verified composed configuration. Decompose its whole-task time T into components (provider decision(s), observation, resolution, feedback/visualization, dispatch, target effect, verification read(s), sleeps/polls, settle waits). Every component with a share of T of at least 5%, or at least 50 ms, has a terminal deletion verdict:
- DELETED (KEEP);
- IRREDUCIBLE (KILL, or required by an invariant);
- OWNER_DECISION (deletion works but changes a product default or policy).
The untested-but-plausibly-deletable share of T must be below 5%.

## E3 — Composition measured on one source (R2-10)
- **Run:** baseline vs the composed surviving deletions on the SAME source, binary, provider, task and environment. At least 30 AB/BA-interleaved pairs per browser class, and at least 20 per native task, with identical verified outcomes.
- **Report:** the whole-task speedup S = median T_baseline / median T_composed with a CI, the per-component decomposition, and the floor ratio T_composed / T_irreducible, where T_irreducible is the sum of the IRREDUCIBLE components.
- **References only, not gates:** compare S with PreAct (8.5–13× warm replay) and SkillDroid (~2.4× pure replay only), stating every difference in benchmark and scope.
- **Compiled replay:** if R2-07 survives, the composed config includes it for admitted tasks, measured over all invocations including fallback and first-run/compile/admission cost.

## E4 — Correctness invariants hold in every arm of every accepted packet
0 stale-ref dispatches, 0 duplicate mutations, 0 unverified successes, 0 authority minted from passive state or event absence, 0 blind replays of may-have-landed effects. Refusals are refused (`effect=refused`), and the controls are discriminating.

## E5 — Deliverables staged (downstream only; nothing posted upstream)
- #10: the final accounting table, with work deleted separate from wall-clock saved.
- #3963 rewrite draft on a fork branch, verified by a fresh reviewer: north-star, invariants, existing owners, KEEP/REVISE/KILL/BLOCKED dispositions, remaining deltas, non-goals, gates, dependency graph.
- #74: the posting queue in its own format, `delta → canonical owner → exact SHA → completed evidence → missing evidence → action type → dependency → stop condition`, with a READY NOW gate check per item.

## E6 — Stability
- **Judges:** two consecutive independent judges find E1–E5 met.
- **No moving targets:** the last wave changed no KEEP/KILL that the rewrite depends on.
- **Freshness:** upstream main drift since the tested sources touches no `libs/cua-driver` path a surviving claim depends on; otherwise recertify.

## Stop rules (end without completion; report what remains)
- 12 waves total.
- 2 consecutive stalled waves: no new terminal disposition and no reduction in E2's untested share.
- Any hard-rule breach (host desktop touched, secret exposed, upstream write).
- Live-provider (TypeSafe) budget: at most 600 requests across the whole loop, tracked in STATE.json.
