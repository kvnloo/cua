# OWN-78: backend receipts and partial-progress failure on the trycua/cua PR 4394 runners

**Disposition: REVISE.** Owner row kvnloo/cua#78 (also feeds kvnloo/cua#10 and kvnloo/cua#74). Upstream item: trycua/cua PR 4394, written as plain text here; nothing was posted upstream.

What held:
- On every live decision-bearing record, the content-free `backend` field matches the HTTP-evidenced responder (30/30).
- With the mock backend, records say `mock` and there is no HTTP at all (20/20 decisions, 0 attempts).
- When the provider fails after a landed mutation, the runner does not replay or restart. It ends with an explicit failure receipt (20/20, FIXTURE).

What did not hold, so KEEP fails:
- The PR's TypeSafe request drops the page/form state. Live TypeSafe then **abstains at step 1 in 30/30 measured trials** (plus 2/2 smoke), while the pre-PR runner verified 5/5 on the same Driver, provider, task and environment. So the live verified-outcome condition and the live partial-progress control cannot be met.
- 2 PR-added TypeScript tests fail in a credential-free environment.

No KILL condition fired.

## Provenance (each SHA separate)

| item | value |
|---|---|
| tested source (runners) | `039257811e0bbb2348c616c52562409923d2856f`, trycua/cua PR 4394 head, `libs/cua-driver/examples/jev-use` only |
| tested source base | `2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4` |
| PR 4394 live head at start (01:49Z) and end (02:19Z) | `039257811e0bbb2348c616c52562409923d2856f` both times, OPEN, no drift (`gh pr view 4394 -R trycua/cua`, read-only) |
| R0 control source | `2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4`, the pre-PR runner |
| Driver | built from `039257811`, sha256 `19bad35248702fd42f6aa372f1f4bebe4ca3728d9be0f67287f1c186a0b47df9`, `cua-driver 0.31.0` (re-recorded inside the isolated session). The PR changes no `libs/cua-driver/rust` file, so this is also the base's Driver. build-driver.sh's trailing `--version` ran once outside the session, with no display access. |
| PREREG commit | `c263e28955f4e6165b8b91ea0686cecaf089cab9`, before every trial, smoke included |
| amendment 1 + harness commit | `68ff8eea0ffa8f9ff1e3e7f80185651458bbc900`, after smoke, before every measured trial |
| publication SHA | the branch commit that adds this README (branch `exp/own-78-provider-receipts-4394-20261002`) |
| environment | `cua-x11-session.sh` (private rootless Xvfb, private dbus, scrubbed env, no AT-SPI); Google Chrome 151.0.7922.71 launched by the Driver; default Driver safety; Python 3.12.13, node v22.23.2, typesafe SDKs 0.6.0, MCP SDKs 1.30.0; provider TypeSafe `api.typesafe.ai`, model `jev-1.13.0` |

The full record is in `provenance.json`. Every block's `raw/<block>/validity.json` confirms three things: the examples and Rust trees are identical to the tested SHA, the Driver sha256 matches, and no forbidden env is present.

## Method

- **Forced backend/path.**
  - `--provider typesafe` (R1, R3, R4, R4s), `--provider mock` (R2), `--provider live` on the pre-PR runner (R0).
  - R3: `TYPESAFE_BASE_URL` points at a closed loopback port from the start.
  - R4/R4s: after the first `browser_type` returns ok, an env-gated launcher seam (`OWN78_SWITCH_BASE_URL`) switches `TYPESAFE_BASE_URL` to a closed loopback port. Both runners build a new TypeSafe client per decision, so step 2 targets the closed port. Runner code is unchanged.
- **Actual responder attribution (measurement-only, env-gated, default-off).**
  - Python: `harness/receipt_launcher.py` imports the unmodified `run.py` and wraps `httpx2.Client.request`, `TypeSafeClient.system_one`, the mock policy and `Driver.call`.
  - TypeScript: `harness/ts_receipts.mjs` is a `node --import` preload that wraps `globalThis.fetch` (the SDK calls it once per attempt) and MCP `Client.prototype.callTool`.
  - Per HTTP attempt they record host, path, status, request-id presence and a sha256 prefix, model, token usage and selected id.
  - The responder is classified from the **HTTP host only**, never from configuration.
  - Nothing records headers, bodies, typed text or the key.
