# i107 lane D: checked execution, D(A-reads) vs A, on the PR 4316 guarded continuation (2026-10-02)

kvnloo/cua#107, comparison arm D. Packet format follows kvnloo/cua PR #106. Upstream items are written as plain text. `<lanes>` is the lanes root.

**Disposition (decision table, map PREREG): REVISE D (missing dependency fact); no promotion.** D deletes one chooser decision per task (2 to 1) with no change to observation, producer RPCs, mutations or outcome. With the scripted mock chooser that deleted decision is worth about 0 ms: the paired effect is NO_MEANINGFUL_BENEFIT in W-quiet, W-churn and K2. In the relocated look-alike control (DC06), D's guard accepted a Submit button that had been moved into a different form and submitted to the decoy, 5 out of 5 times. PR 4316 binds role, name and uniqueness only. The live-provider value of the deleted decision is BLOCKED pending owner budget.

Every row is FIXTURE/BENCHMARK with the chooser named: `choose_mock_for_task` (scripted mock, 0 provider HTTP). No row is LIVE_PROVIDER. TypeSafe requests: 0.

## Identities (kept separate)

| Item | Value |
|---|---|
| Live PR head | trycua/cua PR 4316 `a0bca744067d04f05904319d3d919be30c336556`, OPEN, `mergedAt` null. Read at lane start (04:53:03Z) and end (07:20:08Z), unchanged. Files: `raw/pr4316-head-{start,end}.json` |
| Tested source | branch `exp/i107-d-20261002` from `be68363bc` (map packet HEAD). `libs/cua-driver` tree `a87dc39d`. Caller jev-use tree `72bf8156`, byte-identical to the jev-use tree at `a0bca7440`. Lane commits touch only this directory |
| Harness commit per REAL run | smoke and shakedown: `d08023e61`. Every measured group (CMP-D, K2, controls): `bf0336e27`. The group runs are recorded in `raw/real/chain-log.jsonl` |
| Driver | `cua-driver-i107-092b065d5`, sha256 `f3a5c01a…7aed`, 0.32.0, both arms, not rebuilt. `run_d.py` refuses any other sha256 |
| Chrome | Driver-selected `/opt/google/chrome/chrome`, `isolated_new`, sandbox on |
| Pre-registration | `PREREG.json` committed in `3b40d8333` (05:23:24Z). `PREREG-AMENDMENT-1.json` committed in `d08023e61` (05:43:02Z). Both precede the first measured trial (06:31:27Z). Consistent with map PREREG sha256 `8eeb837f…2c53` |

## Method

- **Arms.** A is jev-use `python/run.py` `run()` without `--guarded-completion`. D is the same call with `--guarded-completion`. `run()` itself is not edited. `harness/run_d.py` patches only the module-level names `run.py` looks up at call time, the same pattern OWN-105 and R2-05 used: the stdio client, the MCP session, `FixtureFormTask.read_oracle`, the chooser, `plan_guarded_completion`, `resolve_guarded_completion`, `task_candidates_for_step`, `asyncio.sleep` and `driver_environment`.
  - Both arms share A's full fresh `semantic_v2` reads, because B is BLOCKED.
  - Settings identical in both arms: `set_agent_cursor_enabled(false)` before `browser_prepare`, focus settle at its default, phase trace on, `visual_observation=auto`.
  - Every trial starts a fresh `cua-driver mcp` and a fresh `isolated_new` browser.
- **Continuation source.** D's continuation comes from `tasks.FIXTURE_TASK_ID`, `tasks.SUBMIT_NAME` and the provider-selected first mutation, all inside PR 4316's own code. Nothing comes from fixture answers.
- **Fixture and oracle.** `harness/i107_fixture.py` runs as a separate process.
  - W-quiet serves the jev-use page byte for byte.
  - W-churn adds a 500-node region (seed 20261002, 20 Hz, 10 nodes per tick) and is shareable with lane AB.
  - The control page applies mutations sent over EventSource and acknowledges each one. The server journals every event on CLOCK_MONOTONIC.
  - T_oracle ends at the first read by a 2 ms poller thread inside the fixture process. That read is independent of the runner.
