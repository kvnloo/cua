# kvnloo/cua#10: final whole-task accounting (round 2, staged)

Lane DOC-10-74, wave 6 of the CUA RFC loop. This is the kvnloo/cua#10 deliverable for kvnloo/cua#73 end condition
E5(a). It is staged on the fork branch `docs/accounting-10-queue-74-20261003` and nothing has been posted. The
companion posting queue for kvnloo/cua#74 is in [`../74-posting-queue/`](../74-posting-queue/README.md).

## What the table is

- **Blocks.** One block per reference task: browser fill->submit, toggle->confirm and modal->act on the jev-use
  fixture (the kvnloo/cua#24 classes), and the native GTK3 checkbox and text-entry tasks.
- **Rows.** Inside a block there is one row per SOURCE (Driver binary). The sources are R, R', B7, R'n, B5 and N3,
  and they are defined in the generated section below.
  - No number is ever added, subtracted or ratioed across two rows or two sources.
  - A "cross-lane reading" combines verdicts only. For example, a B-07 component can carry the R2-10 verdict for that
    component, while its number stays B-07's own.
  - The one computed quantity is a ratio of two numbers from the same row. It is marked "(derived)", and the
    verifier recomputes it.
- **Numbers.** Every number is read by `make_accounting.py` from an accepted packet's summary JSON at an exact
  commit, using `git show <sha>:<path>`. It is stored in `accounting.json` as a pointer
  `{value, from: {packet, file, path, round}}`. `verify_artifacts.py` re-reads every pointer and fails on any
  mismatch beyond the stated rounding. The prose in this file carries no numbers of its own.
- **Status.** A row is ACCEPTED (backed by a fresh-verifier-accepted packet), PENDING (a wave-6 lane is still
  running, so the row can still move and is refreshed in wave 7) or NOT_APPLICABLE.

## Columns

| Column | Meaning |
|---|---|
| Evidence | Evidence classes of the row: REAL, BENCHMARK (FIXTURE), UNIT, SOURCE, LIVE_PROVIDER, or NOT_RUN for a layer that did not run |
| n / Validity / E4 | Pairs (or trials per arm); verified-outcome share per arm; E4 invariant violations (stale dispatch, duplicate mutation, unverified success, refusal returned as success, blind replay) |
| BASE T, Best T | Median T_oracle: from the first observation to the independent target-owned oracle. NOT_MEASURED where the lane has no BASE arm |
| S [CI] | Median T_BASE / median T_best with the packet's CI. "amortized" is the ratio of means over every invocation, including training / compile / admission and fallback |
| KEEP-only S | The composition with only KEEP deletions (owner-decision deletions left at their defaults): COMP_K for browser, S0 for native |
| Floor | Mean composed T / T_irreducible (the sum of the IRREDUCIBLE components) = floor ratio |
| Untested | Share of T without a terminal verdict, under each mapping (below) |
| Work deleted | Milliseconds of work the composed arm removes (BASE minus composed component mean, for the components it deliberately removes), plus provider requests per trial before and after |
| Wall-clock saved | Median paired BASE minus composed T, with CI. This is never added to work deleted |

Component bullets under each block list the components that are material, or at least 1 ms. Each one shows
its verdict (DELETED / IRREDUCIBLE / OWNER_DECISION / UNTESTED / BELOW_GATE) and the lane that issued the verdict.
`accounting.json` holds every component.

**Untested mappings.**
- **Browser A (R2-10 mapping).** The cold first-snapshot excess is counted inside IRREDUCIBLE observation.
- **Browser A2.** Same as A, but B-07's BELOW_GATE sub-spans are counted as UNTESTED.
- **Browser B (B-04 mapping).** The cold excess is counted UNTESTED, because its per-process part is UNDECIDED
  under B-06's pre-registration.
- **B-06 row.** A is B-06's post-hoc amended reading (the owner's call), and B is B-06's primary result.
- **Native A.** The primary R2-10 reading.
- **Native B.** The conservative N-02 reading, which counts the observation-transport client validation and buckets
  as untested.

## Claim boundary