- **Independent target-owned oracle.** `harness/own78_harness.py` runs the fixture server and counts four things on the server: `GET /` (navigations), `POST /reset` (routine starts), `POST /submit` and `/state`.
  - R3/R4/R4s use an experiment-owned journal variant. Its page POSTs every `input` event to `/event/input`, and the server keeps only `{seq, length, equals_token, trusted, input_type}`.
  - An *input mutation* is a transition into the token state, ordered by page seq. A `browser_type` replay with `replace: true` would count again.
  - Smoke confirmed that one `browser_type` is exactly one trusted `insertText` event.
- **Controls.**
  - R2 (mock, key removed) against R1 (live) checks that the field tracks the handler.
  - R3 separates "unreachable before progress" from "after progress".
  - R0 (pre-PR runner) attributes the abstain to the request change.
  - R4s (amendment 1) drives step 1 with a loopback stub speaking the TypeSafe wire format, using a dummy non-secret key. The stub records only criteria ids, the chosen id and whether an Authorization header was present.
- **Locks.** Every block ran inside the isolated session under `flock -s quiet-lane.lock`, at most 10 cells per acquisition. Every trial is kept and there are no replacements.

## Results (all measured trials; N of M; evidence class per row)

| row | class | n (py/ts) | result | registered pass |
|---|---|---|---|---|
| R1 forced TypeSafe | LIVE_PROVIDER+REAL | 10 (6/4) | 10 decisions, all `abstain` at step 1. `backend` == HTTP responder (`api.typesafe.ai`, 200, same selected id, request-id hash match) **10/10**. decisions == 200s in every trial. Fixture verified **0/10**, submits 0. | no (needs 20/20 with verified outcomes) |
| R2 mock | REAL | 10 (5/5) | 20 decisions, all `backend=mock`. **0 HTTP attempts**. Verified 10/10. | yes |
| R3 unreachable before progress | REAL | 6 (3/3) | 0 input events, 0 mutations, 0 submits **6/6**. 0 decision records. Explicit `outcome=unknown phase=decide step=1`, exit 1, **6/6**. 0 reached, 18 loopback-refused. | yes |
| R4 live partial progress | LIVE_PROVIDER+REAL | 20 (12/8) | Step 1 `abstain` **20/20**, so the precondition was met **0/20**. No mutation, no switch. 0 replays, 0 restarts. Failure receipts 0/20 (runs ended `abstained`). | no (precondition never met) |
| R4s stub partial progress (amendment 1) | FIXTURE+REAL | 20 (12/8) | **20/20 pass**: input mutations = 1, submits = 0, `browser_type` = 1, navigations = 1, routine starts = 1, `browser_prepare` = 1, 1 decision. Final `outcome=unknown phase=decide step=2`, exit 1. Every post-switch attempt loopback-refused (60). | yes (FIXTURE, outside the KEEP gate) |
| R0 pre-PR runner control (amendment 1) | LIVE_PROVIDER+REAL | 5 (5/0) | Step 1 `type-verification-value` **5/5** (P(type) 0.81 to 0.85), then submit. Verified **5/5**. Responder `api.typesafe.ai` 10/10. | n/a (attribution control) |
| R5 S1 backend | BLOCKED | 0 | adapter not local; non-TypeSafe provider not permitted | n/a |
| UNIT | UNIT | n/a | Python `unittest discover` 233 OK (1 skipped). `verify_choice_cli`/`verify_decision_cli` (mock, v2, native) rc 0. TS typecheck rc 0. **TS `npm test` 107/109.** The two `guarded-focused` steps are #4316-only, so they don't apply at this head. | no |

## Findings

