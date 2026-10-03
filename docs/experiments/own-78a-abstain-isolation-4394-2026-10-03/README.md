# OWN-78A: which request change makes trycua/cua PR 4394's TypeSafe runner abstain at step 1, and a credential-free fork fix candidate, 2026-10-03

Lane OWN-78A, wave 5. Owner rows: kvnloo/cua#78 (also kvnloo/cua#93 and kvnloo/cua#74). The upstream item is written as plain text: trycua/cua PR 4394. Nothing was pushed or posted.

**Disposition: REVISE.** Two of the three KEEP conditions hold: UNIT 109/109 credential-free, and A2 correct-type 5/5. The third does not: R1-lite did not run. After Part B, 4 of the 24 reached remained, and Part C needed 6 (BLOCKED: lane cap).

## Result in one paragraph

On the jev-use fixture task, each arm ran 5 Williams-ordered trials. Each trial records one live TypeSafe step-1 decision and dispatches nothing.
- The PR request abstained every time: A0 abstain **5/5**, P(type) 0.09-0.12.
- The pre-PR request typed into the right field every time: A3 correct-type **5/5**, P(type) 0.81-0.87. So the comparison is valid.
- Adding only the runner-verified `form` state was not enough: A1 correct-type **1/5**, P(type) 0.34-0.45.
- Adding `form`, `page` and `outline` (the fork fix candidate F) restored typing: A2 correct-type **5/5**, P(type) 0.50-0.53.

The pre-registered rule therefore gives **PAGE_OUTLINE_ALSO_NEEDED**: omitting `form` alone does not explain the abstain, and `page`/`outline` are also needed.

On every PR/F decision record, `backend` equals the HTTP responder (15/15), and all 20 decisions are HTTP 200 with a matching request id. E4 is 0 in every arm. Provider use is 20 attempts / 20 reached, inside the lane cap of 24 / 30.

The two TS tests that failed in OWN-78 now pass credential-free: 109/109 on F, against 107/109 on the PR head.

