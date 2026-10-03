# B-04: browser cold-first-snapshot reconciliation on R2-10's binary R (wave 4, attempt 2)

Owners: kvnloo/cua#93 (experiment spec, invariants), kvnloo/cua#10 (whole-task accounting).
Advances E1 (B-03 left toggle H_W UNDECIDED and fill's "moved only" verdict provisional) and E2
(R2-10 labelled its observation component IRREDUCIBLE by carry-over: 15.7-29.0 ms, 29-33% of COMP T).

## Disposition

**REVISE.** R2-10's browser observation row is replaced by a measured row on R2-10's own binary R. Fill and
toggle are decided together by the same pre-registered rules in the same block:

| class | per-document part (Williams block x; block m) | per-process part | headline untested share (R2-10 → this lane), scripted / live | evidence class |
|---|---|---|---|---|
| fill | **IRREDUCIBLE**. Block x: W80 +57.9 ms [48.0, 65.0], PREWARM +48.2 ms [44.2, 56.3]. Block m: W80 +64.0 [58.1, 66.9], PREWARM +44.7 [31.3, 57.4] | **UNDECIDED** (no estimator passed the P1 negative control) | 15.2% → 39.1% / 14.0% → 36.5% | BENCHMARK+REAL (FIXTURE); live share = BENCHMARK re-analysis of R2-10 LIVE_PROVIDER raw |
| toggle | **IRREDUCIBLE**. Block x: W80 +56.6 ms [40.5, 64.0], PREWARM +53.8 ms [42.3, 68.6]. Block m: W80 +64.0 [61.8, 69.1], PREWARM +37.3 [27.7, 65.6] | **UNDECIDED** (same) | 16.4% → 36.0% / 90.4% → 92.7% | same |
| modal | consistency check only (R2-10 / B-02 row unchanged) | P2 contrast 5.7 ms [3.8, 8.3] (gate-failed estimator) | 16.4% / 90.9% unchanged | BENCHMARK+REAL (FIXTURE) |

- P4 order. Block m (the measured rounds) ran a fixed W80/W0 order within each class: the PREREG row formula
  was not a Williams design (Deviation 7). Block x is a disclosed extension of 180 P4 trials, all valid, run in
  true Williams order. The per-document verdict requires the PREREG rule to pass in both blocks, and it does
  in both classes.
- B-03's toggle H_W and B-02's fill "moved only" are now terminal for the per-document part (IRREDUCIBLE: both
  tested in-task deletions make T_oracle slower). The per-process part stays UNDECIDED because the primary estimator
  and the fallback estimator both fail the pre-registered P1 negative control. Per the pre-registered mapping
  this is not carried over from B-03 or R2-10, and the whole of R2-10's own cold excess counts as UNTESTED.
- R2-10's browser untested shares are **lower bounds** for fill and toggle (scripted and live). With R2-10's
  own cold excess E_R counted as untested, fill and toggle are well above 5%. That share is not closed by this
  lane. The pre-registered mapping does not allow the descriptive split of the gate-failed estimator, which
  would give 31.2% / 28.7% scripted.
- No product change and no knob is proposed, so nothing is DELETED. Browser process reuse or a warm pool
  remains an owner policy question. This lane does not size it with a valid estimator.

Evidence classes:
- BENCHMARK+REAL (FIXTURE): every row measured here (blocks m and x).
- SOURCE: mechanism notes.
- Live rows: BENCHMARK re-analysis of R2-10 LIVE_PROVIDER raw @ 030f6bdbf. No new provider run, so a new
  live trial is NOT_RUN (TypeSafe: 0 attempts, 0 reached).
- Every results table below carries a class column.

## Provenance

| item | value | class |
|---|---|---|
| tested source | `8f3a646b4818b757648835cf89db8886626b1cf0` (R2-10 source head = 989cc76ce + R2-10 PREREG source.steps 1-8) | SOURCE |
| Driver binary | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9`, `cua-driver 0.32.0` (read inside `cua-x11-session.sh`). Re-hashed at the start (02:44:16Z) and the end (03:26:04Z): identical. Not rebuilt. sha256 recorded in every trial record and manifest | REAL |
| browser | Driver-chosen system Chrome (`chrome` executable basename in 655/655 records), Google Chrome 151.0.7922.71 (read in session at start and end), `browser_prepare {allow_launch, isolated_new}`, sandbox on, fresh profile per trial | REAL |
| branch / PREREG | `exp/b-04-observation-reconcile-a2-20261003`; PREREG.json committed in `0683e57ec` at 02:49:10Z, before the first measured trial (02:50:48Z) | SOURCE |
| R2-10 inputs | accepted packet `030f6bdbf` (exp/r2-10-composition-20261002): r2-10-summary.json COMP rows, scripted/live raw tarballs (re-analysis only) | BENCHMARK |
| harness | B-03 `run_b03.py` @ b34eef71e, B-02 `run_critpath.py`/`run_b02.py`/fixtures @ b282ff389, R2-07 `compiled_routine.py` and the R2-10 scripted COMP routine @ 030f6bdbf, all blob-identical copies in `harness/`; R2-10's `Sampler` oracle logic in `run_b04.py` | SOURCE |
| upstream main, start | `41c34cb0d704d816e612dd3f9d0c816cdfacf178` (libs/cua-driver tree df2b49c3), gh read 02:40Z | SOURCE |
| upstream main, end | `41c34cb0d704d816e612dd3f9d0c816cdfacf178`, unchanged (gh read 03:28Z) | SOURCE |
| live PR heads | trycua/cua PR 4316 `a0bca7440` open (start = end); kvnloo/cua#106 `c45845797` open (start = end) | SOURCE |
| P4X block (fix round) | binary re-hashed and version read in session before (03:44:29Z) and after (03:55:12Z) block x: identical (`raw/logs/versions-p4x-*.log`). Live heads re-read at 03:44Z and 03:55Z: upstream main `41c34cb0d`, trycua/cua PR 4316 `a0bca7440`, kvnloo/cua#106 `c45845797`, all unchanged | REAL / SOURCE |
| drift | 989cc76ce..41c34cb0d: 11 commits, 8 files under libs/cua-driver (incl. cua-driver-core `snapshot_store.rs`, trycua/cua PR 4375), none under `cua-driver-core/src/browser/`. All numbers here are for binary R only | SOURCE |
| publication SHA | set by Publish | — |

## Method

- **Forced path.** Configuration = R2-10 COMP, scripted chooser. The settings are feedback off, focus settle 0
  on fill, 10 ms completion poll with a 2.0 s deadline, caller-compiled output validators,
  `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`, guarded completion and compiled replay on fill (R2-10's scripted
  COMP artifact), and R2-10's step loop on toggle/modal. Every trial uses a fresh `cua-driver mcp`, a fresh
  Driver-launched Chrome, fresh fixture servers and a fresh token. The Driver phase trace is on in every
  trial. Telemetry is off.
- **Route / producer (receipts).** Fill uses `trusted_input` typing then `dom` submit. Toggle and modal use
  `dom`, `dom`. Route is required in every valid trial: 655/655. Fill route `compiled` holds in every COMP
  fill cell. COMP forced path: admission-cache env plus at least one `mcp.inner_validation_skipped` mark.
  DEFAULT has no `CUA_DRIVER_EXP_*` and 0 skip marks.
- **Oracle (target-owned, independent).** A harness thread re-reads the jev-use fixture server state every
  2 ms: fill `submitted == token`; toggle `checked`. The server's CLOCK_MONOTONIC journal must show exactly one
  completion mutation. T_oracle (caller-side rule, R2-10) = the first expected-state sample at/after the
  caller-side return of the last accepted mutation, minus task_start. task_start is the return of the task
  `browser_navigate`.
- **Estimators (Driver trace marks).** Span = first `snap.enter` → first `snap.serialized` inside the call
  window.
  - Primary E_span = span(snapshot1) − span(resnap1), where resnap1 is the same semantic_v2 call sent again
    right after snapshot1 returns.
  - Fallback E_walk = the same difference over walk-only marks, which excludes every CDP round trip.
- **Probes** (rounds 0-29; AB/BA order flips with round parity; P4 see below and Deviation 7):
  - P1: negative control. Cold process, same document, first observation at D = 80 / 160 ms after navigate
    returns. 30 per D per class.
  - P2: cold vs warm process at D0. The warm process first loads a matched-content sibling page from the same
    fixture origin (same DOM structure and roles, different text and tokens), snapshots it once, then
    navigates to the task page. 30 AB/BA pairs per class; modal as a consistency check.
  - P3: in a warm process, a new document vs a re-snapshot of the same document at D0. 30 pairs per class.
  - P4: W0 / W80 / PREWARM. PREWARM counts the warm-up inside T. 30 rounds per class.
    - Block m (the measured rounds) was meant to be Williams order but was not. The PREREG formula picks row
      (r + 3k) mod 6, where k is the class's position in a round order that flips with parity. So fill only
      got rows {0, 2, 4} and toggle only rows {1, 3, 5}. Neither is a Latin square. Within each class, W80
      vs W0 had a fixed order: fill ran W0 first in 30/30 rounds, toggle ran W80 first in 30/30.
    - Block x (extension, disclosed, after the data): 180 more P4 trials in true Williams order. k is a
      fixed class index, so each class runs all 6 rows of `williams_any(3)` 5 times. Each arm sits 10
      times in each position, and each ordered arm pair appears 15/30.
    - The per-document verdict needs the PREREG rule to hold in block m and in block x.
  - POS: a 20 ms server-side delay on the first task-document response, mode `tail` (all bytes but the last,
    then the delay). 10 pairs per class.
  - SMOKE: product-default configuration on R. 5 per class.
- **Statistics.** Percentile bootstrap, 10 000 resamples, `random.Random(20261003)`, 95% CI. Paired contrasts
  use rounds where both trials are valid.

## Results (655 of 655 measured trials valid, plus 180 of 180 in P4X block x; BENCHMARK+REAL (FIXTURE))

Cell validity was 100% in every cell (`b04-summary.json` `validity`, `P4X`). E4 was 0 in both blocks: stale
dispatches, duplicate mutations, unverified successes, refusals, fallbacks, non-loopback connects and oracle
reverts. 1-minute loadavg at trial start was min 3.01, median 7.31, max 19.97 in block m, and min 8.39,
median 11.0, max 17.9 in block x. Every trial was kept.

### Controls

**P1 negative control: FAILED for both estimators in both classes.** The gate was |mean| < 1.0 ms with a 95%
CI including 0.

| estimator / class | D80 mean [CI] | D160 mean [CI] | gate | class |
|---|---|---|---|---|
| E_span fill | 6.3 [4.3, 8.9] | 5.1 [3.9, 6.8] | fail (mean ≥ 1, CI excludes 0) | BENCHMARK+REAL (FIXTURE) |
| E_span toggle | 1.2 [0.7, 1.8] | 1.9 [0.9, 3.6] | fail | BENCHMARK+REAL (FIXTURE) |
| E_walk fill | 0.06 [0.03, 0.08] | 0.09 [0.04, 0.18] | fail (CI excludes 0) | BENCHMARK+REAL (FIXTURE) |
| E_walk toggle | 0.04 [0.02, 0.06] | 0.03 [0.02, 0.05] | fail (CI excludes 0) | BENCHMARK+REAL (FIXTURE) |

Mechanism (BENCHMARK, descriptive): the E_span excess that remains after readiness sits mostly in the
`Accessibility` tree fetch, about 4.7 / 4.5 ms of fill's D80 / D160 excess and 0.6 / 0.7 ms of toggle's. The
first AX query of a document costs more than a repeat, even 160 ms after navigation. So the
"same-document re-snapshot" baseline is not a zero-excess baseline for the first observation. E_walk fails
by a tiny but consistent positive bias (≤ 0.1 ms).

**Positive control: FAILED for both estimators** (gate: excess(inject20) − excess(inject0) > 0 in 10/10 pairs
and the CI of the median excludes 0). The injection fired in 10/10 trials per class and ended 17.5 / 18.0 ms
(median, fill / toggle) after `browser_navigate` returned.

| estimator / class | pairs with delta > 0 | median delta [CI] | literal reading: mean excess(inject20) | class |
|---|---|---|---|---|
| E_span fill | 5 / 10 | 1.3 [-1.5, 19.0] | 30.1 (10/10 > 0) | BENCHMARK+REAL (FIXTURE) |
| E_span toggle | 6 / 10 | 1.3 [-7.2, 6.5] | 14.2 (10/10 > 0) | BENCHMARK+REAL (FIXTURE) |
| E_walk fill | 7 / 10 | 0.03 [-0.03, 0.05] | 0.14 | BENCHMARK+REAL (FIXTURE) |
| E_walk toggle | 3 / 10 | -0.01 [-0.07, 0.00] | 0.03 | BENCHMARK+REAL (FIXTURE) |

The delayed last byte does not make the first snapshot wait. Page.navigate returns at commit (SOURCE:
`browser_navigate` in cua-driver-core `browser/tools.rs`), and the snapshot reads the DOM already parsed. So
sensitivity to a server-side delay is not shown. The literal reading cannot fail at cold D0, so it is
reported but is not the gate.

**Default-config smoke on R:** 5/5 fill, 5/5 toggle, 5/5 modal valid (no `CUA_DRIVER_EXP_*`, 0 skip marks).

### Per-process contrast (P2) and per-document contrast (P3), E_span (gate-failed: descriptive only)

| class | cold excess (mean) | warm excess (mean) | P2 contrast median [CI] (mean) | P3 new − same doc median [CI] (mean) | same-doc excess (mean) | evidence class |
|---|---|---|---|---|---|---|
| fill | 24.8 | 8.2 | 12.9 [11.1, 19.0] (16.7) | 6.6 [5.7, 7.6] (8.6) | 0.5 | BENCHMARK+REAL (FIXTURE), descriptive |
| toggle | 16.2 | 8.0 | 7.9 [5.1, 10.4] (8.2) | 4.5 [3.8, 5.7] (6.1) | -0.0 | BENCHMARK+REAL (FIXTURE), descriptive |
| modal | 13.8 | 5.5 | 5.7 [3.8, 8.3] (8.3) | — | — | BENCHMARK+REAL (FIXTURE), descriptive |

E_walk P2 contrasts are 0.08 [0.04, 0.11] (fill), 0.05 [-0.00, 0.08] (toggle) and 0.03 [0.02, 0.04] (modal) ms.
The walk estimator cannot see where the excess lives (CDP round trips).

Component split of the cold excess (snapshot1 − resnap1, mean ms, P2 cold) was:
- fill: DOM.getDocument 13.8, session attach 3.2, AX tree 5.5;
- toggle: DOM.getDocument 9.1, attach 4.1, AX tree 1.0.

These match B-03's split on the B-02 binary, but they are not combined with it.

Had E_span passed P1, its P2 contrast (≥ 1 ms, CI excluding 0) would have mapped to OWNER_DECISION in both
classes. It did not pass, so the pre-registered verdict is UNDECIDED.

### T_oracle rule (P4), median ms; paired difference vs W0, median [CI]

Block m (measured rounds; fixed W80/W0 order per class, Deviation 7):

| class | W0 | W80 | PREWARM (warm-up inside T) | W80 − W0 | PREWARM − W0 | PREWARM − W0 excluding warm-up | warm-up (median) | evidence class |
|---|---|---|---|---|---|---|---|---|
| fill | 74.2 | 136.1 | 121.0 | 64.0 [58.1, 66.9] | 44.7 [31.3, 57.4] | -12.0 [-17.0, -10.0] | 60.5 | BENCHMARK+REAL (FIXTURE); the two right-hand columns are descriptive |
| toggle | 61.3 | 124.3 | 112.5 | 64.0 [61.8, 69.1] | 37.3 [27.7, 65.6] | -8.1 [-11.8, -6.0] | 50.3 | same |

Block x (P4X extension, true Williams order: every class ran all 6 rows 5 times; W0 before W80 in 15/30
rounds and W0 before PREWARM in 15/30, per class; 180/180 valid):

| class | W0 | W80 | PREWARM (warm-up inside T) | W80 − W0 | PREWARM − W0 | evidence class |
|---|---|---|---|---|---|---|
| fill | 111.1 | 174.1 | 169.6 | 57.9 [48.0, 65.0] | 48.2 [44.2, 56.3] | BENCHMARK+REAL (FIXTURE) |
| toggle | 99.4 | 147.3 | 151.1 | 56.6 [40.5, 64.0] | 53.8 [42.3, 68.6] | BENCHMARK+REAL (FIXTURE) |

Order sensitivity, paired difference vs W0 split by which arm ran first, median [CI] (n). This is
descriptive and was added after the data:

| class / contrast | block m: deletion arm first | block m: W0 first | block x: deletion arm first | block x: W0 first | evidence class |
|---|---|---|---|---|---|
| fill W80 − W0 | — (0) | 64.0 (30) | 58.0 [39.9, 72.5] (15) | 56.0 [42.0, 71.9] (15) | BENCHMARK+REAL (FIXTURE), descriptive |
| fill PREWARM − W0 | 57.3 (10) | 37.0 (20) | 52.6 [45.0, 76.4] (15) | 46.3 [30.3, 97.1] (15) | same |
| toggle W80 − W0 | 64.0 (30) | — (0) | 58.8 [37.6, 70.0] (15) | 54.5 [24.0, 63.8] (15) | same |
| toggle PREWARM − W0 | 36.6 (20) | 37.8 (10) | 43.6 [38.8, 67.4] (15) | 65.6 [52.6, 83.7] (15) | same |

In both blocks and both classes, both deletions increase median T_oracle with the CI excluding 0. So the
per-document part is IRREDUCIBLE, in the sense of Deviation 9. The W80 penalty does not depend on order in
block x: the two order halves overlap and are 54-59 ms each. Block m's fixed order therefore did not create
the verdict.

Block x's absolute T values are higher than block m's: W0 is 111.1 vs 74.2 ms for fill. Block x ran about
about 24 min after block m ended, at a higher host load (loadavg median 11.0 vs 7.3). Absolute T is not compared across the two
blocks; only the within-block paired contrasts are used.

A warm process does shorten T itself, by 12.0 / 8.1 ms (block m). The warm-up that buys it costs more than it
saves when it sits inside T. Outside T (a warm pool kept by the product) it would be a policy choice for the
owner. That is not measured as a product here.

### Updated R2-10 E2 observation rows on R

E_R = R2-10's own cold excess, span(snapshot1) − span(snapshot2), mean [CI] over R2-10's COMP trials
(BENCHMARK re-analysis of R2-10 raw, `raw/r210-observation-rows.json`). Headline u = 1 (no valid estimator),
so the whole E_R counts as UNTESTED.

| R2-10 COMP row | mean T | observation (R2-10) | E_R | base observation (IRREDUCIBLE) | E_R verdict | untested share R2-10 → now | descriptive split (gate-failed) | evidence class |
|---|---|---|---|---|---|---|---|---|
| scripted fill | 79.6 | 26.2 | 19.1 [18.1, 20.0] | 7.1 | per-document IRREDUCIBLE, per-process UNDECIDED, size untested | 15.2% → 39.1% | 31.2% | BENCHMARK re-analysis of R2-10 SCRIPTED raw @ 030f6bdbf (fixture) + this lane's FIXTURE BENCHMARK verdicts |
| scripted toggle | 54.8 | 16.0 | 10.7 [9.9, 11.8] | 5.3 | same | 16.4% → 36.0% | 28.7% | BENCHMARK re-analysis of R2-10 SCRIPTED raw @ 030f6bdbf (fixture) + this lane's FIXTURE BENCHMARK verdicts |
| scripted modal | 54.2 | 15.7 | 10.0 [9.2, 10.9] | 5.7 | unchanged (B-02 H_W IRREDUCIBLE) | 16.4% → 16.4% | — | BENCHMARK re-analysis of R2-10 SCRIPTED raw @ 030f6bdbf (fixture) + this lane's FIXTURE BENCHMARK verdicts |
| live fill | 94.0 | 29.0 | 21.2 [19.5, 22.9] | 7.8 | as scripted fill | 14.0% → 36.5% | 29.1% | BENCHMARK re-analysis of R2-10 LIVE_PROVIDER raw @ 030f6bdbf; no new provider run (NOT_RUN) |
| live toggle | 492.5 | 17.2 | 11.6 [10.3, 13.1] | 5.6 | as scripted toggle | 90.4% → 92.7% | 91.8% | BENCHMARK re-analysis of R2-10 LIVE_PROVIDER raw @ 030f6bdbf; no new provider run (NOT_RUN) |
| live modal | 519.6 | 17.3 | 11.7 [10.4, 13.1] | 5.5 | unchanged | 90.9% → 90.9% | — | BENCHMARK re-analysis of R2-10 LIVE_PROVIDER raw @ 030f6bdbf; no new provider run (NOT_RUN) |

Live rows are re-weighted from R2-10's accepted LIVE_PROVIDER raw (BENCHMARK re-analysis). No live trial was run here (NOT_RUN, provider cap 0).
The descriptive split (67.1% of fill's and 62.4% of toggle's cold excess left untested) uses the gate-failed
E_span split and is shown only so the owner can see the range. It is not the verdict.

## Work deleted vs wall-clock saved

No work is deleted: no product change, no knob. Wall-clock is reported separately:
- W80 costs 64.0 ms of T in both classes in block m, and 57.9 / 56.6 ms in Williams block x;
- PREWARM saves 12.0 / 8.1 ms inside the task but adds 60.5 / 50.3 ms of warm-up, a net 44.7 / 37.3 ms
  slower in block m, and 48.2 / 53.8 ms slower in block x.

## Deviations (disclosed)

1. **Aborted attempt 1.** No commit. Its uncommitted harness was reviewed and copied (the harness/ copies were
   re-verified blob-for-blob). Its pilots (13 + 18 trials) and shakedown (54 trials) are excluded. Attempt 2
   ran one 27-trial pilot (measured-plan round 0, SHARED lock, ledger label `b04a2-pilot-r00`, all valid,
   excluded; `raw/pilot-trials.tar.gz`). It ran `run_b04.py` before the `--block` CLI option was added (the
   only edit between the pilot and the PREREG commit). The pilot set no gate, threshold or rule.
2. **POS and SMOKE ran under the EXCLUSIVE lock.** They are interleaved in the measured rounds. The lane spec
   allows SHARED for them, so this is stronger isolation. No number in this packet was measured under a
   SHARED lock.
3. **Analyzer written during and after the data.** `analyze_b04.py`, `make_headlines.py` and
   `verify_artifacts.py` implement PREREG.json, which was committed before them. A draft analyzer ran once
   between chunks (see Deviation 8); the final versions were written after the measured chunks.
   - After the first analyzer run, the secondary T_land row was aligned to the PREREG text (warm-up added for
     PREWARM).
   - Rows added post hoc and labelled descriptive: PREWARM − W0 excluding warm-up, the P1 component split, and
     the descriptive-split shares.
   - No gate or verdict depends on them.
4. **Gate readings that go beyond the spec wording.** These are pre-registered by attempt 1 and kept.
   - The positive control is read as a paired delta (inject20 − inject0); the literal reading is reported.
   - NOT_MATERIAL would also have needed a passed positive control.
   - Neither changed a verdict: P1 failed first.
5. **E_R definition.** E_R uses R2-10's snapshot2 (post-first-action re-snapshot, the B-02/B-03 definition)
   because R2-10 has no resnap1.
6. **Load.** The machine was shared (parallel tracks' builds). The EXCLUSIVE quiet lock excludes other timing
   lanes but not builds. Loadavg is recorded per trial (median 7.31, max 19.97). Chunks 2 and 3 waited about 8 / 7
   min for the lock.
7. **P4 order defect and the Williams extension block x.** Found by the fresh verifier after the packet was
   committed (Method, P4). The defect is in the PREREG's own row formula, not in the runner's reading of it.
   PREREG.json is not edited. Two fixes were made:
   - Disclosure plus order-sensitivity rows for block m: `P4_block_m_order` in `b04-summary.json`, computed
     by `analyze_b04.py` `p4_block()`.
   - A new P4-only block x of 180 trials (`run_b04.py --plan p4x`, `p4x_round_trials()`), run in true
     Williams order under one EXCLUSIVE `bin/quiet-timed` acquisition. Same binary R, same harness, same
     T_oracle rule.
   Block x was decided after the block-m data had been seen. It is an extension, not a replacement: block m
   is kept and still counts. The verdict rule is "IRREDUCIBLE iff the PREREG rule holds in both blocks". That
   rule is stricter than either block alone, so the extension cannot turn a failed rule into a pass.
8. **Interim look.** At 03:12:43Z a draft analyzer computed the gates on the first 455 of 655 trials
   (rounds 0-19). That was after chunk 2 ended (03:12:07Z) and before chunk 3 started (03:19:23Z). The lane
   temp file `interim.json` holds it; it is not in the packet. It changed nothing: chunk 3 ran the
   pre-planned rounds 20-29 with the unchanged `run_b04.py`, and no gate, threshold, rule or stopping
   decision was set or moved.
9. **Reading of the verdict rules.** PREREG maps the per-document part from T_oracle alone (P4). The P1
   fallback clause ("if that also fails P1, the verdict is UNDECIDED") is read as covering the
   estimator-based part, which is the per-process P2 contrast. This reading was pre-registered before the
   data, and the accounting stays conservative (u = 1). In PREWARM, T includes a cold sibling navigate that
   W0's T does not. So IRREDUCIBLE here means "cannot be deleted by an in-task wait or an in-task prewarm".
   It is not a ruling on a warm pool kept outside T, which stays UNDECIDED and is an owner policy question.

## Limits and claim boundary

One host, private Xvfb (`cua-x11-session.sh` under hostless), Driver-chosen system Chrome 151.0.7922.71,
binary R `12b9045a`, tested source `8f3a646b4`, scripted chooser, telemetry off, TypeSafe not used. The fixture
is jev-use (fill → submit, toggle → confirm, modal as a check). The per-process part is UNDECIDED, not
NOT_MATERIAL. Nothing here says a warm pool is or is not worth it. No number is added to or ratioed with
B-02/B-03 numbers (binary 7e6c0609). No product change; no new service; instrumentation is the existing
env-gated phase trace. Upstream main moved 989cc76ce → 41c34cb0d with no change under the browser snapshot
path. The native `snapshot_store.rs` change (trycua/cua PR 4375) is outside this claim. "IRREDUCIBLE" for the
per-document part means not deletable by an in-task wait or an in-task prewarm (Deviation 9). Absolute T is
not compared between P4 blocks m and x (different time and load).

## Locks, isolation, near misses

- Locks (`raw/lock-ledger.jsonl`, verbatim ledger lines):
  - `b04a2-pilot-r00` SHARED, 02:45:26-02:46:24Z;
  - `b04a2-measured-r00-10` EXCLUSIVE, 02:50:41-02:58:30Z;
  - `b04a2-measured-r10-20` EXCLUSIVE, 03:06:59-03:12:07Z;
  - `b04a2-measured-r20-30` EXCLUSIVE, 03:19:23-03:25:52Z;
  - `b04a2-p4x-williams-r00-30` EXCLUSIVE, 03:49:24-03:54:52Z (block x, one acquisition of 5.5 min).
  - Each measured and P4X manifest lies inside its window.
- Every code-executing command ran under `hostless` (one near miss below). Every Driver/Chrome run was inside `cua-x11-session.sh`
  with `CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1`, and the logs show `wayland=unset`.
- Hostless evidence. `cua-x11-session.sh` starts from `env -i`, so the block-m logs cannot show the hostless
  marker. For block x and its version reads, `run-p4x.sh` refuses to start without `CUA_HOSTLESS=1` and passes
  it in as `B04_HOSTLESS`. The session line in `raw/logs/p4x-williams-r00-30.log` and
  `raw/logs/versions-p4x-*.log`, and the P4X manifest, record `hostless=1` (verifier check 12). For block m,
  the recorded evidence is indirect: private displays, a private dbus, `wayland=unset`, and the runner's
  refusal of WAYLAND_DISPLAY/HYPRLAND_*.
- The plain shell was used only for git, gh reads, file reads and edits, and `ps` / `/proc/locks` (read-only).
- Hard-rule breaches: none.
- Near misses: one, in the fix round. A `python3` with an empty here-doc program was started from the plain
  shell, not under hostless, while choosing an edit method. It executed no code and opened no display, bus
  or socket, so it could not have had an effect. Every later Python ran under hostless.
- TypeSafe: 0 attempts, 0 reached.

## Files

| file | what |
|---|---|
| `PREREG.json` | pre-registration (committed in 0683e57ec before the first measured trial) |
| `run_b04.py` | runner (measurement only); `--plan p4x` = P4 Williams extension block x, added after the data |
| `b04_rows.py` | per-trial extraction (estimators, T_oracle, validity) |
| `analyze_b04.py` | statistics, gates, verdicts, accounting → `b04-summary.json`; `p4_block()` = P4 order sensitivity (block m) and block x |
| `r210_observation.py` | R2-10 own cold excess from R2-10 raw → `raw/r210-observation-rows.json` |
| `make_headlines.py` | `headline-numbers.json` |
| `verify_artifacts.py` | packet verifier (passes from a clean clone) |
| `b04-summary.json` | all results |
| `headline-numbers.json` | every quoted number with its source path |
| `provenance.json` | SHAs, binary, browser, heads, environment, raw sha256 |
| `.gitignore` | re-includes `*.log` (repo rule) for the scrubbed session logs |
| `harness/run_b03.py` | B-03 runner, verbatim |
| `harness/run_critpath.py` | B-02, verbatim |
| `harness/run_b02.py` | B-02, verbatim |
| `harness/cdp_raw.py` | B-02, verbatim |
| `harness/b01_fixtures.py` | B-02, verbatim |
| `harness/b01_tasks.py` | B-02, verbatim |
| `harness/compiled_routine.py` | R2-07 via R2-10, verbatim |
| `harness/r2-10-scripted-COMP-routine.json` | R2-10 scripted COMP routine, verbatim |
| `lane-scripts/in-session.sh` | session entry (sanitized copy) |
| `lane-scripts/run-chunk.sh` | one measured chunk under quiet-timed (sanitized copy) |
| `lane-scripts/shared-locked.sh` | SHARED-lock wrapper with ledger receipt (sanitized copy) |
| `lane-scripts/package_raw.py` | deterministic packaging and log scrubbing |
| `raw/measured-trials.tar.gz` | 655 trial records + Driver traces |
| `raw/measured/run-manifest-measured-m-r00-10.json` | chunk manifest |
| `raw/measured/run-manifest-measured-m-r10-20.json` | chunk manifest |
| `raw/measured/run-manifest-measured-m-r20-30.json` | chunk manifest |
| `raw/pilot-trials.tar.gz` | attempt-2 pilot (excluded) |
| `raw/pilot/run-manifest-pilot-r00-01.json` | pilot manifest |
| `raw/lock-ledger.jsonl` | quiet-lane ledger lines of this lane |
| `raw/r210-comp-rows.json` | R2-10 COMP E2 rows @ 030f6bdbf |
| `raw/r210-observation-rows.json` | R2-10 own cold excess per trial |
| `raw/logs/versions-start.log` | version + sha256 in session (start) |
| `raw/logs/versions-end.log` | version + sha256 in session (end) |
| `raw/logs/pilot-r00.log` | pilot session log |
| `raw/logs/measured-r00-10.log` | chunk session log |
| `raw/logs/measured-r10-20.log` | chunk session log |
| `raw/logs/measured-r20-30.log` | chunk session log |
| `lane-scripts/run-p4x.sh` | P4X Williams extension block under quiet-timed, refuses outside hostless (sanitized copy) |
| `raw/p4x-trials.tar.gz` | P4X block x: 180 trial records + Driver traces |
| `raw/p4x/run-manifest-p4x-x-r00-30.json` | P4X manifest (records hostless=1) |
| `raw/logs/p4x-williams-r00-30.log` | P4X session log |
| `raw/logs/versions-p4x-start.log` | version + sha256 in session before block x |
| `raw/logs/versions-p4x-end.log` | version + sha256 in session after block x |

Raw outputs are mirrored to `artifacts/r2/B-04/attempt-2/` in the lane workspace.
