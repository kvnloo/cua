---
title: "Evidence-gated predictive selection for jev-use: RSI-Anything research addendum"
authors:
  - kvnloo
created: 2026-10-12
last_updated: 2026-10-12
status: draft
discussion: https://github.com/kvnloo/cua/issues/93
rfc_pr:
implementation: []
supersedes:
superseded_by:
---

# RFC addendum: RSI-Anything as a caller-side optimization loop above Cua

> **DOWNSTREAM RESEARCH ONLY / NOT AN ACCEPTED CUA CONTRACT.**
> This is a scoped addendum to existing downstream semantic-control RFC [#93](https://github.com/kvnloo/cua/issues/93), not a replacement architecture RFC or a request to reopen upstream [#3963](https://github.com/trycua/cua/issues/3963).
> First step is an **optional measurement experiment** on the existing `jev-use` caller/`DecisionModel` seam. No Driver changes or defaults are proposed.

## Summary / decision sought

Can an outcome predictor trained on independently verified computer-use trajectories improve **end-to-end verified task success and/or the cost per successful task**, when its inference, calibration, feedback collection, fallback, and update costs are included?

Borrow the **propose → predict → select → execute → independently verify → learn → retain/rollback** cycle from [RSI-Anything](https://arxiv.org/abs/2610.13912), but do not build its full training stack into Cua. The caller may optionally use a small outcome estimator to **rank already legal, immutable candidate IDs** only at unresolved decisions. Verified experiences may drive *offline*, versioned challenger policies/world predictors, which are admitted only by paired held-out validation and a rollback gate.

In a simple or fully determined step, keep today's deterministic / guarded-completion path. Avoid the additional model call entirely. Inference is never an authorization or freshness oracle.

The initial proposal changes **zero public Cua Driver, SDK, MCP, or protocol fields**. Whether the experimental caller-side design deserves a reusable public surface is a later maintainer decision, contingent on measured benefit and demand.

## Why now

- Upstream [#3963](https://github.com/trycua/cua/issues/3963) set the core latency goal: **delete unnecessary model decisions, observation work and waits, without widening action authority**. Maintainer [decision](https://github.com/trycua/cua/issues/3963#issuecomment-5896357755) closed the umbrella on September 29: one owner PR per mechanism, opt-in caller-local defaults, forced/observed execution path, independent task oracle, and visible failure/fallback. New mechanisms should link to the historical issue.
- Completed [RFC #3931](https://github.com/trycua/cua/blob/main/rfcs/3931-cua-perception-and-jev-use.md) and [RFC #4268](https://github.com/trycua/cua/blob/main/rfcs/4268-jev-use-native-candidates.md) already place candidate construction and policy above Driver: models only select **caller-supplied candidate IDs**; Driver owns snapshot/ref/session validity, action dispatch, capture binding and observation.
- Current [#4013 / PR #4014](https://github.com/trycua/cua/pull/4014) covers **structured caller-owned planner handoff on abstain**, not another general router. The maintainer explicitly removed general classifier/provider routing from that RFC. This proposal must **not** reintroduce it.
- Upstream [#2794](https://github.com/trycua/cua/issues/2794) owns mechanical action composition; [#4316](https://github.com/trycua/cua/pull/4316) owns narrow opt-in guarded completion. This proposal must not duplicate execution, batching, a verifier or a state store.
- RSI-Anything (published October 9, 2026) provides a testable hypothesis about *which residual decisions merit predictive scoring* and how to accept or reject successive policy/predictor revisions. It is new outside research input, **not proof that Cua becomes faster**.

The user problem is that **nondeterministic residual choices** can waste actions, reparsing, model calls, and retries, while blindly reranking every action can itself add more latency than it removes. Optimize the verified task, not the model score.

## Research lineage and reproducibility evidence

**Original research credit:** Taoyong Cui, Pinxian Zeng, Wanghan Xu, Hao Xiao, Shuhan Xue, Qiang Gao, Wanli Ouyang, Pheng Ann Heng, Zhenfei Yin, Yingcheng Wu and Ling Yang, [RSI-Anything paper](https://arxiv.org/abs/2610.13912) and [Gen-Verse repository](https://github.com/Gen-Verse/RSI-Anything); built on the authors' [JEPA-Anything](https://arxiv.org/abs/2609.20800). Adjacent prior programs include [RLAnything](https://arxiv.org/abs/2602.02488) and [ScienceBuddy](https://arxiv.org/abs/2609.17523). Cua architecture/measurement contributions and maintainers retain their own attribution via the linked RFCs, reviews and PRs; we are adapting an idea, not claiming their design or experiments as ours.

Our [pinned downstream reproduction](https://github.com/kvnloo/oss-factory/pull/84) used RSI source `99dbf000a424b9033651b1096c5da2b6d5fa3865`:
- [Passing recorded-outcome reanalysis](https://github.com/kvnloo/oss-factory/actions/runs/38271855918): 7,980 sanitized original GUI endpoints, 13 published statistical contrasts reproduced and additional paired ablations; 9 chemistry inference tests passed. These are **released outcomes, not independently rerun RSI model inference/training**.
- On RSI's narrow MiniWoB++ checkbox test, the final *selected* controller was 99/100, final pure-world ranker 98/100. The selected controller used `alpha=0` (policy scores, **not world reranking**); pure-world accounted execution time was **5.77×** that selected path. A rule baseline achieved 100/100 on a **different world-test cohort**. These comparisons argue strongly for a cheap fast path and an optional, value-tested estimator, not a new mandatory predictor.
- [Fresh real Chromium smoke](https://github.com/kvnloo/oss-factory/actions/runs/38272197442): 64/64 independent browser executions of the **rule controller**, 2.953 actions/task. This confirms a narrow rule control, **not** trained RSI generalization or a Cua result.
- No RSI weights, full training traces, desktop OSWorld result or actual chemical experiment was independently reproduced. The original GUI full training setup is substantially heavier than a CPU smoke.

Use these numbers solely to **design a discriminating Cua experiment**. Do not import a 99% success claim or a 5.77× Cua latency claim.

## Prior RFC and issue disposition map

| Surface | Actual owner / state | How this addendum relates |
|---|---|---|
| Upstream [#3963](https://github.com/trycua/cua/issues/3963) | **Closed/completed**, maintainer decision; historical latency parent | Link as follow-up; never reopen, rewrite or create a second Driver-level RFC |
| [#3931](https://github.com/trycua/cua/issues/3931), [#4268](https://github.com/trycua/cua/issues/4268) | Completed model-neutral perception/candidate RFCs | Preserve closed choice, immutable action table, capture/snapshot authority and platform parity |
| [#4013](https://github.com/trycua/cua/issues/4013), [PR #4014](https://github.com/trycua/cua/pull/4014) | Open RFC narrowed by maintainer to abstain handoff | Do **not** build a general router or a competing handoff; predictor's decline uses existing refusal/abstain path |
| [#2794](https://github.com/trycua/cua/issues/2794), [#4316](https://github.com/trycua/cua/pull/4316) | Active composition and guarded-completion ownership | Consume their semantics and guard receipts; predictor cannot authorize a child or skip a fresh proof |
| [#4009](https://github.com/trycua/cua/issues/4009), merged [#4052](https://github.com/trycua/cua/pull/4052) | Typed action-outcome provenance and timing owners | Reuse outcomes/phase telemetry; do not replace with predictor confidence |
| Downstream [#93](https://github.com/kvnloo/cua/issues/93), [#73](https://github.com/kvnloo/cua/issues/73) | Experiment umbrella and architecture/disposition | **This RFC belongs here** as one research addendum; no new architecture umbrella |
| Downstream [#10](https://github.com/kvnloo/cua/issues/10), [#24](https://github.com/kvnloo/cua/issues/24) | Whole-task metric contract and reusable multi-task fixtures | Reuse the ledger, oracles, route forcing, paired A/B, negative cases; no second benchmark service |
| Downstream [#107](https://github.com/kvnloo/cua/issues/107) | Scoped reads vs mirror vs checked routine | **Not** a new long-lived state mirror or compiled-route engine |
| Downstream [#94](https://github.com/kvnloo/cua/issues/94), [#109](https://github.com/kvnloo/cua/issues/109) | Platform topology / browser motion experiments | Separate treatments, not required for predictive selection |
| Downstream [#74](https://github.com/kvnloo/cua/issues/74) | Canonical upstream promotion and HITL queue | Own both proposed publication steps and later, evidence-gated implementation selection |

## Architecture and invariants

```text
Existing Cua Driver observation (exact session, generation, refs)
   ↓
Existing caller-built immutable, authorized candidate table
   ↓
Existing exact deterministic fast path / verified continuation
   ├─ proven one action or done → execute/verify, NO prediction overhead
   └─ genuinely unresolved choices
         ↓
      existing chooser (policy-only) [default]
         OR optional bounded outcome estimate for same candidate IDs
         ↓
      selected ID → caller validates original table + current authority
         ↓
      Cua Driver action → fresh independent task oracle
         ↓
      content-free outcome/latency ledger (opt-in)
         ↓
      asynchronous offline update / replay + held-out gates
         ↓
      retain compatible challenger pair OR roll back to incumbent
```

**Always true:**

1. The predictor only scores or ranks a **closed list of already legal caller-constructed candidates**. It cannot create arguments, targets, tool names, postconditions, permissions, or semantic authority. It may abstain.
2. Candidate/ref/capture/session binding and any post-mutation freshness are revalidated by existing Driver/recipe gates at execution. A good predicted outcome never validates an expired action token.
3. A deterministic task oracle or fresh target-owned state determines terminal success. Driver `confirmed`, a model success score, accepted input, a benign event or an unchanged read are **not** sufficient alone.
4. Unknown/refused/pending effects are reconciled before any retry. No duplicate irreversible mutation, uncontrolled exploration or automatic permission escalation.
5. No shared shadow-state service, second verifier, new Driver router/model provider, public action grammar, generic training service, new batch primitive, or default ML download.
6. Default-off, version-pinned and reversible. Cua's shipped behavior must remain unchanged with no optional model installed.
7. Both Python and TypeScript recipe adapters must preserve the existing choice schema or propose an explicit narrow compatibility decision *after* the research gate.

## Minimal candidate and predictor boundary (conceptual only)

Existing immutable action table remains canonical, including target ID, action arguments and caller-owned pre/postconditions. A separate **ephemeral** scoring request may reference its stable candidate IDs and task context:

```json
{
  "task_family": "resettable-owned-fixture",
  "state_generation": "non-authoritative-reference",
  "candidate_ids": ["c0", "c1", "reobserve"],
  "budget_remaining_ms": 1500,
  "predictor_version": "optional-local-v0"
}
```

Predictor responses are advisory `{ candidate_id: p_verified_success, predicted_remaining_ms, uncertainty }` over those IDs only. This is **not** a proposed public schema and must never be placed into Driver's canonical action result. Whether a decision is worth the extra inference depends on actual outcome benefit and full cost; neither a generic confidence threshold nor a fixed candidate-count threshold is justified without calibration.

**Gate at runtime:** first use exact deterministic completion/one-admitted-candidate/guarded continuation. Where choices remain, permit a predictor call only within a configured time and attempt budget; failure, unavailability, low confidence or cost gate misses route to the existing chooser/reobserve/abstain. Never bypass a refusal.

**Gate between versions:** record `policy_id`, `predictor_id`, training-data provenance, task splits, reward/oracle version and model/CPU/GPU cost. Evaluate candidate policy, predictor and **assembled pair** on held-out task families and changed/reordered UI, using paired traces with independent oracles. Admit only if prespecified end-to-end success/cost, safety and calibration gates pass; keep incumbent and rollback. Train offline from consented, screened verified examples, not unreviewed live user-desktop traces.

## Performance objective

Primary: **verified completed tasks per wall-second at fixed error/safety**, also report cost per verified success. Never optimize `actions/task`, prediction accuracy or mean inference time in isolation.

Per attempted task, reuse downstream [#10](https://github.com/kvnloo/cua/issues/10):
- complete verified outcome latency through runner cleanup, cold/warm separated; p50 and p95 with their sample size and uncertainty;
- success/refutation/unknown/abstain/timeout and side effect rates, including **all fallback attempts**;
- predictor invocation rate, chooser calls and tokens, total model cost, observations, action attempts and fresh-oracle reads;
- exact target path forced, **actual** provider/predictor/route taken and why, Driver version/source, session/fixture/platform identity, negative/refusal outcomes;
- update/calibration/retraining/amortized admission cost and memory/disk footprint;
- calibration (e.g. Brier/ECE) on held-out task families and performance under distribution shift.

Use interleaved randomized matched tasks and preregistered acceptance rules. Do not pair published RSI cohorts that differ, and do not sum isolated improvements or assume model-call deletion is a latency win.

## Proposed pilot: prove that prediction is worth invoking

**P0 / no training required:** Inspect the existing `jev-use` decision seam on current origin main; reuse [#24](https://github.com/kvnloo/cua/issues/24) task families and [#10](https://github.com/kvnloo/cua/issues/10) outcome accounting. Select at least two **nontrivial** owned/resettable browser/native task families where multiple valid candidate choices really change the verified outcome. The trivial MiniWoB++ checkbox task is an explicit rule-baseline negative control.

**Arms:**
- **A — shipping caller:** current default policy and existing safe route/fallback, unchanged.
- **B — cheap challenger:** existing deterministic rule, progress and bounded cheaper score/rerank, no learned world model.
- **C — frozen predictive selection:** same candidate pool/provider/budget as A; conditional outcome predictor scores/reranks candidates only when uncertainty justifies the expense.
- **D — feedback-retained challenger (later):** after a fresh train/dev/held-out split and independent evidence, adapt the **caller policy/predictor offline** and admit or reject the pair under the same gates.

For pilot A/B/C, use **at least 30 interleaved paired attempts per task family**, report paired deltas and every failure. Include no-op wrong target, duplicate labels, stale/cross-session refs, changed page generation, false positive completion, applied-but-ack-lost, predictor timeout/error and out-of-domain abstain. Check the forced path actually runs; otherwise the arm is **NOT_EVALUATED**, not success.

Only test D after A/B/C reveal a measurable residual selection problem. Use train/dev/test splits by task family, not just randomized seeds of one widget, so adaptation cannot memorize a benchmark. Begin with inexpensive calibration/logistic/gradient-boosted or heuristic predictors; JEPA/LoRA only after the cheap model fails an observable, valuable capability requirement. Include CPU p95, model warm/cold overhead and amortization.

**Promotion stop conditions:** fail-closed or wrong-authority event; any duplicated consequential mutation; calibration drift unhandled; whole-task metric worse after overhead; missing independent outcome; route unforced; or benefit confined to a trivial task already solved by deterministic rules. If the predictor cannot beat B in a realistic task family, **KILL/LOCAL_ONLY**, do not ship a model.

## Alternatives

1. **Just optimize Jev/LLM inference:** simpler, and may win when model processing dominates; does not learn which decisions actually need prediction. Use as a baseline, not a substitute for proof.
2. **Always invoke RSI world model:** risky, expensive; released RSI checkbox pure-world path was slower and no more successful than the selected policy. Reject as a default.
3. **Add a universal Driver predictor/router:** duplicates discarded architecture, violates accepted #3931/#3963 ownership. Reject.
4. **Use only existing rule + guarded continuation:** **preferred unless C shows incremental value**. Avoid forcing the new idea into the product.
5. **Store a persistent UI mirror/compiled program first:** separate #107/#93 R2-07 evidence lane. Not a prerequisite for residual action ranking.

## Privacy, safety, compatibility

No raw screenshots, DOM content, personal text, credentials, or reconstructable user trajectories in public CI artifacts or automatic training data. Initial fixtures are synthetic/owned. Default telemetry is content-free counts, hashes that cannot be reversed to sensitive user data, fixed reason codes, route receipts, versions, bounded duration and independently verified outcomes. Private live traces require informed opt-in, least retention and permissions. Data/use rights, model/dataset licenses, model weight downloads and network egress must be explicit and separately reviewed.

Offline candidate-version switching cannot change Driver permissions, session lifetimes, SDK protocols or supported target types. Missing predictor/plugin must behave exactly as today's caller. Unknown outcomes retain today's conservative behavior. Platform tests do not transfer from X11 to Hyprland/Wayland, macOS or Windows by assumption.

## Ownership and phased rollout

1. **Downstream research addendum (this PR):** attach to #93, #73 and #10's existing constraints; no runtime changes. #74 owns promotion routing.
2. **Pilot A/B/C in downstream fork (separate, small leaf):** source-seam map, fixed fixture IDs, outcome ledger, no public contract. Qualify and attach negative cases before a new implementation PR.
3. **Independent QA:** hold out task families, quantify uncertainty/model costs and re-verify exact origin head + review feedback on #4316/#4014. Document KEEP/REVISE/KILL.
4. **Upstream research conversation:** if authorized through OSS Factory Linear Todo and no new duplicate exists, open **one** narrowly framed feature/research issue centered on whether optional predicted-outcome reranking merits a recipe-local pilot. Cite RSI-Anything + honest reanalysis boundary, #3931/#4268/#3963/#4013 and the pilot. No new Driver API requested.
5. **Second separately authorized upstream action:** attach that new issue as an **actual GitHub sub-issue** of historical #3963 *if maintainers accept a child under the closed completed umbrella*. GitHub supports native sub-issues; if this parent relation would misrepresent #3963's completion or is declined/unsupported, use only a plain `Related #3963` backlink instead. Do **not** reopen #3963. Keep #4013 and #2794 related links, not duplicate parents.
6. **Only after maintainer direction:** separate tiny opt-in recipe PR if acceptance evidence and a genuine user requirement support it. One owner PR per mechanism; no general Driver RFC without newly discovered public-contract need.

Upstream publications are **NOT DONE**; the two upstream writes require separate factory authorization / Linear Todo gates and current-state duplicate, maintainer and policy checks. Downstream coordination is not authorization to post.

## Prepared issue text (do not auto-post)

**Suggested title:** `[Feature]: Investigate cost-aware predictive candidate selection for jev-use (RSI-Anything)`

**Primary area:** MCP or agent integration

**User problem:** Some nontrivial computer-use tasks still require repeated costly choices among caller-provided legal actions. Faster inference and guarded continuation remove many decisions, but may not identify when *predicting a candidate's likely verified outcome* is worth another model call. Automatically reranking every action could be a latency regression.

**Desired outcome:** An opt-in caller-side comparison of existing policy-only choice against a cheap predictor and a learned outcome predictor on paired, resettable Cua tasks. Candidate legality, fresh refs, permissions, independent task verification and fallback remain unchanged. End-to-end latency, correct completion, predictor overhead and failure denominators decide whether the idea survives.

**Prior art/alternatives:** [RSI-Anything](https://arxiv.org/abs/2610.13912), [repository](https://github.com/Gen-Verse/RSI-Anything), historical [#3963](https://github.com/trycua/cua/issues/3963) and its maintainer decision, completed #3931/#4268, [#4013](https://github.com/trycua/cua/issues/4013) (handoff, **not** a routing service), [#2794](https://github.com/trycua/cua/issues/2794) (mechanical composition). Reanalysis: [passing pinned GUI study](https://github.com/kvnloo/oss-factory/actions/runs/38271855918) where **policy-only 99% vs world 98%** at far lower accounted inference cost, on one narrow checkbox task; this is **not Cua evidence**.

**One question for maintainers:** Would a small, opt-in `jev-use`-only pilot comparing conditional outcome scoring with the existing cheapest safe caller path be useful, provided it adds no Driver policy or public contract?

**Next-stage proof (ours, not a request for maintainers to run tests):** matching initial state and task oracle, forced route receipts, Python/TS parity when appropriate, at least two held-out nontrivial task families, all failed and unknown attempts, model/latency overhead, and a no-regression abort rule.

**Explicitly excluded:** new Driver router/decision service, permissions, generic replay, batching, model downloads or any claimed Cua speedup.

## Decision record (pending)

No maintainer decision yet. No runtime/production implementation, no new Cua A/B results and no upstream posting authorized by this addendum. Record review comments, selected scope and KEEP/REVISE/KILL disposition here rather than silently upgrading the paper's results into Cua evidence.