Note that A2's margin over abstain is thin: P(type) − P(abstain) is 0.08 to 0.12. It is also still well below the pre-PR P(type). The question key, the instructions, `goal`/`history` placement and `visual` also differ between A2 and A3. That remaining gap is not isolated.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | Every Part B trial runs the runner's own `--dry-run --max-steps 1`. The runner writes one step-1 decision record (a `step` event, or `outcome=abstained`) and dispatches nothing. As a backstop, the launcher's `OWN78A_FORBID_MUTATION=1` refuses any mutating Driver tool before dispatch; there were 0 refusals. Each trial's own records prove the path: one `provider_request`, one ok `provider_response`, 0 `browser_type`/`browser_click` calls, and the fixture shows 0 input events, 0 submits and `submitted=null` (20/20). | REAL |
| Actual route / producer | The decision producer is attributed from HTTP evidence. The launcher wraps `httpx2.Client.request` (host, path, status, request id sha256/16) and `TypeSafeClient.system_one` (responder classified from the HTTP host, model, tokens, selected id). The Driver route is real Chrome via `browser_prepare`/`get_browser_state`; no action was dispatched. | LIVE_PROVIDER+REAL |
| Independent target-owned oracle | The fixture page (journal variant) POSTs every `input` event on `input[name=value]`, and the server counts `/submit`. `/state` reports `submitted`. The correct field is the fixture's own `aria-label` "verification value" on `input[name=value]`, read from the fixture source. The chosen ref must resolve to the one textbox with that name. | REAL |
| Negative / fallback controls | A0 (PR as-is) must abstain and A3 (pre-PR) must type. Both held, so the isolation discriminates. The A1 seam is a single-factor control. The stub smoke (0 provider) shows each arm's exact wire field names. Unit red: F1's tests fail without F1 (U-RED-F1). | LIVE_PROVIDER+REAL, FIXTURE, UNIT |
| Tested source SHAs | PR `039257811e0bbb2348c616c52562409923d2856f` (A0, A1, U-PR). F `61eec09092fd161f62651a890c882f276a642855` (A2, U-F), which is F1 `736410ea1`, F2 `9d8aad90c` and F3 `61eec0909` on the PR. Pre-PR `2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4` (A3). Examples tree ids are in `provenance.json`. Every block checked each exported file against its git blob id. | SOURCE |
| Driver binary | `cua-driver-own78-4394-0392578`, sha256 `19bad35248702fd42f6aa372f1f4bebe4ca3728d9be0f67287f1c186a0b47df9`, `cua-driver 0.31.0` (read inside the session in every block). No build: neither the PR nor F touches `libs/cua-driver/rust`. | SOURCE |
| Environment | Private rootless Xvfb via `cua-x11-session.sh` (private dbus, scrubbed env, no AT-SPI), launched under `bin/hostless`, with 0-3 s jitter and an `xdpyinfo` probe per block. Chrome was launched by the Driver (isolated profile, sandbox on, default safety). Python 3.12.13 for the runners; node v22.23.2 for the unit rows only. loadavg at block start was 4.4 to 12.1 (no timing claims). | SOURCE |
| PREREG commit | `99632b75fe0c05d909576739e7bbefbeb249c546`, committed 2026-10-03T07:30:29Z. That is before the recorded unit runs (07:30:58Z), the smoke (07:35:14Z) and the first provider request (L1, 07:36:25Z). The harness and launcher sha256 in every block equal that commit's files. | SOURCE |
| Live PR heads at test time | trycua/cua PR 4394 head `039257811e0bbb2348c616c52562409923d2856f`, OPEN, both at start (07:17:54Z) and at end (07:39:54Z) (`gh pr view`, read-only). The claim is pinned to that SHA. | SOURCE |
| Publication SHA | Set by Publish (`provenance.json: publication_sha`, a placeholder here). It is not the tested SHA. | SOURCE |
| Live heads at publication | Set by Publish. | SOURCE |
| Provider | TypeSafe `api.typesafe.ai`, model `jev-1.13.0` (as recorded). 20 attempts / 20 reached; lane cap 24 reached / 30 attempts; 0 guard refusals. The key was forwarded by name only. | LIVE_PROVIDER |

## Method

**Part A: fix candidate (UNIT + SOURCE, credential-free).**

