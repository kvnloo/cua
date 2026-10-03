# R2-07g: live modal forced-fallback re-run, live toggle literal-rename negative, quiet toggle block, 2026-10-03

Lane R2-07g, wave 7 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-07 Phase L), kvnloo/cua#73. This
block builds on R2-07c (branch `exp/r2-07c-toggle-modal-compiled-a2-20261003`, 7f46edd16), R2-07d
(branch `exp/r2-07d-quiet-timing-phase-l-20261003`, 79f6dd299) and R2-07e (branch
`exp/r2-07e-modal-gate-phase-l-20261003`, 67b99ddc6). It edits none of them. Their code runs in place,
and the three packet trees are identical at every commit of this branch. Upstream items are named as
plain text (trycua/cua PR 4316).

## Result in one paragraph

**Lineage disposition: toggle REVISE / modal REVISE**

- **Modal forced fallback (H_LF FAIL).** LF 0/3 verified. In all three new live invocations the
  compiled precondition failed as designed (the dialog starts open). The guarded continuation then
  offered `confirm-choice` at every step, and TypeSafe chose `reobserve` 4 times each. The step budget
  ran out (`budget_exhausted`) with 0 mutations, no success reported and E4 0. Every decision was
  counted (4 decisions = 4 provider ledger lines per invocation). With R2-07e's single LF, the count is
  pooled with R2-07e 0/4, and all four show the same failure mode (`reobserve` x4).
- **E2 mapping (fixed before the run).** The live modal provider-decision component maps to
  live modal provider-decision component: OWNER_DECISION. Warm deletion is measured (R2-07e: 29/29
  warm, 0 decisions). Admitting a routine whose live fallback continuation succeeds 0/4 is an
  admission-policy choice. The decisions inside a fallback continuation are IRREDUCIBLE by invariant.
- **Toggle LN (descriptive; closes the R2-07e NOT_RUN row).** The routine refused at the failed
  precondition. The live continuation made 4 decisions (`toggle-feature`, `reobserve` x2, `abstain`),
  including 1 accepted non-completion click (the feature checkbox). Result: 0 completion mutations,
  no success reported, E4 0.
- **Quiet toggle block (H_T FAIL).** 40/40 pairs valid in one EXCLUSIVE window, with trial-start
  loadavg 1.43-2.17. Paired diff COMP+CR - COMP was +0.5 ms [-0.6, +2.2] (95%, seed 20261002). The
  upper bound is 0.17 ms over the +2.0 ms margin. So the R2-07d gate fails, and the toggle lineage is
  REVISE with these numbers. The deletion of toggle provider decisions on warm invocations (R2-07e,
  29/29, 0 decisions) is not affected.
- **Provider.** This lane used 16 attempts / 16 reached of the lane cap 16 / 20. All returned 200
  with a request id, model `jev-1.13.0`, 0 blocked by the cap.