- **Sources.** Whole-task T is measured on fixtures: jev-use in a private browser session, and the canonical GTK3
  fixture on private Xvfb with AT-SPI.
  - Live rows use TypeSafe and exist only on source R (989cc76ce).
  - R' is the recertification of R on 0f1955d2f, and its rows are scripted only. The R' live layer is BLOCKED by
    the paid budget.
  - Native T uses the scripted chooser, so it excludes provider decisions. Whether that is acceptable is an
    owner ruling (kvnloo/cua#74 OR-21).
- **The browser speedup is mostly owner decisions.** The large browser S comes from owner-decision deletions,
  chiefly feedback glide. See "Owner-decision dependency" below for the KEEP-only S.
- **Not implied.** No product default changes here, and none is implied. The deletions were measured through
  measurement-only, env-gated, default-off knobs.
- **Live toggle/modal.** Provider decisions stay UNTESTED.
- **Compiled replay.** It is in the composed configuration for fill only. R2-07d failed the modal gate, and Phase L
  did not run.
- **Paper figures.** PreAct and SkillDroid are cited as references only, never as gates or targets.

## Verify

```
python3 docs/rfc/10-final-accounting/verify_artifacts.py            # both deliverables
python3 docs/rfc/74-posting-queue/verify_artifacts.py               # the queue only
```

- **Requirements.** The verifier is stdlib only. Run it under the lane's hostless wrapper, from any checkout of
  the fork that contains the cited commits. It needs network access for the read-only `git ls-remote` of
  kvnloo/cua and trycua/cua; `--offline` skips those checks and says so.
- **Optional environment.**
  - `CUA_PRIVACY_NAMES_FILE`: a private-names list, which is never committed.
  - `CUA_LOOP_STATE`: the loop STATE.json. When it is set, the committed state extract is re-derived and compared.
- **Rebuilding.** The builders are `make_accounting.py`, `../74-posting-queue/make_queue.py` and
  `make_provenance.py`. They regenerate the JSON and the generated sections of both READMEs.
- **Provenance.** `provenance.json` records the input SHAs, the STATE.json sha256, the gh read timestamps, the
  ls-remote read times and the live upstream main.

This lane attempted no TypeSafe request and none reached the provider.

<!-- BEGIN GENERATED: make_accounting.py -->

Sources: **R** = 989cc76ce + R2-10 steps 1-8, binary 12b9045a (R2-10 L-live, R2-10 L-scripted, R2-07d, B-04); **R'** = 0f1955d2f + R2-10 steps 1-8 (45dff8f32), binary 922111c5 (R2-10R, B-06); **B7** = R' + B-07 marks + POST_FAST knob, binary 6f95aef5 (B-07; B-08 PENDING); **R'n** = R' + N-02 marks + focus-guard clamp knob (11a03bf51), binary 78a1137d (N-04); **B5** = R2-10 source + B-05 marks (b376f1ff3), binary f4149bdd (B-05); **N3** = R2-10 source + N-03 marks/knobs (85a73c2c7), binary b1843871 (N-03).

### Browser fill -> submit (jev-use, kvnloo/cua#24 class)

| Row (lane, source) | Evidence | n | Validity / E4 | BASE T | Best T | S [CI] | KEEP-only S | Floor T_comp / T_irr | Untested (A; A2; B) | Work deleted | Wall-clock saved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2-10 (R), L-live (TypeSafe provider) | LIVE_PROVIDER, REAL, BENCHMARK (FIXTURE) | 30 | BASE 1.000; COMP 1.000; e4 0 violations | 3647.2 | 80.9 | 45.11 [42.43, 51.90]; amortized 42.16 [34.68, 48.46] | NOT_MEASURED | 94.03 / 48.24 = 1.95 | A 13.97%; B 36.47% | visualization 3000.5; settles 101.0; client_validation 13.1; mcp_admission 9.8; provider_decision 484.8; provider requests/trial 2.000 -> 0.033 | 3567.3 [3545.6, 3615.1] |
| R2-10 (R), L-scripted (scripted chooser, 0 provider) | REAL, BENCHMARK (FIXTURE) | 32 | BASE 1.000; COMP 1.000; e4 0 violations | 3187.6 | 69.9 | 45.61 [44.35, 46.98]; amortized 43.79 [40.75, 45.98] | 1.01 [1.01, 1.01]; amortized 0.98 [0.92, 1.01] | 79.61 / 43.28 = 1.84 | A 15.17%; B 39.12% | visualization 2997.6; settles 101.1; client_validation 13.1; mcp_admission 9.1; provider requests/trial 2.000 -> 0.031 | 3116.4 [3114.5, 3118.9] |
| R2-07d (R) **NOT_APPLICABLE** | - | - | - | - | - | - | - | - | - | - | R2-07d covers toggle/modal only; the fill compiled replay (R2-07b, re-qualified by FIX-01) is already inside R2-10's fill COMP arm |
| R2-10R (R'), L-scripted (recertification of R2-10 on 0f1955d2f; live layer not re-run) | REAL, BENCHMARK (FIXTURE) | 32 | BASE 1.000; COMP 1.000; e4 0 violations | 3189.9 | 69.9 | 45.65 [44.39, 48.36]; amortized 42.62 [38.78, 45.88] | 1.01 [1.00, 1.01]; amortized 0.98 [0.92, 1.01] | 80.92 / 42.56 = 1.90 | A 15.18%; B 36.70% | visualization 3000.3; settles 101.1; client_validation 13.0; mcp_admission 8.7; provider requests/trial 2.000 -> 0.031 | 3118.4 [3117.3, 3124.0] |
| B-06 (R'), L-scripted, COMP only (per-process cold first snapshot; no BASE arm) | REAL, BENCHMARK (FIXTURE), SOURCE (per-document part carried from B-04) | 32 | C 1.000; Wa 1.000; Wb 1.000; P 1.000 | NOT_MEASURED | C 64.2 / Wa 54.1 | NOT_MEASURED | NOT_MEASURED | n/a | A 15.18%; B 36.70% | NONE (nothing deleted; no product change) | NONE |
| B-07 (B7), L-scripted, COMP only (transport residual on R' + marks; mark-corrected at c_m) | REAL, BENCHMARK (FIXTURE), UNIT (weak), SOURCE | 32 | valid 96; n 96; verified 96; e4 0 violations | NOT_MEASURED | 63.9 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | A 1.64%; A2 3.95%; B 26.17% | PREP_FAST 0.48 (not carried) | PREP_FAST 3.94 [0.09, 10.07] (not carried) |
| B-08 (B7) **PENDING** | - | - | - | - | - | - | - | - | - | - | per-process cold first snapshot on B7 (exp/b-08-per-process-cold-b7-20261003); decides the browser cold-excess verdict on the B7 source |
| B-05 (B5), L-scripted, COMP only (MCP transport sub-spans on R2-10 source + marks) | REAL, BENCHMARK (FIXTURE), UNIT | 32 | valid 96; n 96; e4 0 violations | NOT_MEASURED | 93.9 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | A 4.32%; A2 6.03% | NONE (PARSE_FAST and VALIDATE_FAST are KILL (below the 0.5 ms gate); nothing carried) | NONE |

- **R2-10-live (R)** components (mean ms, material or >= 1 ms): observation 28.96 ms (30.79%): IRREDUCIBLE (R2-10 mapping (this packet)); reval_endpoint 24.64 ms (26.20%): OWNER_DECISION (R2-10 mapping (this packet)); sleeps_polls 9.14 ms (9.72%): IRREDUCIBLE (R2-10 mapping (this packet)); provider_decision 6.04 ms (6.43%): DELETED (R2-10 mapping (this packet)); mcp_transport 5.76 ms (6.13%): UNTESTED (R2-10 mapping (this packet)); dispatch 4.30 ms (4.58%): IRREDUCIBLE (R2-10 mapping (this packet)); reval_other 2.86 ms (3.04%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 2.72 ms (2.89%): UNTESTED (R2-10 mapping (this packet)); target_effect_lag 2.14 ms (2.27%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.93 ms (2.05%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.70 ms (1.81%): UNTESTED (R2-10 mapping (this packet)); input_prep 1.43 ms (1.52%): UNTESTED (R2-10 mapping (this packet))
  - untested mappings: B from B-04 (same source R; re-analysis of R2-10 raw)
- **R2-10-scripted (R)** components (mean ms, material or >= 1 ms): observation 26.19 ms (32.90%): IRREDUCIBLE (R2-10 mapping (this packet)); reval_endpoint 22.45 ms (28.20%): OWNER_DECISION (R2-10 mapping (this packet)); sleeps_polls 9.03 ms (11.35%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 5.24 ms (6.58%): UNTESTED (R2-10 mapping (this packet)); dispatch 3.25 ms (4.08%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 2.35 ms (2.96%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.27 ms (2.85%): IRREDUCIBLE (R2-10 mapping (this packet)); target_effect_lag 1.77 ms (2.23%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.77 ms (2.22%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.65 ms (2.07%): UNTESTED (R2-10 mapping (this packet)); input_prep 1.20 ms (1.51%): UNTESTED (R2-10 mapping (this packet))
  - untested mappings: B from B-04 (same source R; re-analysis of R2-10 raw)
- **R2-10R (R')** components (mean ms, material or >= 1 ms): observation 24.52 ms (30.30%): IRREDUCIBLE (R2-10 mapping (this packet)); reval_endpoint 24.18 ms (29.88%): OWNER_DECISION (R2-10 mapping (this packet)); sleeps_polls 8.83 ms (10.92%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 5.34 ms (6.60%): UNTESTED (R2-10 mapping (this packet)); dispatch 3.93 ms (4.86%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 2.55 ms (3.15%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.49 ms (3.08%): IRREDUCIBLE (R2-10 mapping (this packet)); target_effect_lag 2.04 ms (2.52%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.84 ms (2.28%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.64 ms (2.03%): UNTESTED (R2-10 mapping (this packet)); input_prep 1.27 ms (1.56%): UNTESTED (R2-10 mapping (this packet))
  - untested mappings: B from B-06 primary (same source R'; per-process cold excess UNDECIDED, share is a lower bound)
- **B-06 (R')** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = amended reading (owner's call): per-process part OWNER_DECISION; R2-10R mapping, transport still UNTESTED on R'; B = primary PREREG reading: per-process UNDECIDED, counted UNTESTED (lower bound)
  - cold excess E_R' 17.41 ms; D (C-Wa) 11.94 [10.01, 12.05]; PC 9.99; primary verdict UNDECIDED
  - post-hoc amendment: D 10.02 [8.04, 12.00] -> OWNER_DECISION (owner's call)
  - warm-up outside T 38.3 ms; k=1 92.3 ms; k=5 61.7 ms per task
- **B-07 (B7)** components (mean ms, material or >= 1 ms): observation 22.56 ms (32.89%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); reval_endpoint 21.68 ms (31.61%): OWNER_DECISION (R2-10 mapping (cross-lane verdict; number from B-07)); sleeps_polls 9.44 ms (13.76%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); mcp_transport 3.19 ms (4.64%): terminal by sub-span (B-05 + B-07): route/adm BELOW_GATE, post/parse/validate IRREDUCIBLE, prep DELETED-fragile (not carried) (B-07 verdicts.units + B-05); dispatch 2.69 ms (3.92%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); resolution 1.97 ms (2.88%): UNTESTED (R2-10 mapping (cross-lane verdict; number from B-07)); reval_other 1.88 ms (2.74%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); target_effect_lag 1.49 ms (2.17%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); visualization 1.24 ms (1.81%): OWNER_DECISION (R2-10 mapping (cross-lane verdict; number from B-07))
  - untested mappings: A = R2-10 mapping, cold excess not untested, BELOW_GATE as IRREDUCIBLE; A2 = R2-10 mapping, BELOW_GATE as UNTESTED; B = B-04 mapping: cold excess UNTESTED
  - cold excess mean 16.83 ms (per-process part UNDECIDED, B-06); transport in/out corrected 3.35 ms
- **B-05 (B5)** components (mean ms, material or >= 1 ms): c_out.parse: IRREDUCIBLE (every tested candidate failed) (B-05); PARSE_FAST_caller_ms_ci95 [0.11, 0.34]; c_out.validate: IRREDUCIBLE (every tested candidate failed) (B-05); VALIDATE_FAST_caller_ms_ci95 [-0.04, 0.36]
  - untested mappings: A = B-05 own mapping, BELOW_GATE as IRREDUCIBLE (before B-07 closed route/prep/post); A2 = BELOW_GATE as UNTESTED

### Browser toggle -> confirm (jev-use, kvnloo/cua#24 class)

| Row (lane, source) | Evidence | n | Validity / E4 | BASE T | Best T | S [CI] | KEEP-only S | Floor T_comp / T_irr | Untested (A; A2; B) | Work deleted | Wall-clock saved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2-10 (R), L-live (TypeSafe provider) | LIVE_PROVIDER, REAL, BENCHMARK (FIXTURE) | 30 | BASE 1.000; COMP 1.000; e4 0 violations | 2928.3 | 491.8 | 5.95 [5.70, 6.25] | NOT_MEASURED | 492.47 / 21.88 = 22.51 | A 90.37%; B 92.73% | visualization 2421.0; client_validation 12.5; mcp_admission 9.4; provider requests/trial 2.000 -> 2.000 | 2431.0 [2404.4, 2492.2] |
| R2-10 (R), L-scripted (scripted chooser, 0 provider) | REAL, BENCHMARK (FIXTURE) | 32 | BASE 1.000; COMP 1.000; e4 0 violations | 2507.4 | 53.3 | 47.01 [45.36, 48.54] | 1.01 [1.00, 1.01] | 54.84 / 21.20 = 2.59 | A 16.44%; B 36.04% | visualization 2434.5; client_validation 12.4; mcp_admission 9.3; provider requests/trial 2.000 -> 2.000 | 2452.6 [2449.1, 2458.8] |
| R2-07d (R), L-scripted quiet window (COMP vs COMP+CR compiled routine); live Phase L NOT_RUN | REAL, BENCHMARK (FIXTURE), UNIT, LIVE_PROVIDER NOT_RUN | 40 | G3_pass yes; E4_clean yes | NOT_MEASURED | COMP 47.4 / CR 47.9 | NOT_MEASURED | NOT_MEASURED | 48.22 / 17.64 = 2.73 (derived) | A 17.39% | NONE (compiled routine not carried for toggle/modal (Phase L NOT_RUN; modal gate FAIL)) | NONE |
| R2-10R (R'), L-scripted (recertification of R2-10 on 0f1955d2f; live layer not re-run) | REAL, BENCHMARK (FIXTURE) | 32 | BASE 1.000; COMP 1.000; e4 0 violations | 2503.4 | 53.5 | 46.82 [45.21, 48.69] | 1.01 [1.01, 1.01] | 53.57 / 19.66 = 2.72 | A 16.65%; B 34.93% | visualization 2427.2; client_validation 12.6; mcp_admission 8.5; provider requests/trial 2.000 -> 2.000 | 2448.4 [2441.6, 2452.9] |
| B-06 (R'), L-scripted, COMP only (per-process cold first snapshot; no BASE arm) | REAL, BENCHMARK (FIXTURE), SOURCE (per-document part carried from B-04) | 32 | C 1.000; Wa 1.000; Wb 1.000; P 1.000 | NOT_MEASURED | C 50.2 / Wa 46.1 | NOT_MEASURED | NOT_MEASURED | n/a | A 16.65%; B 34.93% | NONE (nothing deleted; no product change) | NONE |
| B-07 (B7), L-scripted, COMP only (transport residual on R' + marks; mark-corrected at c_m) | REAL, BENCHMARK (FIXTURE), UNIT (weak), SOURCE | 32 | valid 96; n 96; verified 96; e4 0 violations | NOT_MEASURED | 49.4 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | A 0.59%; A2 3.52%; B 19.12% | PREP_FAST 0.45 (not carried) | PREP_FAST 0.23 [-0.98, 1.42] (not carried) |
| B-08 (B7) **PENDING** | - | - | - | - | - | - | - | - | - | - | per-process cold first snapshot on B7 (exp/b-08-per-process-cold-b7-20261003); decides the browser cold-excess verdict on the B7 source |
| B-05 (B5), L-scripted, COMP only (MCP transport sub-spans on R2-10 source + marks) | REAL, BENCHMARK (FIXTURE), UNIT | 32 | valid 96; n 96; e4 0 violations | NOT_MEASURED | 76.2 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | A 4.09%; A2 6.07% | NONE (PARSE_FAST and VALIDATE_FAST are KILL (below the 0.5 ms gate); nothing carried) | NONE |
| R2-07e (R) **PENDING** | - | - | - | - | - | - | - | - | - | - | new pre-registered modal gate + Phase L (exp/r2-07e-modal-gate-phase-l-20261003) |

- **R2-10-live (R)** components (mean ms, material or >= 1 ms): provider_decision 434.79 ms (88.29%): UNTESTED (R2-10 mapping (this packet)); reval_endpoint 23.49 ms (4.77%): OWNER_DECISION (R2-10 mapping (this packet)); observation 17.16 ms (3.48%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 5.18 ms (1.05%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.23 ms (0.45%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_admission 2.15 ms (0.44%): UNTESTED (R2-10 mapping (this packet)); visualization 2.06 ms (0.42%): OWNER_DECISION (R2-10 mapping (this packet)); resolution 1.43 ms (0.29%): UNTESTED (R2-10 mapping (this packet)); dispatch 1.26 ms (0.26%): IRREDUCIBLE (R2-10 mapping (this packet)); verification_reads 1.23 ms (0.25%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: B from B-04 (same source R; re-analysis of R2-10 raw)
- **R2-10-scripted (R)** components (mean ms, material or >= 1 ms): reval_endpoint 22.83 ms (41.62%): OWNER_DECISION (R2-10 mapping (this packet)); observation 16.01 ms (29.20%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 4.75 ms (8.66%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.74 ms (5.00%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.80 ms (3.29%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.65 ms (3.01%): UNTESTED (R2-10 mapping (this packet)); resolution 1.25 ms (2.27%): UNTESTED (R2-10 mapping (this packet)); verification_reads 1.20 ms (2.19%): IRREDUCIBLE (R2-10 mapping (this packet)); dispatch 1.18 ms (2.16%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: B from B-04 (same source R; re-analysis of R2-10 raw)
- **R2-07d (R)** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = R2-07d's own COMP decomposition (R2-10 mapping, transport UNTESTED)
  - CR - COMP 0.5 [-1.3, 0.8] ms; gate (CI upper <= +2.0) yes; disposition REVISE
- **R2-10R (R')** components (mean ms, material or >= 1 ms): reval_endpoint 23.21 ms (43.33%): OWNER_DECISION (R2-10 mapping (this packet)); observation 14.78 ms (27.59%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 4.72 ms (8.81%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.68 ms (5.00%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.78 ms (3.32%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.64 ms (3.05%): UNTESTED (R2-10 mapping (this packet)); resolution 1.20 ms (2.23%): UNTESTED (R2-10 mapping (this packet)); verification_reads 1.14 ms (2.13%): IRREDUCIBLE (R2-10 mapping (this packet)); dispatch 1.06 ms (1.98%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: B from B-06 primary (same source R'; per-process cold excess UNDECIDED, share is a lower bound)
- **B-06 (R')** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = amended reading (owner's call): per-process part OWNER_DECISION; R2-10R mapping, transport still UNTESTED on R'; B = primary PREREG reading: per-process UNDECIDED, counted UNTESTED (lower bound)
  - cold excess E_R' 9.80 ms; D (C-Wa) 6.00 [3.94, 6.17]; PC 10.93; primary verdict UNDECIDED
  - post-hoc amendment: D 4.02 [3.89, 5.97] -> OWNER_DECISION (owner's call)
  - warm-up outside T 30.5 ms; k=1 76.5 ms; k=5 52.2 ms per task
- **B-07 (B7)** components (mean ms, material or >= 1 ms): reval_endpoint 21.27 ms (50.91%): OWNER_DECISION (R2-10 mapping (cross-lane verdict; number from B-07)); observation 11.50 ms (27.52%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); mcp_transport 2.33 ms (5.58%): terminal by sub-span (B-05 + B-07): route/adm BELOW_GATE, post/parse/validate IRREDUCIBLE, prep IRREDUCIBLE (B-07 verdicts.units + B-05); reval_other 1.80 ms (4.31%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); visualization 1.18 ms (2.83%): OWNER_DECISION (R2-10 mapping (cross-lane verdict; number from B-07)); verification_reads 1.04 ms (2.48%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07))
  - untested mappings: A = R2-10 mapping, cold excess not untested, BELOW_GATE as IRREDUCIBLE; A2 = R2-10 mapping, BELOW_GATE as UNTESTED; B = B-04 mapping: cold excess UNTESTED
  - cold excess mean 7.74 ms (per-process part UNDECIDED, B-06); transport in/out corrected 2.45 ms
- **B-05 (B5)** components (mean ms, material or >= 1 ms): c_out.parse: IRREDUCIBLE (every tested candidate failed) (B-05); PARSE_FAST_caller_ms_ci95 [0.01, 0.25]; c_out.validate: IRREDUCIBLE (every tested candidate failed) (B-05); VALIDATE_FAST_caller_ms_ci95 [0.02, 0.24]
  - untested mappings: A = B-05 own mapping, BELOW_GATE as IRREDUCIBLE (before B-07 closed route/prep/post); A2 = BELOW_GATE as UNTESTED

### Browser modal -> act (jev-use, kvnloo/cua#24 class)

| Row (lane, source) | Evidence | n | Validity / E4 | BASE T | Best T | S [CI] | KEEP-only S | Floor T_comp / T_irr | Untested (A; A2; B) | Work deleted | Wall-clock saved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2-10 (R), L-live (TypeSafe provider) | LIVE_PROVIDER, REAL, BENCHMARK (FIXTURE) | 30 | BASE 1.000; COMP 1.000; e4 0 violations | 2930.2 | 511.0 | 5.73 [5.41, 6.00] | NOT_MEASURED | 519.61 / 22.24 = 23.37 | A 90.89%; B 90.89% | visualization 2406.2; client_validation 12.8; mcp_admission 9.2; provider requests/trial 2.000 -> 2.000 | 2423.8 [2385.9, 2446.6] |
| R2-10 (R), L-scripted (scripted chooser, 0 provider) | REAL, BENCHMARK (FIXTURE) | 32 | BASE 1.000; COMP 1.000; e4 0 violations | 2483.6 | 53.3 | 46.56 [45.56, 47.69] | 1.01 [1.00, 1.01] | 54.20 / 20.89 = 2.59 | A 16.43%; B 16.43% | visualization 2411.7; client_validation 12.4; mcp_admission 9.5; provider requests/trial 2.000 -> 2.000 | 2430.9 [2420.1, 2441.7] |
| R2-07d (R), L-scripted quiet window (COMP vs COMP+CR compiled routine); live Phase L NOT_RUN | REAL, BENCHMARK (FIXTURE), UNIT, LIVE_PROVIDER NOT_RUN | 40 | G3_pass yes; E4_clean yes | NOT_MEASURED | COMP 47.5 / CR 47.9 | NOT_MEASURED | NOT_MEASURED | 48.72 / 18.18 = 2.68 (derived) | A 17.14% | NONE (compiled routine not carried for toggle/modal (Phase L NOT_RUN; modal gate FAIL)) | NONE |
| R2-10R (R'), L-scripted (recertification of R2-10 on 0f1955d2f; live layer not re-run) | REAL, BENCHMARK (FIXTURE) | 32 | BASE 1.000; COMP 1.000; e4 0 violations | 2491.4 | 55.5 | 44.86 [43.56, 46.81] | 1.01 [1.01, 1.01] | 55.33 / 20.96 = 2.64 | A 16.21%; B 16.21% | visualization 2417.6; client_validation 12.4; mcp_admission 9.2; provider requests/trial 2.000 -> 2.000 | 2435.5 [2432.0, 2445.0] |
| B-06 (R'), L-scripted, COMP only (per-process cold first snapshot; no BASE arm) | REAL, BENCHMARK (FIXTURE), SOURCE (per-document part carried from B-04) | 16 | C 1.000; Wa 1.000; Wb 1.000; P 1.000 | NOT_MEASURED | C 52.2 / Wa 48.1 | NOT_MEASURED | NOT_MEASURED | n/a | A 16.21% | NONE (nothing deleted; no product change) | NONE |
| B-07 (B7), L-scripted, COMP only (transport residual on R' + marks; mark-corrected at c_m) | REAL, BENCHMARK (FIXTURE), UNIT (weak), SOURCE | 32 | valid 96; n 96; verified 96; e4 0 violations | NOT_MEASURED | 49.4 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | A 0.56%; A2 3.47%; B NOT_MEASURED | PREP_FAST 0.49 (not carried) | PREP_FAST 0.61 [-1.37, 2.90] (not carried) |
| B-08 (B7) **PENDING** | - | - | - | - | - | - | - | - | - | - | per-process cold first snapshot on B7 (exp/b-08-per-process-cold-b7-20261003); decides the browser cold-excess verdict on the B7 source |
| B-05 (B5), L-scripted, COMP only (MCP transport sub-spans on R2-10 source + marks) | REAL, BENCHMARK (FIXTURE), UNIT | 32 | valid 96; n 96; e4 0 violations | NOT_MEASURED | 75.1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | A 7.46%; A2 9.66% | NONE (PARSE_FAST and VALIDATE_FAST are KILL (below the 0.5 ms gate); nothing carried) | NONE |
| R2-07e (R) **PENDING** | - | - | - | - | - | - | - | - | - | - | new pre-registered modal gate + Phase L (exp/r2-07e-modal-gate-phase-l-20261003) |

- **R2-10-live (R)** components (mean ms, material or >= 1 ms): provider_decision 462.41 ms (88.99%): UNTESTED (R2-10 mapping (this packet)); reval_endpoint 23.02 ms (4.43%): OWNER_DECISION (R2-10 mapping (this packet)); observation 17.26 ms (3.32%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 5.36 ms (1.03%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.29 ms (0.44%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 2.08 ms (0.40%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.71 ms (0.33%): UNTESTED (R2-10 mapping (this packet)); dispatch 1.47 ms (0.28%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 1.32 ms (0.25%): UNTESTED (R2-10 mapping (this packet)); verification_reads 1.21 ms (0.23%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: B from B-04 (same source R; re-analysis of R2-10 raw); B-04 did not remap the modal cold excess (B-02 H_W IRREDUCIBLE); B equals A
- **R2-10-scripted (R)** components (mean ms, material or >= 1 ms): reval_endpoint 22.56 ms (41.62%): OWNER_DECISION (R2-10 mapping (this packet)); observation 15.70 ms (28.97%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 4.83 ms (8.92%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.73 ms (5.03%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.84 ms (3.40%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.63 ms (3.00%): UNTESTED (R2-10 mapping (this packet)); dispatch 1.32 ms (2.43%): IRREDUCIBLE (R2-10 mapping (this packet)); verification_reads 1.11 ms (2.05%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 1.10 ms (2.02%): UNTESTED (R2-10 mapping (this packet))
  - untested mappings: B from B-04 (same source R; re-analysis of R2-10 raw); B-04 did not remap the modal cold excess (B-02 H_W IRREDUCIBLE); B equals A
- **R2-07d (R)** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = R2-07d's own COMP decomposition (R2-10 mapping, transport UNTESTED)
  - CR - COMP 0.6 [-1.4, 2.4] ms; gate (CI upper <= +2.0) no; disposition REVISE
- **R2-10R (R')** components (mean ms, material or >= 1 ms): reval_endpoint 23.50 ms (42.47%): OWNER_DECISION (R2-10 mapping (this packet)); observation 15.68 ms (28.34%): IRREDUCIBLE (R2-10 mapping (this packet)); mcp_transport 4.85 ms (8.76%): UNTESTED (R2-10 mapping (this packet)); reval_other 2.87 ms (5.19%): IRREDUCIBLE (R2-10 mapping (this packet)); visualization 1.91 ms (3.45%): OWNER_DECISION (R2-10 mapping (this packet)); mcp_admission 1.64 ms (2.96%): UNTESTED (R2-10 mapping (this packet)); dispatch 1.28 ms (2.32%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 1.14 ms (2.05%): UNTESTED (R2-10 mapping (this packet)); verification_reads 1.12 ms (2.03%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: B from B-06 (modal descriptive; not remapped)
- **B-06 (R')** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = modal descriptive only (not remapped)
  - cold excess E_R' 10.13 ms; D (C-Wa) 5.06 [3.04, 6.99]; PC 9.05; primary verdict DESCRIPTIVE (modal: consistency only)
- **B-07 (B7)** components (mean ms, material or >= 1 ms): reval_endpoint 21.00 ms (50.33%): OWNER_DECISION (R2-10 mapping (cross-lane verdict; number from B-07)); observation 11.79 ms (28.26%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); mcp_transport 2.36 ms (5.65%): terminal by sub-span (B-05 + B-07): route/adm BELOW_GATE, post/parse/validate IRREDUCIBLE, prep IRREDUCIBLE (B-07 verdicts.units + B-05); reval_other 1.70 ms (4.07%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07)); visualization 1.22 ms (2.91%): OWNER_DECISION (R2-10 mapping (cross-lane verdict; number from B-07)); dispatch 1.05 ms (2.52%): IRREDUCIBLE (R2-10 mapping (cross-lane verdict; number from B-07))
  - untested mappings: A = R2-10 mapping, cold excess not untested, BELOW_GATE as IRREDUCIBLE; A2 = R2-10 mapping, BELOW_GATE as UNTESTED; B = B-04 mapping: cold excess UNTESTED
  - cold excess mean 7.54 ms (per-process part UNDECIDED, B-06); transport in/out corrected 2.48 ms
- **B-05 (B5)** components (mean ms, material or >= 1 ms): c_out.parse: IRREDUCIBLE (every tested candidate failed) (B-05); PARSE_FAST_caller_ms_ci95 [0.08, 0.34]; c_out.validate: IRREDUCIBLE (every tested candidate failed) (B-05); VALIDATE_FAST_caller_ms_ci95 [0.04, 0.31]
  - untested mappings: A = B-05 own mapping, BELOW_GATE as IRREDUCIBLE (before B-07 closed route/prep/post); A2 = BELOW_GATE as UNTESTED

### Native GTK3 checkbox toggle (canonical fixture)

| Row (lane, source) | Evidence | n | Validity / E4 | BASE T | Best T | S [CI] | KEEP-only S | Floor T_comp / T_irr | Untested (A; A2; B) | Work deleted | Wall-clock saved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2-10 (R), L-scripted (scripted chooser; native T excludes provider decisions) | REAL, BENCHMARK (FIXTURE, GTK3, private Xvfb + AT-SPI) | 24 | BASE 1.000; S0 1.000; X 1.000; e4 0 violations | 334.9 | 283.0 | 1.18 [1.18, 1.18] | 1.18 [1.17, 1.18] | 284.09 / 272.21 = 1.04 | A 4.14%; B NOT_MEASURED | post_action_sleep 50.9 | 50.0 [49.8, 52.0] |
| R2-10R (R'), L-scripted (scripted chooser; native T excludes provider decisions) | REAL, BENCHMARK (FIXTURE, GTK3, private Xvfb + AT-SPI) | 24 | BASE 1.000; S0 1.000; X 1.000; e4 0 violations | 334.3 | 283.0 | 1.18 [1.18, 1.18] | 1.18 [1.18, 1.18] | 283.09 / 271.83 = 1.04 | A 3.94%; B NOT_MEASURED | post_action_sleep 51.0 | 51.0 [50.3, 52.3] |
| N-04 (R'n), L-scripted (scripted chooser; native T excludes provider decisions) | REAL, BENCHMARK (FIXTURE, GTK3), UNIT | 24 | k1_tasks 192; k5_tasks 240; best_arm_valid_share 1.000; e4_best_arm 0 violations | 334.9 | 280.0 | 1.196 [1.189, 1.198] | 1.180 [1.177, 1.184] | 280.30 / 270.56 = 1.036 | A 1.19%; B 2.23% | post_action_sleep 51.14; action_transport.admission_v 1.58; observation_transport.admission_v 1.49; V admission work 2.84 | 54.27 [53.04, 55.21] |
| N-03 (N3), L-scripted (superseded for E2/E3 by N-04 on R'n) | REAL, BENCHMARK (FIXTURE, GTK3), UNIT | n/a | hcl_rows_valid_verified 168; hcl_rows 168 | NOT_MEASURED | mean 286.51 | NOT_MEASURED | NOT_MEASURED | 286.51 / 275.08 = 1.042 | A 1.47%; B 2.73% | V admission work 3.63 | V 3.10 [0.40, 4.97] |

- **R2-10 (R)** components (mean ms, material or >= 1 ms): settle 240.87 ms (84.78%): IRREDUCIBLE (R2-10 mapping (this packet)); observation_transport 18.73 ms (6.59%): IRREDUCIBLE (R2-10 mapping (this packet)); observation 10.86 ms (3.82%): IRREDUCIBLE (R2-10 mapping (this packet)); action_transport 9.92 ms (3.49%): UNTESTED (R2-10 mapping (this packet)); resolution 1.42 ms (0.50%): UNTESTED (R2-10 mapping (this packet)); dispatch 1.12 ms (0.39%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: A = R2-10 mapping (observation transport IRREDUCIBLE)
  - T_land vs T_oracle (medians): BASE 35.0 vs 334.9 ms; X 35.0 vs 283.0 ms
  - S at T_land: paired S at T_land is not in R2-10's summary; the R2-10 verifier note (S_land about 1.00 checkbox) is not recomputed here
- **R2-10R (R')** components (mean ms, material or >= 1 ms): settle 241.22 ms (85.21%): IRREDUCIBLE (R2-10 mapping (this packet)); observation_transport 18.10 ms (6.39%): IRREDUCIBLE (R2-10 mapping (this packet)); observation 10.93 ms (3.86%): IRREDUCIBLE (R2-10 mapping (this packet)); action_transport 9.34 ms (3.30%): UNTESTED (R2-10 mapping (this packet)); resolution 1.38 ms (0.49%): UNTESTED (R2-10 mapping (this packet)); dispatch 1.09 ms (0.39%): IRREDUCIBLE (R2-10 mapping (this packet))
  - untested mappings: A = R2-10 mapping (observation transport IRREDUCIBLE)
  - T_land vs T_oracle (medians): BASE 35.0 vs 334.3 ms; X 35.0 vs 283.0 ms
  - S at T_land: X 1.00 [0.98, 1.03], S0 1.00
- **N-04 (R'n)** components (mean ms, material or >= 1 ms): settle 241.63 ms (86.21%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); observation_transport 16.63 ms (5.93%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); observation 10.54 ms (3.76%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); action_transport.client_validate 6.30 ms (2.25%): OWNER_DECISION (N-04 primary (R2-10 labels + V/HCL verdicts)); resolution 1.35 ms (0.48%): UNTESTED (N-04 primary (R2-10 labels + V/HCL verdicts))
  - untested mappings: A = primary R2-10 reading; B = conservative N-02 reading (observation-transport client validation counted)
  - T_land (medians) BASE 34.98 / best 31.94 ms; S at T_land best 1.095 [1.093, 1.161], KEEP-only 0.986
  - verdicts: V DELETED, HCL OWNER_DECISION
  - HCL per 5-task session 82.22 ms; HCL at k=1 -0.04 ms
  - V T saved (k=1) 2.94 [2.02, 3.46] ms
- **N-03 (N3)** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = primary R2-10 reading; B = conservative N-02 reading
  - verdicts: V DELETED, HCL OWNER_DECISION
  - ax_fg S0: DELETED; click wrapper saved 51.35 [48.86, 53.72] ms (n=20); X11 ax_fg route at the default config; Part B is not order-counterbalanced (bound about 0.6 ms)
  - HCL per 5-task session 70.93 ms

### Native GTK3 text entry (canonical fixture)

| Row (lane, source) | Evidence | n | Validity / E4 | BASE T | Best T | S [CI] | KEEP-only S | Floor T_comp / T_irr | Untested (A; A2; B) | Work deleted | Wall-clock saved |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R2-10 (R), L-scripted (scripted chooser; native T excludes provider decisions) | REAL, BENCHMARK (FIXTURE, GTK3, private Xvfb + AT-SPI) | 24 | BASE 1.000; S0 1.000; X 1.000; e4 0 violations | 1760.9 | 300.9 | 5.85 [5.81, 5.88] | 1.03 [1.03, 1.03] | 301.98 / 274.90 = 1.10 | A 7.53%; B NOT_MEASURED | post_action_sleep 51.0; reveal 1409.7 | 1458.4 [1458.0, 1460.2] |
| R2-10R (R'), L-scripted (scripted chooser; native T excludes provider decisions) | REAL, BENCHMARK (FIXTURE, GTK3, private Xvfb + AT-SPI) | 24 | BASE 1.000; S0 1.000; X 1.000; e4 0 violations | 1761.3 | 298.9 | 5.89 [5.87, 5.90] | 1.03 [1.03, 1.03] | 299.38 / 273.27 = 1.10 | A 6.89%; B NOT_MEASURED | post_action_sleep 51.0; reveal 1410.3 | 1462.1 [1461.0, 1464.0] |
| N-04 (R'n), L-scripted (scripted chooser; native T excludes provider decisions) | REAL, BENCHMARK (FIXTURE, GTK3), UNIT | 24 | k1_tasks 192; k5_tasks 240; best_arm_valid_share 1.000; e4_best_arm 0 violations | 1764.1 | 296.9 | 5.941 [5.938, 5.957] | 1.030 [1.030, 1.031] | 296.57 / 272.37 = 1.089 | A 1.65%; B 2.62% | post_action_sleep 51.08; reveal 1410.58; action_transport.admission_v 3.39; observation_transport.admission_v 1.35; V admission work 4.35 | 1468.03 [1466.60, 1468.91] |
| N-03 (N3), L-scripted (superseded for E2/E3 by N-04 on R'n) | REAL, BENCHMARK (FIXTURE, GTK3), UNIT | n/a | hcl_rows_valid_verified 168; hcl_rows 168 | NOT_MEASURED | mean 304.98 | NOT_MEASURED | NOT_MEASURED | 304.98 / 278.29 = 1.096 | A 2.02%; B 3.14% | V admission work 5.77 | V 5.15 [3.51, 8.04] |

- **R2-10 (R)** components (mean ms, material or >= 1 ms): settle 240.94 ms (79.79%): IRREDUCIBLE (R2-10 mapping (this packet)); action_transport 20.56 ms (6.81%): UNTESTED (R2-10 mapping (this packet)); observation_transport 19.37 ms (6.41%): IRREDUCIBLE (R2-10 mapping (this packet)); observation 11.27 ms (3.73%): IRREDUCIBLE (R2-10 mapping (this packet)); reveal 4.26 ms (1.41%): OWNER_DECISION (R2-10 mapping (this packet)); dispatch 2.54 ms (0.84%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 1.60 ms (0.53%): UNTESTED (R2-10 mapping (this packet))
  - untested mappings: A = R2-10 mapping (observation transport IRREDUCIBLE)
  - T_land vs T_oracle (medians): BASE 1461.0 vs 1760.9 ms; X 52.9 vs 300.9 ms
  - S at T_land: paired S at T_land is not in R2-10's summary; the R2-10 verifier note (S_land about 1.00 checkbox) is not recomputed here
- **R2-10R (R')** components (mean ms, material or >= 1 ms): settle 241.25 ms (80.58%): IRREDUCIBLE (R2-10 mapping (this packet)); action_transport 18.51 ms (6.18%): UNTESTED (R2-10 mapping (this packet)); observation_transport 17.83 ms (5.96%): IRREDUCIBLE (R2-10 mapping (this packet)); observation 10.85 ms (3.62%): IRREDUCIBLE (R2-10 mapping (this packet)); reveal 5.41 ms (1.81%): OWNER_DECISION (R2-10 mapping (this packet)); dispatch 2.59 ms (0.87%): IRREDUCIBLE (R2-10 mapping (this packet)); resolution 1.56 ms (0.52%): UNTESTED (R2-10 mapping (this packet))
  - untested mappings: A = R2-10 mapping (observation transport IRREDUCIBLE)
  - T_land vs T_oracle (medians): BASE 1461.4 vs 1761.3 ms; X 50.9 vs 298.9 ms
  - S at T_land: X 28.69 [28.68, 28.72], S0 1.00
- **N-04 (R'n)** components (mean ms, material or >= 1 ms): settle 241.54 ms (81.44%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); observation_transport 16.67 ms (5.62%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); action_transport.client_validate 12.54 ms (4.23%): OWNER_DECISION (N-04 primary (R2-10 labels + V/HCL verdicts)); observation 10.61 ms (3.58%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); reveal 6.69 ms (2.26%): OWNER_DECISION (N-04 primary (R2-10 labels + V/HCL verdicts)); dispatch 2.50 ms (0.84%): IRREDUCIBLE (N-04 primary (R2-10 labels + V/HCL verdicts)); resolution 1.52 ms (0.51%): UNTESTED (N-04 primary (R2-10 labels + V/HCL verdicts)); action_transport.drv_inner_post 1.01 ms (0.34%): UNTESTED (N-04 primary (R2-10 labels + V/HCL verdicts))
  - untested mappings: A = primary R2-10 reading; B = conservative N-02 reading (observation-transport client validation counted)
  - T_land (medians) BASE 1464.44 / best 48.92 ms; S at T_land best 29.938 [29.897, 31.154], KEEP-only 1.001
  - verdicts: V DELETED, HCL OWNER_DECISION
  - HCL per 5-task session 73.69 ms; HCL at k=1 0.34 ms
  - V T saved (k=1) 3.04 [2.01, 3.91] ms
- **N-03 (N3)** components (mean ms, material or >= 1 ms): none decomposed in this lane
  - untested mappings: A = primary R2-10 reading; B = conservative N-02 reading
  - verdicts: V DELETED, HCL OWNER_DECISION
  - HCL per 5-task session 101.42 ms

### Owner-decision dependency

The large browser speedups depend on owner decisions. With KEEP-only deletions (feedback glide, H_T settle and endpoint re-proof left at their defaults), browser S is about 1.01 (fill amortized ratio of means 0.98); native KEEP-only S is about 1.18 checkbox and 1.03 text (cursor reveal left at its default).

- Browser KEEP-only S: R2-10_fill 1.01, R2-10_fill_amortized 0.98, R2-10_toggle 1.01, R2-10_modal 1.01, R2-10R_fill 1.01, R2-10R_fill_amortized 0.98.
- Native KEEP-only S: N-04_checkbox 1.180, N-04_text 1.030, R2-10_checkbox 1.18, R2-10_text 1.03.
- Owner items behind the difference: browser feedback glide off/fast (B-01; the single largest component, 94-97% of BASE T); B-01 H_T 100 ms insert_text focus settle; B-02 H_E endpoint re-proof bound check (security policy); native cursor reveal (N-01R H_C; text S 5.9 vs KEEP-only 1.03); HCL lazy validators (session shape); B-06 amended reading of the per-process cold excess; R2-08 API route per task.

### Live-layer gaps

- **R' live layer (R2-10 recertification with TypeSafe on 0f1955d2f): BLOCKED.** paid budget: >= 180 reached needed; 38 of the loop's 600 remained after wave 5
- **live toggle/modal provider decisions (about 88-89% of live COMP T in R2-10): UNTESTED.** BLOCKED by budget; modal also needs a passing non-regression gate (R2-07d modal FAIL) (toggle_provider_ms 434.8, toggle_provider_share 88.29%, modal_provider_ms 462.4, modal_provider_share 88.99%)
- **R2-07e (new pre-registered modal gate + Phase L): PENDING.** wave-6 lane running; refresh in wave 7
- **native live arms (native T including provider decisions): BLOCKED.** owner decision (may native T exclude provider decisions?) or paid budget >= 120 reached

### References only (never gates or targets)

- **PreAct** reports 8.5-13x warm replay acceleration. Differences from this table:
  - benchmark: PreAct's own small benchmark subsets, not the jev-use fixture classes or the GTK3 fixture
  - scope: warm replay of compiled programs only; this table's S is whole-task verified time (first observation to independent oracle) over every invocation, including first-run/compile/admission and fallback
  - baseline: PreAct's baseline is its own agent loop; this table's BASE is the default Driver path with feedback glide on, so most of our S comes from owner-decision deletions, not replay
  - verification: PreAct checks compiled programs before storage; our compiled routine (R2-07b) also needs fresh authority per replayed mutation; out-of-domain reuse degrades in PreAct and is not claimed here
  - provider: our live rows use TypeSafe; scripted rows use no provider
- **SkillDroid** reports about 2.4x, pure replay only. Differences from this table:
  - 35 pure replay rounds were zero-LLM, not all 79 Layer-2 rounds (SkillDroid section 5.1, Tables 2-3, as recorded on kvnloo/cua#93); the other Layer-2 paths include model-assisted matching or step fallback
  - benchmark: Android app tasks, not jev-use browser classes or GTK3
  - scope: pure replay subset, not a whole-workload or CUA speedup; this table measures all attempted invocations

<!-- END GENERATED: make_accounting.py -->