1. **The backend field is configuration-derived adapter identity (SOURCE + FIXTURE).**
   - `browser_provider.backend_name(provider)` maps the configured `--provider` to the string. Nothing reads it from the response.
   - It matched the HTTP responder on every live record (R1 10/10, R4 20/20), and on mock it was `mock` with no HTTP (R2).
   - That holds only because `choose_browser_provider` has no fallback between backends.
   - R4s shows the semantics directly: the step-1 record says `backend=typesafe` while the HTTP responder was the loopback stub (20/20).
   - The field names which client handled the decision, not which network endpoint answered.
2. **The PR's TypeSafe request regresses the browser fixture task (LIVE_PROVIDER + SOURCE).**
   - `browser_decision_request` sends goal, capture_id, regions (empty on the page-structure path), history and candidate ids/descriptions.
   - The pre-PR `task_decision_state` also sent `observation.page`, `observation.form` (the runner-verified state summary: field empty, Submit available) and `observation.outline`.
   - On the same Driver, provider, task and session type, P(type) at step 1 was 0.07 to 0.12 on the PR runner (R1+R4, 30 decisions; P(abstain) 0.51 to 0.66). It was 0.81 to 0.85 on the pre-PR runner (R0).
   - Median input tokens were 526.5 on the PR runner (R1+R4, range 515 to 534) vs 638 on the pre-PR runner (R0 step 1).
   - Both runtimes behave the same: TS shares the same request shape.
3. **No replay after partial progress (FIXTURE).**
   - On the PR runner code path, a provider failure after `browser_type` landed ends in an explicit decide-phase failure. The first mutation is not replayed, the routine does not restart and nothing is submitted (R4s 20/20, Python 12 and TS 8).
   - The live version of this control (R4) could not be reached because of finding 2.
4. **Failure receipts name the attempted backend.**
   - On decide-phase failures (R3 6/6, R4s step 2 20/20), the receipt carries `backend: "typesafe"` even though no TypeSafe response arrived.
   - These records carry no candidate, confidence or probabilities, and are never counted as decisions (configured intent counted as a decision: 0).
   - A consumer must read `backend` on a failure receipt as "attempted", not "handled". This is pre-registered as not KILL.
5. **Two PR-added TS tests fail in a credential-free environment (UNIT).** The upstream "CI: jev-use" workflow reads no secret, and it has not run on PR 4394 (only contributor-attribution and release-reminder checks are listed).
   - `live and typesafe aliases report typesafe…` throws `No API key was provided`: the `TypeSafeClient` constructor checks the key before the mocked `systemOne` runs. With a dummy key the test passes, so this is an env dependence.
   - `S1 uses the bounded browser request…` throws `CUA_S1_DECISION_URL is not set`. With the URL set it still fails (`response is not a cua.decision_choice_v1 decision`), because the mocked response does not satisfy the strict S1 validator. This test is broken by construction.

   Details are in `raw/unit/ts-failures.json`.

## Correctness invariants (E4), all measured trials (71)

| invariant | count |
|---|---|
| decision-bearing receipt naming a backend that did not handle the request (live + mock rows) | 0 |
| decision counted without a provider response | 0 |
| replay of `browser_type` after partial progress | 0 |
| restart (extra navigation, routine start or `browser_prepare`) | 0 |
| duplicate submits | 0 |
| unverified success (runner `verified` without oracle) | 0 |
| configured intent counted as a decision | 0 |
| timeouts / harness errors | 0 / 0 |

## Provider budget (TypeSafe)

- **Reached: 42** of the lane cap of 45. By phase: smoke-live 2, R1 10, R4 20, R0 10.
- Loopback-refused attempts: 90. These count as attempts, not reached.
- **Attempts counted: 132.**
- 22 further HTTP attempts were answered by the loopback stub (R4s and smoke-d). They are not provider attempts.
- Guard refusals: 0.
- `raw/budget.json` holds all 154 HTTP attempts. `verify_artifacts.py` reconciles the three classes.

## Component timings, work deleted, wall-clock