## Headline (evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| H_T: toggle COMP vs COMP+CR, quiet EXCLUSIVE block | 40/40 pairs valid | medians 49.4 -> 49.9 ms; paired diff +0.5 ms [-0.6, +2.2] (95%, seed 20261002; 26/40 positive); H_T FAIL (upper bound > +2.0 ms) | REAL+BENCHMARK |
| H_T sensitivity (both trial loads <= 3.0; not a gate) | 40 of 40 pairs | 40 pairs: +0.5 ms [-0.6, +2.2] (no pair excluded) | REAL+BENCHMARK |
| H_T 97.5% view (seed 20261003; comparison only) | 40 | +0.5 ms [-1.4, +2.3] | REAL+BENCHMARK |
| Load gate, Part T | 41 gate attempts, 41 starts, 0 chunk ends | round-start 1-min loadavg max 2.17 (median 1.72), ceiling 4.0 | REAL |
| G1 / G2 / G3 / E4, Part T | 1/1, 1/1; 84/84 accepted mutations fresh; E4 0 | training + compile + clean-reset admission into `timed-g`; warm 40/40 valid, 0 decisions | REAL |
| Part C controls | controls 12/12 pass | N4a 2/2, N4b 2/2 (non-fresh dispatch refused `effect=refused` 2/2), N8 2/2, default smoke 6/6; G1/G2 2/2 + 2/2; E4 0 | REAL |
| L2 scripted training + admission (store `l2-scripted`) | modal 1/1 + 1/1, toggle 1/1 + 1/1 | verified, 0 provider requests, both artifacts authority-clean before any live call | REAL |
| H_LF: modal forced fallback `n7_presat`, live | LF 0/3 verified | 3x `budget_exhausted`: `confirm-choice` offered at all 12 steps, TypeSafe chose `reobserve` 12/12; 0 mutations; 0 false success; E4 0; 12 decisions = 12 ledger lines; H_LF FAIL | LIVE_PROVIDER+REAL |
| Modal LF pooled with R2-07e (descriptive) | pooled with R2-07e 0/4 | failure mode `budget_exhausted` with `reobserve` x4 in 4/4 | LIVE_PROVIDER+REAL |
| Toggle LN `n1_renamed`, live (descriptive) | 1/1 run | refused at the failed precondition (`requires_present`); decisions `toggle-feature`, `reobserve` x2, `abstain`; 1 accepted non-completion click; 0 completion; outcome `abstained`; no success reported | LIVE_PROVIDER+REAL |
| E2: live modal provider-decision component | - | live modal provider-decision component: OWNER_DECISION; fallback-continuation decisions IRREDUCIBLE | LIVE_PROVIDER+REAL (R2-07e warm + this LF) |
| Provider | 16 attempts / 16 reached | lane cap 16 reached / 20 attempts; all 200; request id 16/16; 0 blocked by the cap; model `jev-1.13.0` | LIVE_PROVIDER |
| Unit | 10/10 + 8/8 | `driver/test_r2_07g.py`; R2-07e `driver/test_r2_07e.py` carry-over | UNIT |
| Paired live BASE vs COMP+CR S | - | BLOCKED: budget (needs >= 120 reached) | BLOCKED |

## The five mechanism requirements (kvnloo/cua#73)

