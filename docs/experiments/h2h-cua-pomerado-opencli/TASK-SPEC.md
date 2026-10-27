# CUA vs Pomerado vs opencli — read-only head-to-head task specification

**Status: PREREGISTERED / NOT_RUN.** This document and [`tasks.json`](tasks.json) describe a bounded, downstream-only experiment. **No task attempt, model mint, Driver route, opencli adapter run, measured duration, price or winner is claimed.** Tracking: [kvnloo/cua#161](https://github.com/kvnloo/cua/issues/161), specifically its [2026-10-27 bounded slice](https://github.com/kvnloo/cua/issues/161#issuecomment-6436019947); existing two-arm [draft #162](https://github.com/kvnloo/cua/pull/162) and [baseline QA draft #163](https://github.com/kvnloo/cua/pull/163) are **reference work only**, not edited or treated as three-arm results.

## Scope and validity boundary

Compare **the same signed-out, read-only website task** on one isolated synthetic fixture origin, across:

- **A — CUA:** a real caller and source-built CUA Driver, including `run_steps` or operator-enabled `run_script` where semantically eligible. The older individual-action `jev-use` caller alone is **not** a sufficient best-available CUA baseline; use the [route-shape gate in #163](https://github.com/kvnloo/cua/blob/chatgpt/cua-pomerado-baseline-20261025/docs/experiments/pomerado-cua-2026-10-25/BASELINE_GATE.md).
- **B — Pomerado:** a locally minted, separately consented, deterministic read-only MCP integration, run by the caller **outside** CUA Driver action authority. Minting uses models; an actual warm invocation must show whether any model requests occurred.
- **C — opencli:** a deterministic fixture-specific adapter that reads through its observed browser route, not an HTTP shortcut or a hardcoded answer. Adapter authoring is a separate preparation cost; no fixture adapter is authored in this slice.

The **pinned fixture really is a single form**, not a catalog: [`fixture_server.py`](https://github.com/kvnloo/cua/blob/6e74bfadd82790312f0ab46ae7ed48027f8aca56/libs/cua-driver/examples/jev-use/fixture_server.py) exposes `GET /` (title, heading, paragraph, form, status) and `GET /state` (submitted value), plus `POST /reset`/ `POST /submit` which are **operator-only setup operations**. The `--visual-fixture` flag swaps the semantic Submit button for a visible presentational control. **No table, list filter, pagination, disclosure widget, arbitrary second page, or reload-changing read value exists at this pinned source.** Inventing such tasks would create unequal or impossible oracles; they are deliberately excluded. A broader multi-page benchmark needs a **separately reviewed fixture change and new spec revision**, not a silent rewrite of an arm or its oracle.

These ten small form-observation tasks validate *parity and provenance only*, not broad website competence or a measured product advantage. The separate #162 preregistration's 30 paired-block/condition minimum is **not satisfied** by the ten repeats/arm here; do not substitute this pilot for that stronger claim.

## Pins — mandatory before any valid attempt

The following source pins are **fixed** in this draft. Values marked **capture before execution** are unknown; they are not filled with fabricated hashes or guessed model IDs. Before the first trial, publish a reviewed, immutable run manifest with the actual digests, full version strings, environment and route configuration. Keep it separately from results. **Any absent, malformed, unverified or changed source/fixture/arm pin makes that attempt `INVALID` and its cohort non-comparable.** A formatted SHA string alone is not provenance: compare file bytes, Git checkout, executable attestation, package integrity and observed process/tool traces.

| Component | Fixed source pin | Mandatory exact per-run/preflight fields |
| --- | --- | --- |
| Fixture | `fixture_commit=6e74bfadd82790312f0ab46ae7ed48027f8aca56` from `kvnloo/cua` main; `fixture_blob_sha=055500f713ba2c33d8544096f4084ebb108757ce`; file `libs/cua-driver/examples/jev-use/fixture_server.py` | `fixture_commit`, `fixture_blob_sha`, actual fixture process/build digest, `fixture_mode` (default or visual_submit), immutable origin identity, effective browser/fixture provenance, independently verified reset/read-only state |
| A · CUA | `driver_source_commit=ff888c6159c9fae3b9c47938f77bcf104373d426`, `driver_version=0.34.0` (per [driver pin investigation](https://github.com/kvnloo/cua/issues/161#issuecomment-6408635294)) | Exact source checkout and Cargo/toolchain profile; `driver_binary_sha256` (64 hex, **capture before execution**), executable `doctor --json` `build.version`, `build.git_sha`, `build.exe_sha256` and **live MCP** `health_report.build` (all must agree); `caller_commit`, `caller_prompt_sha256`, advertised/observed Driver tool and route, browser version |
| B · Pomerado | `pomerado_repo_commit=1d8a016862b6b1c8e43c770a75514d487efb8bc5`; source [`package.json`](https://github.com/Pomerado/pomerado/blob/1d8a016862b6b1c8e43c770a75514d487efb8bc5/package.json) declares `version=0.4.0`, Node `>=24.21.0 <25` | Independently checked package/source or tarball integrity + actual `pomerado_package_version`; **exact** `node_version`, browser/Playwright versions, `mint_model_ids` (all exact provider model IDs used, not a label like "Sol"), mint requests/tokens, `mint_artifact_sha256`, integration source/manifest digest, reviewed read authority, actual `pomerado-mcp` invocation/route evidence. Prior canary CLI discovery does **not** prove this source build or mint |
| C · opencli | `opencli_repo_commit=916705f34456ea54200fb79d0a28fd1cbc0727f6` from `kvnloo/opencli`; [`package.json`](https://github.com/kvnloo/opencli/blob/916705f34456ea54200fb79d0a28fd1cbc0727f6/package.json) declares `version=2.0.2` | Exact `opencli_version`, `node_version`, `adapter_path` + **actual 64-hex `adapter_file_sha256`**, built CLI digest if packaged, command/route trace, browser-bridge/build/version, isolated session evidence; no user Chrome profile or third-party login |
| All three | Task list + final approved PR merge SHA (when available) | `task_spec_merge_sha`, `tasks_json_sha256`, tool/caller instruction hash, exact OS/VM image + browser build, approved network/egress policy, common `fixture_mode`, `task_id`, arm-specific source and runtime hashes, consent/policy flags, independent reset/oracle/audit evidence |

**Unresolved gates (NOT_RUN):** no actual CUA Driver binary digest or confirmed current batch/script-capable route for the requested older pinned commit; no authorized Pomerado mint, exact model IDs or artifact; no fixture-specific opencli adapter/digest or proven isolated browser bridge. A missing arm **blocks comparison**—do not replace it with an obsolete binary, direct HTTP, an unpinned npm installation or a different browser. If source capabilities force a different A pin, amend/review this preregistration **before** testing, never after seeing results.

Fixture reference: the main-branch file and #162's [`PREREG.json`](https://github.com/kvnloo/cua/blob/exp/pomerado-site-procedure-20261025/docs/experiments/pomerado-cua-2026-10-25/PREREG.json). #162's [optional `audit_fixture.py`](https://github.com/kvnloo/cua/blob/exp/pomerado-site-procedure-20261025/docs/experiments/pomerado-cua-2026-10-25/audit_fixture.py) adds mutation accounting, but is **not** part of main and may not be silently assumed. If used, pin its exact source/head and require independent `/audit` instance, epoch and lifetime counters. Without adequate no-write evidence, read-only safety **fails closed**, even if `GET /state` happens to return null.

## Frozen tasks and binary JSON oracles

Each arm receives the **instruction only**, task ID, approved starting path, mode and step/time budget. The evaluator alone loads `oracle` from `tasks.json`. Parse an arm's returned value as a single JSON object; normalize insignificant JSON object key ordering **only** (no case folding, whitespace rewriting within string values, fuzzy labels or hidden coercion). Exact deep equality with the independently confirmed expected JSON is binary success/failure; extra/missing keys fail. Verify fixture pre/post `GET /state == {"submitted":null}` with the evaluator's separate client; inspect read-only mutation counters where the audited wrapper is available. A tool-returned "success" without a demonstrated website route is never sufficient.

`max_steps` is the maximum **task-level observe/navigate/extract decisions** (not a limit imposed on one arm's library API call granularity); `timeout_s` is the **same whole-task deadline** for A/B/C, including retries and fallback, starting at task dispatch. Each attempt starts in a new isolated browser context; no real credentials or external URL. An arm may read `/state` as part of T09 only through its assigned website route; the evaluator's oracle channel remains independent.

| Task | Fixture mode | Start / allowed navigation | Instruction to all arms | Exact expected JSON | Max steps | Deadline |
| --- | --- | --- | --- | --- | ---: | ---: |
| `H2H-T01` | `default` | `/` → `/` | Read the document title from the initial fixture page. Return JSON with key title only. Do not modify any state. | `{"title":"Cua Driver Jev fixture"}` | 4 | 45s |
| `H2H-T02` | `default` | `/` → `/` | Read the main level-one heading. Return JSON with key heading only. Do not modify any state. | `{"heading":"Cua Driver + TypeSafe Jev fixture"}` | 4 | 45s |
| `H2H-T03` | `default` | `/` → `/` | Read the instructional paragraph above the form. Return JSON with key instruction only. Do not modify any state. | `{"instruction":"Enter the verification value and submit it."}` | 4 | 45s |
| `H2H-T04` | `default` | `/` → `/` | Read the form textbox's accessible name and whether it is required. Return JSON keys textbox_accessible_name and required. Do not enter text. | `{"textbox_accessible_name":"verification value","required":true}` | 4 | 45s |
| `H2H-T05` | `default` | `/` → `/` | Read the semantic Submit button's visible label and declared button type. Return JSON keys button_label and button_type. Do not click. | `{"button_label":"Submit","button_type":"submit"}` | 4 | 45s |
| `H2H-T06` | `default` | `/` → `/` | Inspect the form's declared HTTP method and relative action path. Return JSON keys form_method and form_action. Do not submit. | `{"form_method":"post","form_action":"/submit"}` | 4 | 45s |
| `H2H-T07` | `default` | `/` → `/` | Read the form's output status text and return the value after status= as JSON key status. Do not modify any state. | `{"status":"waiting"}` | 4 | 45s |
| `H2H-T08` | `default` | `/` → `/` | Count textbox controls and semantic Submit buttons on the page. Return JSON keys textbox_count and submit_button_count. Do not click or type. | `{"textbox_count":1,"submit_button_count":1}` | 4 | 45s |
| `H2H-T09` | `default` | `/` → `/` → `/state` | Read the heading at the root page, then navigate to /state within this fixture origin and return JSON keys heading and submitted from the JSON response. Do not alter fixture state. | `{"heading":"Cua Driver + TypeSafe Jev fixture","submitted":null}` | 6 | 45s |
| `H2H-T10` | `visual_submit` | `/` → `/` | On the fixture's visual-submit variant, read the text of the presentational Submit control and count semantic Submit buttons. Return JSON keys presentational_submit_text and submit_button_count. Do not click. | `{"presentational_submit_text":"Submit","submit_button_count":0}` | 4 | 45s |

`H2H-T10` requires a freshly launched fixture process with `--visual-fixture`; all other tasks use the ordinary mode. The two modes must never be compared against different page structures within a single task. These are **read-only observations**; `POST /submit`, clicking Submit, typing into the form, and issuing a reset **from any arm** are forbidden.

## Exact counterbalanced schedule — N=10 warm repeats per task per arm

**One unscored warm-up for each (task, arm)** using the same route and origin policy, after separately recording all mint/build/adapter preparation costs. Warm-up errors are logged as feasibility failures, never silently retried until they succeed. Thereafter exactly **five six-attempt mirrored blocks** per task, giving **ten warm attempts to each arm** and 30 attempts/task; ten tasks yield **300 planned scored attempts**. No trials have run.

Mirroring extends ABBA/BAAB to three arms: for each pair of different arms, both precedences occur equally often **within each block**; all arms receive two positions/block. The five patterns balance early/middle/late placements as closely as ten per-arm attempts permit. **Do not** run all A, then all B, then all C.

| Pattern | Exact attempt order (left to right) |
| --- | --- |
| P0 | `A B C C B A` |
| P1 | `B C A A C B` |
| P2 | `C A B B A C` |
| P3 | `A C B B C A` |
| P4 | `B A C C A B` |

Tasks run in ascending task-ID order; within each task execute the **five blocks in the specific order below**. Every character in a pattern represents exactly one independently reset attempt. Never reorder after viewing outcomes; record failures, timeouts and refusals in their assigned slots.

| Task | Chronological blocks; execute all six positions in each block |
| --- | --- |
| `H2H-T01` | P0 → P1 → P2 → P3 → P4 |
| `H2H-T02` | P1 → P2 → P3 → P4 → P0 |
| `H2H-T03` | P2 → P3 → P4 → P0 → P1 |
| `H2H-T04` | P3 → P4 → P0 → P1 → P2 |
| `H2H-T05` | P4 → P0 → P1 → P2 → P3 |
| `H2H-T06` | P0 → P1 → P2 → P3 → P4 |
| `H2H-T07` | P1 → P2 → P3 → P4 → P0 |
| `H2H-T08` | P2 → P3 → P4 → P0 → P1 |
| `H2H-T09` | P3 → P4 → P0 → P1 → P2 |
| `H2H-T10` | P4 → P0 → P1 → P2 → P3 |

At each slot, **operator** quiesces prior activity, performs the fixture reset out-of-band, independently checks `/state` (and pinned `/audit` if enabled), opens the matching fixture mode/origin in a fresh isolated browser context, dispatches the frozen instruction, logs real selected/executed route and all costs, then obtains a separate oracle + no-write snapshot. For `H2H-T09`, only the assigned arm navigates from `/` to `/state`. The operator must not send expected JSON to the arm. Preserve a separately approved manifest digest prior to the first execution; counterbalance and completeness are invalid without immutable pre-execution evidence.

## Scoring, receipts and attribution

One receipt per assigned slot, **including** failure, timeout, fallback, refusal and no-result; warm-up receipts have `scored=false`. Use the vocabulary in #162 [receipt schema](https://github.com/kvnloo/cua/blob/exp/pomerado-site-procedure-20261025/docs/experiments/pomerado-cua-2026-10-25/PREREG.json) but **do not feed this three-arm schema into the two-arm ABBA/BAAB analyzer** as if it supported C.

Mandatory fields per warm receipt: `schema=cua.h2h.receipt.v1`, `run_id`, `task_id`, `fixture_mode`, `block_index`, `pattern`, `position`, `assigned_arm`, `selected_route`, `observed_route`, `route_evidence`, all relevant **run-manifest** digests above, `start/end` timestamps plus monotonic `wall_time_ms`, `returned_json`, `oracle_match`, `verified_success`, `oracle_evidence`, `reset_verified`, `no_mutation_verified`, `model_calls`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `fallback_count`, `refusal`, `error`, `wrong_target`, `unauthorized_effect`, `origin_escape`, `uncertain_effect`, and `status` (`NOT_RUN | REAL | INVALID`). No invented zeros: a missing count is **unknown**, not zero.

- **`oracle_match`:** actual returned JSON exactly equals the task's expected JSON, irrespective of route; missing/incorrect output is false.
- **`verified_success`:** `oracle_match` **and** valid independent state/no-write attestation **and** origin/policy compliance **and** the *assigned native route actually observed*, with `fallback_count=0` and no unsafe side effects. A fallback to A during B/C is a **B/C attempted failure for the primary metric**, even if the final JSON is correct; record its recovered outcome separately.
- **Primary:** warm **native verified successes per wall-minute** = `sum(verified_success) / (sum(wall_time_ms for ALL eligible assigned scored attempts) / 60000)`. Failures, timeouts, refusals and fallbacks remain in denominator and count as zero successes. Timeouts consume their actual bounded elapsed time. No tool-count-only speedup.
- **Secondary:** median end-to-end wall time across **all assigned attempts** (and optionally conditional median among verified successes, separately labelled); provider/model requests, input/cached/output tokens, CPU/runtime cost, fallback rate, negative-case safety, and **cost per native verified success** (undefined if zero successes). One-time Pomerado mint/provider costs and one-time opencli authoring/build labor are reported separately from warm execution, then amortized at **1, 5, 20 and 100 verified/attempted uses with both denominators shown**. No fictitious free mint or zero developer labor.
- **Cohort accounting:** exactly all 30 slots per task, source/runtime pin match, same fixture and consent boundaries, independently reviewed route traces, plus no unsafe effects are mandatory before comparative summaries. A pin violation yields **`INVALID`**, not an excluded slow trial. Missing slots or an unavailable arm yield **`INCOMPLETE`**; all non-executed cells are **`NOT_RUN`**. No winner/rate/p-value from incomplete or mocked slots.
- **Ties:** compute ratios from unrounded counts/durations; exact equal verified success rates are **TIE**, and both zero is **NO VERIFIED WINNER**. If rates differ, rank descriptively but do not imply statistical significance with only ten repeats. Publish counts/uncertainty and paired block data, not just p50 latency. A policy/safety violation invalidates the corresponding attempt/cohort and halts further trials pending review.

## Fairness, isolation and freeze

1. Same isolated **Boat Linux 4-vCPU machine class**, actual CPU/RAM/OS image, Chromium build and allowed network policy for **every** arm; rotate scheduling as above. Same exact fixture source, mode, origin, initial state, browser isolation, step/timeout budgets and task instruction. Block on infrastructure mismatches; record cold/warm state and startup/warm-up overhead rather than changing a single arm's clock boundary.
2. A receives one frozen caller prompt template and model configuration for all eligible A trials, with the *task instruction* inserted without oracle. Current batch/script tools must be observed on the actual binary when eligible; if the pinned driver cannot expose them, **stop** rather than run a strawman baseline. B/C receive the identical task semantics but **cannot read the oracle/expected JSON or evaluator evidence**, including while minting, writing an adapter or retrying.
3. C cannot embed expected outputs or bypass the website with direct fixture HTTP; B cannot use stale minted scripts, unreviewed source changes or inherit CUA action permissions. C's browser bridge may not attach to a user's personal logged-in profile. Every arm must read the *live fixture* through its declared, independently traceable route. No credential, real account, third-party site, unexpected origin/redirect or unapproved egress.
4. No per-task hand-tuning, prompt/selector/adapter revision, browser-profile migration, remint, output postprocessing, retry-budget change or fixture-content change **after freeze**. **Freeze occurs only at this PR's eventual merge SHA** (not its draft HEAD). Any necessary correction gets a reviewed, versioned amendment and **new cohorts**; old results remain associated with the old spec.
5. No authority to mint models, buy capacity or run live tasks is conveyed by this document. Pomerado mint requires a separate approved provider budget and user consent; the other runners need isolated executable and route proof. All uncertain effects, missing audit capabilities or origin escapes fail closed.
6. Raw receipts and redacted route/oracle evidence must be retained for all assigned slots, including failures and cross-block order. The existing [#162](https://github.com/kvnloo/cua/pull/162) and [#163](https://github.com/kvnloo/cua/pull/163) gates can inform provenance but **do not** certify a three-arm run without compatible, independently reviewed execution evidence.

## Validation

Run from repository root using the Python standard library (no new dependencies):

```sh
python -m unittest docs/experiments/h2h-cua-pomerado-opencli/test_task_spec.py -v
```

The validator checks ten unique IDs, required bounded fields, paths restricted to `/` and `/state`, no absolute/external URLs in tasks, every task ID in this document, expected JSON against the pinned fixture HTML/state contract, and adverse examples (duplicate ID, missing oracle, invalid paths and off-origin URL). **Tests NOT RUN — ChatGPT cannot execute code in this connector-only task.** All 300 planned warm result cells and all per-arm warm-ups remain **NOT_RUN**.