This is a correctness lane, so there is no timing claim, no work deleted and no wall-clock saved. Per-trial wall times are descriptive only, and are short when the run ends at step 1. Medians: R1 1.81 s, R4 2.07 s, R3 3.22 s, R2 4.79 s, R4s 4.82 s, R0 5.02 s. 1-minute loadavg at spawn was 4.0 to 14.6, with other lanes active.

## Deviations (all disclosed in raw/)

- **Amendment 1 (R4s, R0).** It was registered after smoke-live showed step-1 abstain and before any measured trial. R1 to R4 ran exactly as registered.
- **Smoke-only row S2** (mock on the journal fixture) was added to check journal counting without spending budget.
- **smoke-c.** In 2 R4s smoke cells the Chrome window did not become visible within the runner's 10 s `wait_for_window`. Both failed before any decision. The runner raised an exception without writing an outcome record. This did not reproduce in smoke-d or in any measured cell. It is kept in `raw/smoke-c`.
- **Receipt sanitizer.** After smoke, and before the harness commit, it was simplified from absolute-path prefixes to "any `/`" for whitelisted Driver result scalars. No observed value contains `/`.
- **TS mock receipts.** The TS mock path has no in-process receipt, because ESM bindings cannot be patched from a preload. TS R2 attribution rests on the `backend` field plus 0 provider fetches. Python R2 has mock receipts (10/10 trials).
- **Skipped R4 trials.** The spec planned "R1 20 + R4 20" reached. Because step 1 abstained, R1 used 10 and R4 used 20. The R0 control used 10 of the remainder under the amendment's rule.

## Limits and claim boundary

- Covered: PR 4394 code at `039257811` with its own-base Driver; TypeSafe and mock only; Python and TS runners; X11 Xvfb; Chrome.
- No timing claim.
- Not covered: the PR 4316 runner, and S1 (R5 BLOCKED).
- R4s is FIXTURE evidence: the step-1 responder was a loopback stub, not TypeSafe.
- The abstain finding is for model `jev-1.13.0` on this fixture task.

## Disposition and revised claim

**REVISE.** Measured revised claim:

- On PR 4394 at `039257811`, the backend field on decision-bearing records equals the HTTP-evidenced responder for 30/30 live and 20/20 mock decisions.
- The field is configuration-derived adapter identity, as shown by the stub (20/20).
- A provider failure after partial progress ends in an explicit failure receipt with no replay or restart (20/20, FIXTURE).
- But the PR's TypeSafe request omits the form state, and the live fixture task abstains at step 1 (30/30 measured plus 2/2 smoke, against 5/5 verified pre-PR). The live verified-outcome and live partial-progress conditions are therefore unmet.
- 2 TS tests fail credential-free.

To reach KEEP, all of the following are needed:
- (a) Restore the runner-verified state (`form`, and `page`/`outline` or an equivalent) in the bounded request.
- (b) Make both TS tests credential-free: inject a client, or pass `apiKey`, and return a valid `cua.decision_choice_v1` body.
- (c) Rerun R1 and R4 live.
- Optionally, (d) rename or document `backend` on failure receipts as the attempted backend.

## Files

- `PREREG.json`, `PREREG-AMENDMENT-1.json`
- `harness/`: launcher, preload, cell harness, phase wrapper, raw packager
- `raw/<block>/<cell>.jsonl`: one file per trial, holding the cell record, runner events, receipts, journal and stub log
- `raw/<block>/validity.json`, `end.json`, `cells.jsonl`; `raw/budget.json`; `raw/unit/`; `raw/build-driver.out`
- `analyze.py` writes `own78-summary.json`
- `verify_artifacts.py` recomputes counts from `raw/`, cross-checks every decision record against HTTP evidence, reconciles the budget, checks the oracle counts, scans for privacy and checks prereg ordering against git. Run it with `python3 verify_artifacts.py`.

Raw outputs, including runner stdout/stderr and full unit logs that are not committed, are mirrored locally under the lane artifacts directory `OWN-78/`.
