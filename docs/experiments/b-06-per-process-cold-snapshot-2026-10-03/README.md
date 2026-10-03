# B-06: browser cold first-snapshot, per-process part, decided on whole-task T_oracle on R' (922111c5), 2026-10-03

Owners: kvnloo/cua#93 (experiment spec, invariants), kvnloo/cua#10 (whole-task accounting), kvnloo/cua#73.
Advances E2 (per-process part of the browser cold first-snapshot excess) and E1 (B-04 left it UNDECIDED).

## Result in one paragraph

All 559 measured trials were valid by the target-owned oracle (main block 335/335, Wn block 96/96, amendment
block x 128/128). E4 was 0 in every arm. TypeSafe was not used (0 attempts, 0 reached).
- **Primary verdict (PREREG.json): UNDECIDED in fill and in toggle. Failed control: PC.**
  - The A/A negative control passed: fill Wa−Wb 0.0 [-1.0, 1.0], toggle Wa−Wb 0.0 [-1.6, 1.0].
  - The 15 ms in-T positive control moved T_oracle clearly (CI excludes 0) but by less than its pre-registered
    [12, 18] ms window: fill P−Wa 10.0 [8.1, 10.0], toggle P−Wa 10.9 [10.0, 12.0].
  - Cause (descriptive): a sleep placed before the first snapshot overlaps browser-side work that the first
    snapshot otherwise waits for. In P, snapshot1 is about 5 ms shorter than in Wa, so the sleep's effect on T is
    sub-additive.
  - Not a verdict, because PC failed: D (C − Wa) was fill D 11.9 [10.0, 12.0] and toggle D 6.0 [3.9, 6.2].
- **Secondary, amended verdict (PREREG-AMENDMENT-1, block x, committed before its trials): OWNER_DECISION in
  fill and in toggle.**
  - Block x moves the 15 ms sleep to right after snapshot1 returns, where it cannot overlap the first
    snapshot's wait.
  - Controls passed. NC: fill Wa−Wb 0.0 [-0.02, 2.0], toggle Wa−Wb -0.1 [-2.0, 0.2]. PC2: fill P2−Wa 16.0
    [14.0, 16.0], toggle P2−Wa 15.1 [14.1, 17.0].
  - D (C − Wa) was fill D 10.0 [8.0, 12.0] (replicate D' 10.0) and toggle D 4.0 [3.9, 6.0] (D' 4.0).
  - So the per-process part is real and material. It can be deleted only by process reuse kept outside T, which
    is an owner session/process-reuse policy, sized about 10 ms (fill) and 4 ms (toggle) per task on R'.
- **E2 on R'.** R2-10R's own cold excess on R' is E_R' 17.4 ms (fill) and E_R' 9.8 ms (toggle).
  - Under the primary verdict it stays UNTESTED, and the scripted untested shares are lower bounds: 36.70%
    (fill) and 34.93% (toggle).
  - Under the amended verdict the cold excess is terminal: per-document IRREDUCIBLE (B-04, carried by SOURCE)
    plus per-process OWNER_DECISION. The shares then fall back to R2-10R's own 15.18% / 16.65%, which are still
    above 5%.

## Disposition

**REVISE.** The pre-registered rule gives **UNDECIDED (failed control: PC)** for the per-process part in both
classes. The disclosed amendment (secondary) gives **OWNER_DECISION** in both classes, with every control passing.

