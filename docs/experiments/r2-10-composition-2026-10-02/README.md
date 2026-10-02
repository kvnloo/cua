# R2-10: whole-task composition on one fresh source (2026-10-02)

Lane R2-10, wave 3 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-10), kvnloo/cua#10 (accounting),
kvnloo/cua#73 (canonical state), kvnloo/cua#105 / kvnloo/cua#73 (FIX-01 re-qualification), kvnloo/cua#24
classes. Upstream items are named as plain text (trycua/cua PR 4316).

**Disposition: KEEP** (pre-registered rule: every class/task has a gating S whose 95% CI lower bound is
above 1, validity and E4 gates hold, Phase 0 passed). Scope and limits are in the claim boundary
below; three OWNER_DECISION components carry most of the browser saving, and the E2 untested-share
target (< 5%) is met only for native checkbox.

## Headline

One binary R (989cc76ce + the listed commits, sha256 `12b9045a...`) in every arm, phase trace on in
every arm, one host, one environment, AB/BA or Williams-balanced, EXCLUSIVE quiet-lane lock + cargo
lock for every measured chunk. S = median T_BASE / median T_composed, T = T_oracle (first 2 ms oracle
sample at/after the last accepted mutation's return that shows the expected final state).

| layer | class/task | n pairs | median T_BASE | median T_composed | S | 95% CI | class |
|---|---|---|---|---|---|---|---|
| L-live (TypeSafe) | fill->submit | n=30 | 3647.2 ms | 80.9 ms | 45.11 | [42.43, 51.90] | LIVE_PROVIDER+REAL+BENCHMARK |
| L-live (TypeSafe) | toggle->confirm | n=30 | 2928.3 ms | 491.8 ms | 5.95 | [5.70, 6.25] | LIVE_PROVIDER+REAL+BENCHMARK |
| L-live (TypeSafe) | modal->act | n=30 | 2930.2 ms | 511.0 ms | 5.73 | [5.41, 6.00] | LIVE_PROVIDER+REAL+BENCHMARK |
| L-scripted | fill->submit | n=32 | 3187.6 ms | 69.9 ms | 45.61 | [44.35, 46.98] | REAL+BENCHMARK |
| L-scripted | toggle->confirm | n=32 | 2507.4 ms | 53.3 ms | 47.01 | [45.36, 48.54] | REAL+BENCHMARK |
| L-scripted | modal->act | n=32 | 2483.6 ms | 53.3 ms | 46.56 | [45.56, 47.69] | REAL+BENCHMARK |
| native GTK3 (X) | checkbox | n=24 | 334.9 ms | 283.0 ms | 1.18 | [1.18, 1.18] | REAL+BENCHMARK (FIXTURE) |
| native GTK3 (X) | text entry | n=24 | 1760.9 ms | 300.9 ms | 5.85 | [5.81, 5.88] | REAL+BENCHMARK (FIXTURE) |

Fill, all invocations including the training invocation charged with compile + admission: live
amortized (ratio of means) 42.16 [34.68, 48.46], warm-only 45.68 [42.44, 52.19]; scripted amortized
43.79 [40.75, 45.98], warm-only 45.61 [44.36, 46.98].

Reported, not gating (scripted layer): S_COMP_K (KEEP-only deletions, feedback and focus settle at
default) fill 1.01 [1.01, 1.01], toggle 1.01 [1.00, 1.01], modal 1.01 [1.00, 1.01]; S_COMP_E (COMP +
endpoint bound check, OWNER_DECISION) fill 59.13 [55.03, 61.43], toggle 63.53 [58.03, 69.03], modal
60.23 [57.52, 66.76]. Native S_S0 (post-action sleep only, KEEP): checkbox 1.18 [1.17, 1.18] (334.9 ms -> 283.5 ms), text 1.03 [1.03, 1.03] (1760.9 ms -> 1709.1 ms).

Validity: 180/180 live, 384/384 scripted, 144/144 native main trials verified by the independent
oracle with exactly one completion mutation and valid forced path (100% per arm per class/task).
E4: 0 stale-ref dispatches, 0 duplicate mutations, 0 unverified successes, 0 refusals returned as
success, 0 blind replays, in every arm and every control. Provider: 306 attempts, 306 reached
(lane caps 330 reached / 363 attempts): 5 in the pre-PREREG shakedown, 301 in L-live.

## What the composed arm is (forced path per arm)

- **BASE** (product default, B-01 K0n shape): cursor feedback ON with the Driver's default glide
  (`set_agent_cursor_motion {glide_duration_ms:0, dwell_after_click_ms:80}`), ordinary runner (run.py
  rules incl. FIX-01 Part B; no guarded completion, no compiled replay), 100 ms completion poll with a
  2.0 s deadline, library MCP output validation, no `CUA_DRIVER_EXP_*` variable.
- **COMP**: feedback OFF via `set_agent_cursor_enabled false` (OWNER_DECISION);
  `CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS=0` on fill (OWNER_DECISION); 10 ms poll, same 2.0 s deadline
  (H_P not material); caller-compiled output validators compiled at tools/list outside T (H_C KEEP);
  `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1` (H_V DELETED fill/toggle; NOT_MATERIAL modal); guarded
  completion on fill (R2-03 KEEP); compiled replay on fill (R2-07b KEEP) with the guarded
  continuation as fallback. The first COMP fill invocation per (layer, arm) runs training (guarded
  step loop), compile and a clean-reset admission replay; all three are counted.
- **COMP_E** (scripted only): COMP + `CUA_DRIVER_EXP_ENDPOINT_REPROOF=bound` (B-02 H_E, OWNER_DECISION).
- **COMP_K** (scripted only): COMP minus every OWNER_DECISION knob (feedback default ON, focus settle default).
- **Native**: BASE defaults; S0 = `CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0` (KEEP, DELETED scoped
  to GTK3 background delivery); X = S0 + `set_agent_cursor_motion {glide_duration_ms:1}` (OWNER_DECISION).
  Native live-provider arms are BLOCKED (budget).

Forced path: browser clicks go through the dom_event route of the Driver CDP engine (candidate
`input_route=dom_event`, receipt route `dom`, `click.cdp_send` mark inside every click call); typing is
`browser_type` (receipt route `trusted_input` in 188/188 accepted type actions, identical across arms).
Native actions are AT-SPI DoAction (click, background delivery) and `set_value`, receipt route
`accessibility`, with the full R2-04 mark sequence in order. Each row is checked against its arm:
feedback marks (arrival waits arrived with the default glide in BASE/COMP_K, none in COMP/COMP_E),
focus settle (100 ms vs 0 ms on fill), poll interval, V knob (`mcp.inner_validation_skipped` on every
admitted call inside T), E knob (`ep.bound_hit` per `reval.native_window`), compiled validators, decision
routes (BASE provider only; COMP fill compiled / training), native knob marks and cursor motion.
0 rows were refused for a route or configuration mismatch.

Actual route/producer (from receipts): fill = `browser_type:trusted_input` then `browser_click:dom`;
toggle/modal = two `browser_click:dom`; native = `click:accessibility` / `set_value:accessibility`.
Decision producers: L-live BASE 2 TypeSafe decisions per trial in every class; L-live COMP fill 1
decision in 30 invocations (the training invocation; 29 warm compiled replays, 0 fallbacks);
L-live COMP toggle/modal 2 decisions per trial (guarded completion binds nothing for these classes).

## Independent target-owned oracle

Browser: the jev-use fixture server state (fill: `submitted == token`; toggle: `checked` true; modal:
`opened` and `modal` true) with a CLOCK_MONOTONIC server journal of every mutation; a harness thread
re-reads it every 2 ms (no HTTP, not the runner). Native: the GTK3 task state file
(`CUA_GTK3_TASK_STATE`, fresh per trial), read every 2 ms by an independent harness thread.

## Phase 0 qualification gate (all passed before any measured trial)

| row | result | class |
|---|---|---|
| (a) unit on R | `cargo test -p cua-driver-core --lib browser::` 193 passed / 0 failed (incl. the FIX-01 detached-node tests); phase_trace 6 passed; jev-use python 257 tests OK (1 skipped), test_runner_refusal.py 9 OK, test_guarded_runner.py 7 OK; npm test 163/163, run_refusal.test.ts 8/8, typecheck rc 0 | UNIT |
| (b) FIX-01 C1/N4a on R, n=20 | first Submit click refused `browser_ref_stale` 20/20, 0 old-node page events, rebind + verify 20/20; U (`b02-560bd8247`, control only) accepted the detached click 5/5 | REAL |
| (c) B-02 N-W2 on R | stale action refused 20/20 toggle and 20/20 modal, 0 detached-handler server effects; U fired the server effect 5/5 per class | REAL |
| (d) default-off smoke, R (no knobs, no trace) vs Cn | tools/list reply byte-identical (sha256 `ca6594c5...`, 195113 bytes, 3 reads each); fill/toggle/modal 5/5 verified on both with identical receipt shapes; native checkbox/text 5/5 verified on both with identical receipt shapes; no trace-like file appeared, native trace files stayed empty (0 of 10 non-empty per binary) | REAL |
| (e) R2-07b gates on R, n=5 | 5/5 verified training executions, 5/5 compiled with a clean authority check, 5/5 clean-reset admission replays verified, fresh binding 10/10 compiled mutations; N4a refuse+rebind = (b); reconcile: applied_ack_lost 5/5 and delayed_after_first_unchanged_read 5/5 verified_by_reconcile, withheld_unresolved 5/5 unknown, 0 duplicates, 0 dispatches after unknown | REAL+FIXTURE |

This closes E4 item 1 (FIX-01 C1/N4a and B-02 N-W2 re-run on a FIX-01 tree) on the R2-10 tree.

## Controls (excluded from T)

| control | n | pass | class |
|---|---|---|---|
| N4a inside L-scripted COMP (node replaced between bind and dispatch; fill inside the compiled replay, toggle/modal before action 2) | 15 (5/class) | 15: refused `browser_ref_stale`, one fresh observation, verified | REAL |
| OOD: scripted COMP fill routine on the toggle/modal page | 5 | 5: precondition `target_not_found` -> guarded continuation -> verified | REAL |
| N-W2 inside COMP (with the admission knob) | 5 | 5: stale action refused, 0 detached effects, fresh re-derivation verified | REAL |
| fallback in measured COMP fill | 122 warm replays (L-live 29; L-scripted 31 each in COMP, COMP_E, COMP_K) | 0 fallbacks needed; all 4 training invocations admitted | REAL |
| native focus steal (~100 ms after the app state changed) | 10 per arm (5 per task) | restored 10/10 in BASE, S0 and X; 0 missed | REAL (FIXTURE) |

The first controls chunk (N1) failed at session start (the private Xvfb on `:99` never came up:
openbox could not open the display, every browser exited before DevTools); its 20 rows are kept in
raw/ as a failed session block and the block was re-run as N2 (Deviation 3).

## Per-component decomposition (COMP arm, mean ms over valid trials, share of mean T_runner)

Browser components come from the Driver trace marks and caller events (B-01 decompose + B-02
taxonomy). Native components come from the merged R2-01+R2-04 trace (CLOCK_MONOTONIC) per N-01R.

| component | verdict | L-live fill | L-live toggle | L-live modal | L-scripted fill | L-scripted toggle | L-scripted modal |
|---|---|---|---|---|---|---|---|
| provider decision(s) | fill DELETED; toggle/modal UNTESTED | 6.0 (6.4%) | 434.8 (88.3%) | 462.4 (89.0%) | ~0 | ~0 | ~0 |
| observation | IRREDUCIBLE | 29.0 (30.8%) | 17.2 (3.5%) | 17.3 (3.3%) | 26.2 (32.9%) | 16.0 (29.2%) | 15.7 (29.0%) |
| endpoint revalidation | OWNER_DECISION (H_E) | 24.6 (26.2%) | 23.5 (4.8%) | 23.0 (4.4%) | 22.4 (28.2%) | 22.8 (41.6%) | 22.6 (41.6%) |
| revalidation other | IRREDUCIBLE | 2.9 | 2.2 | 2.3 | 2.3 | 2.7 (5.0%) | 2.7 (5.0%) |
| MCP admission residual | UNTESTED | 1.7 | 2.1 | 1.7 | 1.7 | 1.6 | 1.6 |
| MCP transport in/out | UNTESTED | 5.8 (6.1%) | 5.2 | 5.4 | 5.2 (6.6%) | 4.7 (8.7%) | 4.8 (8.9%) |
| resolution | UNTESTED | 2.7 | 1.4 | 1.3 | 2.4 | 1.2 | 1.1 |
| visualization residual | OWNER_DECISION | 1.9 | 2.1 | 2.1 | 1.8 | 1.8 | 1.8 |
| dispatch | IRREDUCIBLE | 4.3 | 1.3 | 1.5 | 3.3 | 1.2 | 1.3 |
| sleeps/polls | IRREDUCIBLE (H_P) | 9.1 (9.7%) | 0 | 0 | 9.0 (11.3%) | 0 | 0 |
| target effect, verification reads, input prep, client validation residual, runner, unattributed | mixed | <= 2.1 each | <= 1.2 each | <= 1.2 each | <= 1.8 each | <= 1.2 each | <= 1.1 each |
| **mean T_runner** | | 94.0 ms | 492.5 ms | 519.6 ms | 79.6 ms | 54.8 ms | 54.2 ms |
| **T_irreducible** | | 48.2 ms | 21.9 ms | 22.2 ms | 43.3 ms | 21.2 ms | 20.9 ms |
| **floor ratio T_COMP / T_irreducible** | | 1.95x | 22.51x | 23.37x | 1.84x | 2.59x | 2.59x |
| **untested share (E2)** | | 14.0% | 90.4% | 90.9% | 15.2% | 16.4% | 16.4% |

Native (arm X): checkbox T_irreducible 272.2 ms (focus-guard settle 240.9 ms, observation transport
18.7, observation 10.9, dispatch 1.1, verification read 0.6), floor ratio 1.04x, untested share 4.1%
(action transport 9.9 ms, resolution 1.4); text T_irreducible 274.9 ms, floor ratio 1.10x, untested
share 7.5% (action transport 20.6 ms, resolution 1.6, result 0.4), cursor-reveal residual 4.3 ms
(OWNER_DECISION). Coverage of the decomposition is >= 0.97 of T_runner (browser, every arm) and 1.00 of T_oracle (native).

E2 recertification on COMP: the target (< 5% untested) holds for native checkbox only. Browser
scripted untested share is 15-16%, mostly MCP transport in/out (4.7-5.8 ms, the only untested
component above 5%) plus resolution and the admission/validator residuals. Live toggle/modal
untested share is ~90%: both TypeSafe decisions remain, because guarded completion binds 0 of these
trials and compiled replay is qualified for fill only (pre-registered UNTESTED, plausibly deletable).

## Work deleted vs wall-clock saved

Work deleted = per-component mean (BASE minus COMP) from the decomposition; wall-clock saved =
median paired T_oracle difference (fill COMP rows include the training charge).

| | work deleted (mean ms per task) | wall-clock saved (median paired) |
|---|---|---|
| L-live fill | awaited glide 3000.5, provider decisions 484.8 (2 -> 0.03 per task), focus settle 101.0, client validation 13.1, MCP admission 9.8; work added: 10 ms poll sleeps +6.3, observation +4.5 | 3567.3 ms |
| L-live toggle | glide 2421.0, client validation 12.5, admission 9.4; decisions unchanged (2 -> 2) | 2431.0 ms |
| L-live modal | glide 2406.2, client validation 12.8, admission 9.2; decisions unchanged (2 -> 2) | 2423.8 ms |
| L-scripted fill | glide 2997.6, focus settle 101.1, client validation 13.1, admission 9.1 | 3116.4 ms |
| L-scripted toggle | glide 2434.5, client validation 12.4, admission 9.3 | 2452.6 ms |
| L-scripted modal | glide 2411.7, client validation 12.4, admission 9.5 | 2430.9 ms |
| native checkbox X | post-action sleep 50.9 | 50.0 ms |
| native text X | cursor reveal 1409.7, post-action sleep 51.0 | 1458.4 ms |

The browser saving is dominated by one OWNER_DECISION component (awaited cursor glide: 94-97% of
BASE T); with it at the default (COMP_K) the KEEP-only deletions give S 1.01 in every class. In live
fill the second largest work deletion is the two TypeSafe decisions (guarded completion + compiled
replay). The native text saving is the OWNER_DECISION cursor reveal; the KEEP-only S0 deletion
saves ~50 ms per task (S 1.18 checkbox, 1.03 text).

## References (not gates)

PreAct reports 8.5-13x for warm replay of recorded plans and SkillDroid ~2.4x for pure replay; both are
different benchmarks and platforms (their baselines are agent planning loops, not a Driver with
awaited cursor feedback). Our closest analogue to "warm replay" is L-live fill COMP warm-only
45.68 [42.44, 52.19], but it bundles the OWNER_DECISION feedback removal; the replay-specific
component here is the two deleted TypeSafe decisions (484.8 ms of work per task). Where provider
decisions remain (toggle/modal) the composed speedup is 5.7-6.0x; with feedback at default (COMP_K)
it is ~1.0x. No numbers are compared with B-01, B-02 or N-01R (different source, binary, environment).

## Provenance

| item | value |
|---|---|
| tested source | `exp/r2-10-composition-20261002` head `8f3a646b4818b757648835cf89db8886626b1cf0` (rust tree `f1f93375453d`), = upstream main 989cc76cec262ff8bcf6968b637820340fb9caaa + steps 1-8 (PREREG `source.steps`) |
| control source | `exp/r2-10-control-20261002` head `1381014a3403272cedeb657c3e9d16e7cf36a1ca` (989cc76ce + FIX-01 Part A/B only) |
| binary R | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9`, `cua-driver 0.32.0` (read inside a private session) |
| binary Cn | `cua-driver-r2-10-ctl-1381014a3`, sha256 `bd656a2c73128323b010e2c81267a2c397f78a1e2921857d3f50efd7889938f2`, `cua-driver 0.32.0` |
| U control | `cua-driver-b02-560bd8247`, sha256 `7e6c06090fa2f2b63152a9276fe3a4766f88d2d5cbe7b412236208ee537bd3a0`, `cua-driver 0.32.0` (Phase 0 (b)/(c) only) |
| build | `hostless flock cargo-build.lock build-driver.sh <wt> <label> cua-release-r2-10` (R 206 s, Cn 108 s, 0 Fresh workspace units each) |
| PREREG | commit `2cedaa9a4` (2026-10-02T17:54:12Z) before the first Phase 0 row (17:56:53Z) and the first measured trial (18:13:34Z) |
| live heads, start (17:18Z) | upstream main `989cc76ce`; trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556` (open) |
| live heads, end (19:54Z) | trycua/cua PR 4316 unchanged `a0bca7440`; upstream main moved to `9313551ef` (4 commits ahead of 989cc76ce, 8 libs/cua-driver files: see Drift) |
| publication SHA | the branch commit that carries this README (recorded by Publish) |
| environment | one Linux host (10 CPUs), hostless v2 (Landlock + env scrub) for every code-executing command; native additionally inside hostless-strict (bwrap mask), as N-01R; private Xvfb (`cua-x11-session.sh`), private AT-SPI bus for native; Driver telemetry off (`CUA_DRIVER_RS_TELEMETRY_ENABLED=0`, `DO_NOT_TRACK=1`); Chromium sandbox on; default Driver safety settings |
| load | 1-minute loadavg at trial start: L-live 3.1-8.4 (median ~4.1), L-scripted 2.3-17.1 (median ~4.8), native 1.9-7.0 (median ~3.9). Other tracks (a local model server, sway/Hermes stack, autoresearch, other lanes' builds) kept the host busy outside the quiet lock |
| locks | measured chunks S1, S2, L1, nm1, nm2, nd1, N1, N2 each under `bin/quiet-timed` (EXCLUSIVE, receipt in the loop ledger) and `flock` on the cargo-build lock for the whole chunk (raw/lock-receipts-*.jsonl); Phase 0 rows and shakedowns under the SHARED quiet lock (unit tests also under the cargo lock) |

## Drift (E6)

trycua/cua main moved during the lane from 989cc76ce to 9313551ef: `fix(cua-driver): extend first
Linux snapshot budget (#4375)` adds an omitted-timeout first-snapshot grace (`tool_schema.rs`
`resolve_timeout_ms_with_first_snapshot_grace`, `snapshot_store.rs` semantic-window bookkeeping,
`platform-linux/src/tools/impl_.rs` walk timeout), plus a macOS key-gap commit (`key_pacing.rs`,
`embedded.rs`, `platform-macos`) and two non-driver commits. SOURCE reading: additive; the tools/list
schemas and the MCP admission path are not touched, and the Linux change only raises the walk
timeout budget for a window's first snapshot when the caller omits `timeout_ms` (the GTK3 walk here
takes ~11 ms). The native observation component and the B-01/B-02 admission claims nevertheless
depend on files that changed, so under E6 they need recertification on the new main (SOURCE now,
not re-measured). Not rebased mid-lane.

## Claim boundary

One Linux host, X11 Xvfb, the jev-use fixture (fill) and the kvnloo/cua#24 toggle/modal pages, the
canonical GTK3 fixture. TypeSafe for the browser live layer; the scripted chooser (jev-use
`choose_mock_for_task`) elsewhere. Binary R built from 989cc76ce + the listed commits. OWNER_DECISION
components (feedback off, focus settle 0, endpoint bound check, native fast glide) are labelled and
carry most of the saving; no default change is claimed. Compiled replay is fill-only. Native results
are GTK3 AT-SPI background delivery only. Absolute times are host-state specific (loadavg 2-17); the
paired design keeps the ratios within one window. The secondary (loadavg < 2) analysis is empty for
the browser layers and n=1 for native: the host never reached loadavg < 2 while a measured chunk ran.

## Evidence classes

LIVE_PROVIDER: L-live (306 attempts / 306 reached). REAL: every browser and native trial (private
Xvfb, real Chromium and GTK3 app, real Driver over MCP stdio). BENCHMARK: the timed comparisons under
the EXCLUSIVE lock. FIXTURE: native and the reconcile seam rows (Phase 0 (e)). UNIT: Phase 0 (a).
SOURCE: drift reading, E2 verdict carry-overs. BLOCKED: native live-provider arms (budget).
NOT_RUN: none of the pre-registered rows; secondary loadavg < 2 analysis has no browser pairs.

## Deviations

1. Step 5 conflict resolution was applied automatically by git rerere from a recorded resolution
   (the shared clone's rr-cache): the staged `phase_trace.rs` was byte-identical to the reference
   457bc65d4 file. I checked it is the union of both mark sets (R2-01 `mark/mark_detail/enabled/
   monotonic_ns` API and R2-04 `wall_ns`/line tests), replaced the first doc line (which named
   another track) with a neutral one and disabled rerere for the later steps. The commit message of
   0cc03fbed is the original R2-04 message. No other track's branch or worktree was touched.
2. Harness edits after the PREREG commit: `nw2_one` now records a failed row instead of crashing when
   run_b02.control_one raises after a failed setup (found in N1); the analysis gained the
   work-deleted table, the failed-session-block exclusion and the reconcile dispatch counter fix. No
   arm, plan, metric or gate changed.
3. Controls chunk N1 failed at session start (private Xvfb on `:99` did not come up); kept in raw/,
   excluded from row evaluation as the PREREG's failed-session rule says, re-run as N2. The re-run
   came after the native blocks, not before L-live as `order_of_work` listed.
4. `E2_verdicts_preregistered` text for MCP admission said modal NOT_MATERIAL "counted
   IRREDUCIBLE-scale"; the analysis counts every admission residual as UNTESTED (the more
   conservative reading).
5. Native X sends `{glide_duration_ms: 1}` exactly as specified; N-01R's X also sent
   `dwell_after_click_ms: 0`, which has no Linux runtime reader.
6. Native `--no-trace` smoke rows still list `CUA_DRIVER_PHASE_TRACE_FILE` in `driver_env_keys`
   (the harness builds that list before the variable is removed from the Driver's environment);
   the empty trace files are the evidence.
7. Near misses (no effect; recorded honestly): one stdlib `python3` JSON read of a git blob in the
   plain host shell (17:24Z) and one `perl -0pi` text edit of the analysis file in the plain host
   shell (18:12Z). No GUI/display/bus import, no process or socket, no host desktop contact.
8. The private Xvfb socket appears in the host `/tmp/.X11-unix` under hostless v2 (no mount mask) for
   the browser chunks; native chunks ran inside hostless-strict, which masks it.

## Next

- Qualify a compiled routine for toggle/modal (checked-state precondition, FIX-01 refusal) to attack the
  ~90% live untested share; then re-run L-live for those classes.
- Test MCP transport in/out (the only untested browser component above 5% in the scripted layer).
- Owner decisions on feedback (glide/off), focus settle and the endpoint bound check: these three
  carry the browser S; KEEP-only composition (COMP_K) is ~1.0x.
- Recertify on main 9313551ef (first-snapshot timeout grace in tool_schema.rs / platform-linux).

## Files

- `PREREG.json`: pre-registration (committed before the first measured trial).
- `harness/`: `r2_10_browser.py`, `r2_10_native.py`, `phase0_fix01.py`, `phase0_unit.sh`, `run_chunk.sh`,
  `in_session.sh`, `package_raw.py`, `native-plan.json`; `harness/src/` holds the files copied by path
  (unchanged) from b282ff389 (B-02), 2d71548b4 (R2-07), 4a301d32a (FIX-01), 3bb4a7fc7 (N-01R) and
  0cd63f786 (the B-01 R2-10 PREREG draft this PREREG re-bases).
- `raw/`: trial bundles (browser `*-trials.tar.gz`, native `trials.jsonl.gz`), Phase 0 rows, provider
  ledger, lock receipts, routines, manifests, scrubbed chunk logs, shakedowns.
- `analyze_r2_10.py` -> `r2-10-summary.json`; `make_headlines.py` -> `headline-numbers.json`;
  `provenance.json`; `verify_artifacts.py` (recomputes every headline from raw/ and privacy-scans
  every branch commit; four upstream trycua/cua PR 4316 hits are allowlisted by commit+path: a GitHub Actions runner path in ci-jev-use.yml and a placeholder test key in run_guarded_completion.test.ts). Result: 115/115 checks.
