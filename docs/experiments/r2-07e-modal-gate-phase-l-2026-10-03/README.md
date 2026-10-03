# R2-07e: alpha-adjusted modal gate, then live TypeSafe Phase L per class, 2026-10-03

Lane R2-07e, wave 6 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-07 family), kvnloo/cua#10
(accounting), kvnloo/cua#74 (posting queue). This block builds on R2-07c (branch
`exp/r2-07c-toggle-modal-compiled-a2-20261003`, 7f46edd16) and R2-07d (branch
`exp/r2-07d-quiet-timing-phase-l-20261003`, 79f6dd299). It does not edit either one. Their code runs
in place, and both packet trees are identical at every commit of this branch. Upstream items are
named as plain text (trycua/cua PR 4316).

## Result in one paragraph

**Lineage disposition: KEEP (toggle) / REVISE (modal).**

- **Part Q.** The second, alpha-adjusted look at the modal non-regression gate **passes**. Paired
  diff T(COMP+CR) - T(COMP) is -0.5 ms [-1.4, +0.5] at two-sided 97.5% (seed 20261003, 10 000
  resamples). 60/60 pairs are valid, and G1/G2, G3 and E4 pass.
- **Part C.** Controls 35/35 pass.
- **Part L toggle.** The live provider-decision component is **DELETED**. Warm validity is 29/29,
  with 0 decisions and 0 provider ledger lines. The forced fallback verified with 1 live decision,
  and E4 is 0.
- **Part L modal.** The verdict is **REVISE**, and the failing gate is the forced fallback.
  - Warm compiled replay itself deleted both live decisions: warm valid 29/29, 0 decisions,
    0 provider lines.
  - The pre-registered fallback invocation did not verify. The precondition failed as designed
    (the dialog starts open). The guarded continuation offered `confirm-choice` at every step, but
    TypeSafe chose `reobserve` 4 times, and the step budget ran out. Outcome: 0 mutations, no
    success reported, E4 0. n = 1.
- **Provider.** 15 attempts / 15 reached of the lane cap 18 / 22. This includes the 2-request
  shakedown.

