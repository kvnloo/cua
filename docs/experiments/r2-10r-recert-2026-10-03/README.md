# R2-10R: R2-10 recertification on upstream main 0f1955d2f (attempt 2, 2026-10-03)

Lane R2-10R, wave 4 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-10), kvnloo/cua#10 (whole-task
accounting), kvnloo/cua#73 (E6 freshness). Upstream items are plain text (trycua/cua PR 4375).

**Disposition: RECERTIFIED** (pre-registered rule in PREREG.json `gates`: Phase 0 passes in full,
validity 100% in every arm, 0 E4 violations, every R2-10 scripted/native S whose CI excluded 1 excludes
1 again in the same direction, every component keeps its verdict mapping, D1 element digests identical
40/40). All six gates pass; `recert-summary.json` lists 0 changed claims; the S gate covers 18 gated S rows
(the first version checked only 15; post-hoc correction in `PREREG-AMENDMENT-2.json`, Deviation 10). One
component crossed the 5% line and is flagged below (not hidden). Native timing block nm2 had a few
seconds of another track's unlocked CPU work inside its EXCLUSIVE window; the native claims hold without
it (sensitivity below, Deviation 9). Provider: 0 attempts, 0 reached (lane cap 0).

What this recertifies (E6): every Driver-side R2-10 claim survives trycua/cua PR 4375 (cua-driver-core
snapshot_store.rs, tool_schema.rs, platform-linux tools/impl_.rs) and trycua/cua PR 3489 (cua-driver-sdk
embedded.rs, key_pacing.rs, lib.rs). The first-snapshot grace leaves the native observation's element
set unchanged (D1). R' numbers are never ratioed against R2-10's numbers; only verdicts are compared.

## Headline (L-scripted and native on R')

One binary R' (0f1955d2f + R2-10 steps 1-8, tested head 45dff8f32, sha256 `922111c5...`) in every arm,
phase trace on in every arm, private Xvfb, AB/BA or Williams-balanced, every measured chunk under the
cargo-build lock and then `bin/quiet-timed` (EXCLUSIVE). S = median T_BASE / median T_arm over rounds
where both are valid; T = T_oracle (first 2 ms oracle sample at/after the last accepted mutation's
return showing the expected final state); seeded paired bootstrap, 10000 resamples, 95% percentile CI.

| layer | class/task | arm | n pairs | median T_BASE | median T_arm | S (T_oracle) | 95% CI | S (T_land) | 95% CI | class |
|---|---|---|---|---|---|---|---|---|---|---|
| L-scripted | fill->submit | COMP | n=32 | 3189.9 ms | 69.9 ms | 45.65 | [44.39, 48.36] | 45.65 | [44.39, 48.36] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | toggle->confirm | COMP | n=32 | 2503.4 ms | 53.5 ms | 46.82 | [45.21, 48.69] | 46.89 | [45.21, 48.62] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | modal->act | COMP | n=32 | 2491.4 ms | 55.5 ms | 44.86 | [43.56, 46.81] | 45.10 | [43.58, 46.78] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | fill->submit | COMP_E | n=32 | 3189.9 ms | 53.9 ms | 59.19 | [56.05, 63.91] | 59.21 | [57.07, 63.94] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | toggle->confirm | COMP_E | n=32 | 2503.4 ms | 37.6 ms | 66.56 | [63.47, 69.19] | 66.47 | [63.45, 70.73] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | modal->act | COMP_E | n=32 | 2491.4 ms | 37.3 ms | 66.88 | [63.45, 70.55] | 66.90 | [63.40, 70.50] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | fill->submit | COMP_K (KEEP-only) | n=32 | 3189.9 ms | 3168.0 ms | 1.01 | [1.00, 1.01] | 1.01 | [1.00, 1.01] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | toggle->confirm | COMP_K (KEEP-only) | n=32 | 2503.4 ms | 2481.4 ms | 1.01 | [1.01, 1.01] | 1.01 | [1.01, 1.01] | REAL+BENCHMARK (FIXTURE) |
| L-scripted | modal->act | COMP_K (KEEP-only) | n=32 | 2491.4 ms | 2464.4 ms | 1.01 | [1.01, 1.01] | 1.01 | [1.01, 1.01] | REAL+BENCHMARK (FIXTURE) |
| native GTK3 | checkbox | S0 (KEEP-only) | n=24 | 334.3 ms | 282.9 ms | 1.18 | [1.18, 1.18] | 1.00 | [1.00, 1.04] | REAL+BENCHMARK (FIXTURE) |
| native GTK3 | text entry | S0 (KEEP-only) | n=24 | 1761.3 ms | 1709.0 ms | 1.03 | [1.03, 1.03] | 1.00 | [1.00, 1.00] | REAL+BENCHMARK (FIXTURE) |
| native GTK3 | checkbox | X | n=24 | 334.3 ms | 283.0 ms | 1.18 | [1.18, 1.18] | 1.00 | [0.98, 1.03] | REAL+BENCHMARK (FIXTURE) |
| native GTK3 | text entry | X | n=24 | 1761.3 ms | 298.9 ms | 5.89 | [5.87, 5.90] | 28.69 | [28.68, 28.72] | REAL+BENCHMARK (FIXTURE) |

