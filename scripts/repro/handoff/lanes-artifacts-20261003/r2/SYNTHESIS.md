# CUA research round 2: P0 synthesis (R2-01 to R2-06), 2026-10-01

Owner: the kvnloo/cua#10 whole-task accounting role for round 2. This is a synthesis of six independently verified lane packets. It adds no new trials and does not recompute any lane number. Every figure below is quoted from the lane packet at the commit listed in "Packets", and that packet's `verify_artifacts.py` recomputes it from `raw/`. All six verifiers were re-run at those commits at 23:15Z and returned rc 0.

Path placeholders: `<lanes>` is the lanes root and `<tmp>` is the lane temp root. This file contains no host name, absolute paths or secrets.

## 0. Packets, provenance and what to publish

The lane-result JSON relayed to this step is stale for R2-01, R2-02, R2-04, R2-05 and R2-06: each branch moved on after verification. Publish the packet HEADs below and quote the packet READMEs, not the relayed headlines.

| Lane | Branch (local, not yet on the fork) | Packet HEAD to publish | Do NOT publish / cite |
|---|---|---|---|
| R2-01 | `exp/r2-01-feedback-ab-20261001` | `2ca82efaedf0083c3732b7855c78a5d1442f9dce` | `699b7a9c0` (missing raw logs) |
| R2-02 | `exp/r2-02-cdp-wake-20261001` | `8e751a75dd454ab396a4172c3ba98759323c01c2` | `5ac057914` (invalid C3 counted as a pass; "63/63 controls"). The relayed full SHA `5ac0579146c5…` does not exist |
| R2-03 | `exp/r2-03-guarded-live-20261001` | `6bab214abb707a3db9e8a7d641d160c3f58e08d5` | n/a (no fix pass) |
| R2-04 | `exp/r2-04-atspi-profile-20261001` | `9bfd437390571985870a66d941f43dbe417f31c0` | `539283cd6` (unit logs missing; H_A KILL not scoped to tree size) |
| R2-05 | `exp/r2-05-ack-loss-real-20261001` | `236e37e01792d4e60ee5334f702b47e6f122921e` | `4acf76b1d` (pre-write rule overstated; "placement 120/120") |
| R2-06 | `exp/r2-06-trusted-input-20261001` | `f00b9396365a44e69c44498a1cb52f18aa8a3871` | `7722428362e8…` and `138f091fb` (local paths in the probe; reflog-only, never push) |

Live heads, re-read with gh at 2026-10-01T23:15Z:
- trycua/cua main: `3e2f3a1ea4a2a4fad519794f729d448c646e2775`, 4 commits ahead of the tested base `229b65b28`. The verifiers checked the first 3 (`effd9b298`, `021b87ddf`) and found no `libs/cua-driver` change. The 4th commit was not diffed here, so re-check it at publication.
- trycua/cua PR 4316: `a0bca744067d04f05904319d3d919be30c336556`, OPEN, not draft. This equals the R2-03 and R2-05 tested Driver source.
- trycua/cua PR 4394: `039257811e0bbb2348c616c52562409923d2856f`, OPEN. Not tested by any lane.
- kvnloo/cua#105: `98a45e6c528da9e2715288c20c2a0feeeef8e73f`, OPEN draft. This equals the R2-05 tested caller source.

None of these live heads is certified by any packet except where it equals a tested source. The publication SHA is filled in by the orchestrator.

Binaries, kept apart because no number is compared across them:

| Binary | sha256 | Version | Source | Used by |
|---|---|---|---|---|
| main | `8b037961…4cd3` | 0.32.0 | `229b65b28` | R2-04 arm M, R2-06 |
| R2-01 trace | `41338733…c346` | 0.32.0 | `7d3a28b66` (main + default-off phase trace) | R2-01 |
| R2-02 probe | `7034a43b…84c1` (pairs, controls); `38f8c11d…553b` (C3 extension) | 0.32.0 | `4d092b160` / `55846dc66` | R2-02 |
| R2-04 phase | `940eb2c2…161a` | 0.32.0 | `28b915ae9` (main + phase marks) | R2-04 arm P |
| trycua/cua PR 4316 | `e57bb9ae…ff95` | 0.31.0 | `a0bca7440` | R2-03, R2-05 |

