# B-04: browser cold-first-snapshot reconciliation on R2-10's binary R (wave 4, attempt 2)

Owners: kvnloo/cua#93 (experiment spec, invariants), kvnloo/cua#10 (whole-task accounting).
Advances E1 (B-03 left toggle H_W UNDECIDED and fill's "moved only" verdict provisional) and E2
(R2-10 labelled its observation component IRREDUCIBLE by carry-over: 15.7-29.0 ms, 29-33% of COMP T).

## Disposition

**REVISE.** R2-10's browser observation row is replaced by a measured row on R2-10's own binary R. Fill and
toggle are decided together by the same pre-registered rules in the same block:

| class | per-document part | per-process part | headline untested share (R2-10 → this lane), scripted / live |
|---|---|---|---|
| fill | **IRREDUCIBLE** (W80 +64.0 ms [58.1, 66.9], PREWARM +44.7 ms [31.3, 57.4]) | **UNDECIDED** (no estimator passed the P1 negative control) | 15.2% → 39.1% / 14.0% → 36.5% |
| toggle | **IRREDUCIBLE** (W80 +64.0 ms [61.8, 69.1], PREWARM +37.3 ms [27.7, 65.6]) | **UNDECIDED** (same) | 16.4% → 36.0% / 90.4% → 92.7% |
| modal | consistency check only (R2-10 / B-02 row unchanged) | P2 contrast 5.7 ms [3.8, 8.3] (gate-failed estimator) | 16.4% / 90.9% unchanged |

- B-03's toggle H_W and B-02's fill "moved only" are now terminal for the per-document part (IRREDUCIBLE: both
  tested deletions make T_oracle slower). The per-process part stays UNDECIDED because the primary estimator
  and the fallback estimator both fail the pre-registered P1 negative control. Per the pre-registered mapping
  this is not carried over from B-03 or R2-10, and the whole of R2-10's own cold excess counts as UNTESTED.
- R2-10's browser untested shares are **lower bounds** for fill and toggle (scripted and live). With R2-10's
  own cold excess E_R counted as untested, fill and toggle are well above 5%. That share is not closed by this
  lane. The pre-registered mapping does not allow the descriptive split of the gate-failed estimator, which
  would give 31.2% / 28.7% scripted.
- No product change and no knob is proposed, so nothing is DELETED. Browser process reuse or a warm pool
  remains an owner policy question. This lane does not size it with a valid estimator.

Evidence: BENCHMARK+REAL (FIXTURE) for every measured row, SOURCE for mechanism notes, NOT_RUN for live
provider rows (TypeSafe: 0 attempts, 0 reached; live R2-10 rows are re-weighted from R2-10's raw, not re-run).

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
- **Probes** (rounds 0-29; AB/BA order flips with round parity; P4 in Williams rows):
  - P1: negative control. Cold process, same document, first observation at D = 80 / 160 ms after navigate
    returns. 30 per D per class.
  - P2: cold vs warm process at D0. The warm process first loads a matched-content sibling page from the same
    fixture origin (same DOM structure and roles, different text and tokens), snapshots it once, then
    navigates to the task page. 30 AB/BA pairs per class; modal as a consistency check.
  - P3: in a warm process, a new document vs a re-snapshot of the same document at D0. 30 pairs per class.
  - P4: W0 / W80 / PREWARM. PREWARM counts the warm-up inside T. 30 Williams rounds per class.
  - POS: a 20 ms server-side delay on the first task-document response, mode `tail` (all bytes but the last,
    then the delay). 10 pairs per class.
  - SMOKE: product-default configuration on R. 5 per class.
- **Statistics.** Percentile bootstrap, 10 000 resamples, `random.Random(20261003)`, 95% CI. Paired contrasts
  use rounds where both trials are valid.

## Results (655 of 655 measured trials valid; BENCHMARK+REAL (FIXTURE))

Cell validity was 100% in every cell (`b04-summary.json` `validity`). E4: 0 stale dispatches, 0 duplicate
mutations, 0 unverified successes, 0 refusals, 0 fallbacks, 0 non-loopback connects, and 0 oracle reverts.
1-minute loadavg at trial start was min 3.01, median 7.31, max 19.97. Every trial was kept.

### Controls

**P1 negative control: FAILED for both estimators in both classes.** The gate was |mean| < 1.0 ms with a 95%
CI including 0.

| estimator / class | D80 mean [CI] | D160 mean [CI] | gate |
|---|---|---|---|
| E_span fill | 6.3 [4.3, 8.9] | 5.1 [3.9, 6.8] | fail (mean ≥ 1, CI excludes 0) |
| E_span toggle | 1.2 [0.7, 1.8] | 1.9 [0.9, 3.6] | fail |
| E_walk fill | 0.06 [0.03, 0.08] | 0.09 [0.04, 0.18] | fail (CI excludes 0) |
| E_walk toggle | 0.04 [0.02, 0.06] | 0.03 [0.02, 0.05] | fail (CI excludes 0) |

Mechanism (BENCHMARK, descriptive): the E_span excess that remains after readiness sits mostly in the
`Accessibility` tree fetch, about 4.7 / 4.5 ms of fill's D80 / D160 excess and 0.6 / 0.7 ms of toggle's. The
first AX query of a document costs more than a repeat, even 160 ms after navigation. So the
"same-document re-snapshot" baseline is not a zero-excess baseline for the first observation. E_walk fails
by a tiny but consistent positive bias (≤ 0.1 ms).

**Positive control: FAILED for both estimators** (gate: excess(inject20) − excess(inject0) > 0 in 10/10 pairs
and the CI of the median excludes 0). The injection fired in 10/10 trials per class and ended 17.5 / 18.0 ms
(median, fill / toggle) after `browser_navigate` returned.

| estimator / class | pairs with delta > 0 | median delta [CI] | literal reading: mean excess(inject20) |
|---|---|---|---|
| E_span fill | 5 / 10 | 1.3 [-1.5, 19.0] | 30.1 (10/10 > 0) |
| E_span toggle | 6 / 10 | 1.3 [-7.2, 6.5] | 14.2 (10/10 > 0) |
| E_walk fill | 7 / 10 | 0.03 [-0.03, 0.05] | 0.14 |
| E_walk toggle | 3 / 10 | -0.01 [-0.07, 0.00] | 0.03 |

The delayed last byte does not make the first snapshot wait. Page.navigate returns at commit (SOURCE:
`browser_navigate` in cua-driver-core `browser/tools.rs`), and the snapshot reads the DOM already parsed. So
sensitivity to a server-side delay is not shown. The literal reading cannot fail at cold D0, so it is
reported but is not the gate.

**Default-config smoke on R:** 5/5 fill, 5/5 toggle, 5/5 modal valid (no `CUA_DRIVER_EXP_*`, 0 skip marks).

### Per-process contrast (P2) and per-document contrast (P3), E_span (gate-failed: descriptive only)

| class | cold excess (mean) | warm excess (mean) | P2 contrast median [CI] (mean) | P3 new − same doc median [CI] (mean) | same-doc excess (mean) |
|---|---|---|---|---|---|
| fill | 24.8 | 8.2 | 12.9 [11.1, 19.0] (16.7) | 6.6 [5.7, 7.6] (8.6) | 0.5 |
| toggle | 16.2 | 8.0 | 7.9 [5.1, 10.4] (8.2) | 4.5 [3.8, 5.7] (6.1) | -0.0 |
| modal | 13.8 | 5.5 | 5.7 [3.8, 8.3] (8.3) | — | — |

E_walk P2 contrasts are 0.08 [0.04, 0.11] (fill), 0.05 [-0.00, 0.08] (toggle) and 0.03 [0.02, 0.04] (modal) ms.
The walk estimator cannot see where the excess lives (CDP round trips).

Component split of the cold excess (snapshot1 − resnap1, mean ms, P2 cold) was:
- fill: DOM.getDocument 13.8, session attach 3.2, AX tree 5.5;
- toggle: DOM.getDocument 9.1, attach 4.1, AX tree 1.0.

These match B-03's split on the B-02 binary, but they are not combined with it.

Had E_span passed P1, its P2 contrast (≥ 1 ms, CI excluding 0) would have mapped to OWNER_DECISION in both
classes. It did not pass, so the pre-registered verdict is UNDECIDED.

### T_oracle rule (P4), median ms; paired difference vs W0, median [CI]

| class | W0 | W80 | PREWARM (warm-up inside T) | W80 − W0 | PREWARM − W0 | PREWARM − W0 excluding warm-up | warm-up (median) |
|---|---|---|---|---|---|---|---|
| fill | 74.2 | 136.1 | 121.0 | 64.0 [58.1, 66.9] | 44.7 [31.3, 57.4] | -12.0 [-17.0, -10.0] | 60.5 |
| toggle | 61.3 | 124.3 | 112.5 | 64.0 [61.8, 69.1] | 37.3 [27.7, 65.6] | -8.1 [-11.8, -6.0] | 50.3 |

Both deletions increase median T_oracle with the CI excluding 0 in both classes, so per-document =
IRREDUCIBLE. A warm process does shorten T itself, by 12.0 / 8.1 ms. The warm-up that buys it costs more
than it saves when it sits inside T. Outside T (a warm pool kept by the product) it would be a policy choice
for the owner. That is not measured as a product here.

### Updated R2-10 E2 observation rows on R

E_R = R2-10's own cold excess, span(snapshot1) − span(snapshot2), mean [CI] over R2-10's COMP trials
(BENCHMARK re-analysis of R2-10 raw, `raw/r210-observation-rows.json`). Headline u = 1 (no valid estimator),
so the whole E_R counts as UNTESTED.

| R2-10 COMP row | mean T | observation (R2-10) | E_R | base observation (IRREDUCIBLE) | E_R verdict | untested share R2-10 → now | descriptive split (gate-failed) |
|---|---|---|---|---|---|---|---|
| scripted fill | 79.6 | 26.2 | 19.1 [18.1, 20.0] | 7.1 | per-document IRREDUCIBLE, per-process UNDECIDED, size untested | 15.2% → 39.1% | 31.2% |
| scripted toggle | 54.8 | 16.0 | 10.7 [9.9, 11.8] | 5.3 | same | 16.4% → 36.0% | 28.7% |
| scripted modal | 54.2 | 15.7 | 10.0 [9.2, 10.9] | 5.7 | unchanged (B-02 H_W IRREDUCIBLE) | 16.4% → 16.4% | — |
| live fill | 94.0 | 29.0 | 21.2 [19.5, 22.9] | 7.8 | as scripted fill | 14.0% → 36.5% | 29.1% |
| live toggle | 492.5 | 17.2 | 11.6 [10.3, 13.1] | 5.6 | as scripted toggle | 90.4% → 92.7% | 91.8% |
| live modal | 519.6 | 17.3 | 11.7 [10.4, 13.1] | 5.5 | unchanged | 90.9% → 90.9% | — |

Live rows are re-weighted from R2-10's accepted live raw. No live trial was run here (NOT_RUN, provider cap 0).
The descriptive split (67.1% of fill's and 62.4% of toggle's cold excess left untested) uses the gate-failed
E_span split and is shown only so the owner can see the range. It is not the verdict.

## Work deleted vs wall-clock saved

No work is deleted: no product change, no knob. Wall-clock is reported separately:
- W80 costs 64.0 ms of T in both classes;
- PREWARM saves 12.0 / 8.1 ms inside the task but adds 60.5 / 50.3 ms of warm-up, a net 44.7 / 37.3 ms
  slower.

## Deviations (disclosed)

1. **Aborted attempt 1.** No commit. Its uncommitted harness was reviewed and copied (the harness/ copies were
   re-verified blob-for-blob). Its pilots (13 + 18 trials) and shakedown (54 trials) are excluded. Attempt 2
   ran one 27-trial pilot (measured-plan round 0, SHARED lock, ledger label `b04a2-pilot-r00`, all valid,
   excluded; `raw/pilot-trials.tar.gz`). It ran `run_b04.py` before the `--block` CLI option was added (the
   only edit between the pilot and the PREREG commit). The pilot set no gate, threshold or rule.
2. **POS and SMOKE ran under the EXCLUSIVE lock.** They are interleaved in the measured rounds. The lane spec
   allows SHARED for them, so this is stronger isolation. No number in this packet was measured under a
   SHARED lock.
3. **Analyzer written after the data.** `analyze_b04.py`, `make_headlines.py` and `verify_artifacts.py` were
   written after the measured chunks. They implement PREREG.json, which was committed before them.
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

## Limits and claim boundary

One host, private Xvfb (`cua-x11-session.sh` under hostless), Driver-chosen system Chrome 151.0.7922.71,
binary R `12b9045a`, tested source `8f3a646b4`, scripted chooser, telemetry off, TypeSafe not used. The fixture
is jev-use (fill → submit, toggle → confirm, modal as a check). The per-process part is UNDECIDED, not
NOT_MATERIAL. Nothing here says a warm pool is or is not worth it. No number is added to or ratioed with
B-02/B-03 numbers (binary 7e6c0609). No product change; no new service; instrumentation is the existing
env-gated phase trace. Upstream main moved 989cc76ce → 41c34cb0d with no change under the browser snapshot
path. The native `snapshot_store.rs` change (trycua/cua PR 4375) is outside this claim.

## Locks, isolation, near misses

- Locks (`raw/lock-ledger.jsonl`, verbatim ledger lines):
  - `b04a2-pilot-r00` SHARED, 02:45:26-02:46:24Z;
  - `b04a2-measured-r00-10` EXCLUSIVE, 02:50:41-02:58:30Z;
  - `b04a2-measured-r10-20` EXCLUSIVE, 03:06:59-03:12:07Z;
  - `b04a2-measured-r20-30` EXCLUSIVE, 03:19:23-03:25:52Z.
  - Each measured manifest lies inside its window.
- Every code-executing command ran under `hostless`. Every Driver/Chrome run was inside `cua-x11-session.sh`
  with `CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1`, and the logs show `wayland=unset`.
- The plain shell was used only for git, gh reads, file reads and edits, and `ps` / `/proc/locks` (read-only).
- Hard-rule breaches: none. Near misses: none.
- TypeSafe: 0 attempts, 0 reached.

## Files

| file | what |
|---|---|
| `PREREG.json` | pre-registration (committed in 0683e57ec before the first measured trial) |
| `run_b04.py` | runner (measurement only) |
| `b04_rows.py` | per-trial extraction (estimators, T_oracle, validity) |
| `analyze_b04.py` | statistics, gates, verdicts, accounting → `b04-summary.json` |
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

Raw outputs are mirrored to `artifacts/r2/B-04/attempt-2/` in the lane workspace.