The COMP_K CIs print as [1.00, 1.01] / [1.01, 1.01] at two decimals; unrounded, all three lie above 1
(fill [1.003, 1.008], toggle [1.007, 1.010], modal [1.009, 1.015]; `r2-10r-summary.json`).

Fill, all invocations with the training invocation charged with compile + admission: COMP amortized
(ratio of means) 42.62 [38.78, 45.88], warm-only 45.66 [44.39, 48.39]. KEEP-only fill (COMP_K)
amortized ratio of means 0.98 [0.92, 1.01] (not gated: its R2-10 CI also included 1; the training
invocation of the KEEP-only arm pays a full feedback-ON step loop plus a feedback-ON admission replay).
The other gated fill rows (4 decimals, `recert-summary.json` `S_direction.rows`): COMP_E amortized
56.4091 [52.6800, 59.9564], COMP_E warm-only 59.1965 [57.0584, 63.9202], COMP_K warm-only
1.0069 [1.0032, 1.0081].

T_land vs T_oracle: on the browser classes S_land equals S within the CI (the effect lands inside the
last call). On native, the post-action sleep (S0) runs after the effect has already landed, so S0
deletes no T_land time (S_land 1.00) while it deletes 51-53 ms of T_oracle; the X arm's text gain is
the cursor reveal before the set_value effect, so it shows on both metrics.

Validity: 384/384 scripted measured trials and 144/144 native measured trials verified by the
independent oracle with exactly one completion mutation and a valid forced path (100% in all 18
arm x class/task cells). E4: 0 stale-ref dispatches, 0 duplicate mutations, 0 unverified successes,
0 refusals returned as success, 0 blind replays in every arm, every admission replay and every control.

## Recertification gates (verdicts only; reference = accepted R2-10 summary)