- **Isolation and locks.**
  - Every executing command ran under `<lanes>/bin/hostless`, with REAL runs inside `cua-x11-session.sh`.
  - Partway through the lane the orchestrator replaced the bubblewrap v1 wrapper with hostless v2 (environment scrub, private runtime directory, Landlock scope, no user namespace). The isolated browser could launch only under v2 (amendment 1, `provenance.json`).
  - Each block manifest records the hostless ancestor, `uid_map` and private DISPLAY.
  - Every REAL group ran under one `quiet-timed` EXCLUSIVE acquisition. The receipts are in `raw/real/<group>/lock-receipt.json`.
- **Analysis.** `analyze.py` builds the results from `harness/d_analysis.py`, which reuses B-01's verbatim `b01_analysis.py`.
  - i107 ledger marks are filtered out of the decomposition.
  - PR 4316 plan and resolve time is counted as resolution/validation.
  - Paired bootstrap: 10,000 resamples, seed 20261002.
  - Threshold: max(5 ms, 5% of A's median).

## Results

### CMP-D (K1) and CMP-D-K2: wall-clock

Paired delta is D − A on T_oracle, in ms. Every pair is valid and every pair kept: 30 out of 30 in each condition.

| Comparison / condition | A median (p95) | D median (p95) | Paired median delta [95% CI] | Threshold | Verdict | Signs (−/+) |
|---|---|---|---|---|---|---|
| CMP-D W-quiet | 270.6 (294.8) | 271.6 (306.5) | +1.07 [−10.04, +10.79] | 13.53 | NO_MEANINGFUL_BENEFIT | 15/15 |
| CMP-D W-churn | 1221.1 (1366.8) | 1219.1 (1346.3) | −4.44 [−40.95, +20.55] | 61.05 | NO_MEANINGFUL_BENEFIT | 16/14 |
| CMP-D-K2 W-quiet (64 uppercase letters) | 247.3 (380.6) | 278.7 (332.0) | −0.64 [−6.13, +12.75] | 12.36 | NO_MEANINGFUL_BENEFIT | 16/14 |

- No condition was INCONCLUSIVE, so the continuation rule triggered no extra block.
- **Outcomes.** 30 out of 30 verified by the oracle in every arm and condition. No refuted, abstained, unknown, timeout, budget_exhausted or error trials.
- **Required-zero counts on measured pairs: all 0.** That covers stale-ref effects, unauthorized actions, wrong targets, duplicate effects and unverified successes.
- **Accounting gate.** Named-span coverage of T_oracle had a median of at least 0.9987 and a minimum of at least 0.9954 in every arm and condition, so every value passes the >0.90 gate.
- **Load caveat.** The 1-minute loadavg was 11.6 to 22.2 (median 14.6) on every measured trial, driven by other tracks' unlocked work. The pre-registered sensitivity analysis, which drops pairs above 8, therefore has no data (NO_DATA). The arms were interleaved within each pair, so the load is common to both, but it is not a quiet machine.

### Work deleted vs wall-clock (kept separate)

Per-task medians from REAL traces.

| Per task | A | D |
|---|---|---|
| Chooser decisions | 2 | **1** |
| Decision time (mock) | 0.013 ms (quiet) / 0.014 (churn) | 0.006 / 0.006 |
| PR 4316 program creation (plan) | 0 | 1 call, 0.020 to 0.031 ms |
| PR 4316 verification (resolve) | 0 | 1 call, 0.029 to 0.033 ms |
| Full semantic_v2 snapshots | 2 | 2 |
| Producer CDP sends | 54 (W-quiet) / 54 (W-churn) | 54 / 54 |
| CDP reply bytes | 46,676 / 1,657,207 | 46,676 / 1,657,234 |
| Acquired DOM / layout / AX nodes | 42/30/42 (W-quiet); 2048/2032/3044 (W-churn) | the same |
| CDP events received | 10 / 687 | 10 / 687 |
| MCP snapshot bytes | 5,952 / 103,462 | 5,952 / 103,486 |
| Driver mutations | 2 | 2 |

- D deletes one provider/chooser decision per task. It adds one plan call and one resolve call.
- With the mock chooser, D's decision path costs more than A's, but both are below 0.06 ms. That is noise against roughly 270 ms (W-quiet) and roughly 1220 ms (W-churn) totals.
- The live-provider value is BLOCKED. R2-03's live −212 ms was measured on 0.31.0 with TypeSafe and is not borrowed or summed here.

**#10 spans, A W-quiet medians in ms** (D is the same within noise; full tables are in `d-summary.json`):

| Span | ms |
|---|---|
| Observation acquisition | 54.8 |
| Projection / encoding / transport | 24.0 |
| Provider inference | 0.01 |
| Resolution / validation | 78.9 (mostly endpoint revalidation) |
| Dispatch | 6.9 |
| Wait | 105.4 (the Driver's default 100 ms focus settle) |
| Fresh verification | 0.8 |
| Residual | 0.3 |

- Under W-churn, acquisition rises to 222 ms and projection/encoding/transport to 786 ms: about 100 KB per snapshot plus client validation.
- **Cleanup** (session close plus browser exit) took about 470 ms. **Lifetime** was 1545 ms in W-quiet and 2510 ms in W-churn.
- **Resources:** Driver 0.40 s CPU and 45 MiB VmHWM in W-quiet; 1.19 s and 68 MiB in W-churn. The browser tree used about 1.1 GiB RSS. A and D did not differ.

### Dependency controls

REAL, 5 per control per arm, 190 trials. Only the fixture journal and oracle grade the outcome.

| Control | A | D (guard) | Note |
|---|---|---|---|
| DC01 field changed after type | re-typed, 5/5 verified | declined `field_not_proven` 5/5, re-typed, 5/5 verified | as expected |
| DC03 competing Submit (inserted first) | **5/5 wrong target** (first match) | declined `submit_not_unique` 5/5, then the fallback chooser (arm A's logic) clicked the competing button: **5/5 wrong target** | the guard's decline does not protect the fallback path |
| DC04 Submit removed | no click, budget_exhausted 5/5 | declined `submit_not_unique` 5/5, budget_exhausted | no false success |
| DC05a benign re-render | 5/5 verified | accepted with a fresh ref 5/5, verified | |
| DC05b replacement in check-to-dispatch | the Driver dispatched to the detached node 5/5 (no effect), the next step verified | the same 5/5 | **Driver stale acceptance** (R2-07 gap), both arms, 0 duplicates |
| DC06 relocated look-alike in another form | **5/5 decoy submit** | **guard accepted 5/5, 5/5 decoy submit** | **missing scope fact; blocks D's promotion** |
| DC07 document replacement before dispatch | the Driver refused `browser_ref_stale` 5/5, no dispatch, no effect | the same | the refusal arrives as a non-error result with `effect: refused`, and the jev-use `Driver.call` treats it as success. The runner polled for 2 s and recovered on the next step (5/5 verified). Caller defect, not a safety breach |
| DC10 session replacement probe | refused `protected_resource_scope_invalid` 5/5, 0 submits during the probe | the same | |
| DC12 hidden (display:none) | budget_exhausted 5/5 | declined 5/5 | Submit absent from the snapshot's action refs |
| DC13 offscreen | 5/5 verified | accepted 5/5, verified | offscreen Submit kept and clicked via `dom_event` |
| DC14a overlay before snapshot | budget_exhausted 5/5 | declined 5/5 | page_occluded |
| DC14b overlay in check-to-dispatch | 5/5 effect lands | accepted 5/5, effect lands | `dom_event` bypasses hit testing (route property) |
| DC15 focus moved | 5/5 verified | accepted 5/5 | |
| DC16a disabled fieldset / DC16b aria-disabled | budget_exhausted 5/5 each | declined 5/5 each | the Driver drops the click action |
| DC17a value cleared by script | re-typed, 5/5 verified | declined `field_not_proven` 5/5, verified | |
| DC17b ::before name change | budget_exhausted 5/5 | declined 5/5 | |
| DC20a ack lost after the effect applied (OWN-105 seam) | runner `unknown` 5/5, 1 submit each, 0 redispatch | the same | no duplicates |
| DC20b effect delayed 300 ms | 5/5 verified late, 0 redispatch | the same | |

Required-zero totals across controls:

- **D:** wrong_target_effect 10 (DC06 5, DC03 fallback 5). All other counts 0.
- **A:** wrong_target_effect 10 (DC06 5, DC03 5). All other counts 0.
- **Driver stale acceptance:** 5 per arm (DC05b).

The UNIT guard matrix (`raw/unit/guard-matrix.json`) predicted every REAL guard outcome above, including DC06 accepted and DC16b declined. Its Driver-dependent branches resolved as follows:

| Control | Branch observed in REAL runs |
|---|---|
| DC12 | Submit absent from the action refs (Driver omission counters show no `css_hidden`) |
| DC13 | `submit_kept_offscreen` |
| DC14a | `submit_omitted_page_occluded` |
| DC16a, DC16b | `ax_disabled_no_actions` |
| DC17b | `ax_name_includes_before` |

## Evidence labels

| Row | Label |
|---|---|
| CMP-D, K2, controls | REAL, FIXTURE/BENCHMARK, scripted chooser |
| Guard matrix and structural counts with the fake Driver | UNIT |
| Seam and source map | SOURCE (map packet) |
| Live provider | BLOCKED |
| K3, K4, E, DC08, DC09 | NOT_RUN (map PREREG) |
| DC11, DC18 | lanes AB/CSHADOW, not this lane |

## Deviations and disclosures

1. **Hostless v2.** REAL runs used hostless v2, which the orchestrator installed at 05:06:31Z. Amendment 1 records it, and I treated the canonical wrapper replacement as the provided isolation wrapper. v1 had blocked every browser launch.
2. **Lock groups.** Amendment 1 lets one quiet-timed acquisition cover several consecutive blocks (6 acquisitions in total). No pair, order or condition changed.
3. **Harness changes after the PREREG and before the measured runs:**
   - hostless-ancestor detection, because the private session clears the environment;
   - content-free mutation envelopes, after the shakedown showed DC07's `effect: refused`.

   Both are measurement-only and test-first (red logs `red-6`, `red-7`).
4. **TDD receipts.** The first commit missed the unit logs because of the repository's `*.log` ignore rule. They were added in the next commit, with a packet `.gitignore` negation.
5. **Cancelled waiter.** One queued `quiet-timed` waiter of mine (CMP-D, still waiting on flock, never acquired) was cancelled and relaunched detached. It is logged in the chain log. No trial ran in it.
6. **Driver telemetry.** The Driver prints "sends content-free product telemetry by default". The runner process is loopback-only (0 non-loopback attempts). The Driver's own telemetry was left at its default, as in every other lane.
7. **Load.** The loadavg-above-8 sensitivity analysis has no data, because the machine was loaded on every measured trial.

## Files

| Path | Contents |
|---|---|
| `PREREG.json`, `PREREG-AMENDMENT-1.json` | frozen plan and amendment |
| `harness/` | runner, fixture, schedule, analysis, guard matrix, fake Driver (tests only), `session_entry.sh`, `tests/` |
| `raw/real/<group>/` | `trials-<group>.tar.gz` (per trial: events, Driver trace, run.py log), manifests, sanitized session log, lock receipt; `raw/real/chain-log.jsonl` (group runs) |
| `raw/unit/` | red and green logs, `guard-matrix.json`, `structural-work.json` |
| `raw/pr4316-head-*.json` | live PR head reads |
| `d-summary.json` | every headline (recomputed by `analyze.py`) |
| `ledger/i107-d-ledger.jsonl` | #10 task × arm × trial ledger, one row per REAL trial including excluded smoke and shakedown |
| `ledger/cells.json` | per-cell status |
| `provenance.json` | build, wrapper and environment identities |
| `verify_artifacts.py` | recomputes everything from `raw/`, checks receipts, verbatim copies and privacy |

To verify, run `python3 verify_artifacts.py`.
