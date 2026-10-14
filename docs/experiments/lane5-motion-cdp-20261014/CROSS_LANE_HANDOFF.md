# Lane 5 cross-lane evidence handoff — 2026-10-14

**Research / integration receipt only.** Not a new public CUA Driver, AODL, Hermes, OMP, T3Code, GEV or z0evals API. Reuse CUA's existing typed `ActionResult` and session/ref semantics, and review the [outcome-contract owner](https://github.com/trycua/cua/issues/4009) and [downstream uncertain-mutation work](https://github.com/kvnloo/cua/pull/105) before implementing adapters.

## Consumer invariants

| Consumer | Safe shared capability | Non-negotiable refusal |
|---|---|---|
| Hermes | Plan with immutable typed candidate ID; observe fresh before mutation; distinguish guard admitted from independently verified | Never interpret provider-chosen/candidate confidence as action authority |
| OMP | Surface action target, foreground/background route and user approval; preserve cancellation receipt | A cancelled caller/session does **not** prove an already-admitted effect cannot land |
| T3Code | Voice-command / quick-navigation mapping only to existing named, session-bound actions; retain independent outcome | No focus/submit action from stale UI revision or ambiguous candidate |
| GEV | Consume **read-only** verified computer-state or fleet-operator action receipts with provenance | No automated irreversible map/remote-control mutation on an unverified success |
| z0evals | Ingest the experiment's exact source + environment, all trials, independent oracle and paired deltas | Do not pool CDP-only samples with CUA Driver end-to-end benchmark results |

## Minimal receipt interpretation — map existing runtime fields, do not publish a new schema

1. **Candidate:** exact CUA session; action/candidate ID; target identity and generation; observation/provider provenance. Cached semantic revision is freshness metadata, **not** authorization.
2. **Admission:** whether action was allowed and which existing policy/ref check authorized it, without leaking action content.
3. **Dispatch:** separate *attempted*, *known-delivered*, *known-refused before delivery*, and *may-have-landed*. A general refusal/error may have unknown delivery.
4. **Outcome:** distinguish target-owned `verified`, `refuted`, `unknown`, and `timed_out` from Driver success/accepted.
5. **Retry:** an accepted/unresolved mutation, acknowledgement loss, or cancellation is **observe/reconcile**, never blind replay. One unchanged read does not retire an in-flight effect; no automatic second Submit.
6. **Measurement:** every attempted task in the denominator; monotonic whole-task time to target oracle; cold/warm separated; full cleanup lifetime; forced route, backend, tool/decision/observation/action counts and failures. Use existing [accounting owner #10](https://github.com/kvnloo/cua/issues/10).

## First-wave measurements handed off
Local isolated Chromium, CDP direct (not CUA Driver): 30 AB/BA matched pairs; 60/60 verified page-owned `Submit` mutations; median visual hash changes 4/4 vs 0/4 under cooperative reduced-motion CSS. Median click-to-oracle 54.58 vs 53.67 ms, paired bootstrap Δ interval [-1.99, +0.59] ms: **no proven latency improvement**. See `motion_ab.py`, `motion_ab_trials.json`, `motion_ab_summary.json` in this directory.

**Next upstream-relevant gate:** reconcile existing [guarded-completion PR #4316](https://github.com/trycua/cua/pull/4316) maintainer feedback, real source-Driver CI review, and #110 Rustfmt/test inventory/schema gates. For batching use **upstream** `run_steps` and `run_script` with same task-oracle A/B, not a parallel batching API.

**Provenance:** maintainers of upstream #3963, #4009, #4316, #4935 and #4936 retain design ownership; #105/#10/#93 downstream contributors retain the measured and safety findings. This artifact is a consumer mapping and local experiment, not an original claim for those contributions.
