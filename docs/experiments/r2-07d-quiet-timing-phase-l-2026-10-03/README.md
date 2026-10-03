# R2-07d: quiet-window timing block for the toggle/modal compiled routine, then live Phase L, 2026-10-03

Lane R2-07d, wave 5 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-07 family), kvnloo/cua#10
(accounting), kvnloo/cua#74 (posting queue). This is a new block that reports alongside R2-07c
(branch `exp/r2-07c-toggle-modal-compiled-a2-20261003`, commit 7f46edd16). It does not edit R2-07c.
Upstream items are named as plain text (trycua/cua PR 4316).

## Result in one paragraph

**Disposition: REVISE.** The failing gate is the pre-registered timing non-regression gate in the
**modal** class. Phase S ran 40/40 AB/BA pairs per class in one EXCLUSIVE window, and every pair
started at a 1-min loadavg of 2.96 or less (83 gate attempts, 82 starts, 1 chunk ends). Every
timing cell was verified, and the correctness carry-over held: G1/G2, G3 84/84 fresh per class, 0 E4,
and controls 35/35 pass. Paired diff T(COMP+CR) - T(COMP):

- **toggle:** +0.5 ms [-1.3, +0.8], medians 47.4 -> 47.9 ms, so the toggle gate PASS.
- **modal:** +0.6 ms [-1.4, +2.4], medians 47.5 -> 47.9 ms. The CI upper bound is above the
  +2.0 ms limit, so the modal gate FAIL.

PREREG makes Phase S passing in BOTH classes a precondition for Phase L, so the live TypeSafe arm
was **NOT_RUN**. Provider: 0 attempts / 0 reached (lane cap 18 / 22 unused). The live toggle/modal
provider-decision component (R2-10: 434.8 / 462.4 ms, 88-89% of live COMP T) therefore stays
**UNTESTED**. It is not DELETED. Under the pre-registered rule, the compiled routine is **excluded**
from the composed toggle/modal configuration.