- **F1** (`736410ea1`) adds `runner_verified_state(task, sources)` in Python and `runnerVerifiedState` in TS: `page`, `form` and `outline`, secret-redacted. These are the same values the pre-PR `task_decision_state` built, and `task_decision_state` now reuses the helper (byte-identical).
  - The TypeSafe observation is now `{capture_id, regions, history}` (the PR's, unchanged) + `{page, form, outline}`.
  - In Python this goes through an optional `runner_state` on `TypeSafeDecisionModel`. In TS it is a spread into `chooseBoundedWithTypeSafe`.
  - The validated `cua.jev_choice_request_v1`, the S1 path, every PR field and the `backend` receipt semantics are unchanged.
- **F2** (`9d8aad90c`) gives `chooseBrowserProvider` optional injected dependencies (`typesafeClient`, `s1Url`); the defaults are unchanged.
  - The aliases test injects a fake client and also asserts the restored state.
  - The S1 test injects the URL and returns a valid `cua.decision_choice_v1` body.
- **F3** (`61eec0909`) is documentation only: `backend` on a decide-phase failure receipt names the attempted backend.
- **Unit runs.** `harness/unit.sh` runs the CI commands under `bin/hostless`, with `env -u TYPESAFE_API_KEY` and every `TYPESAFE_*`/`CUA_S1_*` variable unset (recorded `credential_env_present=0`). It ran on three trees exported by SHA:
  - PR (U-PR);
  - F (U-F);
  - RED, which is PR + F2's TS changes without F1 + F1's Python test (`raw/unit/red-tree.diff`).

**Part B: isolation (LIVE_PROVIDER+REAL).**

- **Arms.**
  - A0: PR runner, `--provider typesafe`.
  - A1: PR runner + the env-gated launcher seam `OWN78A_SEAM_ADD_FORM=1`, which adds only `observation.form = task.state_summary(sources)`.
  - A2: F runner.
  - A3: pre-PR runner, `--provider live`.
- **Design.** 5 rounds. Rounds 1-4 form a 4x4 Williams square and round 5 repeats round 1 (PREREG `design.order`). The blocks were L1 (rounds 1-2), L2 (3-4) and L3 (5), each under `flock -s quiet-lane.lock` with at most 10 cells per acquisition (lock receipts `own78a-L1..L3` in `raw/locks.jsonl`). Every trial is kept, with no replacements.
- **Budget guard.** The launcher counts every non-loopback attempt before sending. Its per-cell allowance is 1 reached / 2 attempts. The harness does not start a cell that the remaining lane cap cannot cover.
- **Smoke (FIXTURE).** Before any request, the arms A0..A3 and C ran against a loopback stub speaking the TypeSafe wire format, with a dummy non-secret key and 0 provider requests.

**Part C: R1-lite.** The precondition was registered as at least 6 reached left. 24 − 20 = 4, so Part C was not run.

## Request shape (field names only)

| Request | `state` key paths sent | question / instructions | Evidence class |
|---|---|---|---|
| PR (A0) | `observation.{capture_id, regions, history}` | `candidate`; instructions = task goal (88 chars, sha256/16 `93f13cd3c9968119`) | SOURCE + FIXTURE (wire) + LIVE (SDK) |
| PR + form (A1) | A0 + `observation.form.{verification_field, submit_button}` | same as A0 | same |
| F = PR + form + page + outline (A2) | A0 + `observation.page.{title, url}`, `observation.form.{...}`, `observation.outline` | same as A0 | same |
| pre-PR (A3) | `goal`, `observation.{page.{title,url}, form.{...}, outline, visual}`, `history` | `driver_action`; "Which complete executable action should Cua Driver run next?" (60 chars, `be0bd953302a388d`) | same |
| TS runner (PR and F) | Same keys as the Python runner; `observation` is one JSON string | same as Python | SOURCE + UNIT (TS test asserts the F keys) |

The smoke recorded the same key paths both on the wire (in the stub) and at the SDK boundary, for every arm (`own78a-summary.json: smoke`). In the live trials, the key paths were identical across the 5 trials of each arm.

## Results (N of M, evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| U-PR (PR head, credential-free) | TS 107/109 | Exactly the two named failures ('S1 uses the bounded browser request...', 'live and typesafe aliases report typesafe...'). Python 233 OK (1 skipped). Typecheck rc 0. 4 CLI verifiers rc 0. | UNIT |
| U-F (fix candidate, credential-free) | TS **109/109** | Python 234 OK (1 skipped; +1 F1 test). Typecheck rc 0. 4 CLI verifiers rc 0. | UNIT |
| U-RED-F1 (F1's tests without F1) | TS 108/109, Python 1 error | Only `test_typesafe_request_restores_runner_verified_page_state` (`KeyError: 'form'`) and the TS aliases test (restored-`form` deepEqual: actual `undefined`) fail. This is the red for F1. | UNIT |
| A0 PR request | 5 of 5 | A0 abstain **5/5**. P(type) 0.09-0.12, P(abstain) 0.61-0.64. Input tokens median 529 (525-534). | LIVE_PROVIDER+REAL |
| A1 PR + form | 5 of 5 | A1 correct-type **1/5** (4 abstain). P(type) 0.34-0.45, P(abstain) 0.43-0.56. Input tokens median 554. | LIVE_PROVIDER+REAL |
| A2 F (PR + form + page + outline) | 5 of 5 | A2 correct-type **5/5**. P(type) 0.50-0.53, P(abstain) 0.41-0.43. Input tokens median 697 (694-701). | LIVE_PROVIDER+REAL |
| A3 pre-PR request (control) | 5 of 5 | A3 correct-type **5/5**. P(type) 0.81-0.87, P(abstain) 0.08-0.12. Input tokens 638. | LIVE_PROVIDER+REAL |
| Attribution (pre-registered rule) | 20 of 20 | Valid (A0 ≥ 4/5 abstain, A3 ≥ 4/5 correct-type). A1 ≤ 1/5 and A2 ≥ 4/5, so **PAGE_OUTLINE_ALSO_NEEDED**. | LIVE_PROVIDER+REAL |
| Correct target | 11 of 11 type decisions | The chosen `type-verification-value` ref resolved to the single textbox named by the fixture's own aria-label "verification value" every time. | REAL |
| backend == responder | 15 of 15 (A0, A1, A2) | `backend: typesafe` == responder `api.typesafe.ai`, HTTP 200, request-id sha256/16 equal. A3: n/a (the pre-PR runner has no backend field), but HTTP-evidenced responder 5/5. | LIVE_PROVIDER |
| No mutation in dry-run trials | 20 of 20 | 0 input events, 0 submits, `submitted=null`, 0 mutating Driver calls, 0 backstop refusals. | REAL |
| Smoke (stub, all arms + C) | 5 of 5 | The field names per arm are as in the table above. The A1 seam added only `form`. C on F verified end to end: submitted == token, 1 submit, 1 input event. 0 provider requests. | FIXTURE |
| R1-lite on F (3 trials) | 0 of 3 | NOT_RUN. The precondition (≥ 6 reached left) was not met: 4 left after Part B. | BLOCKED |
| R1 live full n=20 / R4 live full n=20 | 0 | NOT_RUN. Needs about 60 reached. | BLOCKED (budget) |
| R4 live partial progress (this lane) | 0 | NOT_RUN | BLOCKED (budget) |
| S1 backend row | 0 | The adapter is not local, and only TypeSafe is permitted. | BLOCKED |

**E4 per arm (A0, A1, A2, A3):** every arm is 0 on each count: 0 duplicate mutations, 0 unverified successes, 0 replays after partial progress, 0 decisions counted from failure receipts. There were 0 failure receipts at all. Decisions come only from ok `provider_response` receipts.

**Budget:** 20 attempts / 20 reached, all to `api.typesafe.ai`, all status 200, all with a request id, 0 guard refusals (`raw/provider-ledger.jsonl`, `raw/budget.json`). The smoke and the unit rows used 0 provider requests.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Evidence class |
|---|---|---|---|
| F1 restored state | None: this is a correctness fix. It adds about 168 input tokens per step-1 decision (median 697 vs 529). | Not measured (no timing claim) | LIVE_PROVIDER |

Component timings: none were measured. This lane makes no timing claim, so it adds no critical-path rows.

## Deviations

- **Unit attempt 1** (07:30:58Z) used tree exports that lacked two repository files the Python suite reads (`.github/workflows/authorized-live-jev-use.yml` and the GTK3 fixture under `libs/cua-driver/tests`).
  - The same 2 environment errors appeared on all three trees (`raw/unit/attempt1-incomplete-export-*`).
  - The exports were completed by SHA and re-run at 07:33:38Z. Those are the reported rows.
  - The TS results were identical in both attempts.
- **Development runs.** F1/F2 were also run during development, before the PREREG commit, in the lane worktree. Those runs are not reported.
- **Fixture.** All arms used the journal variant of the fixture, so the no-mutation oracle is target-owned. OWN-78's pre-PR control used the stock page, and the results agree (OWN-78 P(type) 0.81-0.85; here 0.81-0.87).
- **A1 seam location.** A1 is the PR tree plus a measurement-only, env-gated launcher seam, not a product change. The seam adds `form` at the same position in the observation as F does.
- **Near miss.** Before any lane work, the agent ran `python3` in the plain host shell twice. Both only parsed the loop's state JSON, with no GUI import and no display access. Every later code-executing command ran under `bin/hostless`.

## Limits and claim boundary

- **Covered:** model `jev-1.13.0` as recorded; this fixture task (fill → submit, step 1 only); the Python runner; Linux private Xvfb; Chrome; Driver 0.31.0 built from `039257811`.
- **n = 5 per arm.** A2's typing margin is thin (P(type) − P(abstain) is 0.08-0.12 per trial), and P(type) stays below the pre-PR request's. The other differences between A2 and A3 (question key, instructions, `goal`/`history` placement, `visual`) are not isolated. More n is BLOCKED (budget).
- **TS:** request-shape parity and the restored keys are SOURCE + UNIT only; there were no live TS trials.
- **End-to-end on F:** stub-only (FIXTURE). R1-lite was not run live.
- **Scope of F:** a fork fix candidate on top of an upstream PR. Nothing was pushed, posted or linked upstream.
- **No new service.** The seams are measurement-only, env-gated and default-off.

## Disposition

**REVISE** (kvnloo/cua#78, fork fix candidate F at `61eec0909`), by the pre-registered rule.
- UNIT 109/109 credential-free: **held**.
- A2 correct-type ≥ 4/5: **held** (5/5).
- R1-lite 3/3 verified with backend == responder: **failing row**, NOT_RUN (BLOCKED: lane cap; Part B used 20 of 24 reached and R1-lite needs up to 6).

Revised claim (measured): on the PR request the step-1 abstain is not caused by the `form` omission alone. Restoring `form` + `page` + `outline` (F1) turns the abstain into a correct-field type 5/5, and F makes both TS tests pass credential-free.

KEEP needs 3 live R1-lite trials on F, at most 6 reached. Full-n live R1 20 / R4 20 (about 60 reached) and the S1 backend row stay BLOCKED.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed before every recorded run and request |
| `README.md` | this file |
| `.gitignore` | packet-local template ignore rules |
| `provenance.json` | SHAs, heads at start/end, Driver, environment, publication-SHA placeholder |
| `own78a-summary.json` | every number above, recomputed by `analyze.py` from `raw/` |
| `analyze.py` | writes `own78a-summary.json` |
| `verify_artifacts.py` | recomputes the summary, checks headlines, units, budget, locks, ordering, privacy of every commit, cited files |
| `verify_helper.py` | template cited-file check (copied from `docs/experiments/_template/` at cca59642d) |
| `harness/own78a_harness.py` | cell harness (trees, fixture oracle, stub, budget) |
| `harness/own78a_launcher.py` | measurement-only launcher (receipts, budget guard, A1 seam, mutation backstop) |
| `harness/live_block.sh`, `harness/in_session.sh` | shared-lock block wrapper; in-session jitter + `xdpyinfo` probe |
| `harness/unit.sh` | credential-free unit runner |
| `harness/package_raw.py` | copies the lane outputs into `raw/` |
| `harness/privacy_scan.py` | privacy scan of every commit (names from an untracked `CUA_PRIVACY_NAMES_FILE`) |
| `raw/L1/`, `raw/L2/`, `raw/L3/` | per block: `validity.json`, `end.json`, `cells.jsonl`, one `<cell>.jsonl` per trial (cell, runner events, receipts, journal) |
| `raw/smoke/` | stub smoke, same layout plus stub records |
| `raw/provider-ledger.jsonl` | host, path, status, request-id presence + sha256/16, latency, trial per attempt |
| `raw/budget.json`, `raw/locks.jsonl` | lane budget; shared-lock receipts |
| `raw/unit/` | `pr/`, `f/`, `red/` and `attempt1-incomplete-export-*/`: `steps.txt`, `env.txt`, `summary.json`; `red-tree.diff` |

Run `python3 verify_artifacts.py` from a clone of the branch, under the lane's `bin/hostless`, with `CUA_PRIVACY_NAMES_FILE` set to an untracked names file. Runner stdout/stderr and the full unit logs are not committed. They are mirrored in the lane artifacts directory `OWN-78A/`.