Environment for every lane: Linux 7.2.2, 10 CPUs, a private rootless Xvfb with openbox, picom and a private dbus started by `cua-x11-session.sh`, and Google Chrome 151.0.7922.71 chosen by the Driver with default safety settings. R2-04 also had a private AT-SPI bus and registry. No lane touched the host Wayland/Hyprland session.

## 1. kvnloo/cua#10 accounting table, per arm

Read each row only against other rows of the same lane. Lanes differ in fixture, source, binary, provider and load. **No figure in this table may be added to, subtracted from or multiplied by a figure from another lane (R2-10 rule).**

Abbreviations: obs = semantic observations; dec = provider or chooser decisions; act = mutating Driver actions; vis = visual parses.

| Lane / arm | Source · binary · provider | dec / task | obs / task | vis | act / task | Explicit sleeps / polls (caller unless stated) | Verified-outcome p50 / p95 (ms) | Verified / attempted · failures | Route attribution (actual) | Class |
|---|---|---|---|---|---|---|---|---|---|---|
| R2-01 ON | `7d3a28b66` · `41338733` · mock chooser (no HTTP) | 2 mock | 2 `semantic_v2` (+1 bind read) | 0 (no capture call made) | 2 (`browser_type`, `browser_click`) | 0 completion sleeps (first post-call read verified); **Driver: 2 awaited cursor-glide arrivals per task** | click send → verified: 1542.778 / 1545.676 | 24/24 · 0 | type: public `trusted_input` (CDP `Input.insertText`); click: `dom` / `dom_event` (trace `click.enter`) | REAL + BENCHMARK |
| R2-01 OFF | same | 2 mock | 2 (+1) | 0 | 2 | 0 completion sleeps; Driver: 0 glide waits | 24.478 / 29.683 | 24/24 · 0 | same | REAL + BENCHMARK |
| R2-02 A_poll | `4d092b160` · `7034a43b` · none (harness picks candidates) | 0 | 2 | 0 | 2 | 4 × 100 ms sleeps in 3/24 trials; 28 post-call oracle reads | click → verified: 1543.461 / 1670.660 | 24/24 · 0 | `dom` / `dom_event` | REAL + BENCHMARK |
| R2-02 B_event | same, probe armed | 0 | 2 | 0 | 2 | 0 sleeps; 24 reads; **+3 CDP round trips per click** (`Page.enable`, `Page.getFrameTree`, `Page.disable`) + 1 demux subscriber | 1592.255 / 1646.033 | 24/24 · 0 | `dom`; wake producer `Page.frameNavigated` (wake hint only) | REAL + BENCHMARK |
| R2-03 baseline | `a0bca7440` · `e57bb9ae` · TypeSafe `jev-1.13.0` (live) | **2** (receipts: 80 HTTP 200 with request id) | 2 | 0 (skipped 2/2 steps) | 2 | runner-side polls/sleeps not surfaced; independent harness oracle polls every 4 ms | `task_verified_ms`: 3698.287 / 3964.796 | 40/40 · 0 | `[provider, provider]`; Driver `trusted_input` (type) + `dom` (click) | LIVE_PROVIDER + REAL + BENCHMARK |
| R2-03 guarded | same + `--guarded-completion` | **1** (40 HTTP) | 2 | 0 | 2 | same | 3519.708 / 3737.487 | 40/40 · 0 | `[provider, guarded-completion]`; fresh ref = dispatched 40/40 | LIVE_PROVIDER + REAL + BENCHMARK |
| R2-04 M checkbox / button / text | `229b65b28` · `8b037961` · none | 0 | 1 `get_window_state` (tree + screenshot, not parsed) + 1 verification obs | 0 | 1 / 1 / 2 | caller mutation wait 0.05 ms; **Driver per click: fixed 50 ms post-`DoAction` sleep + 220 ms focus-guard settle watch** | trial start → verified: 585.2 / 1717.0; 711.7 / 933.7; 3046.2 / 3059.8 | 40/40 each · 0 | `accessibility`; `Action.DoAction` (+`SetTextContents`) on the bus | REAL |
| R2-04 P (same types) | `28b915ae9` · `940eb2c2` · none | 0 | same | 0 | same | same | 583.9 / 1717.0; 711.6 / 933.9; 3045.8 / 3055.9 | 40/40 each · 0 | same | REAL |
| R2-05 typed (6 rows × 10) | caller `98a45e6c5` · `e57bb9ae` · mock | 1 mock + guarded completion | per runner | 0 (visual off) | 1 Submit dispatched per original run; +1 fresh run in RA only | reconciliation: 0.1 s reads up to 3 s | not measured (correctness lane) | outcomes: verified/reconciled 40 (R0, RA, RB, RC); `unresolved_unknown` 20 (RA2, RD: correct conservative result); **duplicates 0/60** | guarded-completion `dom_event` Submit; `route=dom` | REAL (+UNIT, SOURCE) |
| R2-05 naive (5 rows × 10) | same | same | per runner | 0 | 1 + restart | none beyond the runner's own reads | not measured | verified 50/50; **duplicates 10/50** (RD 10/10) | same | REAL |
| R2-05 runner (RE) | same | same | per runner | 0 | 1 | 20 × 0.1 s post-click reads + step-3 read | not measured | 0 duplicates; **10/10 ended in an uncaught `DriverToolError` with no outcome event and no receipt** | same | REAL |
| R2-06 T (trusted) | `229b65b28` · `8b037961` · none | 0 | 1 `semantic_v2` | 0 | 2 (`browser_type`, `browser_click` foreground) | 1 immediate read, then 50 ms re-reads to 3000 ms | not computed per trial. Click tool span 1613.0 / 1675.4; late class first verified 52.9 / 54.2 / 55.9 ms after return (min / p50 / max) | single read 17/30; **bounded 30/30**; accepted 30/30 | `trusted_input`; page `isTrusted:true` pointer chain on Submit 30/30 | REAL |
| R2-06 D (dom_event) | same | 0 | 1 | 0 | 2 | same | not computed. Click tool span 1564.7 / 1578.5 | single read 30/30; bounded 30/30 | `dom`; page `isTrusted:false` synthetic click | REAL |

