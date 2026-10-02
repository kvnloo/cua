# B-01: browser critical-path decomposition on the R2-10 composition source, 2026-10-02

## Result in one paragraph

On one source (upstream main `229b65b28` + the R2-01 phase trace + trycua/cua PR 4316 at `a0bca7440` + this lane's measurement-only marks and focus-settle knob), with the mock chooser, the three #24 browser classes take a median whole-task time T of 3180.7 ms (fill→submit, K0n baseline shape), 2487.3 ms (toggle→confirm) and 2471.7 ms (modal→act) with agent-cursor feedback at its default. About 94–97% of that is the awaited cursor glide. The glide is speed-based: the arrival wait grows 2.097 ms per pixel of *planned* path (r² 0.998). The planned Dubins path has a median length of 684.2 px, while the straight start-to-target distance is only 11–283 px. Frame pacing is not the cause: the median wait is 1393.8 ms and no frame took longer than 18.3 ms. The fast glide (K1) keeps the cursor visible and recovers 98.6–98.7% of the saving of feedback OFF in every class (H_V **KEEP**). Deleting the 100 ms focus settle in `browser_type` saves 101.2 ms with 0 dropped characters in 100 knob-0 trials (H_T **OWNER_DECISION**). The 100 ms completion poll is not material at library defaults (H_P: no material component). Compiling the MCP client's output-schema validators once per session deletes about 12.5 ms per two-action task: toggle 13.5 ms, modal 11.7 ms, both KEEP. On fill that saving moves into the target-effect lag plus the poll instead. The best composed configurations finish in 78.7 ms (fill, K3), 52.2 ms (toggle, K5) and 53.2 ms (modal, K5). What remains is dominated by three Driver costs this lane did not test causally: per-mutation endpoint re-proof (~10 ms per action), tools/list re-validation at MCP admission (~4.4 ms per call) and the cold first snapshot (~8–15 ms). That gives an untested-plausibly-deletable share of 51.2% (fill), 70.2% (toggle) and 69.3% (modal) of composed T. **E2 is therefore not met by this lane; the next deletions are localized to exact Driver call sites below.** All 485 trials verified or behaved as their control required: 0 duplicate mutations, 0 unverified successes, 0 stale-ref dispatches, 0 provider requests.

## Scope and owners

- Lane B-01, wave 1. Owners: kvnloo/cua#93 (R2-01 follow-up, R2-10 prep), #10 (accounting), #73 (canonical state), #24 (task classes).
- Advances E1 (why the glide takes ~1.5 s), E2 (browser decomposition with per-component verdicts), E3 prep (R2-10 source, fixtures, harness, live PREREG draft and budget) and E4 (stale-ref, dropped-character, duplicate and unverified-success controls).
- Pre-registration: `PREREG.json`, committed as `2bc7d0f1d` at 2026-10-02T02:43:42Z, before the first measured trial (02:43:58Z, `raw/timeline-receipts.json`). It was not edited afterwards.
- No new service, shadow state, second verifier, router, lifecycle registry, batch API or event service. The knob and the marks are env-gated and default-off. No GitHub writes and no pushes.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Base | `7d3a28b663a041b072b4be8aadb187a1eab5fd28` (R2-01 phase trace on upstream main `229b65b28`) | SOURCE |
| Composition merge | `0c6a53237c1d42f35680afe3796113dd25b48e1b` = `git merge --no-ff a0bca744067d04f05904319d3d919be30c336556` (trycua/cua PR 4316 live head). Conflict-free. It touches `libs/cua-driver/examples/jev-use` and also `.github/workflows/ci-jev-use.yml` (CI only) | SOURCE |
| Tested Driver source | `f5c991e5927513c8b94da4330c94276dc5f8ce22` (one measurement-only commit: marks + `CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS`). Later commits on the branch touch `docs/experiments/` only | SOURCE |
| Live PR 4316 head (gh, start 01:50:11Z and end 03:05:10Z) | `a0bca744067d04f05904319d3d919be30c336556`, OPEN, unchanged = the merged head | SOURCE |
| Upstream main | `c4d0c6625b5c93849aa8bec610782410e9d45f69` has a `libs/cua-driver` tree identical to `229b65b28` (`git diff --quiet`, rc 0). So does the latest main read at the end, `8d4e7a08618611453794035f7ff6187f99f0c1e9` (gh and git agree) | SOURCE |
| Publication SHA | set by the Publish agent; this lane did not push | — |
| Driver binary | `cua-driver-b01-f5c991e59`, sha256 `2e0248ad2b6efedd6c5f7acba6b5d8bd92160a29a6c9c80061bce5ea4efa43f3`, `cua-driver 0.32.0` (read inside the session). Built with `build-driver.sh` (family `cua-release-r2-01`) under the cargo lock (shared quiet lock); 0 Fresh units, 92 s (`raw/build-receipt.txt`). Same binary in every arm | SOURCE |
| Browser | Driver-chosen Google Chrome 151.0.7922.71, `isolated_new` profile, sandbox on, no permission-mode override, no approval bypass, no `*-e2e` wrapper | REAL |
| Provider | mock (`choose_mock_for_task`). TypeSafe attempts 0, reached 0. The runner refuses and counts every non-loopback connect: 0 in all 485 trials | REAL |

Details are in `provenance.json`.

## Environment

- Linux 7.2.2 x86_64, 10 CPUs, 23 GiB.
- `cua-x11-session.sh`: private rootless Xvfb 1920x1080x24, openbox, picom (xrender) and private dbus. No AT-SPI bus. Host Wayland/Hyprland variables scrubbed.
- jev-use `.venv` (Python 3.12, mcp 1.30.0, typesafe_sdk 0.6.0).
- Locks:
  - The 440 measured trials (primary, K5 and T0-stress blocks) ran in one EXCLUSIVE quiet-lane window, 02:43:58Z to 02:58:18Z.
  - The 40 controls ran in 4 SHARED windows of at most 10 trials each.
  - The default-off smoke ran in 1 SHARED window.
- The 1-minute loadavg before each measured trial ranged from 1.12 to 3.34 (every value is in the trial records).

## Method

- **Classes.**
  - fill→submit: the jev-use `FixtureFormTask` on its own `FixtureServer` at this source. The oracle is server state `submitted == token`, an exact string match.
  - toggle→confirm and modal→act: the #24 pages and handlers copied verbatim from kvnloo/cua `5474aa31f` (`b01_fixtures.py`; `verify_artifacts.py` re-checks the copy against the git object). The oracle is `oracle_ok` on the server state.
  - Every fixture journals each mutation on CLOCK_MONOTONIC on the server side. The server state is the oracle; the runner's outcome is logged but is not the oracle.
- **Trial (forced path).** Each trial runs these steps in order (`run_critpath.py`, reusing jev-use `run.py` functions):
  1. Start a fresh `cua-driver mcp`.
  2. Apply the arm's `set_agent_cursor_enabled` and `set_agent_cursor_motion`. Defaults are made explicit in non-K1 arms.
  3. `browser_prepare` with `isolated_new`, then `wait_for_window`, bind, and navigate.
  4. Run the jev-use step loop: oracle read, `semantic_v2` snapshot, `task_candidates_for_step`, then either the PR 4316 guarded resolve (fill) or `choose_mock_for_task`. Then `plan_guarded_completion` and the action.
  5. Run the completion poll: read, then sleep `poll_ms` with a 2.0 s deadline.

  The fixture is reset and the token is unique per trial.
- **Arms.**
  - K0n: default ON, no guard (fill only; the R2-10 baseline shape).
  - K0: default ON.
  - K1: fast glide `{glide_duration_ms:1, dwell_after_click_ms:0}`, cursor still enabled.
  - K2: feedback OFF.
  - K3: OFF + focus settle 0 (fill only).
  - K4: OFF + settle 0 where applicable + 10 ms poll with the same deadline.
  - K5: K4 + caller-side compiled output-schema validators. Added after the shakedown localized ~6 ms per action call to `mcp` `ClientSession._validate_tool_result`; pre-registered before any measured trial.
  - fill K0–K4 run PR 4316 guarded completion.
- **Design.**
  - Primary block: 20 rounds. In each round every class runs its arms in a Williams-balanced order, n = 20 per arm per class.
  - K5 block: 20 AB/BA K4/K5 pairs per class.
  - T0-stress block: 20 AB/BA pairs of K3 vs K2 on fill with a 64-character token.
- **Clocks.** Caller events use `time.monotonic_ns()`. Driver marks come from `CUA_DRIVER_PHASE_TRACE_FILE`. The journal is stamped on CLOCK_MONOTONIC. An independent harness thread re-reads the server state every 2 ms.
- **T.**
  - T_runner = send of the first `semantic_v2` call until the return of the runner's first oracle read that classifies as verified. This is the primary metric for every gate.
  - T_oracle = the same start until the 2 ms harness read first confirms.
- **Decomposition.** T_runner is decomposed by telescoping over caller events and the Driver marks inside each call window (taxonomy in `PREREG.json`, code in `b01_analysis.py`). Named-span coverage was 1.000 in every arm; the sum of components matches T to within float rounding.
- **Statistics.**
  - Medians and nearest-rank p95.
  - Paired differences within a round.
  - Seeded percentile bootstrap over rounds: 10000 resamples, seed 20261002.

## Results: whole-task T_runner, median ms (n = 20 per arm per class, every trial verified)

| Class | K0n | K0 | K1 | K2 | K3 | K4 | K4 (K5 block) | K5 | Evidence class |
|---|---|---|---|---|---|---|---|---|---|
| fill | 3180.7 | 3184.7 | 220.6 | 181.7 | 78.7 | 80.1 | 79.0 | 79.4 | BENCHMARK |
| toggle | — | 2487.3 | 98.7 | 66.1 | — | 65.7 | 65.8 | 52.2 | BENCHMARK |
| modal | — | 2471.7 | 98.0 | 65.6 | — | 67.2 | 65.7 | 53.2 | BENCHMARK |

Validity was 20/20 in every arm and class (REAL). Failures: none. T_oracle medians are in `b01-summary.json`; they sit within about 2 ms of T_runner, except fill K5 (see H_C).

Paired differences (median, 95% CI; BENCHMARK):

| Class | K0−K1 | K0−K2 | K1−K2 (residual) | K2−K3 | K3/K2−K4 | K4−K5 |
|---|---|---|---|---|---|---|
| fill | 2963.7 [2960.3, 2969.5] | 3002.6 [2998.3, 3005.1] | 38.8 [37.0, 40.8] | 101.2 [99.2, 104.6] | −0.5 [−2.7, 2.0] | 0.0 [−2.1, 3.1] (T_oracle: 9.0 [6.7, 12.2]) |
| toggle | 2388.3 [2386.5, 2390.4] | 2421.3 [2418.4, 2423.0] | 32.8 [30.5, 34.2] | — | 0.4 [−1.3, 3.7] | 13.5 [12.1, 15.4] |
| modal | 2373.8 [2369.3, 2379.7] | 2406.7 [2404.7, 2409.9] | 33.8 [30.9, 35.0] | — | −1.6 [−3.0, 2.3] | 11.7 [10.4, 13.2] |

K0n vs K0 on fill (guard vs no guard, mock chooser): −2.1 [−9.3, 3.5] ms. With a mock chooser the guard deletes a decision that costs about 0 ms. Its live value (2→1 provider requests, about −212 ms) is R2-03's and is measured live in R2-10.

## Hypotheses (pre-registered gates)

| Hypothesis | Result | Verdict | Evidence class |
|---|---|---|---|
| H_V fast glide ≥ 90% of OFF's saving | R = 0.987 [0.986, 0.989] fill, 0.986 [0.986, 0.988] toggle, 0.986 [0.984, 0.988] modal. Residual cost of keeping the cursor: 38.8 / 32.8 / 33.8 ms per task | **KEEP** (all classes) | BENCHMARK |
| H_T delete the 100 ms focus settle (knob 0) | K2−K3 101.2 [99.2, 104.6] ms (19/20 pairs positive). T0 stress (64-char token): 101.2 [100.2, 104.4] ms, 20/20 positive. 0 dropped or reordered characters in 100 knob-0 fill trials (100 submits, exact match), and 0 in 100 knob-unset trials. The settle span is 101.1 ms unset vs 0.05 ms at 0. Readiness was true on the first poll in 200/200 measured fill trials (0 readiness sleeps) | **OWNER_DECISION** (the source comment cites Edge-on-Linux drops, not testable here) | BENCHMARK + REAL |
| H_P 100 ms completion poll | The sleep was entered in 1/20 K3 fill trials and 0/20 K2 toggle and modal trials, below the 10% materiality bar. Paired CIs include 0 in every class | **no material component** (all classes) | BENCHMARK |
| H_C compiled MCP output-schema validators (secondary) | Client validation is 12.9 ms → 0.4 ms per task in every class. Whole-task saving: toggle 13.5 [12.1, 15.4] and modal 11.7 [10.4, 13.2] ms (20/20 positive). On fill the runner time is unchanged, 0.0 [−2.1, 3.1] ms, while T_oracle improves by 9.0 [6.7, 12.2] ms. The fill click now returns before the submit lands, so the poll was entered in 20/20 fill K5 trials and the 10 ms granularity absorbs the gain | **KEEP** toggle, modal; **not material** fill | BENCHMARK |

## E1: why the glide takes about 1.5 s (REAL + BENCHMARK)

- **What was measured.** 160 ON arrival waits (K0, K0n; 2 per task). Each wait mark carries:
  - the glide plan read before `MoveTo`: start, target, straight distance, planned Dubins path length, motion settings, and the time predicted by `tick_motion`'s speed law at 16 ms frames;
  - the render loop's frame statistics.
- **Fit on planned path length.** arrival_wait = −38.6 [−47.8, −28.4] ms + 2.097 [2.081, 2.111] ms/px × path_length (r² 0.998). That is about 477 px/s across planned paths of 527–745 px (median 684.2 px).
- **Fit on straight distance (the pre-registered regression).** slope 1.71 [1.645, 1.777] ms/px, intercept 1077.3 [1068.6, 1088.4] ms, r² 0.94. Most of the wait is independent of the straight distance (11–283 px). The `PathPlanner` Dubins path has an 80 px turning radius and a fixed π/4 end heading, which forces a loop: the planned path is 2.6–48× the straight line.
- **Prediction vs measurement.** The predicted speed-law time matches the measured wait: measured minus predicted is −5.8 ms at the median.
- **Frame pacing.** 0 frames exceeded the 50 ms motion-step cap, and the maximum frame was 18.3 ms. Frame pacing on Xvfb/picom does not stretch the glide; the length comes from the speed law (300→900→200 px/s profile) over the Dubins path length.
- **Fast glide.** With `glide_duration_ms:1` the wait is one frame tick plus paint (median 11.1 ms, max 29.0 ms).
- **K1 residual.** The remaining 33–39 ms per task in K1 vs OFF is those two one-frame waits plus about 14 ms of overlay first-use before the first wait per trial. That 14 ms includes this lane's glide-plan read under the render lock and is not attributed further.

## E2: decomposition and verdicts (mean ms; share = mean component / mean T)

The best composed arm is selected by the pre-registered rule: lowest median T among K2–K5 whose gates and validity held. That gives fill K3 (K5 is excluded on fill because H_C is not material there), and K5 for toggle and modal. The baseline is fill K0n and toggle/modal K0. All rows are BENCHMARK from REAL traces.

**fill, best composed K3 (mean T 84.9 ms):**

| Component | Mean ms | Share | Verdict |
|---|---|---|---|
| decision (mock) | 0.0 | 0% | live decision measured in R2-10 |
| observation (2 snapshots) | 20.9 | 24.6% | IRREDUCIBLE count (one fresh `semantic_v2` per action; refs are never durable authority). Per-call cost: 19.4 ms CDP vs 1.5 ms processing. The first snapshot costs 14.9 ms more than the second (cold `DOM.getDocument`, attach, AX): UNTESTED |
| revalidate | 21.8 | 25.7% | IRREDUCIBLE check (#73 per-mutation re-proof). Of this, 19.8 ms (≈10 ms per action) is the owned-endpoint re-proof (`/proc` socket-owner scan + `/json/version` per port, `discover_owned_endpoint`): UNTESTED |
| MCP transport, total 27.5 ms: driver pre-dispatch | 9.2 | 10.8% | UNTESTED. `validate_tool_call` runs against a freshly built `tools_list()` twice per call (proxy admission + `handle_request_inner`): 8.7 ms |
| MCP transport: client output-schema validation | 13.1 | 15.4% | tested (H_C): deleted in K5 (0.4 ms), but no fill wall-clock saving (the time moves to target-effect lag + poll) |
| MCP transport: stdio + driver post-dispatch | 5.2 | 6.2% | IRREDUCIBLE (JSON-RPC over stdio; post-dispatch 2.6 + transport 2.6) |
| sleeps/polls | 5.0 | 5.9% | tested (H_P): 1/20 trials entered one 100 ms sleep; no material component. K4's 10 ms poll bounds it |
| settles | 0.05 | 0% | DELETED in this arm by the knob (H_T OWNER_DECISION) |
| visualization (OFF) | 1.6 | 1.8% | below threshold |
| dispatch (`Input.insertText` / `Runtime.callFunctionOn`) | 2.3 | 2.7% | below threshold (IRREDUCIBLE) |
| resolution, input_prep, dispatch_post, verification reads, effect lag, runner | 5.8 total | 6.8% | each below threshold |
| unattributed | 0.0 | 0% | — |

**toggle, best composed K5 (mean T 53.1 ms)** and **modal, best composed K5 (mean T 54.5 ms):**

| Component | toggle mean ms (share) | modal mean ms (share) | Verdict |
|---|---|---|---|
| observation | 11.9 (22.4%) | 12.3 (22.6%) | IRREDUCIBLE count. Cold-first excess ≈ 8.3 ms: UNTESTED |
| revalidate | 22.2 (41.8%) | 22.6 (41.5%) | IRREDUCIBLE check. Endpoint re-proof 20.3 / 20.6 ms: UNTESTED |
| driver pre-dispatch | 9.1 (17.1%) | 9.4 (17.2%) | UNTESTED (tools/list validation twice per call) |
| client validation | 0.4 (0.7%) | 0.4 (0.7%) | DELETED (H_C KEEP) |
| driver post-dispatch + transport | 4.4 (8.2%) | 4.6 (8.4%) | IRREDUCIBLE (stdio JSON-RPC) |
| everything else | ≤ 1.6 each | ≤ 1.7 each | below threshold |

**Baselines.**

| Class (arm) | Mean T | Visualization | Other material components |
|---|---|---|---|
| fill (K0n) | 3185.0 ms | 2998.0 ms (94.1%), of which the arrival wait is 2985.2 ms: OWNER_DECISION (existing per-session settings delete it; a default change is the owner's call, #93) | focus settle 101.1 ms (3.2%): OWNER_DECISION (H_T). Every other component is below 5% and 50 ms |
| toggle (K0) | 2487.1 ms | 2420.2 ms (97.3%): OWNER_DECISION | none |
| modal (K0) | 2476.2 ms | 2409.2 ms (97.3%): OWNER_DECISION | none |

**Untested-but-plausibly-deletable share.** This is the sum of the endpoint re-proof, the MCP admission validation, the cold-first-snapshot excess and the unattributed time, divided by mean T:

| Class | Composed arm | Baseline |
|---|---|---|
| fill | 51.2% | 1.4% |
| toggle | 70.2% | 1.5% |
| modal | 69.3% | 1.5% |

The E2 gate (< 5%) is **not met** for the composed configurations. The remaining time sits in three Driver call sites this lane only localized:

1. `BrowserEngine::revalidate_for_mutation` → `owned_endpoint` / `discover_owned_endpoint`: ~10 ms per mutation. Security-relevant; any cheaper equivalent proof is an owner question.
2. `proxy::run_direct` + `server::handle_request_inner` → `validate_tool_call(.., &tools_list())`: ~4.4 ms per call.
3. The first `semantic_v2` snapshot's cold CDP work: ~8–15 ms.

## Work deleted vs wall-clock saved

**Work deleted (structural, per task):**

| Knob | What it removes |
|---|---|
| OFF | 2 overlay `MoveTo` + `PinAbove` + `ClickPulse` and 2 awaited arrivals (≈2.4–3.0 s of speed-law gliding). The visibility `Runtime.evaluate` and `Page.getLayoutMetrics` calls still run |
| fast glide | The same CDP work as default ON; the 2 awaited arrivals shrink to one frame each |
| T0 (fill) | One 100 ms `tokio::time::sleep` per `browser_type` (replace=true insert_text path). The readiness check, `DOM.focus` and the selection still run |
| P10 | Nothing in the product; caller poll granularity only |
| K5 | Per tools/call result, one metaschema check and one validator construction in the client (≈6.3 ms per action call, ≈0 for `get_browser_state`); compiled once at tools/list instead, outside T (~100 ms per session for 20 schemas) |

**Wall-clock saved** (this source, binary and session; paired medians):

| Knob | fill | toggle | modal |
|---|---|---|---|
| OFF vs default | 3002.6 ms | 2421.3 ms | 2406.7 ms |
| fast glide vs default | 2963.7 ms | 2388.3 ms | 2373.8 ms |
| T0 | 101.2 ms | — | — |
| P10 | 0 (CI includes 0) | 0 (CI includes 0) | 0 (CI includes 0) |
| K5 | 0 (work deleted, wall-clock not saved) | 13.5 ms | 11.7 ms |

Baseline → composed: fill 3180.7 → 78.7 ms; toggle 2487.3 → 52.2 ms; modal 2471.7 → 53.2 ms (medians). This includes the mock chooser, so it is not the R2-10 live speedup.

## Negative and fallback controls

| Control | Result | Evidence class |
|---|---|---|
| Stale ref: re-navigate, then send the step-2 ref with `dom_event`, 2 per arm per class | 28/28: envelope `effect=refused` with `isError=false`, 0 completion mutations, oracle unchanged. The refusal code is not exposed at `code`/`refusal.code` (as in R2-01) | REAL |
| First action only (fill type / toggle checkbox / modal open), 2 per class | 6/6: oracle not satisfied, 0 completion mutations | REAL |
| Guard decline on jev-use `DUPLICATE_SUBMIT_ON_INPUT` (K0 ×3, K4 ×3) | 6/6: guard declined with `submit_not_unique`, provider route at step 2, verified, exactly 1 submit | REAL |
| T0 stress, 64-char token: K3 vs K2 (20 + 20) | 40/40 exact match; 0 dropped or reordered characters | REAL |
| P10 / K5: unverified successes and duplicate mutations | 0 and 0 (across all 485 trials) | REAL |
| Guarded completion on toggle/modal | Does not apply at the tested source: `plan_guarded_completion` binds only `FIXTURE_TASK_ID`; it bound nothing in 160/160 toggle and modal K0–K4 trials. This is a finding for R2-07/R2-10 | SOURCE + REAL |
| Live request builder for toggle/modal (dry, 0 HTTP) | 4/4 requests built by jev-use `choose_for_task` decode as the TypeSafe SDK's `SystemOneRequest`; 0 socket connects (`raw/live-request-validation.json`) | FIXTURE |
| Default-off smoke: trace and knob unset | 5/5 fill verified; no trace file, no trace-field file, and neither variable in the session command (`raw/default-off-trace-check.txt`) | REAL |
| Unit: `cua-driver-core` lib, `platform-linux` lib, `cua-driver-sdk` lib, `cua-driver` bins (run inside the session) | 818/818 (7 B-01 tests), 602 passed + 10 ignored (3 B-01 tests), 95/95, 290/290 | UNIT |
| jev-use Python/TS suites | not touched, not re-run | NOT_RUN |

## Deviations

1. Before the PREREG commit, the single measurement commit was amended twice. The first amendment added MCP/SDK boundary marks after the first shakedown showed about 7 ms of unexplained post-dispatch time; the second added revalidation-step marks. The two superseded binaries (`b01-56817bd72`, `b01-9e0267548`) were used only in shakedowns, which are excluded. No measured trial used them.
2. The extra marks (MCP stdio/server/SDK boundaries, revalidation steps, glide plan, frame statistics) go beyond the mark list in the task spec. All are measurement-only, env-gated and in the one commit.
3. After the PREREG commit, `run_critpath.py`'s smoke plan lock mode was changed from `none` to `shared`. This affects only the default-off smoke. The measured run had already loaded the committed file.
4. The E2 untested-share rule was written after the runs. Its parts are the endpoint re-proof sub-span, the MCP admission validation sub-spans, the first-minus-second snapshot excess and the unattributed time. The PREREG named the gate, not the arithmetic.
5. The fixture servers run inside the runner process, as jev-use's do. On fill, the submit's journal time includes GIL contention with the client's schema validation: the effect lag from the CDP send was ≈9 ms in K4 vs 4.1 ms in K5. The T_runner gates are unaffected (same process in every arm); the effect-lag diagnostic is process-local.
6. rustfmt formatting was not applied to the instrumentation (as in R2-01). `build-driver.sh` runs `<bin> --version` outside the session (no display use); the version was re-read inside the session.
7. The fill Williams square (n = 6) is partial over 20 rounds: rows were used 4, 4, 3, 3, 3 and 3 times, as pre-registered.
8. Unrelated to the lane: other lanes' unlocked work kept loadavg at 1.1–3.3. Every trial's loadavg is recorded.

## Limits

- One fixture per class, one browser build and one X11 session (Xvfb + picom).
- The glide law and Dubins planning are cross-platform code, but the arrival mechanics differ on Wayland (#94), macOS and Windows.
- The mock chooser means provider decision time is not included.
- n = 20 per arm per class; p95 values are estimates.
- The focus-settle deletion is tested only on Chrome 151 on Linux X11. Edge is not tested.
- The keystroke `browser_type` mode, with its 15 ms per-character sleep, never ran (0 `key.*` marks), because jev-use uses `insert_text`.

## Claim boundary

Every result here holds only for this configuration:

- jev-use fill fixture + #24 toggle/modal pages
- X11 Xvfb/openbox/picom
- Chrome 151
- Driver `229b65b28` + R2-01 trace + B-01 marks/knob (`f5c991e59`, binary sha256 `2e0248ad…`)
- PR 4316 caller at `a0bca7440`
- mock chooser

On this configuration: the default glide's ~1.4 s per action is the speed law over a long planned Dubins path; the fast glide recovers ≥ 98.4% (CI lower bound) of feedback-OFF's saving; deleting the 100 ms focus settle saves ~101 ms with no dropped characters; and compiled client validators save ~12–14 ms on toggle and modal.

This is not a default change, not a LIVE_PROVIDER claim, and nothing transfers to Wayland, macOS, Windows or Edge.

## Disposition

- **H_V KEEP** (all classes).
- **H_T OWNER_DECISION**.
- **H_P no material component** (all classes), with the K5 interaction noted.
- **H_C KEEP** for toggle and modal, not material for fill.
- **E1 answered**: speed law × planned Dubins path length; not frame pacing.
- **E2 decomposed but not met.** The untested share is 51–70% in the composed arms, in three localized Driver call sites, which are the next lanes.
- **E3 prep ready**: source, fixtures and harness validated, plus `R2-10-PREREG-DRAFT.json`. The draft uses 30 AB/BA pairs per class. Its TypeSafe budget is 3 (fill), 4 (toggle) and 4 (modal) requests per pair, 330 requests reaching the provider in total, with an attempt cap of 363. It uses this lane's binary with knobs only in the composed arm. Composed = fast glide + T0 + P10 + compiled validators + guard (fill) + an R2-07 slot.
- **E4**: every control passed.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | the pre-registration |
| `R2-10-PREREG-DRAFT.json` | the live R2-10 draft, generated by `make_r2_10_draft.py` from the summary |
| `run_critpath.py` | trial runner |
| `b01_fixtures.py` | verbatim #24 fixtures + journal |
| `b01_tasks.py` | toggle/modal task specs |
| `validate_live_request.py` | dry request validation |
| `b01_analysis.py`, `analyze.py` | decomposition, statistics, gates → `b01-summary.json` |
| `verify_artifacts.py` | recomputes the summary from `raw/`, checks README headline numbers (`headline-numbers.json`), lock windows, 0 provider HTTP, PREREG order, verbatim fixtures, UNIT receipts, default-off smoke and a privacy scan |
| `provenance.json` | provenance record |
| `raw/trials-measured.tar.gz` | 440 measured trials (caller JSONL + Driver trace each) |
| `raw/trials-controls-smoke.tar.gz` | controls and smoke trials |
| `raw/run-manifest-*.json` | run manifests with lock receipts |
| `raw/session-*.log` | sanitized session logs |
| `raw/unit/` | UNIT logs |
| `raw/build-receipt.txt`, `raw/timeline-receipts.json` | build and timeline receipts |
| `raw/snapshots/` | toggle/modal snapshots from the shakedown |
| `raw/live-request-validation.json` | dry live-request validation result |
| `raw/shakedown/` | the excluded shakedown |

Raw outputs are mirrored, uncompressed, to the lane artifacts directory `artifacts/r2/B-01/`.