The owner decides whether the amended reading closes E1/E2 for this row. If it does:
- the per-process part becomes an owner policy item (process or session reuse kept outside T, about 10 ms fill /
  4 ms toggle per task on R');
- the browser cold first-snapshot excess is terminal;
- R2-10R's scripted untested shares go back to 15.18% (fill) and 16.65% (toggle).

Either way, nothing is DELETED: there is no product change and no knob.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | R2-10R COMP, scripted chooser: feedback off; focus settle 0 on fill; 10 ms completion poll, 2.0 s deadline; caller-compiled output validators; `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`; guarded completion + compiled replay on fill (R2-10R scripted COMP routine); R2-10 step loop on toggle/modal; Driver phase trace on; telemetry off. Per-trial receipts: admission-cache env and ≥ 1 `mcp.inner_validation_skipped` mark (320/320 main-block COMP trials, minimum 10 marks); fill route `compiled` 128/128 | REAL (FIXTURE) |
| Actual route / producer | Driver receipt route per action: fill `trusted_input`, `dom`; toggle/modal `dom`, `dom` (320/320 main block; 128/128 block x via validity). Driver pid and Chrome browser pid with /proc start time: warm arms identical at warm-up and at task start in 336/336 (main + Wn) and 96/96 (block x); every (pid, start time) pair unique across all 559 trials, so C always had new processes | REAL |
| Independent target-owned oracle | jev-use fixture server state, re-read every 2 ms by a harness thread (B-04/R2-10 `Sampler`): fill `submitted == token`, toggle `checked`, modal action applied; server CLOCK_MONOTONIC journal with exactly one completion mutation. T_oracle = first expected-state sample at/after the caller-side return of the last accepted mutation − task_start (return of the task `browser_navigate`) | REAL (FIXTURE) |
| Negative / fallback controls | NC A/A (Wa−Wb), PC (P−Wa, 15.0 ms in T before snapshot1; amendment PC2 = P2−Wa, 15.0 ms right after snapshot1), validity ≥ 95% per cell, product-default smoke 5/5 per class. NC passed everywhere; PC failed its size window in the main block; PC2 passed in block x | BENCHMARK+REAL (FIXTURE) |
| Tested source SHA | `45dff8f3227a21ff8bef1af4bf4c2bcbd9449b2a` (R' = 0f1955d2f + R2-10 steps 1-8); libs/cua-driver tree `11ee32235d5e`, rust tree `3ae6bd440862`, browser dir tree `5f94d38e37d0` | SOURCE |
| SOURCE carry of B-04 | `git diff --stat 8f3a646b4 45dff8f32 -- libs/cua-driver/rust/crates/cua-driver-core/src/browser/` is empty (both trees `5f94d38e37d0`), so B-04's per-document verdict (IRREDUCIBLE on R `12b9045a`) carries to R' by SOURCE identity; B-04 P4 not re-run | SOURCE |
| Driver binary | `cua-driver-r2-10r-a2-45dff8f32`, sha256 `922111c518d73b9675a9800d39a389c17070d40d16f25ada1426a90eccd06ec8`, `cua-driver 0.32.0` (read inside the session at start and end); re-hashed 07:18Z and 11:32Z, identical; not rebuilt; sha256 in every trial record and manifest | REAL |
| Browser | Driver-chosen system Chrome (exe basename `chrome` in 559/559), Google Chrome 151.0.7922.71 (read in session at start and end); `browser_prepare {allow_launch, isolated_new}`, sandbox on, fresh profile per trial | REAL |
| Environment | One Linux 7.2.2 host shared with other tracks; `bin/hostless` around every code-executing command; `cua-x11-session.sh` private rootless Xvfb + private dbus; 0-3 s start jitter + `xdpyinfo` probe before each session (0 display-collision retries); 1-min loadavg at trial start main + Wn min 1.28 / median 3.14 / max 4.87, block x median about 1.3 | SOURCE |
| PREREG commit | `19ea50dc2`, committed 07:30:11Z, before the first measured trial at 07:39:23Z. PREREG-AMENDMENT-1 `5c79ea0e4`, committed 10:52:28Z, before the first block-x trial at 11:29:09Z | SOURCE |
| Live PR heads at test time | start (07:28Z): upstream main `cb685fad7` (libs/cua-driver tree `df2b49c3`), trycua/cua PR 4316 `a0bca7440` open, kvnloo/cua#106 `c45845797` open. End (11:33Z): upstream main `379085c5e` (14 commits; every libs/cua-driver change is macOS/Windows/e2e/docs, nothing in cua-driver-core or platform-linux), PR 4316 and #106 unchanged | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); never equal-by-assumption to the tested SHA | SOURCE |
| Live heads at publication | set by Publish (`provenance.json: live_heads_at_publication`) | SOURCE |
| Provider | none (scripted chooser); TypeSafe cap 0: 0 attempts, 0 reached | NOT_RUN |

## Method

- **Arms.** Every trial starts a fresh `cua-driver mcp`, a fresh Driver-launched Chrome, fresh fixture servers
  and a fresh token. The arms differ only between `browser_prepare` and the task navigate:
  - C (cold): nothing. The task document is the process's first.
  - Wa and Wb (warm, two labels for A/A): OUTSIDE T, `browser_navigate` to B-04's matched-content sibling page,
    then one semantic_v2 snapshot. The sibling page has the same fixture origin, DOM structure and roles, with
    different text and tokens. The task navigate then runs in the same tab, Driver and Chrome. The warm-up is
    timed separately.
  - P: Wa plus a 15.0 ms CLOCK_MONOTONIC sleep inside T, between the task navigate return and the first
    snapshot call. The measured sleep was 15.0001 ms median, maximum 15.0033.
  - Wn (descriptive): the warm-up navigates to the sibling page without a snapshot.
  - SMOKE: product-default configuration (no `CUA_DRIVER_EXP_*`), cold.
  - P2 (amendment only): Wa plus the same 15.0 ms sleep, placed right after snapshot1 returns.
- **Design.**
  - Main block: a 4x4 Williams square over C/Wa/Wb/P (first-order carry-over balanced). Fill and toggle ran 32
    rounds each (8 squares); modal ran 16 (consistency only). Smoke ran in rounds 0-4.
  - Wn block: 16 rounds of AB/BA Wn/Wa pairs per class.
  - Block x (amendment): a Williams square over C/Wa/Wb/P2, 16 rounds each for fill and toggle.
  - Pre-registered load rule: a round starts only at a 1-min loadavg ≤ 4.0, waiting up to 60 s.
    - Chunk `b06-main-a1-r10-21` hit the rule before round 16 (load1 5.51 after 60 s) and released both locks.
    - Rounds 16-21 then ran in chunk `b06-main-a1-r16-21`.
    - No round was cut, so every round ran in its first attempt.
- **Locks.**
  - Each measured chunk took the cargo-build lock first, then one EXCLUSIVE `bin/quiet-timed` acquisition with
    a 600 s cap inside it. Ledger lines are in `raw/lock-ledger.jsonl`.
  - Pilot, version reads, the R2-10R re-analysis and the analyzer ran under the SHARED lock, with a receipt
    line for each.
- **Statistics.** Paired within-round differences. Percentile bootstrap of the median, 10 000 resamples, a fresh
  `random.Random(20261003)` per contrast, 95% CI. T_oracle values sit on the 2 ms oracle sampling grid, so the
  medians and CI bounds cluster near even milliseconds.
- **Commands** (machine paths come from the environment, never from the packet):
  - Measured chunks: `hostless bash lane-scripts/run-chunk.sh <label> <main|wn|x> <rounds> <block> 1`, which
    runs `run_b06.py` inside `cua-x11-session.sh` through `lane-scripts/session-retry.sh` and
    `lane-scripts/in-session.sh`.
  - Analysis: `hostless python3 analyze_b06.py`, then `make_headlines.py`, then `verify_artifacts.py`.

## Results (N of M, evidence class per row)

### Controls and verdict, main block (primary, PREREG.json)

| class | NC Wa−Wb median [CI] | PC P−Wa median [CI] | validity | smoke | D (C−Wa) median [CI] | D' (C−Wb) | verdict | evidence class |
|---|---|---|---|---|---|---|---|---|
| fill | Wa−Wb 0.0 [-1.0, 1.0] pass | P−Wa 10.0 [8.1, 10.0] **fail** (below 12) | 128/128 | 5/5 | D 11.9 [10.0, 12.0] (not a verdict) | D' 10.0 | UNDECIDED | BENCHMARK+REAL (FIXTURE) |
| toggle | Wa−Wb 0.0 [-1.6, 1.0] pass | P−Wa 10.9 [10.0, 12.0] **fail** (below 12) | 128/128 | 5/5 | D 6.0 [3.9, 6.2] (not a verdict) | D' 5.8 | UNDECIDED | BENCHMARK+REAL (FIXTURE) |
| modal (consistency) | Wa−Wb 0.0 [-1.0, 2.0] | P−Wa 9.1 [8.0, 10.0] | 64/64 | 5/5 | D 5.1 [3.0, 7.0] | D' 5.2 | descriptive | BENCHMARK+REAL (FIXTURE) |

Load sensitivity: keeping only rounds where every trial started at ≤ 4.0 leaves 30 (fill), 27 (toggle) and 12
(modal) rounds. Every gate keeps its outcome; the D medians are 11.9 / 6.0 / 5.1 ms
(`b06-summary.json` `load_sensitivity`).
Evidence class: BENCHMARK+REAL (FIXTURE).

Median T_oracle per arm, ms:

| class | C | Wa | Wb | P | evidence class |
|---|---|---|---|---|---|
| fill | C 64.2 | Wa 54.1 | Wb 53.1 | P 64.1 | BENCHMARK+REAL (FIXTURE) |
| toggle | C 50.2 | Wa 46.1 | Wb 46.1 | P 56.2 | BENCHMARK+REAL (FIXTURE) |
| modal | C 52.2 | Wa 48.1 | Wb 48.2 | P 56.1 | BENCHMARK+REAL (FIXTURE) |

**Why PC failed (mechanism, descriptive).** Sleeping 15 ms before snapshot1 shortens snapshot1 itself.
- Fill snapshot1 call median: 5.2 ms in P vs 10.7 ms in Wa. DOM.getDocument: 0.40 vs 2.97 ms. Session attach:
  0.35 vs 2.51 ms.
- B-04's E_R-form excess span(snapshot1) − span(snapshot2) is 0.3 ms in P vs 5.8 ms in Wa.
- So in a warm process, about 5 ms of the first snapshot is waiting for the just-committed document. A sleep at
  that point absorbs it, and the 15 ms sleep adds only about 10 ms to T.
- This is the same per-document effect B-04 found with an 80 ms wait. The [12, 18] window assumed additivity.

### Amendment block x (secondary, PREREG-AMENDMENT-1)

| class | NC Wa−Wb median [CI] | PC2 P2−Wa median [CI] | validity | D (C−Wa) median [CI] | D' (C−Wb) | amended verdict | evidence class |
|---|---|---|---|---|---|---|---|
| fill | Wa−Wb 0.0 [-0.02, 2.0] pass | P2−Wa 16.0 [14.0, 16.0] pass | 64/64 | D 10.0 [8.0, 12.0] | D' 10.0 | OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |
| toggle | Wa−Wb -0.1 [-2.0, 0.2] pass | P2−Wa 15.1 [14.1, 17.0] pass | 64/64 | D 4.0 [3.9, 6.0] | D' 4.0 | OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |

- In P2, snapshot1 has Wa's shape (fill 9.6 vs 10.1 ms), so the sleep is additive. The 2 ms sampling grid puts
  the medians at 15-16 ms.
- Every block-x round started at loadavg ≤ 4.0, so the sensitivity view is identical.
- Block-x numbers are never pooled with main-block numbers.

### Descriptive (no gates)

**Snapshot1 split, median ms** (Driver phase trace, main block; attach / DOM.getDocument / Accessibility tree):

| class | C | Wa | P | evidence class |
|---|---|---|---|---|
| fill | 3.07 / 8.15 / 3.95 | 2.51 / 2.97 / 0.90 | 0.35 / 0.40 / 0.90 | BENCHMARK+REAL (FIXTURE) |
| toggle | 2.51 / 4.54 / 0.83 | 2.23 / 1.72 / 0.55 | 0.32 / 0.30 / 0.57 | BENCHMARK+REAL (FIXTURE) |

**B-04 E_R-form estimator span(snapshot1) − span(snapshot2), median ms:**
- fill: C 16.0, Wa 5.8, Wb 5.3, P 0.3;
- toggle: C 8.8, Wa 4.1, Wb 4.5, P 0.4.

The evidence class is BENCHMARK+REAL (FIXTURE). B-04's E_span needed a re-snapshot inside T, which would change
T, so it was not added.

**Warm-up and amortized cost** (main block, median ms; per-task cost = T_Wa + warm-up / k):

| class | C | Wa | warm-up | k = 1 | k = 5 | evidence class |
|---|---|---|---|---|---|---|
| fill | C 64.2 | Wa 54.1 | warm-up 38.3 | k=1 92.3 | k=5 61.7 | BENCHMARK+REAL (FIXTURE), descriptive |
| toggle | C 50.2 | Wa 46.1 | warm-up 30.5 | k=1 76.5 | k=5 52.2 | same |
| modal | C 52.2 | Wa 48.1 | warm-up 32.4 | k=1 80.5 | k=5 54.6 | same |

- A warm-up paid inside one task costs more than it saves.
- Spread over 5 tasks per process, it comes out slightly ahead of C in fill (61.7 vs 64.2 ms) and slightly
  behind in toggle (52.2 vs 50.2 ms) and modal (54.6 vs 52.2 ms).
- The only deletion is process reuse with the warm-up kept outside T. That is the owner policy question; this
  lane neither sizes nor endorses a warm pool.

**Wn vs Wa (process vs prior snapshot), Wn block:**

| class | Wn−Wa median [CI] | Wn / Wa median T | snapshot1 AX tree Wn vs Wa | evidence class |
|---|---|---|---|---|
| fill | Wn−Wa 6.0 [4.0, 7.0] | 56.2 / 52.1 | 3.66 vs 0.85 ms | BENCHMARK+REAL (FIXTURE), descriptive |
| toggle | Wn−Wa 1.8 [0.03, 2.1] | 46.1 / 44.2 | 0.75 vs 0.61 ms | same |
| modal | Wn−Wa 2.2 [1.1, 4.2] | 46.4 / 44.1 | 0.70 vs 0.47 ms | same |

- In fill, both effects warm the path. A process that has only navigated (Wn) still pays about 6 ms more than
  one that also snapshotted (Wa); the largest visible part is the snapshot1 Accessibility-tree fetch (3.66 vs
  0.85 ms). Wn's snapshot1 DOM.getDocument (2.56 ms) is already near Wa's (2.16 ms), so the process plus a
  prior navigation warms the DOM path and the prior snapshot warms the AX path.
- In toggle and modal, the process and navigation do most of it, and the prior snapshot adds about 2 ms.
- The comparison with C is across blocks, so it is not computed.

### E2 on R' (R2-10R scripted COMP; BENCHMARK re-analysis of R2-10R raw @ c183b95e3)

E_R' is R2-10R's own cold excess, span(snapshot1) − span(snapshot2) (B-04 rule, `r10r_observation.py`,
`raw/r10r-observation-rows.json`, 32/32 per class valid). The untested ms and mean T come from
`r2-10r-summary.json` `browser.scripted.decomposition.*/COMP` (`raw/r10r-comp-rows.json`).

| class | mean T | untested (R2-10R) | E_R' mean [CI] | share R2-10R as published | B-04 mapping (pre-B-06) | primary B-06 (UNDECIDED) | amended B-06 (OWNER_DECISION) | evidence class |
|---|---|---|---|---|---|---|---|---|
| fill | 80.9 | 12.28 | E_R' 17.4 [16.5, 18.4] | 15.18% | 36.70% | 36.70% (lower bound) | 15.18% | BENCHMARK re-analysis (R2-10R REAL+BENCHMARK raw) + this lane's verdicts |
| toggle | 53.6 | 8.92 | E_R' 9.8 [9.1, 10.6] | 16.65% | 34.93% | 34.93% (lower bound) | 16.65% | same |
| modal | 55.3 | 8.97 | E_R' 10.1 [9.3, 11.0] | 16.21% | 34.51% (if remapped) | 16.21% (B-04 row unchanged) | 16.21% | same |

- **BELOW_GATE views.** R2-10R carries no BELOW_GATE label measured on R'. With BELOW_GATE counted as
  IRREDUCIBLE and with it counted as UNTESTED, the shares are identical: the table above.
  B-05's BELOW_GATE split (binary B5) is cited, not combined.
- **No cross-binary arithmetic.** No number from B-04 (binary R) or B-05 (binary B5) is added to or ratioed with an
  R' number.
- **Sizes and timing.** The per-process OWNER_DECISION size (D, this lane) and E_R' (R2-10R) are on the same
  binary but were measured at different times. They are shown side by side, not subtracted.
- **E2 gap.** Under either reading, the browser classes stay above the 5% E2 threshold. The remaining untested ms
  are R2-10R's mcp_transport, resolution, admission residual and similar rows (B-05's territory).

### E4 (every arm)

| arm | n | stale-ref dispatch | duplicate mutation | unverified success | refusal returned as success | non-loopback connect | evidence class |
|---|---|---|---|---|---|---|---|
| C / Wa / Wb / P (main) | 80 each | 0 | 0 | 0 | 0 | 0 | REAL (FIXTURE) |
| SMOKE | 15 | 0 | 0 | 0 | 0 | 0 | REAL (FIXTURE) |
| Wn / Wa (Wn block) | 48 each | 0 | 0 | 0 | 0 | 0 | REAL (FIXTURE) |
| C / Wa / Wb / P2 (block x) | 32 each | 0 | 0 | 0 | 0 | 0 | REAL (FIXTURE) |

There were also 0 routine fallbacks and 0 oracle reverts after ok.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Evidence class |
|---|---|---|---|
| process reuse with the warm-up outside T (owner policy, not a product change here) | none in the product (no knob, no change). Mechanism: a reused process skips the cold DOM.getDocument / AX-tree / attach work of the first snapshot (fill snapshot1 21.2 → 10.7 ms) | in-task T: fill D 11.9 [10.0, 12.0] and toggle D 6.0 [3.9, 6.2] in the main block (primary, not a verdict); fill D 10.0 [8.0, 12.0] and toggle D 4.0 [3.9, 6.0] in block x (amended verdict). The warm-up itself costs warm-up 38.3 (fill) / warm-up 30.5 (toggle) ms outside T | BENCHMARK+REAL (FIXTURE) |
| in-task prewarm | none | negative (k = 1: warm-up inside T is slower; B-04 PREWARM) | BENCHMARK+REAL (FIXTURE), descriptive |

## Deviations

1. **libs/cua-driver tree label.** The spec says R' has libs/cua-driver tree `df2b49c32e73`. That tree belongs
   to R's base 0f1955d2f, and it equals upstream main cb685fad7's tree. R' itself (base + steps 1-8) has tree
   `11ee32235d5e`. Both are recorded. The browser directory is identical in R and R'.
2. **Routine source path.** R2-10R's scripted COMP routine lives in its packet's
   `raw/browser/scripted-routines/`, not `harness/`. Its `harness/r2_10_browser.py` holds the COMP
   configuration. Both are copied blob-identically into `harness/r2-10r/`.
   - The routine artifact equals B-04's copy; only `compile_ms` differs.
   - The COMP arm line of `harness/b04/run_b04.py` equals R2-10R's. Both facts are checked by the verifier.
3. **Pilot.** A 7-trial pilot ran before PREREG under the SHARED lock with the load rule disabled. It is
   excluded (`raw/pilot-trials.tar.gz`).
4. **Analyzer written during the data.** `analyze_b06.py`, `make_headlines.py`, `r10r_observation.py`,
   `verify_artifacts.py` and `lane-scripts/package_raw.py` implement PREREG.json and were written after it.
   - The main-block gates were computed once after the main block was complete (09:39Z, SHARED lock
     `b06-analyze-main`), before the Wn block ran. The Wn block has no gate.
   - That look found the PC failure and led to Amendment 1.
5. **Amendment 1 (block x).** It was added after the main-block result and committed before any block-x trial.
   - It changes no primary gate or verdict.
   - Its verdict is reported as secondary and labelled "amended".
   - The runner gained arm P2 and plan `x` only. The edit was made after the Wn chunk's runner had loaded, so
     main, Wn and pilot ran the PREREG runner.
   - `b06_rows.py` gained P2 in its warm set and sleep check. The analyzer gained the block-x section.
6. **Load stop.** The load rule ended chunk `b06-main-a1-r10-21` before round 16. Rounds 16-21 ran later with
   the same attempt number, because they had never started.
7. **Lock waits.** Measured chunks waited up to about 75 min for the cargo-build lock and the EXCLUSIVE quiet
   lock. A queue of builds and timing lanes was ahead, and shared readers kept arriving while the exclusive
   request waited. No trial ran outside an EXCLUSIVE window.
8. **Analyzer reading.** For NOT_MATERIAL, sign agreement of D' was also required, and a zero median counts as
   agreeing. This was pre-registered and did not matter: no class came near NOT_MATERIAL.

Near misses: one. While comparing B-04's and R2-10R's routine files during lane setup (before PREREG), a
`python3 -c` JSON pretty-print (stdlib only, no display, bus or socket) ran from the plain shell instead of under
hostless. It touched no desktop session and produced no reported number. Every later Python ran under hostless.
Hard-rule breaches: none.

## Limits and claim boundary

- **Scope.** One host under shared load, private Xvfb, Driver-chosen system Chrome 151.0.7922.71, binary R'
  `922111c5` only, tested source `45dff8f32`, scripted chooser, TypeSafe not used.
- **Fixture.** jev-use fixture (fill → submit) and the kvnloo/cua#24 toggle/modal pages, with B-04's sibling
  pages for the warm-up.
- **What the verdict covers.** Process reuse outside T for a single task. It does not design or endorse a warm
  pool, a session lifecycle, or any new service.
- **No product change.** Instrumentation is the existing env-gated phase trace; default Driver behaviour is
  unchanged.
- **Primary vs amended.** The primary verdict is UNDECIDED. OWNER_DECISION rests on Amendment 1, which was
  pre-registered before its trials but after the main-block result was known.
- **Resolution.** T_oracle has a 2 ms sampling grid, so toggle's D (about 4-6 ms) is resolved only to that grid.
- **Cross-block comparisons.** Absolute T is not compared across blocks.
- **Upstream drift.** Upstream main moved during the lane (cb685fad7 → 379085c5e). Every libs/cua-driver change
  is outside the Linux browser path.

## Locks, isolation, near misses

- Ledger (`raw/lock-ledger.jsonl`, verbatim). Measured, all EXCLUSIVE `quiet-timed`, each preceded by the
  cargo-build lock:
  - `b06-main-a1-r00-09` 07:39:15-07:43:01Z;
  - `b06-main-a1-r10-21` 07:52:21-07:56:00Z (rc 75, load stop);
  - `b06-main-a1-r22-31` 08:56:57-08:58:50Z;
  - `b06-main-a1-r16-21` 09:36:35-09:37:47Z;
  - `b06-wn-a1-r00-15` 10:51:46-10:54:10Z;
  - `b06-x-a1-r00-15` 11:29:01-11:31:58Z.
- SHARED: `b06-pilot-r00`, `b06-versions-start`, `b06-r10r-observation`, `b06-analyze-main`,
  `b06-versions-end` (and `b06-analyze-final`, after packaging).
- Every manifest lies inside its window (verifier check).
- Session logs show `hostless=1`, `wayland=unset`, `telemetry_env=0`, `dnt=1`, a private display, and
  `xdpyinfo=ok`.
- The plain shell was used for git, gh reads, file reads/edits and `ps`, `/proc/locks` and `sha256sum`
  (read-only), apart from the near miss above.
- TypeSafe: 0 attempts, 0 reached.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed in 19ea50dc2 before the first measured trial |
| `PREREG-AMENDMENT-1.json` | block x (additive positive control), committed in 5c79ea0e4 before its first trial |
| `README.md` | this file |
| `.gitignore` | packet-local `!*.log`, `!build/` (template) |
| `run_b06.py` | runner (measurement only): arms, plans, pid receipts, load rule |
| `b06_rows.py` | per-trial extraction (B-04 `b04_rows.row` + B-06 receipts and validity) |
| `analyze_b06.py` | statistics, gates, verdicts, E2 mapping → `b06-summary.json` |
| `r10r_observation.py` | R2-10R own cold excess E_R' and COMP rows from R2-10R's packet → `raw/r10r-observation-rows.json`, `raw/r10r-comp-rows.json` |
| `make_headlines.py` | `headline-numbers.json` |
| `verify_artifacts.py` | packet verifier (recompute, headlines, harness identity, receipts, locks, cited files, PREREG order, privacy of every commit) |
| `verify_helper.py` | cited-file check (template copy) |
| `b06-summary.json` | all results |
| `headline-numbers.json` | every quoted number with its summary path |
| `provenance.json` | SHAs, binary, browser, heads, environment |
| `harness/b04/run_b04.py` | B-04 runner, blob-identical |
| `harness/b04/b04_rows.py` | B-04 extraction, blob-identical |
| `harness/b04/harness/b01_fixtures.py` | blob-identical (B-04 harness/) |
| `harness/b04/harness/b01_tasks.py` | blob-identical |
| `harness/b04/harness/cdp_raw.py` | blob-identical |
| `harness/b04/harness/compiled_routine.py` | blob-identical |
| `harness/b04/harness/r2-10-scripted-COMP-routine.json` | blob-identical |
| `harness/b04/harness/run_b02.py` | blob-identical |
| `harness/b04/harness/run_b03.py` | blob-identical |
| `harness/b04/harness/run_critpath.py` | blob-identical |
| `harness/r2-10r/r2_10_browser.py` | R2-10R COMP configuration, blob-identical |
| `harness/r2-10r/scripted-COMP.json` | R2-10R scripted COMP routine (replayed), blob-identical |
| `lane-scripts/run-chunk.sh` | measured chunk: cargo lock, EXCLUSIVE quiet-timed, 600 s cap inside |
| `lane-scripts/session-retry.sh` | 0-3 s jitter, display-collision retry |
| `lane-scripts/in-session.sh` | session entry and refusals, version read |
| `lane-scripts/shared-locked.sh` | SHARED-lock wrapper with ledger receipt |
| `lane-scripts/package_raw.py` | deterministic packaging and scrubbing |
| `raw/main-trials.tar.gz` | main block: 335 trial records + Driver traces |
| `raw/wn-trials.tar.gz` | Wn block: 96 trial records + Driver traces |
| `raw/x-trials.tar.gz` | amendment block x: 128 trial records + Driver traces |
| `raw/pilot-trials.tar.gz` | pilot (excluded) |
| `raw/main/run-manifest-main-m-a1-r00-09.json` | chunk manifest |
| `raw/main/run-manifest-main-m-a1-r10-21.json` | chunk manifest (load stop, every load check) |
| `raw/main/run-manifest-main-m-a1-r16-21.json` | chunk manifest |
| `raw/main/run-manifest-main-m-a1-r22-31.json` | chunk manifest |
| `raw/wn/run-manifest-wn-w-a1-r00-15.json` | chunk manifest |
| `raw/x/run-manifest-x-x-a1-r00-15.json` | chunk manifest |
| `raw/pilot/run-manifest-pilot-pilot-a1-r00-00.json` | pilot manifest |
| `raw/lock-ledger.jsonl` | this lane's quiet-lane ledger lines |
| `raw/r10r-comp-rows.json` | R2-10R COMP decomposition rows @ c183b95e3 |
| `raw/r10r-observation-rows.json` | R2-10R E_R' per trial @ c183b95e3 |
| `raw/logs/b06-main-a1-r00-09.log` | chunk log |
| `raw/logs/b06-main-a1-r10-21.log` | chunk log |
| `raw/logs/b06-main-a1-r16-21.log` | chunk log |
| `raw/logs/b06-main-a1-r22-31.log` | chunk log |
| `raw/logs/b06-wn-a1-r00-15.log` | chunk log |
| `raw/logs/b06-x-a1-r00-15.log` | chunk log |
| `raw/logs/pilot-r00.log` | pilot log |
| `raw/logs/versions-start.log` | version + sha256 in session (start) |
| `raw/logs/versions-end.log` | version + sha256 in session (end) |

Raw outputs are mirrored to `artifacts/r2/B-06/` in the lane workspace.