### Work deleted (structural) vs wall-clock saved (measured), kept separate per lane

| Lane | Work deleted | Wall-clock saved (that lane's own fixture, binary and environment only) |
|---|---|---|
| R2-01 | Feedback OFF skips, per DOM click and per type, one overlay `PinAbove`/`MoveTo`/`ClickPulse` sequence and one awaited glide arrival: 2 awaited waits per fill→submit task. No CDP call, authorization check, revalidation or oracle read is removed. | Paired median **1517.9 ms per click**, 95% CI [1516.7, 1519.3], ON slower in 24/24 pairs. Descriptive and post-hoc: 1480.2 ms per type and 3012.0 ms per two-action trial. |
| R2-02 | Removed 4 sleeps and 4 reads across 24 trials. Added 3 CDP round trips and 1 subscriber per click. Net structural work **increases**. | **None.** The event arm was slower: +42.1 ms paired median, CI [+31.9, +56.9]. This is a session-age-drifting average: +10.9 ms over the first 6 pairs and +52.7 ms over the last 6. |
| R2-03 | Per task: 1 provider HTTP request, 1 decision, 710 input and 45 output tokens. Receipt-backed in 40/40 pairs. Driver actions and observations unchanged. | Paired median **211.849 ms per task**, 95% CI [−251.777, −192.138], guarded faster in 35/40 pairs. The 5.7% in the README is the paired median divided by the baseline median; the arm medians differ by 4.8%. |
| R2-04 | None (profile only). | None claimed. Candidate waits: cursor reveal 254.6–1416.4 ms, 50 ms post-`DoAction` sleep, ~241 ms settle watch. |
| R2-05 | None targeted. The typed consumer avoided 10 journal-confirmed duplicate mutations versus naive in RD, and spent 1 extra run per RA trial. | Not measured (no timing claim). |
| R2-06 | None. The fix **adds** a bounded re-read. | None claimed. The bounded re-read costs about one 50 ms poll in 13/30 trusted trials. |

There is no cross-lane total. In particular, R2-01's ~1.5 s per action (main + trace, mock, 0.32.0) and R2-03's ~212 ms per task (trycua/cua PR 4316, TypeSafe, 0.31.0) come from different sources, binaries and providers. They must not be summed or treated as a composed speedup. Only a measured R2-10 run on one compatible source can say what the two do together.

### Phase-0 coverage (>90% named-span gate)

- **R2-01** and **R2-04**: coverage is 1.0 by construction, because the marks are contiguous. The substantive result is the localization: in R2-01, one named phase (the visualization arrival wait) explains 98.46% of the ON click span; in R2-04, the cursor reveal plus the fixed waits explain most of each click.
- **R2-03**: median 1.0, range 0.976–1.006. The cap was not applied, so a post-oracle overrun is counted, and the residual is not reported separately.
- **R2-02**: the gate does not apply, because no latency claim is promoted (KILL).
- **R2-05, R2-06**: correctness lanes with no latency claim.

## 2. Dispositions

| Hypothesis | Disposition | Decisive evidence | Boundary |
|---|---|---|---|
| **R2-01** H1: the ~1.5 s browser action span is the agent-cursor glide | **KEEP** (KEEP_H1; all 4 pre-registered gates met) | ON 1541.6 vs OFF 23.5 ms click median. Paired D 1517.9 ms, CI [1516.7, 1519.3], 24/24 pairs. 98.46% of the ON span is inside `visualize_browser_action` (overlay arrival wait, median 1517.2 ms). Route, oracle outcome and failures (0/48) identical in both arms. Verifier re-run: 3/3 pairs, D 1518.1 ms. | One fixture and route (`dom_event`) plus `browser_type`, X11/Xvfb/picom, Chrome 151, mock provider. Authorization is unchanged by construction (SOURCE), not traced. Why the glide takes ~1.5 s was not profiled. **Not** a recommendation to turn feedback off by default. |
| **R2-02** commit-event wake beats the 100 ms poll | **KILL** (pre-registered: event slower, CI lower bound > 0) | +42.1 ms paired median, CI [+31.9, +56.9]; poll faster in 21/24 pairs. The oracle effect lands ~1 ms after `Runtime.callFunctionOn` returns, so the poll's first read already verifies (21/24). `Page.frameNavigated` necessarily lags the effect. Verifier fresh-session re-run: +13.9, +12.0 and +18.3 ms (direction confirmed, magnitude about a third). Correctness design held: 69/69 valid controls (57/57 on binary `7034a43b`, 12/12 on `38f8c11d`), 0 false successes. | This fixture, the `dom_event` route and the `isolated_new` CDP policy. Magnitude depends on session age (suspected per-call `Target.attachToTarget` without detach; SOURCE only, unverified). Run-1 C3 is invalid; the early-event guard rests only on the extension. `wait_for_window` is NOT_RUN. Delayed-effect pages untested. |
| **R2-03** guarded completion with a real provider deletes a decision and saves wall-clock | **KEEP** | 2 → 1 provider requests in 40/40 pairs, receipt-backed (api.typesafe.ai, HTTP 200, request id). Paired `task_verified_ms` −211.849 ms, CI [−251.777, −192.138], 35/40 pairs faster. Fresh post-mutation ref dispatched 40/40, 0 stale. C1 guard decline 3/3; C2 provider unreachable 2/2 with 0 mutations. Verifier re-run: 3 pairs, −236.3, −206.6 and −293.5 ms. | One fill→submit fixture, Python runner only, trycua/cua PR 4316 binary `e57bb9ae`, TypeSafe only, loadavg ~10 during timing. No control for provider failure **after** partial progress (the kvnloo/cua#78 criterion). trycua/cua PR 4394 code is not tested. |
| **R2-04** H_A: AT-SPI bulk/cache (`Cache.GetItems`/`Collection`) is the next native tactic | **KILL, scoped to this 9-element GTK3 window and the background element-token route** | Gate D max 0.005 against a 0.5 threshold. Click: 5 RPCs, ~0.2–0.3 ms bus time. Tree: 145 RPCs, ~2.9 ms inside a ~26 ms call. BULK NOT_RUN by rule. | Large-tree apps untested. A linear extrapolation (~16k RPCs, ~320 ms per 1000 elements) is NOT_RUN arithmetic. Bulk/cache stays a conditional tactic for large trees, as in kvnloo/cua#93. |
| **R2-04** H_B: Driver-internal localization of native action time | **KEEP**; R2-04 overall **REVISE** | All 240 measured trials verified. Cursor reveal 254.6 / 382.9 / 1416.4 ms, `set_value` cursor positioning 1288.4 ms, fixed post-`DoAction` sleep ~51.3 ms, settle restore ~241 ms. The app changed state ~299 ms before return. Distortion ≤0.4% (P vs M). Verifier re-run reproduced every span. | Localization, not causation: no intervention arm. One fixture and toolkit, X11. |
| **R2-05** a possibly landed effect stays unknown until reconciled; one negative read never authorizes replay | **KEEP** | Real MCP stdio, real Driver and Chrome, journal oracle. Typed duplicates 0/60. RD naive duplicated 10/10 (CI 0.692–1.000). RC's first reconciliation read was negative 10/10 while the original was in flight, and it then landed. kvnloo/cua#105 receipt `attempted=true, effect=unknown` 20/20 in RA. | Faults are injected at an in-process seam (REAL path, injected fault). Typed zeros after `unknown_effect` hold **by construction**; the only typed interval with empirical content is RA's reconsideration, 0/10 → upper bound 0.309. Reconciliation is experiment code: the kvnloo/cua#105 runner stops at `unknown`. The pre-write rule holds only when the request's own write raised. An SDK `ClosedResourceError` from `call_tool` is not proof (mcp 1.30.0 can raise it after the effect landed). TypeScript runner, Driver crash, pipe cut and cancellation are NOT_RUN. |
| **R2-06** H: trusted-route "accepted but not verified" is a verification-timing race, not lost input | **KEEP** | Accepted 30/30; single read 17/30; bounded 30/30. All 13 late trials show the full trusted chain on Submit and exactly 1 POST, landing 3.6–10.1 ms after return. POST timing separates the classes in 70/70 trials. 0 X11 events; focus, activation and geometry nominal 30/30. Verifier re-run: 5/5 trusted trials verified on first read, so the late class did **not** reproduce (P ≈ 0.06 if the true rate were 13/30). | The late rate depends on caller read latency and load, and is not a Driver property. The 30/30 "fix" is a re-scoring of the same receipts, not an independent test. E1's own 3/5 misses cannot be confirmed to share this cause. The mechanism is not isolated: browser-side scheduling and the co-located fixture server's GIL were not separated. Uncertainty intervals are not in `analyze.py` (open advisory). |

Side findings that are not hypotheses but go to owners:
1. **Receipt delivery mislabel (R2-06, SOURCE + REAL).** Foreground trusted `browser_click` returns `delivery:{mode:"background"}`, because `action_record.rs` `actual_delivery_from_legacy` hard-codes `Background` for `browser_click`/`browser_pointer`/`browser_type`. The actual-delivery field is not trustworthy for these tools.
2. **Suspected per-call CDP session accumulation (R2-02, SOURCE only).** One unit of CDP event traffic is added per tool call (C1: exactly 4 × (seq + 1) events per deadline), with no matching detach found. Unverified. If real, it affects long sessions in every browser lane.
3. **kvnloo/cua#105 runner gaps (R2-05).** (a) No bounded reconciliation in the runner. (b) No guard against a second completion while the first is unresolved. (c) A read failure after an unverified completion escapes uncaught, with no receipt (RE 10/10).
4. **The bounded re-read applies on every route (R2-06, R2-01, R2-02).** In R2-06, 25/30 dom_event POSTs also landed after tool return, by at most +1.83 ms. R2-01 and R2-02 both saw the effect land just after return (median +0.3 to +1 ms), so "the first read verifies" is a race that happens to be won on this fixture. In R2-04 (native) the effect landed ~299 ms *before* return.

RFC/contract delta: **none** from any lane. No lane added a service, verifier, router, registry, batch API or event service. All instrumentation is measurement-only, env-gated and default-off, and each was checked by a default-off smoke run or a source review.

## 3. What this unblocks or kills in P1, and ranked next experiments

### P1 status

| P1 id | Status after P0 | Gating P0 result(s) |
|---|---|---|
| **R2-07** one verified compiled routine | **Unblocked, with one prerequisite.** The fixture (jev-use fill→submit, admitted by kvnloo/cua#24), fresh-ref authority (R2-03, 40/40) and target oracle exist. Gate 5 (reconcile a may-have-landed mutation before fallback dispatches) is **not** provided by the runner (R2-05 Finding 4), so the R2-07 caller under test must include bounded reconciliation, or kvnloo/cua#105 must add it first. Hold feedback constant across arms and report it. Otherwise ~1.5 s per action (R2-01) dwarfs what a compiled replay removes, which on this fixture is decisions: one live decision is ~206 ms in R2-03. Do not borrow those numbers; measure in-run. Every verification must be a bounded re-read (R2-06). | R2-03 KEEP, R2-05 KEEP (and its runner-gap finding), R2-06 KEEP, R2-01 KEEP_H1 (as a confound to control) |
| **R2-08** one cross-surface equivalence test | **Unblocked, independent of P0.** No P0 lane produced evidence for or against a programmatic surface. R2-01, R2-06 and R2-02 add one requirement: the comparison must use bounded re-reads of the same target oracle, because effect timing differs by route (dom vs trusted). | None decisive; R2-06 sets the verification rule |
| **R2-09** native event wake | **Deprioritized / REVISE target.** On the GTK3 fixture there is no caller-side wait to delete: the effect lands ~299 ms before return and the caller's mutation wait is 0.05 ms (R2-04). The browser analogue was KILLed because the wake lags the oracle (R2-02). The only native wait left is Driver-internal: the fixed 50 ms post-`DoAction` sleep (the app signal arrives 0.1–0.5 ms after `DoAction`). Run R2-09 only after a causal A/B shows that the sleep can be shortened safely. The 220 ms settle watch guards against focus steal, and event absence cannot prove "no steal", so it is not an event-wake target. | R2-04 (H_B KEEP, no caller wait), R2-02 KILL (lagging wake) |
| **R2-10** compose surviving deletions | **Unblocked for a 2-factor run; nothing composed yet.** Surviving treatments: guarded completion (R2-03) and feedback-off as a host opt-in (R2-01). Excluded: CDP commit wake (R2-02 KILL), AT-SPI bulk (R2-04 H_A KILL, scoped). The bounded re-read (R2-06) and reconcile-before-replay (R2-05) are correctness requirements in every arm, not treatments. The two survivors were measured on **different** sources, binaries (0.31.0 vs 0.32.0) and providers (TypeSafe vs mock), so composition must be re-measured on one source that has both guarded completion and `set_agent_cursor_enabled`. Confirm that the tool exists at that source before pre-registering. | R2-01 KEEP_H1, R2-03 KEEP; R2-02 and R2-04 remove candidates |

### Ranked next experiments

Ranked by critical-path work deleted, then evidence cost, risk and upstream fit. Each gate cites the P0 result that admits it.

1. **R2-10 2×2: guarded completion × feedback ON/OFF** on one exact source and binary with a live TypeSafe provider. Use ≥30 AB/BA-interleaved blocks with per-trial loadavg, the fixture `/state` oracle with bounded re-reads, and reconcile-before-replay. Report each main effect and the interaction; do not sum. Gate: R2-01 KEEP_H1 + R2-03 KEEP. Highest expected deletion on the critical path, at low risk (an existing toggle and flag, no new service).
2. **Native causal A/B on the R2-04 waits:** cursor reveal (via `set_agent_cursor_enabled`, if it governs the native overlay), the fixed 50 ms post-`DoAction` sleep, and the 220 ms settle watch. Each needs its own arm, the same state-file oracle, and stale-token and focus-steal negatives. Gate: R2-04 H_B KEEP, REVISE.
3. **Glide-duration profile (R2-01 NOT_RUN):** why the X11 overlay glide takes ~1.5 s (renderer pacing, speed-based distance, picom/Xvfb frame timing). This is measurement-only and feeds any non-blocking-glide or opt-in-knob proposal through kvnloo/cua#73 / kvnloo/cua#74. Gate: R2-01.
4. **kvnloo/cua#105 runner hardening test:** a fixture that keeps Submit observable after an unresolved completion, to test (a) an unresolved-completion guard in the runner loop and (b) a receipt on read failure after an unverified completion. Include a provider failure after partial progress, which also closes R2-03's missing kvnloo/cua#78 control. Gate: R2-05 Findings 4–5. Correctness, small.
5. **R2-07 bounded compiled-routine probe** on jev-use fill→submit. Use ≥20 warm attempts per arm, feedback held fixed, all of kvnloo/cua#93's gates, and caller-side reconciliation. Gate: R2-03, R2-05, R2-06 (and item 4 if the runner should own reconciliation).
6. **CDP session-accumulation check (R2-02 confound):** on main, count attached targets/sessions and CDP event volume over N tool calls in one session. If confirmed, file it with the browser-timing owner. Gate: R2-02 drift section. It also decides whether any long-session browser timing (including R2-01's single-session run) carries a drift term.
7. **Receipt delivery-truthfulness unit check:** a failing test showing foreground trusted `browser_click` reports `background`. Route it to kvnloo/cua#38 / upstream trycua/cua 4009 (outcome vocabulary). Gate: R2-06 separate finding.
8. **Independent, pre-registered test of the bounded re-read** on a fresh run and a second fixture with a slow or asynchronous handler. This replaces the R2-06 re-scoring, and it should include an immediate-read latency stamp per trial. Gate: R2-06 (non-independent fix arm; late class did not reproduce in the verifier re-run).
9. **R2-08** cross-surface equivalence, as specified in kvnloo/cua#93. Independent.
10. **Large-tree AT-SPI profile** (file manager or office suite) to decide whether gate D ever fires. Run BULK only if it does. Gate: R2-04 H_A scope.
11. **R2-09** native wake. Only after item 2 shows the 50 ms sleep is causal and replaceable.

## 4. Completeness critic

### Not run (NOT_RUN or BLOCKED, by lane)

- **R2-01:** why the glide takes ~1.5 s; jev-use Python/TS suites (code untouched); any live provider; other compositors.
- **R2-02:** `wait_for_window`'s 0.25 s poll (no CDP event exists for native window creation); earlier wake signals (`Network.requestWillBeSent`, `Page.frameStartedNavigating`); the existing-profile CDP policy path (where `Page.disable` would be refused); delayed-effect pages; CPU cost; a per-block session reset.
- **R2-03:** the TypeScript runner live; any provider other than TypeSafe (S1 exists only in trycua/cua PR 4394, whose adapter is not local); trycua/cua PR 4394 code itself; provider failure after `browser_type` landed; monetary cost (no price field).
- **R2-04:** the BULK arm; the keyboard/pointer fallback route; large trees; other toolkits (Qt, VCL, Chromium); any causal intervention.
- **R2-05:** the TypeScript runner on a real transport; Driver crash and OS pipe cut as fault mechanisms; socket transport; cancellation and native lifetime (kvnloo/cua#9); idempotency rows; any timing.
- **R2-06:** the conditional trycua/cua PR 4316 arm (not triggered); the 0.31.0 binary E1 used; an independent test of the fix; uncertainty intervals in `analyze.py` (the edit was denied by the permission classifier; the verifier's exact values are quoted in the lane result: bounded [0.886, 1], single [0.392, 0.726], McNemar p ≈ 2.4e-4).
- **P1:** R2-07, R2-08, R2-09 and R2-10 were not started. No composed treatment exists.

### Missing or weak controls

- **R2-01:** the stale-ref refusal code was not captured (the trace is consistent with `browser_ref_stale`). The UNIT logs predate the instrumentation commit by ~2 min, and whether the test compiles held the cargo lock was not recorded.
- **R2-02:** the run-1 C3 early control could not fail; it was replaced by a 6+6 extension on a different binary. The session-age confound was not controlled. C1 "lost" is suppression on the consumer side, not a lost CDP event.
- **R2-03:** no provider failure after partial progress. Runner-side polls, sleeps and fresh reads are not surfaced. Receipt logging adds 2 more lines per baseline trial (sub-millisecond, undisclosed in the README). About 3.2 s in one baseline provider call (pair 16) is unattributed.
- **R2-04:** the binary per session is not in the raw meta (corroborated by the verifier outside the packet). There is an unexplained 8.4–9.7 ms monitor-on speedup in two strata. Gate D uses monitor-side bus time; Driver-side AT-SPI time gives D ≈ 0.01, which does not change the verdict.
- **R2-05:** the gates were registered after pilot3 had shown the outcomes, so they are not blind. Typed zero-duplicate counts after `unknown_effect` hold by construction. The scoped pre-write rule was checked harness-side from raw/, never by a caller. The Chrome version is not captured per run.
- **R2-06:** the X recorder's positive check exercised motion only, not button events. The immediate-read latency was not stored per trial. The fixture server shares a process (and the GIL) with the MCP client. The late class did not reproduce in the verifier re-run (0/5).

### Claims that rest on one run

Every lane's measured result is one run: one session or batch, on one host, on one day.
- R2-01: 24 pairs in one session.
- R2-02: 24 pairs in one long Driver/browser session, which is the source of the drift.
- R2-03: 40 pairs at loadavg ~10.
- R2-04: one 8-session batch.
- R2-05: 120 trials in one session.
- R2-06: one 8-block run.

The independent verifier re-runs were small (3 to 10 trials) and pooled with nothing. They confirm direction for R2-01, R2-02, R2-03, R2-04 and R2-05. They **do not** confirm the R2-06 late rate (0/5 late vs 13/30), and they put the R2-02 magnitude at about a third of the packet's.

p95 values from n = 24–40 are estimates, not tail guarantees.

### Platforms and surfaces untested

The following were untested in every lane:
- macOS and Windows;
- Wayland and Omarchy/Hyprland (kvnloo/cua#94);
- GPU compositors and real (non-Xvfb) X servers;
- any browser other than Chrome 151 (the Driver picked `/opt/google/chrome`, not `/usr/bin/chromium`);
- non-GTK3 native toolkits;
- multi-monitor or HiDPI setups (DPR was 1 throughout).

### Cross-lane contamination and rule deviations to log

- **Timing windows overlapped with other lanes' correctness work.**
  - R2-03's timing window (22:09:01–22:18:41Z, loadavg median 10.19) overlapped R2-01's unlocked shakedown (~22:09:14Z) and R2-05's unlocked 120-trial correctness run (22:15:46–22:44:16Z, up to 10.82).
  - R2-05's run also overlapped R2-01 (22:18:41–22:21:30Z), R2-04 (from 22:21:30Z) and R2-02 (22:22:39–22:28:09Z).
  - R2-06 (22:04:05–22:09:00Z) overlapped R2-03's C1/C2 correctness controls.
  - R2-01's in-session cargo test compile (~22:22:53–22:24:31Z) overlapped R2-02's timing window (22:22:39–22:28:09Z).
  - Every timing lane interleaved its arms and recorded loadavg per trial, so the contamination spreads across arms. Absolute magnitudes, especially tails, carry it.
- **Commands run outside the isolated session:** `build-driver.sh`'s `--version` (setup, R2-01, R2-02, R2-04), and R2-03's `chrome --version`. Neither uses the display. R2-04 ran its unit tests in the host shell with host display variables set; they were re-run in the session, and the tests launch no Driver, GTK app or browser. R2-06 ran `xinput --help` once against the host X server. That call was read-only and failed, but the rules required a stop-and-report, and the lane disclosed it instead. **Orchestrator decision needed.**
- **Git history and refs:** R2-06 rewrote its own local pre-registration commit to remove local paths: `PREREG.json` is byte-identical, the change is disclosed, and the old commits are reflog-only. R2-02 ran `git fetch upstream main`, which moved `refs/remotes/upstream/main` only, with no local branch touched.
- **Clean:** no GitHub writes, pushes, secrets printed or foreign processes killed in any lane. The TypeSafe key was forwarded by name only, and only in R2-03 (lane 132 plus verifier 9 = 141 of the 300-request cap).

## 5. Draft comments (not posted)

Written under `<lanes>/artifacts/r2/drafts/`:
- `93.md`: results table and packet links (kvnloo/cua#93)
- `10.md`: accounting rows (kvnloo/cua#10)
- `73.md`: worker-queue status (kvnloo/cua#73)
- `105.md`: R2-05 evidence (kvnloo/cua#105)
- `20.md`: R2-04 evidence relevant to invalidation and R2-09 (kvnloo/cua#20)
- `78.md`: R2-03 receipt evidence and the missing partial-progress control (kvnloo/cua#78)

The links use `https://github.com/kvnloo/cua/blob/<branch>/docs/experiments/...`. The branches are **not on the fork yet**, so the links resolve only after the orchestrator pushes the packet HEADs listed in section 0. Upstream items are written as plain text ("trycua/cua PR 4316") so that posting does not autolink upstream threads.