## Headline (evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| Part Q modal, COMP vs COMP+CR (gate) | 60/60 pairs valid | medians 47.4 -> 47.8 ms; paired diff -0.5 ms [-1.4, +0.5] (97.5%; 30/60 positive); modal gate PASS (upper bound <= +2.0 ms) | REAL+BENCHMARK |
| Part Q modal, 95% view (b01 seed, comparison only) | 60 pairs | -0.5 ms [-1.4, +0.5] | REAL+BENCHMARK |
| Part Q modal, sensitivity (both trial loads <= 3.0) | 58 pairs | -0.5 ms, 97.5% CI [-1.4, +0.5] | REAL+BENCHMARK |
| R2-07d modal block, side by side (look 1, not pooled) | 40/40 | +0.6 ms [-1.4, +2.4] (95%, seed 20261002), FAIL stands | REAL+BENCHMARK (R2-07d) |
| Pooled 100 modal pairs (descriptive only) | 100 | +0.3 ms, 97.5% CI [-1.4, +0.5] | descriptive |
| Part Q toggle sanity block (descriptive, no gate) | 10/10 pairs valid | medians 47.4 -> 47.9 ms; paired diff +0.7 ms [+0.5, +2.6] (9/10 positive) | REAL+BENCHMARK |
| Load gate, Part Q | 72 gate attempts, 72 starts, 0 chunk ends | unit-start load 1-min max 2.92 (median 2.17); trial-start loadavg 1.57-3.17 | REAL |
| G1 / G2 Part Q (training + compile + clean-reset admission, store `timed-e`) | modal 1/1 + 1/1, toggle 1/1 + 1/1 | verified, authority-clean, admitted with 0 fallback / 0 decisions | REAL |
| G3 / E4 Part Q | modal 124/124 accepted mutations fresh, toggle 24/24; E4 0 | 0 non-fresh dispatch attempts | REAL |
| Part C controls | controls 35/35 pass | G4 19/19, N-W2 2/2, G5 4/4, default smoke 10/10; G1/G2 2/2 + 2/2; G3 non-fresh dispatch refused `effect=refused` 2/2; E4 0 | REAL; G5 FIXTURE (reconcile seam) + REAL |
| Part L toggle (TypeSafe) | 30/30 invocations, LF 1/1 | toggle: DELETED; warm valid 29/29; warm decisions 0, warm provider lines 0; median warm T 46.2 ms | LIVE_PROVIDER+REAL |
| Part L modal (TypeSafe) | 30/30 invocations, LF 0/1 verified | modal: REVISE; warm valid 29/29; warm decisions 0, warm provider lines 0; median warm T 47.9 ms; LF chose `reobserve` x4, unverified | LIVE_PROVIDER+REAL |
| LN descriptive live negative (literal role+name rename) | modal 1/1 run, toggle NOT_RUN (budget) | modal: refused at the failed precondition, 4 live decisions, 0 completion, no success reported | LIVE_PROVIDER+REAL / NOT_RUN |
| Provider | 15 attempts / 15 reached | lane cap 18 reached / 22 attempts; all 200, request id present 15/15; 0 blocked by the cap; model `jev-1.13.0` | LIVE_PROVIDER |
| Unit | 8/8 + 19/19 | `driver/test_r2_07e.py`; R2-07c `harness/test_compiled_routine_tm.py` carry-over | UNIT |
| Paired live BASE vs COMP+CR S | - | BLOCKED: budget (needs >= 120 reached) | BLOCKED |

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | COMP: R2-10 COMP trial unchanged (`r2_07c.one_comp` -> `rb10.one`). Its configuration is feedback OFF, 10 ms completion poll, compiled validators, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1` and phase trace on, and the step loop decides each click (scripted in Q/C, TypeSafe in L training and fallback). COMP+CR: the same Driver configuration plus compiled fresh-bound replay of the admitted artifact (`r2_07c.one_c`). Every click gets a fresh `semantic_v2` observation and 0 decisions. A failed precondition hands the current state to the guarded continuation, and its decisions are counted | REAL |
| Actual route / producer | From the launcher's Driver-call receipts. Each click is a `browser_click` with `input_route=dom_event`, receipt route `dom` and a `click.cdp_send` mark (R2-10 `browser_row`). Warm and admission cells: route `compiled` only, 0 decided events and 0 provider ledger lines. Training cells: 2 `provider` decisions. Live decisions are attributed per trial in `raw/provider-ledger.jsonl` (trial, class, arm, layer) | REAL / LIVE_PROVIDER |
| Independent target-owned oracle | jev-use #24 fixture server state + CLOCK_MONOTONIC journal. It is sampled every 2 ms by an independent harness thread (`rb10.Sampler`), never the runner. A verified task needs exactly 1 completion mutation from the journal. T_oracle = first expected-state sample at/after the caller return of the last accepted mutation, minus task start | REAL |
| Negative / fallback controls | Part C: N1-N8 (incl. N4a stale ref refused then rebound, N4b non-fresh dispatch refused, N5 old capability refused, N8 wrong page dispatches nothing), N-W2, G5 applied_ack_lost + withheld_unresolved, and the default smoke. Part L: LF (verdict-bearing forced fallback) and LN (descriptive live negative) | REAL / FIXTURE / LIVE_PROVIDER |
| Tested source SHA | Driver source `8f3a646b4818b757648835cf89db8886626b1cf0` (`libs/cua-driver` tree `bf8e7bdc90fdce295e44743f2754a6502d5d6e0e`). R2-07c harness at `7f46edd1681fbf58586f8b4972636c3da56e3be6` (harness tree `66bad345b1736b97b66884bbf40a1505c16083bf`). R2-07d runner at `79f6dd29958b2a73b477544ca9e777efade8a6c3` (`driver/r2_07d.py` blob `0989b68bc57d8fc16de3c0ab2cf80c61cd6bd334`). R2-07e runner at the PREREG commit `097c7131338155b8ba678799a64fa99715b8ea83`; `driver/` is unchanged after it. No Driver build | SOURCE |
| Driver binary | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9`, `cua-driver 0.32.0`. Re-hashed on the host at the start (13:06:46Z) and end (14:11:56Z), identical both times. Every run manifest and trial record carries name, sha256 and version, and the runner refuses on a mismatch | SOURCE |
| Environment | One shared Linux host. Every code-executing command ran under `hostless`. Driver and Chrome ran inside `cua-x11-session.sh` (private Xvfb + D-Bus) with an `xdpyinfo` probe before any trial. Google Chrome 151.0.7922.71 with an isolated profile per trial and the sandbox on. `CUA_DRIVER_RS_TELEMETRY_ENABLED=false` was passed through `CUA_SESSION_EXTRA_ENV`; the harness also sets `CUA_DRIVER_RS_TELEMETRY_ENABLED=0` and `DO_NOT_TRACK=1` in the Driver env. Default Driver safety settings | SOURCE |
| PREREG commit | `097c71313`, committed 2026-10-03T13:13:12Z. That is before the first measured trial (controls C1, 13:13:46Z), the first Q trial (14:05:24Z) and the first Phase L request (14:09:39Z). The live shakedown (13:19Z) ran after it and is excluded from results | SOURCE |
| Live heads at test time | Start 13:06:54Z: upstream main `c8edda06be53e13a759c69de125ce37189023954`, trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556` (open). End 14:11:56Z: upstream main `32b34fbc75abeb96af77df49ae0da72328e67707`, one commit later, touching only `libs/cua-driver/scripts` installers. PR 4316 head unchanged (open) | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); not assumed equal to the tested SHA | SOURCE |
| Provider | TypeSafe `api.typesafe.ai` `/v1/systemone`, model id `jev-1.13.0` (from the response, 15/15). Key forwarded by NAME only (`CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY`) | LIVE_PROVIDER |

## Method

### Part Q (REAL+BENCHMARK)

`driver/r2_07e.py --plan q` builds its plan from `r2_07c.build_plan("timing", 0, 60)`, restricted
to modal plus a toggle sanity block.

- **Plan.**
  - One training (+ compile + clean-reset admission) per class into store `timed-e`.
  - Then 60 modal AB/BA pairs: AB (COMP first) on even rounds, BA on odd rounds.
  - Then 10 toggle pairs on rounds 5, 10, 17, 22, 29, 34, 41, 46, 53 and 58. Their parity alternates,
    so the toggle arm order alternates too.
  - Each trial gets a fresh Driver, Chrome, loopback fixture servers, token and session label.
- **Load rule.** `r2_07d.gate` runs unchanged. A unit starts at a 1-min loadavg <= 3.0. Otherwise
  it waits up to 60 s and then ends the chunk (exit 75).
- **Locks.** Each chunk runs under `bin/quiet-timed R2-07e-Q<n>` (EXCLUSIVE) and takes
  `cargo-build.lock` inside it with `flock -w 60`, following the W6 lock order.
  - Chunks Q1-Q5 (13:37Z-13:57Z) acquired the quiet lock, could not get the cargo lock within 60 s
    because another lane held it, and exited 74 before any session or trial. Each released the
    quiet lock.
  - Q6 (14:05:18-14:08:22Z) ran all 72 units in 177 s.
  - The loop waited outside the locks for a host load <= 3.0 before every chunk.
- **Gate.** `analyze_r2_07e.paired_gate`, committed with the PREREG. It is the median paired diff
  with a seeded percentile bootstrap: two-sided 97.5%, seed 20261003, 10 000 resamples.
  - PASS iff the upper bound is <= +2.0 ms, 60/60 pairs are valid, G1/G2 pass, G3 is 100% fresh and
    E4 is 0.
  - **Alpha split, disclosed.** Look 1 (R2-07d: two-sided 95%, one-sided 0.025) failed. Look 2 (this
    block: two-sided 97.5%, one-sided 0.0125). The Bonferroni sum of the one-sided error rates is
    0.0375 <= 0.05. Look 1 is never pooled into the gate.

### Part C (REAL; SHARED quiet lock, <= 10 cells per acquisition)

The R2-07d controls plan, relabelled into store `scripted-e`, ran in 4 acquisitions (37 specs + 2
admissions). Pass rules are `analyze_r2_07c.g4_pass` / `nw2_row`, unchanged. G3 non-fresh = the
two N4b rows.

### Part L (LIVE_PROVIDER+REAL)

Both classes met their preconditions:

- toggle: R2-07d toggle Phase S PASS and Part C pass;
- modal: Part Q PASS and Part C pass.

`driver/r2_07e.py --plan live --classes toggle,modal` ran 64 specs.

- **Plan.** `r2_07c.build_plan("live", 0, 30)`, with the class order alternating per round, then
  per class:
  - LF (verdict-bearing forced fallback, `n7_presat`);
  - LN (descriptive literal-rename negative, `n1_renamed`).
- **Live rules.** These are `r2_07c.main_async`'s rules:
  - stop before an invocation if reached+4 or attempts+4 would exceed 18 / 22;
  - a warm invocation without an admitted routine retrains once, then the class stops.
- **Chunk.** One chunk, `bin/quiet-timed R2-07e-L1` (EXCLUSIVE, cargo lock inside), 14:09:32-14:11:00Z,
  trial-start loadavg 1.52-2.56.
- **Shakedown.** One toggle training via the unchanged R2-07c `r2_07c.py --plan live_shake` under
  SHARED. It used 2 requests and is excluded from results.
- **Provider guard.** `r2_07c.install_provider_ledger_c` counts each HTTP attempt before sending
  and refuses past the cap.

### Analysis

`analyze_r2_07e.py` reuses the R2-07d analysis (`rows_of`, `controls`, `g1_g2`, `g3_of`,
`pair_stats`) and, through it, the R2-07c analysis (`row_of`, `g4_pass`, `decomposition`,
`e4_total`) and the R2-10 per-trial row, all by import and unchanged.

## Results

### Part Q (REAL+BENCHMARK, chunk Q6)

| class | median T COMP | median T COMP+CR | paired diff CR-COMP, median [97.5% CI] | 95% CI (b01 seed) | S = COMP/CR [95%] | trial loadavg | gate |
|---|---|---|---|---|---|---|---|
| modal (gate) | 47.4 ms | 47.8 ms | -0.5 ms [-1.4, +0.5], range -9.0 to +6.6 | [-1.4, +0.5] | 0.992 [0.991, 1.027] | 1.57-3.17 (median 2.18) | PASS |
| toggle (sanity, descriptive) | 47.4 ms | 47.9 ms | +0.7 ms [+0.5, +2.6], range -1.5 to +2.8 | [+0.5, +2.5] | 0.990 [0.966, 0.990] | 1.70-3.43 (median 2.30) | none |

- **Medians against the paired median.** The difference of the arm medians (+0.4 ms) and the median
  of the paired differences (-0.5 ms) have opposite signs. The gate is pre-registered on the paired
  median. Both are reported, and neither is a saving.
- **Toggle sanity block.** It shows a small positive offset at n = 10 (+0.5 to +2.6 ms). It has no
  gate. R2-07d's 40-pair toggle block, the accepted Phase S PASS, measured +0.5 ms [-1.3, +0.8].
- **R2-07d look 1, side by side (not pooled).** Modal +0.6 ms [-1.4, +2.4] (95%) and
  [-1.5, +2.4] (97.5%). It stays a FAIL. The pooled 100-pair figure is +0.3 ms [-1.4, +0.5]
  (97.5%) and is descriptive only, because it comes from different windows and a different session
  environment variable. No absolute T is compared with R2-07d.

Component decomposition, mean ms over the 60 valid modal cells per arm (R2-10 e2_components,
coverage 0.986):

| component | modal COMP | modal COMP+CR |
|---|---|---|
| observation | 13.1 | 13.3 |
| endpoint revalidation | 20.7 | 20.7 |
| other revalidation | 2.0 | 2.1 |
| MCP transport | 4.3 | 4.2 |
| MCP admission | 1.5 | 1.5 |
| visualization | 1.7 | 1.7 |
| dispatch | 1.2 | 1.2 |
| resolution | 1.0 | 1.0 |
| verification reads | 1.0 | 0.5 |
| client validation / runner / sleeps-polls / effect lag / unattributed | 1.6 | 1.3 |
| mean T_runner | 48.3 | 47.5 |

Costs in the timing window:

| cost | modal | toggle |
|---|---|---|
| training T_oracle | 45.1 ms | 49.3 ms |
| compile | 0.115 ms | 0.236 ms |
| admission T_oracle | 45.9 ms | 44.0 ms |

### Part C controls (REAL; 1 rep per row per class)

| row | toggle | modal |
|---|---|---|
| G1 training / G2 clean-reset admission (store `scripted-e`) | 1/1, 1/1 | 1/1, 1/1 |
| N1 renamed / N2 missing: routine stops at the failed precondition, 0 completion, not verified | 1/1, 1/1 | 1/1, 1/1 |
| N3 duplicate: continuation drops the non-unique candidate, 0 completion | 1/1 | 1/1 |
| N4a stale ref: refused `browser_ref_stale` (`effect=refused`), one rebind, verified, 1 completion | 1/1 | 1/1 |
| N4b superseding snapshot (G3 non-fresh dispatch): refused `effect=refused`, rebind, verified | 1/1 | 1/1 |
| N5 session replaced: old capability refused, fresh bind, verified | 1/1 | 1/1 |
| N6 unexpected dialog: routine stops before action 2, 0 completion | 1/1 | 1/1 |
| N7 precondition already satisfied: routine dispatches nothing, continuation verifies, 1 accepted mutation | 1/1 | 1/1 |
| N8 wrong page (toggle on fill, toggle on modal; modal on toggle): 0 accepted mutations | 2/2 | 1/1 |
| N-W2 stale action: refused `effect=refused`, 0 detached effects, fresh re-derivation verified | 1/1 | 1/1 |
| G5 applied_ack_lost: `verified_by_reconcile`, 1 completion, no re-dispatch | 1/1 | 1/1 |
| G5 withheld_unresolved: stays `unknown`, no re-dispatch (reconcile before replay, never blind) | 1/1 | 1/1 |
| default smoke (R2-10 BASE, no `CUA_DRIVER_EXP_*`, no trace): verified, 1 completion | 5/5 | 5/5 |

### Part L (LIVE_PROVIDER+REAL)

| metric | toggle | modal |
|---|---|---|
| invocations run / planned | 30/30 | 30/30 |
| training T_oracle (2 live decisions, 2 reached) | 581.3 ms | 445.6 ms |
| compile | 0.183 ms | 0.110 ms |
| clean-reset admission T_oracle (0 decisions) | 47.9 ms | 45.9 ms |
| warm validity (denominator 29) | 29/29 | 29/29 |
| warm decisions / warm provider ledger lines / warm fallbacks | 0 / 0 / 0 | 0 / 0 / 0 |
| median / mean warm T_oracle | 46.2 / 47.4 ms | 47.9 / 47.5 ms |
| amortized mean over 30 (+compile + admission) | 66.8 ms | 62.3 ms |
| ratio of means (amortized / warm) | 1.41 | 1.31 |
| LF forced fallback (`n7_presat`): decisions, outcome | 1 (`click-confirm`), verified, T_oracle 257.9 ms | 4 (`reobserve` x4), budget_exhausted, 0 mutations, 794.6 ms to end |
| amortized mean over 31 incl. LF | 73.0 ms; ratio 1.54 | n/a (LF unverified, T_oracle undefined) |
| decisions per invocation (30) / (31 incl. LF) | 0.067 / 0.097 | 0.067 / 0.194 |
| LN literal rename (`n1_renamed`, descriptive) | NOT_RUN (budget: reached 15 + 4 > 18) | refused at the failed precondition (`target_not_found`); 4 live decisions (`open-dialog`, `reobserve` x3); 2 non-completion clicks (Open dialog, idempotent); 0 completion; no success reported |
| G3 (all L cells) / E4 (all L cells, LF/LN included) | pass / 0 | pass / 0 |
| trial-start loadavg | 1.52-2.56 | 1.52-2.56 |

Decomposition (R2-10 e2_components), mean ms:

| view | toggle T_runner | toggle provider decision (share) | modal T_runner | modal provider decision (share) |
|---|---|---|---|---|
| training (n=1) | 580.5 | 489.1 (84.2%) | 446.0 | 392.2 (87.9%) |
| warm (n=29) | 47.3 | 0.0 (0%) | 47.4 | 0.0 (0%) |
| all 30 invocations | 65.1 | 16.3 (25.0%) | 60.7 | 13.1 (21.6%) |

In the warm view the largest components are endpoint revalidation (about 20 ms), observation
(about 13.4 ms) and MCP transport (about 4.3 ms). These are the same Driver work as the
scripted COMP+CR cells.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock (same run) | Evidence class |
|---|---|---|---|
| compiled routine, toggle, live | 2 TypeSafe decisions and 2 provider requests per warm invocation (29/29 warm with 0 decisions, 0 ledger lines) | the training invocation took 581.3 ms with 489.1 ms of provider decision; warm median 46.2 ms. This is a within-run contrast (n = 1 training), not an S against R2-10 | LIVE_PROVIDER+REAL |
| compiled routine, modal, live | same (29/29 warm, 0 decisions, 0 lines) | training 445.6 ms (392.2 ms decision) vs warm median 47.9 ms; the same caveat applies | LIVE_PROVIDER+REAL |
| compiled routine, modal, scripted (Part Q) | the 2 scripted decisions, the per-step pre-oracle reads (-0.5 ms) and the completion-poll sleep (-0.3 ms); adds one fresh observation (+0.2 ms) | paired median -0.5 ms [-1.4, +0.5]: non-regression shown; no saving shown | REAL+BENCHMARK |

## Deviations

1. **Forced fallback design (decided before any trial; in PREREG).** The lane spec asks for one
   forced fallback that renames the compiled role+name target and expects it to verify. With the
   jev-use tasks those two cannot both hold.
   - `BrowserSemanticSource.find` and the ToggleConfirm/Modal task candidates match role+name
     exactly, so no candidate ever addresses a renamed target (SOURCE). R2-07c N1 10/10 and R2-07d
     N1 2/2 were unverified (REAL).
   - The verdict-bearing fallback (LF) therefore uses the precondition-failure variant that the
     guarded continuation can complete (`n7_presat`, R2-07c's G6 fallback cell).
   - The literal rename (LN) ran as a descriptive live negative, budget permitting. Toggle LN was
     NOT_RUN for budget and stays in the denominator.
2. **Telemetry variable.** The lane spec says R2-07d did not set it. In fact the R2-07d wrapper
   passed `CUA_DRIVER_RS_TELEMETRY_ENABLED=0`, and the R2-10 harness sets `0` in the Driver env in
   every lane (`rb10.driver_env_for`). This lane passes `false` in the session env as specified.
   The Driver parses both as off. Absolute T is still never compared with R2-07d.
3. `analyze_r2_07e.py` (everything except `paired_gate`, which `verify_artifacts.py` checks is
   unchanged since the PREREG), `driver/package_e.py`, `verify_artifacts.py`, `provenance.json` and
   `headline-numbers.json` were written after the PREREG commit. They implement the PREREG metrics.
4. **Pre-PREREG shakedown.** `R2-07e-shake-c1`: SHARED, scripted, 3 specs, 0 TypeSafe requests.
   Kept in `raw/shake-c-*`; excluded.
5. **Loop logs.** Chunk and loop logs in `raw/loop-logs/` drop the private-session noise lines:
   `[session]`, dbus-daemon, and lines naming a local absolute path. The per-file counts are in
   `raw/package-report.json`. Trial bundles are unfiltered.
6. **Unused budget.** The provider cap was not exhausted: 3 reached of the 18 remain unused.

## Limits and claim boundary

- One shared host, private Xvfb, Google Chrome 151, binary R (the 989cc76ce lineage, not R'),
  TypeSafe as configured by the jev-use runner (model `jev-1.13.0`). The routine is caller-side
  only: no new service, registry, router or engine.
- Logical routine identity persists (role+name targets, preconditions). Refs, tokens, captures,
  capabilities and session epochs do not. All 9 artifacts in `raw/artifacts/` pass the authority
  scan.
- Phase L is n = 1 training, 29 warm and 1 LF per class. The modal LF failure is a single live
  invocation. It shows the live continuation from the dialog-open state can stall on `reobserve`.
  It does not estimate a rate.
- Phase L T is never presented as an S against R2-10's live numbers. The paired live BASE vs
  COMP+CR S stays BLOCKED (it needs >= 120 reached).
- The toggle sanity block (+0.7 ms [+0.5, +2.6], n = 10) is descriptive. It does not reopen
  R2-07d's accepted toggle Phase S PASS, but it is not evidence of toggle non-regression either.

## Disposition

**Lineage disposition: KEEP (toggle) / REVISE (modal).**

- **toggle: DELETED (KEEP).**
  - All gates hold: warm 29/29, warm decisions 0, warm provider lines 0, E4 0, LF verified with its
    1 decision counted, and Phase S PASS (R2-07d).
  - E2: the live toggle provider-decision component (84% of the training invocation here; 88-89% of
    live COMP T in R2-10) is DELETED on admitted COMP+CR.
  - E3: the compiled routine enters the composed toggle configuration. Amortized over 30
    invocations the mean is 66.8 ms (73.0 ms with the fallback), measured over all invocations.
- **modal: REVISE.**
  - Failing gate: LF forced fallback not verified (TypeSafe chose `reobserve` 4 times with
    `confirm-choice` offered).
  - What holds: Part Q PASS, warm 29/29 with 0 decisions and 0 provider lines, E4 0, controls.
  - E2: warm deletion is measured, but the verdict-bearing fallback path is not shown to complete
    under the live provider.
- **Not a KILL candidate.** 0 E4 violations in every arm and every block. Neither fallback reported
  success, and nothing was blind-replayed.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration (commit `097c71313`) |
| `README.md` | this file |
| `.gitignore` | packet-local overrides (template), re-includes `raw/artifacts/` |
| `provenance.json` | provenance fields; `publication_sha` set by Publish |
| `r2-07e-summary.json` | full analysis output |
| `headline-numbers.json` | headline numbers with the exact README text |
| `analyze_r2_07e.py` | analysis (`paired_gate` pre-registered; imports the R2-07d/R2-07c analyses unchanged) |
| `verify_artifacts.py` | identity, PREREG-before-trials, `paired_gate` unchanged, summary recompute, headlines, authority, provider cap, cited files, privacy of every commit. Run under hostless; `--skip-git` on an export |
| `driver/r2_07e.py` | Q / controls / live runner (imports r2_07c and r2_07d unchanged) |
| `driver/run_chunk_e.sh` | W6 lock order + private session wrapper |
| `driver/test_r2_07e.py` | unit tests of the R2-07e additions |
| `driver/package_e.py` | packaging + privacy scan (R2-07d `package_d.clean`, R2-07c `package_raw` unchanged) |
| `raw/q-trials.tar.gz`, `raw/q-manifests/`, `raw/q-routines/`, `raw/q-load-gate.jsonl`, `raw/q-progress.json` | Part Q (144 trial records: 2 trainings, 2 admissions, 140 timing cells) |
| `raw/ctl-trials.tar.gz`, `raw/ctl-manifests/`, `raw/ctl-routines/` | Part C |
| `raw/live-trials.tar.gz`, `raw/live-manifests/`, `raw/live-routines/`, `raw/live-live-progress.json` | Part L (65 records: 2 trainings, 2 admissions, 58 warm, 2 LF, 1 LN) |
| `raw/lshake-*` | live shakedown (excluded) |
| `raw/shake-c-*` | pre-PREREG scripted shakedown (excluded) |
| `raw/provider-ledger.jsonl` | every provider attempt (no bodies, no headers) |
| `raw/artifacts/` | 9 compiled artifacts |
| `raw/lock-receipts-global.jsonl`, `raw/lock-receipts-lane.jsonl` | quiet-lane ledger lines labelled `R2-07e-*`; lane ledger |
| `raw/loop-logs/`, `raw/unit/`, `raw/package-report.json` | chunk/loop logs, unit outputs, packaging report |