| gate | result | class |
|---|---|---|
| Phase 0 (a)-(e) on R' | pass in full (table below) | UNIT, REAL |
| validity 100% every arm | 18/18 cells at 1.0 | REAL+BENCHMARK (FIXTURE) |
| 0 E4 violations | 0 in every arm, admission and control | REAL |
| S direction: every R2-10 scripted/native S row whose CI excluded 1 (18 gated S rows, all above 1) | 18/18 above 1 again (scripted COMP, COMP_E, COMP_K per class; COMP and COMP_E fill amortized and warm-only; COMP_K fill warm-only; native S0 and X per task). COMP_K fill amortized is reported, not gated (its R2-10 CI included 1; on R' it includes 1 again) | REAL+BENCHMARK (FIXTURE) |
| verdict mapping | 0 verdict mismatches over 18 decomposition units (12 scripted arm x class, 6 native arm x task); 16/16 work-deleted signs kept for components whose R2-10 deletion was >= 5 ms | REAL+BENCHMARK (FIXTURE) |
| D1 element digests | 1 distinct elements digest over 40/40 valid trials | REAL+BENCHMARK (FIXTURE) |

Flagged (not hidden): `scripted/toggle/COMP:reval_other` (IRREDUCIBLE) crossed the 5% line downward
(R' 2.68 ms = 4.9995% of mean T_runner; R2-10 just above 5%). Its verdict is unchanged; no E2 untested
status changed (`recert-summary.json` `flagged_threshold_crossings`, `flagged_e2_status_changes`).

## Native block nm2: external interference and sensitivity (post-hoc, PREREG-AMENDMENT-2)

Another track's verifier (bend-stack lane B389) ran a few seconds of single-core Python without the
quiet-lane lock at about 05:52:45-05:53:32Z, inside this lane's EXCLUSIVE window r2-10r-a2-nm2
(05:51:37.630-05:54:27.287Z). The lane learned of it after the results commit, from the other track's
synthesis (section 9) and the session orchestrator's note `EXTERNAL-INTERFERENCE.md` in the lane
mirror. Correctness rows are unaffected. nm2 stays counted as pre-registered; it was not re-run.
`sensitivity_nm2.py` recomputes the four gated native S rows with the same S rule
(`nm2-sensitivity.json`, recomputed by `verify_artifacts.py`):

| native S (T_oracle) | nm1 only (rounds 0-11) | 95% CI | n | nm2 window rounds dropped | 95% CI | n | class |
|---|---|---|---|---|---|---|---|
| checkbox S0 | 1.1837 | [1.1754, 1.1888] | n=12 | 1.1837 | [1.1793, 1.1853] | n=19 | REAL+BENCHMARK (FIXTURE) |
| text S0 | 1.0305 | [1.0293, 1.0315] | n=12 | 1.0305 | [1.0298, 1.0315] | n=20 | REAL+BENCHMARK (FIXTURE) |
| checkbox X | 1.1835 | [1.1782, 1.1881] | n=12 | 1.1835 | [1.1799, 1.1876] | n=19 | REAL+BENCHMARK (FIXTURE) |
| text X | 5.8906 | [5.8614, 5.8972] | n=12 | 5.8910 | [5.8713, 5.8972] | n=20 | REAL+BENCHMARK (FIXTURE) |

"Dropped" removes every round (all three arms) that has a main nm2 trial overlapping the window +/- 5 s:
27 nm2 trials (nm2-025..nm2-051), checkbox rounds 16-20 and text rounds 16-19. All 8 rows exclude 1
above 1, the R2-10 direction. Per-arm median T_oracle in nm1 vs nm2 differs by at most 0.96 ms, and the
1-minute loadavg of the overlapping trials was 1.67-2.13.

## Drift row D1: first-snapshot grace (trycua/cua PR 4375) on the native observation

Forced path: arm G = first `get_window_state` of a fresh GTK3 checkbox window with `timeout_ms`
omitted (grace path); arm E = the same call with explicit `timeout_ms` 1000. 20 AB/BA pairs, fresh
Driver and fresh fixture per trial, one EXCLUSIVE acquisition (`r2-10r-a2-d1`).

| row | result | class |
|---|---|---|
| validity | 40/40 valid (no failure, app state unchanged by the observation) | REAL |
| forced path | G reported timeout_ms 2000 in 20/20; E reported timeout_ms 1000 in 20/20 | REAL |
| no grace once a semantic snapshot exists (control outside T) | second call reported 1000 in 40/40 | REAL |
| element set | 1 distinct elements digest (tree_markdown digest also 1 distinct; second-call digest equal 40/40) | REAL |
| truncation | truncated=false 40/40, nodes_visited 9, nodes_pending 0 in every trial | REAL |
| median T of the observation call | G 48.9 ms, E 50.6 ms | BENCHMARK |
| median walk | G 9.5 ms walk, E 10.5 ms walk | BENCHMARK |
| paired T difference G - E | median +4.95 ms, 95% CI [-5.02, +21.37] ms | BENCHMARK (indicative: load-contaminated) |
| paired Driver span difference G - E | median +2.63 ms, 95% CI [-3.60, +16.71] ms | BENCHMARK (indicative: load-contaminated) |

The grace changes the walk budget only; the GTK3 walk takes ~10 ms, far below either budget, so the
observation span difference is not distinguishable from 0 and the element set is identical. D1 ran at
a 1-minute loadavg of 18.5-25.0: it rose from 22.0 to 25.0 inside the EXCLUSIVE window and was still
18.5 after 80 s, so other tracks' unlocked work ran during it (not decay from the previous holder). The
two paired-difference timing rows are therefore labelled indicative (load-contaminated); the gated D1
correctness rows (digests, truncation, forced path, dispatch count) do not depend on load. The tails
(max T 327 ms) are load, in both arms.

Browser path: SOURCE call graph (`raw/drift/d1-callgraph-grep.txt`): the only call site of
`resolve_timeout_ms_with_first_snapshot_grace` / `contains_semantic_window` outside tests is
platform-linux `GetWindowStateTool::invoke` (`linux_snapshot_timeout_ms`). Trace mark count over every
browser trace in this packet (472 browser trace files, 212355 marks): 0 get_window_state dispatches
and 0 lines naming either symbol; the positive control is D1 itself (one `get_window_state`
dispatch_enter per observation call: 2 per trial in 40/40 D1 trials).

## What each arm is (forced path, unchanged from R2-10)

- **BASE**: feedback ON with the Driver default glide (`set_agent_cursor_motion {glide_duration_ms:0,
  dwell_after_click_ms:80}`), ordinary runner, 100 ms completion poll, library MCP output validation,
  no `CUA_DRIVER_EXP_*` variable.
- **COMP**: feedback OFF (OWNER_DECISION); `CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS=0` on fill
  (OWNER_DECISION); 10 ms poll; caller-compiled validators (compiled at tools/list outside T);
  `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`; guarded completion and compiled replay on fill. The first
  invocation per arm ran training, compile and a clean-reset admission (all counted; admitted in COMP,
  COMP_E and COMP_K, admission replays verified 3/3 with fresh bindings).
- **COMP_E**: COMP + `CUA_DRIVER_EXP_ENDPOINT_REPROOF=bound` (OWNER_DECISION).
- **COMP_K**: COMP minus the OWNER_DECISION knobs (feedback default ON, focus settle default).
- **Native**: BASE defaults; S0 = `CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0` (KEEP); X = S0 +
  `set_agent_cursor_motion {glide_duration_ms:1}` (OWNER_DECISION).

Every trial used a fresh Driver, a fresh isolated Chromium (fresh token) or GTK3 app, and a fresh
fixture. Scripted design: 32 rounds, classes rotated, the 4 arms in Williams row (r mod 4), run as S1
(rounds 0-15) and S2r (rounds 16-31). Native: `harness/native-plan.json` blocks nm1, nm2 (24 rounds
per task, Williams 3-treatment) and nd1 (focus steal).

Actual route/producer (receipts + marks): fill = `browser_type:trusted_input` (128/128 accepted type
actions) then `browser_click:dom`; toggle/modal = two `browser_click:dom`, each click with
`input_route=dom_event` and a `click.cdp_send` mark inside the call; native = `click:accessibility`
(AT-SPI DoAction) and `set_value:accessibility` with the R2-04 mark sequence in order. Arm configuration
marks (arrival waits/glide, focus settle, poll, V/E knob marks, compiled validators, decision routes,
native knob marks and cursor motion) were checked on every row; 0 rows were refused for a mismatch.
Decision producers: BASE 2 scripted decisions per trial in every class; COMP fill 1 decision in 32
invocations (the training invocation; 31 warm compiled replays; 0 fallbacks); COMP toggle/modal 2.

## Independent target-owned oracle

Browser: the jev-use fixture server state (fill `submitted == token`; toggle `checked`; modal `opened`
and `modal`) with its CLOCK_MONOTONIC mutation journal, re-read every 2 ms by a harness thread (not the
runner). Native: the GTK3 task state file (`CUA_GTK3_TASK_STATE`, fresh per trial), read every 2 ms by
an independent harness thread. D1 has no task outcome: its oracle is the app state file (unchanged by
the observation in 40/40) plus the Driver-reported walk fields.

## Phase 0 on R' (all passed before the first measured trial)

| row | result | class |
|---|---|---|
| (a) unit | `cargo test -p cua-driver-core --lib browser::` 193 passed / 0 failed incl. the 4 FIX-01 detached-node tests; `tool_schema::` 13 passed incl. `first_snapshot_grace_never_overrides_an_explicit_timeout`; `snapshot_store::` 31 passed incl. `semantic_membership_ignores_capture_only_publication`; `phase_trace` 6 passed; jev-use python 257 OK (1 skipped), test_runner_refusal.py 9 OK, test_guarded_runner.py 7 OK; npm test 163/163, run_refusal.test.ts 8/8, typecheck rc 0 | UNIT |
| (b) FIX-01 C1/N4a on R', n=20 | first Submit click refused `browser_ref_stale` 20/20, 0 old-node page events, rebind + verify 20/20; U (`b02-560bd8247`) accepted the detached click 5/5 | REAL |
| (c) B-02 N-W2 on R', n=20 per class | stale action refused 20/20 toggle and 20/20 modal, 0 detached-handler effects, fresh re-derivation verified 40/40; U fired the server effect 5/5 toggle and 5/5 modal | REAL |
| (d) default-off smoke, R' (no knobs, no trace) vs Cn' | tools/list reply byte-identical (sha256 `33772fab...`, 195291 bytes, 3 reads each); fill/toggle/modal 5/5 verified on both with identical receipt shapes; native checkbox/text 5/5 verified on both with identical receipt shapes; no trace-like file appeared, native trace files stayed empty (0 of 10 non-empty per binary) | REAL |
| (e) R2-07b gates on R', n=5 | 5/5 verified training, 5/5 compiled with a clean authority check, 5/5 clean-reset admission replays verified, fresh binding 10/10; reconcile applied_ack_lost 5/5 and delayed_after_first_unchanged_read 5/5 verified_by_reconcile, withheld_unresolved 5/5 unknown; 0 duplicates, 0 dispatches after unknown | REAL+FIXTURE |

Attempt-1 row c-nw2-U (rc=1) explained: a failed session start, not a U or R' fault. In that session
openbox and picom could not open the display, the Driver logged `X11 overlay: cannot connect to
display` in every trial and xvfb-run's cleanup found the Xvfb pid already gone; every trial then failed
in setup, and `run_critpath.OraclePoller.stop` joined a never-started thread, so the rows read
`cannot join thread before it is started` instead of the real error. Attempt 2 fixed the harness
(Deviation 2) and re-ran the row: U fired 5/5 per class.

## Controls (outside T)

| control | n | result | class |
|---|---|---|---|
| N4a inside COMP (node replaced between bind and dispatch) | 15 (5/class) | 15/15 refused `browser_ref_stale`, rebound on a fresh observation, verified | REAL |
| OOD: COMP fill routine on the toggle/modal page | 5 | 5/5 precondition miss -> guarded continuation (fallback) -> verified | REAL |
| N-W2 inside COMP | 5 | 5/5 stale action refused, 0 detached effects, fresh marker seen, verified | REAL |
| fallback in measured COMP fill | 93 warm replays (31 each in COMP, COMP_E, COMP_K) | 0 fallbacks needed; 3/3 training invocations admitted | REAL |
| native focus steal ~100 ms after the app state changed | 30 (5 per task per arm) | stolen 30/30, 0 missed, verified 30/30; focus returned to the exact pre-steal state 30/30 | REAL (FIXTURE) |

Focus-steal note: the harness's `restored` field compares the final focus with the focus captured
before the first action; it reads 26/30 (BASE 9/10, S0 9/10, X 8/10). In the 4 other trials the app
itself had moved X input focus to another window of the same X client (0xA00004; pre-trial focus
0xA00003) before the steal, and the Driver restored that
pre-steal state exactly (raw/native/nd1). R2-10 reported 10/10 per arm on the same field.

## Per-component decomposition (L-scripted COMP, mean ms and share of mean T_runner)

Definitions and verdicts are R2-10's (B-01 decompose + B-02 taxonomy; `* ` = above 5% or 50 ms).

| component | verdict | fill | toggle | modal |
|---|---|---|---|---|
| observation | IRREDUCIBLE | 24.5 (30.3%)* | 14.8 (27.6%)* | 15.7 (28.3%)* |
| reval_endpoint | OWNER_DECISION | 24.2 (29.9%)* | 23.2 (43.3%)* | 23.5 (42.5%)* |
| sleeps_polls | IRREDUCIBLE | 8.8 (10.9%)* | 0.0 | 0.0 |
| mcp_transport (total) | UNTESTED | 5.3 (6.6%)* | 4.7 (8.8%)* | 4.8 (8.8%)* |
| - mcp_transport_in (client send + pre-dispatch outside admission) | (part of mcp_transport) | 1.35 | 1.40 | 1.45 |
| - mcp_transport_out (client return/parse + post-dispatch) | (part of mcp_transport) | 3.99 | 3.32 | 3.40 |
| dispatch | IRREDUCIBLE | 3.9 (4.9%) | 1.1 (2.0%) | 1.3 (2.3%) |
| reval_other | IRREDUCIBLE | 2.5 (3.1%) | 2.7 (5.0%, flagged) | 2.9 (5.2%)* |
| resolution | UNTESTED | 2.5 (3.1%) | 1.2 (2.2%) | 1.1 (2.1%) |
| target_effect_lag | IRREDUCIBLE | 2.0 (2.5%) | 0.0 | 0.0 |
| visualization | OWNER_DECISION | 1.8 (2.3%) | 1.8 (3.3%) | 1.9 (3.5%) |
| mcp_admission (residual after the cache) | UNTESTED | 1.6 (2.0%) | 1.6 (3.1%) | 1.6 (3.0%) |
| input_prep | UNTESTED | 1.3 (1.6%) | 0.0 | 0.0 |
| verification_reads | IRREDUCIBLE | 0.7 (0.9%) | 1.1 (2.1%) | 1.1 (2.0%) |
| unattributed | UNTESTED | 0.8 (1.0%) | 0.7 (1.3%) | 0.7 (1.3%) |
| client_validation | UNTESTED | 0.4 (0.5%) | 0.4 (0.7%) | 0.4 (0.7%) |
| runner | UNTESTED | 0.3 (0.4%) | 0.3 (0.5%) | 0.2 (0.4%) |
| settles | OWNER_DECISION | 0.0 | 0.0 | 0.0 |
| provider_decision | DELETED (fill) / UNTESTED | 0.0 | 0.0 | 0.0 |
| mean T_runner | | 80.9 ms | 53.6 ms | 55.3 ms |
| T_irreducible / floor ratio | | 42.6 ms / 1.90x | 19.7 ms / 2.72x | 21.0 ms / 2.64x |
| E2 untested share | | 15.2% | 16.6% | 16.2% |

The transport split is reporting-only (Deviation 3): in + out equal R2-10's `mcp_transport` exactly
(`transport_split.*.check_sum_ms` = 0) in every arm; BASE/COMP/COMP_E/COMP_K give 1.3-1.5 ms in and
3.3-4.1 ms out per trial, so the outbound half (client receive/parse + Driver post-dispatch) is
~70% of it. Resolution and the admission residual stay separate rows as in R2-10 (wave 5 maps B-05
onto mcp_transport_in/out and mcp_admission, N-03 onto the native transport rows below).

Native (X arm; BASE in brackets), mean ms and share of mean T_oracle:

| component | verdict | checkbox X [BASE] | text X [BASE] |
|---|---|---|---|
| settle | IRREDUCIBLE | 241.2 (85.2%)* [241.3] | 241.2 (80.6%)* [241.4] |
| observation_transport | IRREDUCIBLE | 18.1 (6.4%)* [18.0] | 17.8 (6.0%)* [18.2] |
| - in / out | (part of it) | 2.15 / 15.95 | 2.05 / 15.78 |
| observation | IRREDUCIBLE | 10.9 (3.9%) [11.0] | 10.9 (3.6%) [11.2] |
| action_transport | UNTESTED | 9.3 (3.3%) [9.4] | 18.5 (6.2%)* [18.9] |
| - in / out | (part of it) | 2.35 / 7.00 | 4.68 / 13.83 |
| reveal | OWNER_DECISION | 0.0 [0.0] | 5.4 (1.8%) [1415.7 (80.3%)] |
| post_action_sleep | DELETED | 0.1 [51.1] | 0.1 [51.1] |
| dispatch | IRREDUCIBLE | 1.1 [1.1] | 2.6 [3.1] |
| resolution | UNTESTED | 1.4 | 1.6 |
| verification_read / result / runner / effect_lag | IRREDUCIBLE / UNTESTED / UNTESTED / IRREDUCIBLE | 0.5 / 0.2 / 0.2 / 0.0 | 0.7 / 0.4 / 0.2 / 0.0 |
| mean T_oracle | | 283.1 ms | 299.4 ms |
| T_irreducible / floor ratio | | 271.8 ms / 1.04x | 273.3 ms / 1.10x |
| E2 untested share | | 3.9% | 6.9% |

Every component keeps its R2-10 verdict label in every arm (`recert-summary.json`
`verdict_mapping.decomposition`, 18 units). The E2 status is unchanged: the browser COMP untested
shares stay above 5% (driven by mcp_transport and resolution, as in R2-10); native checkbox stays
below 5%, native text stays above.

## Work deleted vs wall-clock saved

Work deleted = BASE minus arm component means (per trial); wall-clock saved = median paired T_oracle
difference. They are reported separately.

| unit | main work deleted (ms per trial) | provider decisions per trial BASE -> arm | wall-clock saved (median paired) |
|---|---|---|---|
| scripted fill COMP | visualization 3000.3, settles 101.1, client_validation 13.0, mcp_admission 8.7, input_prep 1.6 (sleeps_polls -5.7) | 2 -> 0.03 | 3118.4 ms |
| scripted toggle COMP | visualization 2427.2, client_validation 12.6, mcp_admission 8.5, dispatch 1.1, observation 1.1 | 2 -> 2 | 2448.4 ms |
| scripted modal COMP | visualization 2417.6, client_validation 12.4, mcp_admission 9.2, dispatch 1.0 (observation -2.6) | 2 -> 2 | 2435.5 ms |
| native checkbox S0 / X | post_action_sleep 51.0 | - | 51.6 ms / 51.0 ms |
| native text S0 / X | post_action_sleep 51.0 (S0); post_action_sleep 51.0 + reveal 1410.3 (X) | - | 52.5 ms / 1462.1 ms |

Per-component values for every unit are in `r2-10r-summary.json` (`work_deleted_vs_wall_clock`). The
scripted chooser costs ~0 ms, so the deleted provider decisions save work (1.97 scripted decisions per
fill trial) but almost no wall-clock in this layer; the live layer is where they cost time (R2-10).

## Live layer: BLOCKED (paid budget), SOURCE argument

BASE needs 2 TypeSafe decisions per trial, so 30 pairs x 3 classes need at least 180 reached; 58
remain in the loop and this lane's cap is 0. SOURCE argument: the drift 989cc76ce..0f1955d2f touches
no file on the caller-side provider decision path (jev-use runners, provider adapters and the
chooser are unchanged: `raw/rebase/files-drift.txt`); the Driver portion of a live trial is the same
tool calls the scripted layer makes on R', recertified above. The live-layer numbers stay certified at
989cc76ce only.

## Provenance

| item | value |
|---|---|
| tested source | R' head `45dff8f3227a21ff8bef1af4bf4c2bcbd9449b2a` = 0f1955d2f + R2-10 steps 1-8; rust tree `3ae6bd4408628fa098760e4886e3b2e45f89d807`; packet commits on top touch no libs/ file |
| control | Cn' `8a2362770f2120c136c69a50b711a6b9e3a69b8f` (0f1955d2f + FIX-01 Part A/B), rust tree `c609a7b60601` |
| rebase check | `raw/rebase/a2-recheck.txt`: range-diff 989cc76ce..8f3a646b4 vs 0f1955d2f..45dff8f32 all 8 '=', Cn' range-diff both '='; whole-step +/- line hashes identical; lib.rs and impl_.rs (touched by both sides) differ only in blob ids and hunk offsets (`raw/rebase/*.r2-10.diff` vs `*.rprime.diff`) |
| R' binary | `cua-driver-r2-10r-a2-45dff8f32`, sha256 `922111c518d73b9675a9800d39a389c17070d40d16f25ada1426a90eccd06ec8`, in-session `cua-driver 0.32.0`; attempt 1 built `d830ee77...` from the same tree (the build embeds the worktree HEAD) |
| Cn' binary | `cua-driver-r2-10r-a2-ctl-8a2362770`, sha256 `e66fac2cac19bc7899598f4a3d8337de1fc69fcaf99163e5553f1dc2d9f91b0b`, `cua-driver 0.32.0`; attempt 1 `97dfc91e...` (builds are not byte-reproducible here) |
| U control | `cua-driver-b02-560bd8247`, sha256 `7e6c06090fa2f2b63152a9276fe3a4766f88d2d5cbe7b412236208ee537bd3a0`, `cua-driver 0.32.0` (Phase 0 (b)/(c) only) |
| PREREG | `PREREG.json` committed in 3028d8078 (attempt 1, before any Phase 0 row); `PREREG-AMENDMENT-1.json` committed in 0bfd24053 at 2026-10-03T02:52:22Z, before the first counted row (02:59:54Z) and the first measured trial (03:45:11Z); `PREREG-AMENDMENT-2.json` is post-hoc (after the results commit 184b39b43; no trial added, re-run or removed) |
| browser Driver attribution | the browser run manifests (S1, S2r, N1) do not record the Driver binary; the lane run scripts (`raw/provenance/run-scripts/`, redacted copies, roots replaced by `<lanes>`/`<tmp>`) pass `--driver` = R' a2-45dff8f32 to every browser chunk; native, D1 and Phase 0 raw record `driver_bin_name` and `driver_sha256` directly |
| environment | one Linux host; bin/hostless v2 for every code-executing command; native/D1 also in bin/hostless-strict with AT-SPI; private Xvfb (cua-x11-session.sh); telemetry off; wrapper hashes `raw/provenance/wrappers-sha256.txt`; 1-minute loadavg per trial in raw/ |
| locks | every measured chunk (d1, S1, S2r, N1, nm1, nm2, nd1) under the cargo-build lock then `bin/quiet-timed` (receipts `raw/lock-receipts-global.jsonl`, lane `raw/lock-receipts-lane.jsonl`); Phase 0 rows and shakedowns under the SHARED lock with receipts; Phase 0 (a) cargo lock first |
| live heads | start (02:41:33Z) upstream main 41c34cb0d, end (05:57:56Z) a8d5788fd: 2 commits / 11 files, 0 under libs/cua-driver; libs/cua-driver tree `df2b49c32e73` = 0f1955d2f's at both reads; trycua/cua PR 4316 OPEN a0bca7440 (unchanged), PR 4375 merged 920a42f10, PR 3489 merged 310cdfd58 (`raw/provenance/heads-*.json`) |
| publication SHA | filled by Publish |
| provider | TypeSafe 0 attempts, 0 reached (cap 0) |

## Evidence classes

UNIT: Phase 0 (a). REAL: Phase 0 (b)-(e), controls, D1 validity/forced path/digests. REAL+BENCHMARK
(FIXTURE): scripted timing (jev-use fixture server and kvnloo/cua#24 pages) and native timing (GTK3
fixture) under the EXCLUSIVE lock; nm2 with the disclosed interference (Deviation 9). BENCHMARK
(indicative): D1 timing differences (load-contaminated). SOURCE: the
rebase range-diff, the D1 browser call graph, the live-layer argument. BLOCKED: live layer (paid
budget). NOT_RUN: none of the pre-registered rows.

## Deviations

1. Attempt 1 (aborted, read-only, nothing counted): SHARED-lock shakedowns, pilot and Phase 0 blocks
   on 2026-10-02 22:13-22:28Z, no EXCLUSIVE trial, 0 TypeSafe requests. Receipt labels
   (`raw/provenance/attempt-1-receipts.jsonl`): r2-10r-shake1, r2-10r-nshake1, r2-10r-d1shake1,
   r2-10r-p0b-c1-R, r2-10r-p0b-c1-U, r2-10r-p0c-nw2-R, r2-10r-p0c-nw2-U (rc=1), r2-10r-p0d-tools-R,
   r2-10r-p0d-smoke-R, r2-10r-p0d-tools-C, r2-10r-p0d-smoke-C, r2-10r-p0a-unit, r2-10r-p0d-native-R,
   r2-10r-p0d-native-C, r2-10r-p0e-train. Phase 0, D1 and every measured row were re-run in full on
   attempt-2 binaries.
2. Harness edits after the inherited PREREG (all disclosed in PREREG-AMENDMENT-1.json or below; no arm,
   plan, metric, oracle or pass rule changed): `harness/in_session.sh` fails fast with no trial written
   when `xdpyinfo` cannot reach the session display; `harness/r2_10_browser.py` guards
   `OraclePoller.stop` so a setup failure keeps its real error; `harness/package_raw.py` keeps only
   r2-10r-a2- receipts and packages failed-session logs and the interrupted S2 block;
   `harness/run_chunk.sh` (commit 567d76e2b, before S2r) runs the 25 min cap inside the EXCLUSIVE
   acquisition.
3. Analysis edits: reporting-only transport in/out split (`transport_split`; sums equal R2-10's
   components); `analyze_r2_10.py --out` now defaults to `r2-10r-summary.json` as the inherited PREREG
   already stated (the copied code still named `r2-10-summary.json`). make_headlines.py and
   verify_artifacts.py carry attempt 1's uncommitted edits, reviewed and committed by attempt 2.
4. Failed session starts (the cua-x11-session display race, still open): Phase 0 (b) on R' failed at
   session start twice (labels r2-10r-a2-p0b-c1-R and r2-10r-a2-p0b-c1-R-r1; the display probe
   reported `session_failed_to_start`, no trial written; logs in raw/logs/failed-sessions-*) and passed
   as r2-10r-a2-p0b-c1-R-r2.
5. Interrupted chunk: the first S2 acquisition (label r2-10r-a2-S2) was killed by its own outer
   `timeout 3000`, which also counted ~40 min of lock-queue wait, after 165 of 192 trials (165/165
   verified; the 166th trial was cut mid-call). Its quiet-timed wrapper was killed with it, so the
   loop ledger has no receipt for that acquisition. The block is kept in
   `raw/interrupted/S2-trials.tar.gz` and `raw/logs/interrupted-S2.log`, is not analysed, and S2 was
   re-run in full as S2r (rounds 16-31, same plan). Chrome in the cut trial left a core file in the
   lane worktree (isolated profile under the lane temp root); it was moved out of the worktree and is
   not part of the packet.
6. Scripted chunking follows R2-10 (S1 rounds 0-15, S2 rounds 16-31) instead of the inherited PREREG's
   four chunks of 8 rounds (PREREG-AMENDMENT-1.json); the trial sequence is the same.
7. Lock waits: other tracks held the quiet lane for long stretches; the measured chunks waited
   20-40 min each in the cargo/quiet queue. No chunk ran outside its EXCLUSIVE acquisition.
8. Near miss (no effect; `raw/provenance/near-misses.txt`): one `python3 -c 1` interpreter start in the
   plain host shell at ~02:41Z, typed by mistake inside a read-only grep command; no import, file,
   display, bus, socket or process effect.
9. External interference in nm2 (disclosed post-hoc): another track's verifier ran a few seconds of
   single-core Python without the quiet-lane lock at about 05:52:45-05:53:32Z inside the EXCLUSIVE
   window r2-10r-a2-nm2 (05:51:37.630-05:54:27.287Z). Source: the other track's synthesis, section 9,
   and the orchestrator's note `EXTERNAL-INTERFERENCE.md` in the lane mirror, written after 184b39b43.
   Not re-run; nm1-only and window-dropped native S keep the R2-10 direction 8/8 (section above,
   `nm2-sensitivity.json`).
10. S_direction coverage (post-hoc correction, `PREREG-AMENDMENT-2.json`): the PREREG rule covers every
   R2-10 S row whose CI excluded 1, but its enumeration and the first `recert_gates.s_paths` listed 15 of
   the 18. Added: COMP_E fill amortized and warm-only, COMP_K fill warm-only (all three exclude 1 above
   1 again on R'); COMP_K fill amortized is reported, not gated. `reference/r2-10-reference.json` was
   re-extracted from the same R2-10 blob 5fe2549a and `recert-summary.json` recomputed; disposition and
   changed claims are unchanged.
11. Other fixes after the fresh verifier: `verify_artifacts.py` uses `git rev-parse --verify -q` for the
   R2-10 reference blob, so a single-branch clone falls back to the recorded sha1 instead of crashing;
   scripted rows are labelled REAL+BENCHMARK (FIXTURE); the D1 timing differences are labelled
   indicative. Committed session logs contain ephemeral private-session D-Bus socket addresses
   (no user or host name); they are kept as recorded.
12. Publish-gate fixes (PUB-02, 2026-10-03; no trial, number, gate or verdict changed). (a) The
   verifier inherited from R2-10 carried a hex-encoded private-name list. The branch was rebuilt from
   45dff8f32 so that no commit carries it: `verify_artifacts.py` now reads private names from the
   untracked file named by `CUA_PRIVACY_NAMES_FILE` plus the verifying host's name (whole-token match),
   decodes and scans hex and base64 runs, scans gzip members but not the compressed bytes, and fails on
   a committed list of encoded name-like strings. Each rebuilt commit keeps its author date and its
   original tree except `verify_artifacts.py`. SHAs cited elsewhere in this packet are the originals:
   caf3d68a7 = bda126df2, 3028d8078 = 8e67e6bbc (PREREG; R' was built at 3028d8078, whose
   libs/cua-driver tree 8e67e6bbc shares), 0bfd24053 = 56e980c6f, 567d76e2b = 2bd181dff,
   184b39b43 = 8be812d0c, c183b95e3 = ac46b5032. (b) `raw/provenance/builds.log` is annotated:
   the first Cn' control build ended rc=143 because the RECERT-FIX lane's `pkill -f` at ~02:44:58Z
   matched this lane's build chain, not because of a 120 s tool timeout as the original log line
   says. That line is kept; the rerun built Cn'.

## Limits

One Linux host under heavy shared load (other tracks), private Xvfb, the jev-use fixture and the
kvnloo/cua#24 toggle/modal pages, the canonical GTK3 fixture, the scripted chooser. D1 measured one
GTK3 window with a 9-node tree; a larger tree near the 1000 ms budget is the case where the grace can
change the element set and is not covered here. Browser untested share stays above 5% (E2 not met for
browser classes, as in R2-10).

## Claim boundary

R' = 0f1955d2f + R2-10 steps 1-8 reproduces every R2-10 scripted and native verdict (direction of S,
component verdict mapping, 100% validity, 0 E4 violations) on one Linux host, private Xvfb, jev-use
fixture and kvnloo/cua#24 pages, canonical GTK3 fixture, scripted chooser; the first-snapshot grace
leaves the GTK3 checkbox window's element set unchanged. The live layer stays certified at 989cc76ce
only (budget). R' numbers are not ratioed against R2-10's. OWNER_DECISION components are labelled;
no default change is claimed.

## Files

- `PREREG.json` (attempt 1, committed before any Phase 0 row), `PREREG-AMENDMENT-1.json` (attempt 2,
  before the first counted row), `PREREG-AMENDMENT-2.json` (post-hoc corrections and sensitivity).
- `nm2-sensitivity.json` (sensitivity_nm2.py): native S without the interfered nm2 block.
- `r2-10r-summary.json` (analyze_r2_10.py), `d1-summary.json` (analyze_d1.py), `recert-summary.json`
  (recert_gates.py vs `reference/r2-10-reference.json`), `headline-numbers.json` (make_headlines.py),
  `provenance.json`, `verify_artifacts.py`.
- `raw/`: browser trial bundles, native and drift trials, Phase 0 rows, shakedowns, the interrupted S2
  block, lock receipts, chunk logs, rebase evidence, provenance reads.
- Verify from a clean clone of the lane head: `python3 verify_artifacts.py` (standard library only).
  Set `CUA_PRIVACY_NAMES_FILE` to an untracked file of private names (one per line) to extend the
  name check beyond the verifying host's name; the names are never committed.