## Headline (evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| Phase S toggle, COMP vs COMP+CR | 40/40 pairs valid | median T 47.4 -> 47.9 ms; paired diff +0.5 ms [-1.3, +0.8] (21/40 positive); S = 0.991 [0.987, 1.028]; toggle gate PASS | REAL+BENCHMARK |
| Phase S modal, COMP vs COMP+CR | 40/40 pairs valid | median T 47.5 -> 47.9 ms; paired diff +0.6 ms [-1.4, +2.4] (25/40 positive); S = 0.991 [0.987, 1.027]; modal gate FAIL | REAL+BENCHMARK |
| Sensitivity view (exclude pairs with either trial started above 3.0) | 40/40 per class kept | identical to the gate rows (trial-start loadavg max 2.96) | REAL+BENCHMARK |
| Load gate | 83 gate attempts, 82 starts, 1 chunk ends | chunk Q1 ended at load 4.84 -> 3.14 after 60 s (0 trials); chunk Q3 ran all 82 units (one 5 s wait) | REAL |
| G1 / G2, block Q (training + compile + clean-reset admission) | toggle 1/1 + 1/1, modal 1/1 + 1/1 | verified, compiled, authority-clean; admission verified with 0 fallback and 0 decisions | REAL |
| G3 fresh binding, block Q | 84/84 toggle, 84/84 modal accepted mutations fresh | 0 non-fresh dispatch attempts | REAL |
| E4, block Q (both arms) | 0 violations over 164 cells | 0 stale dispatch, ambiguous dispatch, duplicate, unverified success, refusal returned as success, blind replay or dispatch after unknown | REAL |
| Warm COMP+CR cells in block Q | 40/40 + 40/40 valid | route compiled only, 0 decisions, 0 fallbacks | REAL |
| Controls block C (carry-over smoke) | controls 35/35 pass | G4 19/19, N-W2 2/2, G5 4/4, default smoke 10/10; G3 36/36 fresh, 2/2 non-fresh refused `effect=refused`; 0 E4 | REAL; G5 FIXTURE (reconcile seam) + REAL |
| Unit | 6/6 + 19/19 | `driver/test_r2_07d.py` (gate, unit grouping, plan counts); R2-07c `harness/test_compiled_routine_tm.py` carry-over | UNIT |
| Phase L live COMP+CR (TypeSafe) | 0/58 warm invocations | NOT_RUN: pre-registered precondition (Phase S passes in both classes) failed in modal | NOT_RUN |
| Paired live BASE vs COMP+CR S | - | BLOCKED: budget (needs >= 120 reached) | BLOCKED |
| Provider | 0 attempts / 0 reached | lane cap 18 reached / 22 attempts, unused | LIVE_PROVIDER (none sent) |

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | COMP: R2-10 COMP trial, unchanged (`r2_07c.one_comp` -> `rb10.one`): feedback OFF, 10 ms completion poll, compiled validators, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`, phase trace on, scripted chooser decides each click. COMP+CR: the same Driver configuration plus compiled replay of the admitted artifact (`r2_07c.one_c`), with a fresh `semantic_v2` observation before every click and 0 decisions. Each trial record carries its arm config, Driver env and receipts | REAL |
| Actual route / producer | From the launcher's Driver-call receipts: two `browser_click` with `input_route=dom_event`, receipt route `dom`, and a `click.cdp_send` mark inside each click window (R2-10 `browser_row`). Warm/admission cells: route `compiled` only, 0 decided events, 0 provider requests. COMP and training cells: 2 `provider` decisions from the scripted chooser | REAL |
| Independent target-owned oracle | jev-use #24 fixture server state + journal (toggle `checked` true; modal `opened` and `modal` true), sampled every 2 ms by an independent harness thread (`rb10.Sampler`), never the runner; exactly 1 completion mutation from the journal; T_oracle by the R2-10 caller-side rule | REAL |
| Negative / fallback controls | block C: N1-N8 (incl. N4a stale ref refused then rebound, N5 old capability refused, N8 wrong page dispatches nothing), N-W2, G5 applied_ack_lost + withheld, default smoke; all discriminating (see Controls) | REAL / FIXTURE |
| Tested source SHA | `7f46edd1681fbf58586f8b4972636c3da56e3be6` (R2-07c packet commit; Driver source `8f3a646b4818b757648835cf89db8886626b1cf0`, `libs/cua-driver` tree `bf8e7bdc90fdce295e44743f2754a6502d5d6e0e` at both). No Driver change in this lane | SOURCE |
| Harness identity | R2-07c `harness/` tree `66bad345b1736b97b66884bbf40a1505c16083bf` (49 files) and `analyze_r2_07c.py` blob `dab482887210fc68ab13a325aae55bd09388ac4d`, unchanged at every commit of this branch (`verify_artifacts.py` check 1). The harness runs in place, so G1-G6 carry over | SOURCE |
| Driver binary | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9`, `cua-driver 0.32.0`. Re-hashed on the host at the start (07:20Z) and end (12:01:38Z), identical. Inside every session the runner re-hashes it, refuses on a mismatch and reads the version (run manifests; every COMP+CR record) | SOURCE |
| Environment | one Linux host; every code-executing command under `hostless`; Driver/Chrome inside `cua-x11-session.sh` (private Xvfb + D-Bus) with a 0-2.9 s start jitter and an `xdpyinfo` probe before any trial; Google Chrome 151.0.7922.71 (the Driver's root-owned candidate), isolated profile; telemetry off; Chromium sandbox on; default Driver safety settings; trial-start 1-min loadavg 1.82-2.96 in the timing window | SOURCE |
| PREREG commit | `935d6f67a`, committed 2026-10-03T07:28:22Z, before the first post-PREREG trial (controls, 07:28:41Z) and the first timing trial (11:57:35Z) | SOURCE |
| Live heads at test time | start 07:18:54Z: upstream main `cb685fad7aef1df6a35ffec653295a0cea4daee6`, trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556` (open). End 12:01:38Z: upstream main `379085c5e267451db8d52989f47bd9fb85ab38ef` (14 commits; `libs/cua-driver` changes only under platform-macos, platform-windows, cua-driver-e2e, Skills and tests/fixtures, none on a Linux, browser or jev-use path), PR 4316 head unchanged (open) | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); not assumed equal to the tested SHA | SOURCE |
| Live heads at publication | set by Publish (`provenance.json: live_heads_at_publication`) | SOURCE |
| Provider | TypeSafe, 0 attempts / 0 reached (Phase L NOT_RUN); `TYPESAFE_API_KEY` never forwarded (the runner refuses if present) | NOT_RUN |

## Method

- **Block Q (Phase S timing).** `driver/r2_07d.py --plan timing_q --rounds 40` calls
  `r2_07c.build_plan("timing", 0, 40)`. The plan is one training (+compile + clean-reset admission)
  per class into store `timed`, then 40 rounds. Round r alternates the class order every 2 rounds
  and the arm order every round (AB on even r, BA on odd r), as in R2-07c. Each trial gets a fresh
  Driver, Chrome, loopback fixture servers, token and session label.
- **Load rule (pre-registered).** A unit (a training, or one pair = both arms of one class in one
  round) starts only when the 1-min loadavg is <= 3.0. Otherwise the runner polls every 1 s for up
  to 60 s inside the acquisition, then ends the chunk (exit 75) and resumes the same unit indices
  later. Every gate attempt is in `raw/q-load-gate.jsonl`.
- **Locks.** Each measured chunk takes `cargo-build.lock` first, then `bin/quiet-timed R2-07d-Q<n>`
  (EXCLUSIVE + receipt in the loop ledger). No new unit starts after 480 s, and the session is capped
  at 600 s. Q1 (07:45:06-07:46:13Z) ended at the gate with 0 trials. Q3 (11:57:28-12:00:47Z, 3.2 min
  held) ran all 82 units. The receipts are in `raw/lock-receipts-global.jsonl`.
- **Gate.** Per class: median paired diff T_oracle(COMP+CR warm) - T_oracle(COMP) with a 95% seeded
  paired bootstrap CI (`b01_analysis.paired_diff`, seed 20261002, 10000 resamples). PASS iff the CI
  upper bound is <= +2.0 ms, all 40 pairs ran, and every timing cell is valid. Phase S passes in a
  class iff that gate, G1/G2, G3 and E4 all pass.
- **Controls (block C).** These ran under the SHARED quiet-lane lock, <= 10 cells per acquisition:
  - 1 training (+admission) per class into store `scripted`;
  - G4 1 rep per row per class (19 cells);
  - N-W2 1 per class;
  - G5 applied_ack_lost and withheld_unresolved, 1 per class;
  - default smoke: the R2-10 BASE arm via `rb10.one` with kind `smoke` (no `CUA_DRIVER_EXP_*`
    variable, no phase trace, feedback on, 100 ms poll), 5 per class.
- **Analysis.** `analyze_r2_07d.py` reuses the R2-07c analysis (`row_of`, `g4_pass`, `nw2_row`,
  `decomposition`, `e4_total`) and the R2-10 per-trial row, unchanged, by import. It writes
  `r2-07d-summary.json` and `headline-numbers.json`.

## Results

### Phase S timing (REAL+BENCHMARK, chunk Q3)

| class | median T COMP | median T COMP+CR | paired diff CR-COMP (median, 95% CI) | S = COMP/CR | 1-min loadavg at trial start | gate |
|---|---|---|---|---|---|---|
| toggle | 47.4 ms | 47.9 ms | +0.5 ms [-1.3, +0.8], range -10.9 to +6.5 | 0.991 [0.987, 1.028] | 1.82-2.96 (median 2.29) | PASS |
| modal | 47.5 ms | 47.9 ms | +0.6 ms [-1.4, +2.4], range -7.4 to +8.5 | 0.991 [0.987, 1.027] | 1.82-2.96 (median 2.30) | FAIL |

For comparison only (same binary and harness, not pooled): R2-07c measured the same contrast at a
loadavg of 8-32 with a per-pair spread of about +-100 ms. At a loadavg below 3 the per-pair range is
-11 to +9 ms, and both medians of T fall from about 83-95 ms to about 47-48 ms. The modal CI upper
bound misses the +2.0 ms limit by 0.4 ms. The packet reports that as a FAIL under the pre-registered
rule and does not reinterpret it.

### Component decomposition, mean ms over the 40 valid timing cells per arm (R2-10 e2_components, coverage 0.99)

| component | toggle COMP | toggle COMP+CR | modal COMP | modal COMP+CR |
|---|---|---|---|---|
| observation | 13.3 | 13.9 | 13.6 | 13.9 |
| endpoint revalidation | 20.3 | 20.1 | 20.5 | 20.5 |
| other revalidation | 2.2 | 2.3 | 2.1 | 2.3 |
| MCP transport | 4.3 | 4.3 | 4.4 | 4.5 |
| MCP admission | 1.5 | 1.5 | 1.6 | 1.5 |
| visualization | 1.8 | 1.8 | 1.7 | 1.7 |
| resolution | 1.2 | 1.2 | 1.0 | 1.1 |
| dispatch | 1.0 | 1.0 | 1.2 | 1.2 |
| verification reads | 1.1 | 0.5 | 1.0 | 0.5 |
| client validation / runner / sleeps / unattributed | 1.4 | 1.4 | 1.5 | 1.4 |
| mean T_runner | 48.0 | 48.0 | 48.8 | 48.6 |

Both arms do the same Driver work. The routine deletes the scripted chooser and the candidate builds,
which take under 0.1 ms with the mock chooser, plus the per-step pre-oracle reads (verification reads
about -0.5 ms). Its fresh observation before the second click costs about +0.3 to +0.6 ms.

### Costs in the timing window (REAL+BENCHMARK)

| cost | toggle | modal |
|---|---|---|
| training (R2-10 COMP step loop, 2 scripted decisions), T_oracle | 81.1 ms | 47.7 ms |
| compile | 0.181 ms | 0.110 ms |
| clean-reset admission replay, T_oracle | 47.8 ms | 49.9 ms |
| warm replay | 40/40 valid, 0 fallbacks, 0 decisions | 40/40 valid, 0 fallbacks, 0 decisions |

### Controls (block C, REAL; 1 rep per row per class)

| row | toggle | modal |
|---|---|---|
| N1 renamed / N2 missing: routine stops at the failed precondition, 0 completion mutations, not verified | 1/1, 1/1 | 1/1, 1/1 |
| N3 duplicate: ambiguous precondition, the continuation drops the non-unique candidate, 0 completion | 1/1 | 1/1 |
| N4a stale ref: node replaced, action 2 refused `browser_ref_stale` with Driver `effect=refused`, one rebind (3 observations), verified, 1 completion | 1/1 | 1/1 |
| N4b superseding snapshot: non-fresh attempt refused `effect=refused`, one rebind, verified | 1/1 | 1/1 |
| N5 session replaced: old capability refused (`authorization_host_failed`), fresh bind, verified | 1/1 | 1/1 |
| N6 unexpected dialog: `dialog_opened` journaled, routine stops before action 2, 0 completion | 1/1 | 1/1 |
| N7 precondition already satisfied: routine dispatches nothing, the continuation verifies with exactly 1 accepted mutation | 1/1 | 1/1 |
| N8 wrong page (toggle on fill, toggle on modal; modal on toggle): 0 accepted mutations, 0 completion | 2/2 | 1/1 |
| N-W2 stale action: refused `browser_ref_stale` (`effect=refused`), 0 mutations from it, fresh re-derivation verified | 1/1 | 1/1 |
| G5 applied_ack_lost: `verified_by_reconcile`, 1 completion, no re-dispatch | 1/1 | 1/1 |
| G5 withheld_unresolved: stays `unknown` (the effect lands only after the harness releases it), no re-dispatch | 1/1 | 1/1 |
| default smoke (BASE, no experiment variable, no trace): verified, exact match, 1 completion | 5/5 | 5/5 |

These match R2-07c's rows (5 reps there), which is what shows the harness and Driver behaviour are
unchanged.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Evidence class |
|---|---|---|---|
| compiled routine, toggle (scripted) | 2 chooser decisions + 2 candidate builds per warm invocation (< 0.1 ms with the mock), pre-step oracle reads (-0.6 ms mean); adds one fresh observation (+0.6 ms mean) | paired median +0.5 ms [-1.3, +0.8]: non-regression shown (CI upper <= +2 ms); no saving shown | REAL+BENCHMARK |
| compiled routine, modal (scripted) | same (-0.5 ms reads, +0.3 ms observation) | paired median +0.6 ms [-1.4, +2.4]: non-regression NOT shown | REAL+BENCHMARK |
| live provider decisions (R2-10: 434.8 / 462.4 ms, 88-89% of live COMP T) | not measured: Phase L NOT_RUN | not measured | NOT_RUN |

## Deviations

1. **Lock acquisition mechanics changed after PREREG.** The arms, plan, gate and metrics did not
   change. Q2 (07:46Z) waited 30 min while holding `cargo-build.lock` for the EXCLUSIVE quiet-lane
   lock, which back-to-back SHARED holders starved. That blocked five other lanes' builds. The lane
   stopped its own Q2 process tree (exact PIDs, before any lock acquisition, trial or gate attempt)
   and changed `driver/run_chunk_d.sh` in two steps:
   - first, hold the cargo lock only while a probe finds the quiet lock free (exit 74 if busy,
     nothing run);
   - then (11:55Z) make that probe a blocking exclusive wait capped at 240 s, after a 90 s
     non-blocking poll variant rarely found a gap.

   Each change restarted the loop between tries. `raw/q-loop.log` records Q1, Q2 and both
   restarts. Q3 ran under the final version, with the cargo lock held for the whole window.
2. **Pre-PREREG shakedowns** (SHARED, scripted, 0 TypeSafe requests) are excluded and kept:
   - `shake-q` (the gate ended the chunk at load 5.7-6.6, 0 trials);
   - three `R2-07d-shake-c` acquisitions that exited at argument parsing (rc 2, 0 trials; a
     shell word-splitting mistake);
   - `shake-c1..c3` (9 cells).
3. `analyze_r2_07d.py`, `driver/package_d.py`, `verify_artifacts.py` (beyond its privacy/identity
   part) and `headline-numbers.json` were written or completed after the PREREG commit. They
   implement the PREREG metrics.
4. Chunk and unit logs in `raw/` drop the private-session noise lines: `[session]` lines,
   dbus-daemon activation lines, and lines naming a local absolute path such as the session run dir
   or a fuse mount. The per-file counts are in `raw/package-report.json`. The trial JSONL bundles
   are unfiltered.
5. Phase L was not run, so neither was its live shakedown.

## Limits and claim boundary

- One host, private Xvfb, Google Chrome 151 (system), binary R (sha256 `12b9045a...`), the jev-use
  #24 toggle/modal fixture, scripted chooser only. No TypeSafe number is claimed and no model id was
  recorded, because no live request was made.
- The modal gate fails by 0.4 ms of CI width. This packet does not claim a regression mechanism
  (the decomposition shows the same Driver work). It also does not claim non-regression for modal.
- The toggle pass is one class of the two the pre-registered rule requires.
- The routine is caller-side only: no new service, registry, router or engine. Logical routine
  identity persists in the artifact (role+name targets, preconditions). Refs, tokens, captures,
  capabilities and session epochs do not, and all 6 artifacts in `raw/artifacts/` pass the
  authority scan.
- The paired live BASE vs COMP+CR S is BLOCKED on budget (it needs >= 120 reached). Phase L would
  never be compared with R2-10's live numbers as an S.

## Disposition

Disposition: REVISE.

- **Failing gate:** timing non-regression in the modal class, CI upper +2.4 ms > +2.0 ms.
- **What passed:** toggle timing, G1/G2/G3, E4 0, controls 35/35, and the authority scan.
- **Phase L:** NOT_RUN by its pre-registered precondition.
- **E2:** the live toggle/modal provider-decision component stays UNTESTED. It is not DELETED.
- **E3:** the compiled routine is excluded from the composed toggle/modal configuration.
- **Not an E4 KILL candidate:** there were 0 E4 violations.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration (commit `935d6f67a`) |
| `README.md` | this file |
| `.gitignore` | packet-local overrides (template), re-includes `raw/artifacts/` |
| `provenance.json` | the provenance fields above; `publication_sha` set by Publish |
| `r2-07d-summary.json` | full analysis output |
| `headline-numbers.json` | headline numbers with the exact README text |
| `analyze_r2_07d.py` | the analysis (imports the R2-07c analysis unchanged) |
| `verify_artifacts.py` | 11 checks: harness identity, PREREG before trials, summary recompute, headlines, authority, cited files, privacy of every commit (4 sub-checks). Run under hostless; `--skip-git` on an export |
| `driver/r2_07d.py` | load-gated Phase S runner + controls plan (imports `r2_07c` unchanged) |
| `driver/run_chunk_d.sh` | locks + private session wrapper |
| `driver/probe_then.sh` | xdpyinfo session probe |
| `driver/test_r2_07d.py` | unit tests of the R2-07d additions |
| `driver/package_d.py` | packaging + privacy scan (uses R2-07c `harness/package_raw.py` unchanged) |
| `raw/q-trials.tar.gz` | block Q per-trial JSONL + Driver traces (164 trial records: 2 trainings, 2 admissions, 160 timing cells) |
| `raw/q-load-gate.jsonl`, `raw/q-progress.json`, `raw/q-loop.log` | load gate attempts, unit progress, loop log |
| `raw/q-manifests/`, `raw/q-routines/`, `raw/q-chunk-logs/` | chunk manifests (Q1, Q3), routine store, chunk logs |
| `raw/ctl-trials.tar.gz`, `raw/ctl-manifests/`, `raw/ctl-routines/`, `raw/ctl-chunk-logs/` | controls block C |
| `raw/shake-q-*`, `raw/shake-c-*` | pre-PREREG shakedowns (excluded) |
| `raw/artifacts/` | 6 compiled artifacts (q, ctl, shake-c) |
| `raw/lock-receipts-global.jsonl`, `raw/lock-receipts-lane.jsonl` | quiet-lane ledger lines labelled `R2-07d-*`; lane ledger |
| `raw/unit/` | unit outputs |
| `raw/package-report.json` | packaging report incl. dropped noise-line counts |