| Requirement | This packet | Evidence class |
|---|---|---|
| Forced path | **T.** COMP is the R2-10 COMP trial unchanged (`r2_07c.one_comp` -> `rb10.one`): feedback OFF, 10 ms completion poll, compiled validators, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`, phase trace on, scripted chooser. COMP+CR is the same Driver configuration plus compiled fresh-bound replay of the admitted artifact (`r2_07c.one_c`). **L2.** The fixture variant forces the compiled precondition to fail. `n7_presat`: the dialog starts open, so `requires_absent 'Confirm choice'` fails. `n1_renamed`: 'Confirm' is renamed 'Save', so `requires_present` fails. The routine dispatches nothing and hands the current state to the guarded continuation, whose decisions come live from TypeSafe | SOURCE / REAL |
| Actual route / producer | From the launcher's Driver-call receipts. Warm and admission cells use route `compiled` only, with 2 `browser_click` `dom_event` dispatches, 0 decided events and 0 provider lines. LF/LN cells use route `compiled` then `fallback:provider` x4. The offered candidate ids at every continuation step are in the trial events (`offered_per_step` in the summary). Every provider attempt is attributed to its trial in `raw/provider-ledger.jsonl` | REAL / LIVE_PROVIDER |
| Independent target-owned oracle | jev-use kvnloo/cua#24 fixture server state + CLOCK_MONOTONIC journal. It is sampled every 2 ms by an independent harness thread (`rb10.Sampler`), never the runner. A verified task needs exactly 1 completion mutation in the server journal. LN expects 0 completions and no success reported. Every accepted click is counted, completion or not | REAL |
| Negative / fallback controls | Part C: N4a stale ref (refused `browser_ref_stale`, rebind, verified), N4b superseding snapshot (non-fresh dispatch refused `effect=refused`), N8 wrong page (0 accepted mutations), and the default smoke. E4 counters run on every T, C and L2 cell. LF is itself the fallback case, and LN is the negative | REAL / LIVE_PROVIDER |
| Exact provenance | Below: tested source, Driver sha256 + version (re-hashed at start and end), environment, live heads at start and end, PREREG commit, publication SHA kept separate | SOURCE |

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Tested source SHA | Driver source `8f3a646b4818b757648835cf89db8886626b1cf0` (`libs/cua-driver` tree `bf8e7bdc90fdce295e44743f2754a6502d5d6e0e`, identical at the base). R2-07c harness tree `66bad345b1736b97b66884bbf40a1505c16083bf`. R2-07d runner blob `0989b68bc57d8fc16de3c0ab2cf80c61cd6bd334`. R2-07e packet tree `8c3901b1d660a760a1d0e34281cd43d1e26d2dcb`, runner blob `27d850be87d83189cbe0c02f77c6746af72e4a4f`. Lane runner `driver/r2_07g.py` at the PREREG commit (unchanged after it). No Driver build | SOURCE |
| Driver binary | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9`, `cua-driver 0.32.0`. Re-hashed on the host at the start (15:56:11Z) and end (19:28:27Z), identical. Every run manifest and every COMP+CR trial record carries name, sha256 and version. The runner refuses on a sha256 mismatch before any trial | SOURCE |
| Environment | One shared Linux host. Every code-executing command ran under `hostless`. Driver and Chrome ran inside `cua-x11-session.sh` (private Xvfb + D-Bus), with an `xdpyinfo` probe before any trial, an isolated Chrome profile per trial and the sandbox on. `CUA_DRIVER_RS_TELEMETRY_ENABLED=false` was set via `CUA_SESSION_EXTRA_ENV`. Default Driver safety settings | SOURCE |
| PREREG commit | `721b461db`, committed 2026-10-03T16:04:23Z. That is before the first measured trial (Part C, 17:37:10Z), the first Part T trial (18:48:29Z) and the first live request (19:27Z) | SOURCE |
| Live heads at test time | Start 15:56:11Z: trycua/cua main `9a2b1d99ec8044ff58b2a2b46802edd2609c057b`; trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556` (open); trycua/cua PR 4394 head `039257811e0bbb2348c616c52562409923d2856f` (open). End 19:28:27Z: main `e6127c6412eb2348f71ac40c70d088f6ca115a60` (later upstream commits; binary R is unaffected), PR 4316 and PR 4394 heads unchanged (open). Read-only `gh` | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); not assumed equal to the tested SHA | SOURCE |
| Provider | TypeSafe `api.typesafe.ai` `/v1/systemone`, model id `jev-1.13.0` (from the response, 16/16). The key was forwarded by NAME only (`CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY`) | LIVE_PROVIDER |

## Method

### Part T (REAL+BENCHMARK)

`driver/r2_07g.py --plan t` runs `r2_07c.build_plan("timing", 0, 40)` restricted to toggle, in store
`timed-g`.

- **Plan.** One scripted training + compile + clean-reset admission runs at round -1. Then come 40
  AB/BA pairs: COMP first on even rounds, COMP+CR first on odd rounds. Each trial gets a fresh Driver,
  Chrome, loopback fixture servers, token and session label.
- **Load rule.** A unit starts only at a round-start 1-min loadavg <= 4.0 (`r2_07d.gate` with ceiling
  4.0). Outside the locks, the loop waited for host load <= 4.0 before acquiring.
- **Locks.** First a non-blocking check that the cargo lock is free. Then `bin/quiet-timed r207g-T1`
  (EXCLUSIVE). Inside it, `flock -w 60` on the cargo lock, and the session runs under `timeout 900`.
  T1 acquired the quiet lock at 18:48:20Z and released it at 18:50:07Z. All 41 units ran in the one
  chunk.
- **Gate.** `analyze_r2_07g.t_gate` (pre-registered) applies the R2-07d text unchanged. It takes the
  median paired diff with the b01 95% seeded bootstrap (seed 20261002, 10 000 resamples). PASS iff the
  upper bound is <= +2.0 ms, all 40 pairs ran and every cell is valid.

### Part C (REAL; SHARED quiet lock, <= 10 cells per acquisition)

`--plan controls` ran 14 specs in 2 acquisitions (`r207g-C1`, `r207g-C2`):

- 1 training + admission per class (`scripted-g`);
- N4a, N4b and N8 (toggle-on-modal, modal-on-toggle), 1 per class;
- the default smoke (R2-10 BASE, no `CUA_DRIVER_EXP_*`, no trace), 3 per class.

Pass rules are `analyze_r2_07c.g4_pass`, unchanged.

### Part L2 (LIVE_PROVIDER+REAL; one EXCLUSIVE chunk `r207g-L1`)

`--plan l2` ran in this order:

1. **Scripted training.** Per class, one scripted training + compile + clean-reset admission into
   `l2-scripted`. The layer does not start with `live`, so the chooser is scripted, and the ledger
   shows 0 requests. Before any live invocation, the runner checks the admitted artifact with
   `check_artifact_authority_tm`.
2. **Modal LF x 3.** Variant `n7_presat`, with live decisions in the continuation.
3. **Toggle LN x 1.** Variant `n1_renamed`, live.

Budget and timing:

- **Budget guard.** Before each live invocation the runner stops if reached+4 > 16 or attempts+4 > 20.
  `r2_07c.install_provider_ledger_c` counts every HTTP attempt before sending and refuses past the cap.
  The guard never fired (12 reached before the LN, and 12 + 4 = 16).
- **Window.** L1 acquired the quiet lock at 19:27:34Z and released it at 19:28:08Z. Per-invocation
  loadavg was 5.51-6.51; no load ceiling was pre-registered for L2.
- **Shakedowns.** The only shakedowns were pre-PREREG and scripted, with 0 TypeSafe requests:
  `r207g-shake-t1` (load gate ended it, exit 75, 0 trials) and `r207g-shake-l1` (`--plan l2shake`).
  Both are kept in `raw/shake-*` and excluded.

### Analysis

`analyze_r2_07g.py` reuses the R2-07e analysis (`latest_pairs`, `fb_row`, `paired_gate`). Through it,
it reuses the R2-07d analysis (`rows_of`, `g1_g2`, `g3_of`, `pair_stats`) and the R2-07c analysis
(`row_of`, `g4_pass`, `decomposition`, `e4_total`). All are imported unchanged.

## Results

### Part T (REAL+BENCHMARK, chunk T1)

| metric | value |
|---|---|
| pairs | 40/40 pairs valid (0 failed, 0 not run, 0 interrupted) |
| median T COMP / COMP+CR | 49.4 -> 49.9 ms |
| paired diff COMP+CR - COMP, median [95%] | +0.5 ms [-0.6, +2.2], range -14.5 to +10.2, 26/40 positive |
| S = median T_COMP / median T_COMP_CR [95%] | 0.990 [0.973, 1.023] |
| 97.5% view (seed 20261003, comparison only) | +0.5 ms [-1.4, +2.3] |
| trial-start loadavg | 1.43-2.17 (median 1.71) |
| G1 / G2 | 1/1 / 1/1 (training T_oracle 123.2 ms with 2 scripted decisions; compile 0.175 ms; admission T_oracle 55.8 ms) |
| G3 / E4 | 84/84 accepted mutations fresh, 0 non-fresh attempts / 0 |
| warm | 40/40 valid, 0 decisions, 0 fallbacks |
| H_T | FAIL (upper bound +2.17 ms > +2.0 ms) |

Side by side, never pooled:

- R2-07d's 40-pair toggle block (the accepted Phase S PASS) measured +0.5 ms [-1.3, +0.8].
- R2-07e's 10-pair toggle sanity block measured +0.7 ms [+0.5, +2.6].

All three blocks put the median paired cost of the compiled path at about +0.5 ms. Only the interval
width separates PASS from FAIL. No absolute T is compared across these blocks.

Component decomposition, mean ms over the 40 valid cells per arm (R2-10 e2_components, coverage
0.986):

| component | COMP | COMP+CR |
|---|---|---|
| endpoint revalidation | 20.8 | 21.0 |
| observation | 14.1 | 14.3 |
| MCP transport | 4.5 | 4.5 |
| other revalidation | 2.5 | 2.7 |
| visualization | 1.7 | 1.7 |
| MCP admission | 1.6 | 1.6 |
| resolution | 1.1 | 1.2 |
| verification reads | 1.1 | 0.5 |
| dispatch | 1.0 | 1.0 |
| target effect lag / sleeps-polls / client validation / runner / unattributed | 1.8 | 1.4 |
| mean T_runner | 50.3 | 49.9 |

The arm means favour COMP+CR by 0.4 ms. The median paired difference is +0.5 ms against it. The
pre-registered statistic is the paired median. The compiled path trades the per-step pre-oracle reads
(-0.6 ms) and the completion-poll sleep for one more fresh observation and revalidation (+0.6 ms).
This is the same shape as R2-07e's modal block.

### Part C controls (REAL; 1 rep per row per class)

| row | toggle | modal |
|---|---|---|
| G1 training / G2 clean-reset admission (store `scripted-g`) | 1/1, 1/1 | 1/1, 1/1 |
| N4a stale ref: refused `browser_ref_stale` (`effect=refused`), one rebind, verified, 1 completion | 1/1 | 1/1 |
| N4b superseding snapshot (G3 non-fresh dispatch): refused `effect=refused`, rebind, verified | 1/1 | 1/1 |
| N8 wrong page (toggle on modal; modal on toggle): 0 accepted mutations, 0 completion | 1/1 | 1/1 |
| default smoke (R2-10 BASE, no `CUA_DRIVER_EXP_*`, no trace): verified, 1 completion | 3/3 | 3/3 |
| E4 | 0 | 0 |

### Part L2 (LIVE_PROVIDER+REAL)

| invocation | precondition failure | offered at every step | decisions (live) | ledger lines | accepted / completion mutations | outcome | t to end | E4 |
|---|---|---|---|---|---|---|---|---|
| L002 modal LF r00 | `requires_absent` (index 0) | `confirm-choice`, `reobserve`, `abstain` | `reobserve` x4 | 4 | 0 / 0 | `budget_exhausted`, not verified | 1040.9 ms | 0 |
| L003 modal LF r01 | `requires_absent` (index 0) | `confirm-choice`, `reobserve`, `abstain` | `reobserve` x4 | 4 | 0 / 0 | `budget_exhausted`, not verified | 923.2 ms | 0 |
| L004 modal LF r02 | `requires_absent` (index 0) | `confirm-choice`, `reobserve`, `abstain` | `reobserve` x4 | 4 | 0 / 0 | `budget_exhausted`, not verified | 863.0 ms | 0 |
| L005 toggle LN r03 | `requires_present` (index 0) | step 1 `toggle-feature`, `reobserve`, `abstain`; steps 2-4 `reobserve`, `abstain` | `toggle-feature`, `reobserve` x2, `abstain` | 4 | 1 / 0 (1 non-completion click: the feature checkbox) | `abstained`, not verified, no success reported | 1175.3 ms | 0 |

- **Scripted training.** The training per class (2 scripted decisions, 0 requests) verified. Modal
  T_oracle was 61.9 ms and toggle 59.2 ms. Compile took 0.193 / 0.112 ms. Clean-reset admission
  verified with 0 decisions (52.0 / 56.1 ms). All 7 compiled artifacts in `raw/artifacts/` pass the
  authority scan.
- **H_LF.** `lf_gate`: planned 3, ran 3, verified 0, false success 0, E4 0, every decision counted.
  Result: FAIL.
- **Pooled with R2-07e (descriptive).** 0/4. All four modal LF invocations, R2-07e's L061 included,
  ended `budget_exhausted` after `reobserve` x4 with `confirm-choice` offered.
- **Scripted contrast (not a claim).** The scripted chooser completes the same `n7_presat` fallback
  with 1 decision. This was seen in R2-07c's G6 cells and in this lane's excluded shakedown, 3/3. The
  stall is specific to the live provider's choice in this state.
- **Hypothesis, untested.** The continuation starts with an empty history, while the modal task's
  first expected action is `open-dialog`, which is not offered when the dialog is already open. This
  is not tested here.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock (same run) | Evidence class |
|---|---|---|---|
| compiled routine, modal, live fallback | none: the continuation made 4 live decisions per LF (12 in all) and completed nothing; the warm deletion (2 decisions per warm invocation) is R2-07e's and is not re-measured here | LF ran 863-1041 ms to the step-budget end with no verified outcome; no T_oracle | LIVE_PROVIDER+REAL |
| compiled routine, toggle, scripted (Part T) | the 2 scripted decisions per warm invocation and the per-step pre-oracle reads; adds one fresh observation per click | paired median +0.5 ms [-0.6, +2.2]: no saving; non-inferiority at +2.0 ms not shown | REAL+BENCHMARK |

## Deviations

1. **Order of Part C and Part T.** The PREREG order was T, then C, then L2. Part C ran first (17:37Z),
   and T followed at 18:48Z.
   - The cause was the quiet lane. From 16:13Z to 18:48Z no EXCLUSIVE `quiet-timed` acquisition was
     possible on the host for any lane. The last EXCLUSIVE receipt in the loop ledger before T1 is
     R2-07e-L1 at 14:11Z.
   - The blocking holders were long-lived helper processes started by another track (test stubs of a
     parallel integration track). They had inherited SHARED `quiet-lane.lock` file descriptors and kept
     them open, as seen read-only in `/proc/locks`. Nothing was killed by this lane. The last of them
     went away between 18:38Z and 18:48Z, and T1 acquired the lock at 18:48:20Z.
   - Part C is scripted, takes no timing claim and makes 0 provider requests. Running it in a SHARED
     acquisition before T changes no T measurement.
   - L2 still ran after both, as pre-registered. The L1 chunk waited about 27 minutes before its
     first trial: first for a free cargo lock (21 prechecks exited 74 with no lock acquired, as logged
     in `raw/lock-receipts-lane.jsonl`), then for the EXCLUSIVE quiet lock.
2. **Driver identity in COMP and smoke records.** The PREREG says identity is recorded "in every trial
   and manifest". The R2-10 `rb10.one` record (COMP arm and default smoke) carries no identity field.
   This is unchanged from R2-07d/R2-07e. Those records are covered by their chunk manifest, which
   carries name, sha256 and version, and by the runner's sha256 refusal at chunk start.
   `verify_artifacts.py` checks every COMP+CR record and every manifest, and checks that every trial
   is listed by a manifest or carries identity itself.
3. **Analysis written after the PREREG.** These parts were written after the PREREG commit and
   implement the PREREG metrics: everything in `analyze_r2_07g.py` except the pre-registered `t_gate`,
   `lf_gate`, `false_success` and `e2_mapping` (`verify_artifacts.py` checks those are unchanged since
   `721b461db`), plus `l2_row` / `offered_per_step`, `verify_artifacts.py`, `provenance.json`,
   `headline-numbers.json` and this README.
4. **L2 load.** The per-invocation loadavg in L2 was 5.51-6.51. No L2 load ceiling was
   pre-registered, and L2 makes no timing claim. The outer loop started at host load 2.21, before the
   26-minute lock wait.
5. **Loop logs.** Chunk and loop logs in `raw/loop-logs/` drop the private-session noise lines:
   `[session]`, dbus-daemon, and lines naming a local absolute path. The per-file counts are in
   `raw/package-report.json`. Trial bundles are unfiltered.

## Limits and claim boundary

- One shared host, private Xvfb (`cua-x11-session.sh`, everything under `bin/hostless`), binary R (the
  989cc76ce lineage), TypeSafe as configured by the jev-use runner (model `jev-1.13.0`).
- n = 3 LF estimates no rate. With R2-07e, 0/4 are verified, and all four show one failure mode.
- No paired live BASE vs COMP+CR S is claimed. It stays BLOCKED (needs >= 120 reached).
- Phase L T is never set against R2-10 live numbers.
- The routine is caller-side only: no new service, registry, router or engine.
- Logical routine identity persists. Refs, tokens, captures, capabilities and session epochs do not.
- Part T is one 40-pair window. Its CI upper bound misses the margin by 0.17 ms. It is reported side by
  side with R2-07d (PASS) and R2-07e (sanity), never pooled.
- The disposition depends on the owner accepting the SOURCE-forced `n7_presat` substitution for the
  literal rename. `BrowserSemanticSource.find` matches role+name exactly, so a renamed target cannot
  verify. The toggle LN here, which is descriptive, is consistent with that: 0 completions.

## Disposition

**Lineage disposition: toggle REVISE / modal REVISE**

- **Modal: REVISE (H_LF FAIL, 0/3; pooled 0/4).**
  - E2 mapping, fixed before the run: the live modal provider-decision component is OWNER_DECISION.
    Warm compiled replay deletes it (R2-07e: 29/29 warm, 0 decisions, 0 provider lines). The live
    forced fallback continuation succeeded 0/4. Admitting the modal routine is therefore an
    admission-policy choice for the owner, given what a failed precondition costs: up to 4 live
    decisions, about 0.9-1.0 s, and no completion.
  - The decisions inside a fallback continuation are IRREDUCIBLE by invariant: a failed precondition
    must re-decide, and blind replay is forbidden.
  - Not a KILL candidate: 0 E4 in every cell, 0 false success, and nothing was blind-replayed.
- **Toggle: REVISE (H_T FAIL).** The revised claim is measured: COMP+CR costs +0.5 ms [-0.6, +2.2]
  per invocation against COMP (95%, n = 40, quiet window). It is non-inferior at a +2.2 ms margin, but
  not at the pre-registered +2.0 ms.
  - The toggle work deletion stands (R2-07e: 29/29 warm, 0 decisions; LF verified).
  - G3, E4 and the controls all pass.
- **Toggle LN: terminal.** It closes the R2-07e NOT_RUN row. The routine refused at the failed
  precondition, made 4 live decisions and 1 accepted non-completion click, with 0 completion and no
  success reported.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration (commit `721b461db`) |
| `README.md` | this file |
| `.gitignore` | packet-local overrides (template), re-includes `raw/artifacts/` |
| `provenance.json` | provenance fields; `publication_sha` set by Publish |
| `r2-07g-summary.json` | full analysis output |
| `headline-numbers.json` | headline numbers with the exact README text |
| `analyze_r2_07g.py` | analysis (`t_gate`, `lf_gate`, `false_success`, `e2_mapping` pre-registered; imports the R2-07e/R2-07d/R2-07c analyses unchanged) |
| `verify_artifacts.py` | identity, PREREG-before-trials, pre-registered gate functions unchanged, summary recompute, headlines, gate recompute, Driver identity, authority, provider cap and attribution, cited files, word-boundary privacy scan of every commit. Run under hostless; `--skip-git` on an export |
| `driver/r2_07g.py` | T / controls / L2 runner (imports r2_07e, r2_07d, r2_07c unchanged) |
| `driver/run_chunk_g.sh` | lock order (cargo precheck, quiet-timed, cargo inside) + private session wrapper |
| `driver/test_r2_07g.py` | unit tests of the R2-07g additions and gate functions |
| `driver/package_g.py` | packaging + privacy scan (R2-07e `package_e` unchanged) |
| `raw/t-trials.tar.gz`, `raw/t-manifests/`, `raw/t-routines/`, `raw/t-load-gate.jsonl`, `raw/t-progress.json` | Part T (82 trial records: 1 training, 1 admission, 80 timing cells) |
| `raw/ctl-trials.tar.gz`, `raw/ctl-manifests/`, `raw/ctl-routines/` | Part C (16 records incl. 2 admissions) |
| `raw/l2-trials.tar.gz`, `raw/l2-manifests/`, `raw/l2-routines/`, `raw/l2-live-progress.json` | Part L2 (8 records: 2 trainings, 2 admissions, 3 LF, 1 LN) |
| `raw/shake-*` | pre-PREREG scripted shakedowns (excluded) |
| `raw/provider-ledger.jsonl` | every provider attempt (no bodies, no headers) |
| `raw/artifacts/` | 7 compiled artifacts |
| `raw/lock-receipts-global.jsonl`, `raw/lock-receipts-lane.jsonl` | quiet-lane ledger lines labelled `r207g-*`; lane ledger |
| `raw/loop-logs/`, `raw/unit/`, `raw/package-report.json` | chunk/loop logs, unit outputs, packaging report |
