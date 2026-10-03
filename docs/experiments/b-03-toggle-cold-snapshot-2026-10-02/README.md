# B-03: toggle cold-first-snapshot excess, per-process vs per-document, 2026-10-02

## Result in one paragraph

**Part 1 (BENCHMARK re-analysis of B-02 raw/, no trials).** The spec-literal best arm is K5EV in every class. Its median T_oracle is 115.9 / 79.8 / 83.0 ms for fill / toggle / modal. Every component of at least 5% or 50 ms now has a verdict with a source packet. The B-02 untested-share rule gives:

| Class | K5V | K5EV |
|---|---|---|
| fill | 1.6% | 1.9% |
| modal | 2.2% | 2.8% |
| toggle | 22.1% | 32.4% |

So modal (K5EV) is now decomposed and is under 5%. Toggle is the only browser class still at or above 5%, under both best-arm readings.

**Part 2 (REAL + BENCHMARK, 227 trials).**

- 220 measured trials plus 7 excluded shakedown trials. 220/220 measured trials were verified by the target-owned oracle. Validity was 100% in every cell, with 0 stale dispatches, 0 duplicate mutations and 0 unverified successes.
- **The pre-registered negative control failed.** A same-document re-snapshot with no navigation still showed an excess of 1.9 ms [0.5, 2.6], so its CI excludes 0. Under the analysis committed before the measured block, a failed gate makes the toggle cold-excess verdicts **UNDECIDED**.
- The pre-registered fill positive replication also failed. Fill's per-process part is 6.6 ms [1.7, 14.7], 28% of fill's excess, below the 50% that "moved only" requires.

**Toggle's untested share therefore stays at or above 5%:** 22.3% (K5V) and 32.1% (K5EV), restated on B-02's E2 rows (27.7% / 37.7% in this block's own cold D0 cells).

**Mechanism.** The probe still settles what the excess is. In both knob sets an 80 ms wait after navigate (first observation about 81–82 ms after navigate returns) removes almost all of it, including the per-process part that exists at D0 (post hoc: 17.5 [13.7, 21.8] ms for K5EV, 64% of E): the cold excess falls from 19.3 to 1.3 ms (K5V) and from 27.4 to 1.3 ms (K5EV). That holds in the cold process as well as the warm one. As a result:

- The spec's per-process contrast, measured at D=80, is close to zero: 0.4 ms [−0.2, 2.6] (K5V) and 1.3 ms [0.2, 3.3] (K5EV).
- Waiting never pays. T_oracle including the wait is 64.7 ms [58.1, 70.9] (K5V) and 53.8 ms [41.6, 58.8] (K5EV) *slower* than snapshotting at once.
- Pre-warming the process saves snapshot time but costs more than it saves. Warm T_oracle including the warm-up is 124.1 / 53.6 ms slower than cold.

If the failed negative-control gate were waived (post hoc, **not a verdict**), the rules would give:

- per-document part: IRREDUCIBLE;
- per-process part: UNDECIDED (1.3 / 2.4 ms);
- toggle untested share: 3.1% (K5V) and 5.3% (K5EV), restated on B-02.

TypeSafe: 0 attempts, 0 reached.

## Scope and owners

- Lane B-03, wave 3 (experiment). Owners: kvnloo/cua#93 (R2 follow-ups), kvnloo/cua#10 (whole-task accounting), kvnloo/cua#73 (B-02 publish fix, best-arm rule).
- What this lane advances:
  - **E2:** a decisive mechanism probe of toggle's last browser gap, B-02's H_W UNDECIDED; and the K5EV decomposition for every class.
  - **E1:** closes the B-02 H_W follow-up with a disposition (see Disposition).
- What this lane does not do:
  - No Driver change and no rebuild; no knob was added or changed.
  - No new service, shadow state, router, registry, batch API, event service or warm pool.
  - The warm-up arm is a harness-side measurement only. Events are not used as oracle.
- Pre-registration:
  - `PREREG.json`: commit `2edc0bee2`, 17:26:25Z. It precedes the shakedown (first trial 17:27:22Z) and the measured block (17:32:49Z).
  - `PREREG-AMENDMENT-1.json`: commit `2549fc1e8`, 17:30:48Z, before the measured block. It redefines the stale-dispatch invariant, which the shakedown showed was wrong (Deviation 1), and adds two descriptive measures.
  - `PREREG.json` was never edited.
  - The post-hoc block in `analyze_b03.py` (`post_hoc` in `b03-summary.json`) was added after the measured block. `verify_artifacts.py` checks that every other key of the summary equals the output of the pre-registered analyzer at `2549fc1e8`.

## Provenance (each SHA separate)

| Item | Value | Evidence class |
|---|---|---|
| Lane base | `b282ff3894fa85a7b82257cb1edd5088c2f0ac37` (exp/b-02-browser-driver-sites-20261002 head, B-02 accepted packet) | SOURCE |
| Tested Driver source | `f5c991e5927513c8b94da4330c94276dc5f8ce22` (B-01 source: upstream main `229b65b28` + R2-01 trace `7d3a28b66` + trycua/cua PR 4316 merge `0c6a53237` + B-01 marks) + `560bd8247c36c9d249f481b509a073c131e93620` (B-02 marks and knobs, default off) | SOURCE |
| Driver binary | `cua-driver-b02-560bd8247`, sha256 `7e6c06090fa2f2b63152a9276fe3a4766f88d2d5cbe7b412236208ee537bd3a0`, `cua-driver 0.32.0` (read inside `cua-x11-session.sh`). Re-hashed at the start (17:21:53Z) and the end (17:46:14Z): identical. Not rebuilt. This binary **predates FIX-01** (dom_event `isConnected` refusal). No arm here re-renders or replaces a node between snapshot and dispatch, so the detached-node path is not exercised | SOURCE |
| Packet commits | PREREG + runner + Part 1 `2edc0bee2`; amendment + analyzer + shakedown raw `2549fc1e8`; results commit (this README) | SOURCE |
| Harness | `run_b03.py`. It is B-01's `run_critpath.run_trial` step loop reproduced with three insertions, each marked `B-03`: the P warm-up, the D delay and the nc pre-snapshot. It uses B-02's `run_b02` knob plumbing and `rc.one` bookkeeping. B-02's files are imported in place from `../b-02-browser-driver-sites-2026-10-02/` and are byte-identical to `b282ff389` (`verify_artifacts.py`) | SOURCE |
| Live trycua/cua PR 4316 head (gh) | `a0bca744067d04f05904319d3d919be30c336556`, open, read at 17:46Z. It equals the head merged into the tested source | SOURCE |
| Upstream main (gh, 17:46Z) | `da46c4bc85bc43f9641d3ce4b6f319e6d7b6c1a9`: 45 commits and 437 files ahead of `229b65b28` (local `git diff --name-only`; the 300 first reported is the GitHub compare-API cap), **18 of them under `libs/cua-driver`** (that count stands). None touches the browser engine, the snapshot/CDP code or Linux `browser_platform.rs`. They touch contract/compatibility, `cua-driver-core/src/tool_schema.rs` (element_token schema constraints, trycua/cua PR 4318), the doctor, skills, Linux Wayland/Hyprland, macOS and Windows. `tool_schema.rs` feeds the admission validation, so the admission residual is the one number here that a later source could shift. Recertify before R2-10 cites it | SOURCE |
| Publication SHA | set by the Publish agent; this lane did not push | — |
| Provider | scripted mock chooser (`choose_mock_for_task`); TypeSafe attempts 0, reached 0; every runner manifest records 0 non-loopback connects | REAL |

## Environment

- Linux 7.2.2 x86_64, 10 CPUs, shared with the i107, stack, ar, own75r, n02, FIX-02 and R2-10 tracks. Cargo builds held the cargo lock but not the quiet-lane lock during both measured windows.
- 1-minute loadavg per trial was 13.03–25.37 across the measured block. Every value is in `per_trial`.
- Isolation:
  - Every code-executing command ran as `TMPDIR=<lane-tmp>/w3-b03 hostless …` (hostless v2).
  - Every browser and Driver command also ran inside `cua-x11-session.sh`: private rootless Xvfb 1920x1080x24, openbox, picom, private dbus, `env -i`. Extra environment: `CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"`. Every Driver received `CUA_DRIVER_RS_TELEMETRY_ENABLED=0` (`forced_path.telemetry_env`).
  - B-02 ran with telemetry at its default, so absolute times are not compared with B-02 (Deviation 3).
- DISPLAY: `:102` for the shakedown, `:99` for both measured chunks (`raw/*/…session.log`, manifests).
- Browser: the Driver-chosen system Chrome, launched by `browser_prepare {allow_launch, isolated_new}`. Sandbox on, a fresh isolated profile per trial, no user profile.
- Locks (`raw/lock-ledger.jsonl`, verbatim quiet-timed ledger lines):

| Block | Lock | Window |
|---|---|---|
| measured chunk A, rounds 0–9 (110 trials) | EXCLUSIVE `b03-measured-a` | 17:32:42.554Z–17:35:21.360Z; runner 17:32:49.013Z–17:35:20.331Z |
| measured chunk B, rounds 10–19 (110 trials) | EXCLUSIVE `b03-measured-b` | 17:40:33.996Z–17:43:27.744Z; runner 17:40:40.827Z–17:43:26.816Z |
| shakedown (7 trials, excluded) | SHARED, runner-acquired | 17:27:22.949Z–17:27:35.341Z |

  Each chunk lasted under 3 minutes, well under the 15-minute limit. R2-10 was building (cargo lock) and not waiting on the quiet lane at either start (read-only `ps` check). It did queue behind chunk A at its end: R2-10's `r2-10-shake1` (SHARED) acquired the quiet lock at 17:35:21.377Z, 17 ms after `b03-measured-a` released it at 17:35:21.360Z (loop ledger). No R2-10 trial ran inside a B-03 window.

## Method

**Part 1 (`analyze_part1.py` → `part1-summary.json`; BENCHMARK re-analysis).**

- Loads B-02's `raw/measured-trials.tar.gz`: 240 trials, 240 valid.
- Uses B-02's `analyze_browser.trial_row` / `arm_block` and B-01's telescoping `decompose`, unchanged.
- Two best-arm readings:
  - spec-literal: the lowest median T_oracle among arms whose validity held, with no knob-verdict filter;
  - B-02's KEEP-only rule.
- Material: a mean component of at least 5% of mean T_runner, or at least 50 ms.
- Every material component is split into parts, each with a verdict and a source packet:
  - observation = base snapshot + cold excess;
  - revalidate = endpoint proof + remaining steps;
  - pre-dispatch = admission validation + glue.
- Untested share: B-02's rule unchanged (admission residual in V arms + unattributed + cold excess where H_W is UNDECIDED, over mean T_runner).

**Part 2 (`run_b03.py` → `analyze_b03.py` → `b03-summary.json`; REAL + BENCHMARK).**

- Design: 20 rounds.
  - Each round runs the 8 toggle cells (P × D × K) once, in Williams row r mod 8 of `williams(8)`. Rows 0–3 were used 3 times and rows 4–7 twice.
  - In even rounds it also runs the 4 fill cells (P × D, K5V), in Williams row (r/2) mod 4.
  - Each round also runs one negative-control trial.
  - Layout per round: toggle 1–4, fill 1–2, nc, toggle 5–8, fill 3–4.
  - Every trial uses one fresh `cua-driver mcp` and one fresh Driver-launched browser. Base knobs are B-01's K5 as in B-02 (feedback off, focus settle 0 on fill, 10 ms completion poll, caller-compiled output validators, trycua/cua PR 4316 guarded completion on fill). K adds `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1` (K5V), plus `CUA_DRIVER_EXP_ENDPOINT_REPROOF=bound` (K5EV), through the Driver environment only.
- P (process warmth):
  - cold: as B-02.
  - warm: after bind, one throwaway `browser_navigate` plus `semantic_v2` snapshot of a different document on the same owned fixture origin, before task start. The warm-up document is `<i24 origin>/modal` for toggle and `<fill origin>/state` for fill. Both return 200 and mutate nothing. The task navigate follows.
- D (snapshot delay):
  - 0: as B-02.
  - 80: the harness sleeps 80 ms (measured 80.1–80.6 ms) after the step-1 pre-observation oracle read. The first observation is therefore sent about 81–82 ms after navigate returns (median 81.2–81.9 ms from navigate return to the first observation send).
- Negative control (nc): toggle, K5V, cold, D0. One extra `semantic_v2` snapshot of the task document follows the task navigate. The task's snapshot1 is therefore a re-snapshot of the same document with no navigation in between.
- Forced path, from each trial's own records (every trial):
  - B-01 forced path: tools, routes, `input_route=dom_event` for every click, feedback off, 10 ms poll, settle 0 on fill.
  - B-02 knob path from the Driver's marks: V makes every tools/call in T show `mcp.inner_validation_skipped`; E shows `ep.bound_stored` at bind and one `ep.bound_hit` per mutation in T.
  - Actual route reported by the Driver: `dom`/`dom` for toggle, `trusted_input`/`dom` for fill, in every trial.
- Producer attribution: the Driver's `snap.*` marks of snapshot1 and snapshot2:
  - attach (`Target.attachToTarget` flattened session);
  - `DOM.getDocument`;
  - `Page.getFrameTree`;
  - `DOMSnapshot.captureSnapshot` + `Page.getLayoutMetrics`;
  - `Accessibility.getFullAXTree`;
  - total (`snap.enter` → `snap.serialized`).
- Oracle (independent, target-owned): the fixture server state (`JournalState` for toggle, `FixtureState` for fill), re-read every 2 ms by a harness thread, plus the server's CLOCK_MONOTONIC mutation journal. The runner's outcome is logged but is not the oracle.
- Measures:
  - first-snapshot span: the snapshot1 call window;
  - cold excess = snapshot1 span − snapshot2 span (B-02's definition);
  - T_oracle: `task_start`, stamped immediately before the D wait (for D=0 it equals the first observation send), to the first oracle-confirmed read. For D=80 it includes the wait;
  - T_runner: same start, to the runner's verified read;
  - warm-up span;
  - bind return → oracle.
- Statistics: round-paired differences, with B-01's seeded percentile bootstrap (10000 resamples, seed 20261002). Verdicts use medians and CIs. The ms accounting uses means, which are additive.

## Part 1 results: E2 decomposition of B-02's measured block (BENCHMARK re-analysis)

**Best arms.** Median T_oracle (B-02 measured block, n = 20 per arm):

| Class | K5 | K5E | K5V | K5EV | spec-literal best | B-02 KEEP-only best |
|---|---|---|---|---|---|---|
| fill | 156.5 | 138.7 | 148.3 | 115.9 | K5EV | K5V |
| toggle | 119.2 | 97.2 | 108.3 | 79.8 | K5EV | K5V |
| modal | 127.7 | 92.2 | 109.9 | 83.0 | K5EV | K5 |

**Material components of the spec-literal best arm K5EV** (mean ms, share of mean T_runner):

| Class (mean T_runner) | Component | Parts and verdicts (source) |
|---|---|---|
| fill (126.8) | observation 55.8 (44.0%) | base snapshots 24.6 IRREDUCIBLE (B-01R); cold excess 31.2 NOT DELETED (moved only) (B-02 H_W; see the fill caveat below) |
| | revalidate 20.3 (16.0%) | bound endpoint check 10.7 OWNER_DECISION (B-02 H_E); remaining re-proof 9.6 IRREDUCIBLE (kvnloo/cua#73, B-01R) |
| | sleeps_polls 7.9 (6.2%) | IRREDUCIBLE (B-01R H_P: no material component; 10 ms poll) |
| | resolution 8.1 (6.4%) | IRREDUCIBLE (B-01R: ref resolution before dispatch) |
| toggle (86.1) | observation 36.7 (42.7%) | base 11.3 IRREDUCIBLE (B-01R); cold excess 25.5 **UNDECIDED** (B-02 H_W; this lane: still UNDECIDED) |
| | revalidate 21.9 (25.4%) | bound check 10.0 OWNER_DECISION (B-02); remaining 11.9 IRREDUCIBLE (B-01R) |
| | visualization 4.7 (5.5%) | OWNER_DECISION (B-01R: feedback off, K1 fast glide KEEP; residual bookkeeping) |
| | transport 4.4 (5.2%) | IRREDUCIBLE (B-01R: stdio JSON-RPC) |
| modal (82.6) | observation 37.8 (45.8%) | base 13.8 IRREDUCIBLE (B-01R); cold excess 24.0 IRREDUCIBLE (B-02 H_W) |
| | revalidate 19.5 (23.6%) | bound check 10.3 OWNER_DECISION (B-02); remaining 9.2 IRREDUCIBLE (B-01R) |
| | visualization 4.2 (5.1%) | OWNER_DECISION (B-01R) |
| | transport 4.3 (5.2%) | IRREDUCIBLE (B-01R) |

**Untested share** (B-02 rule; admission residual 2.3–2.5 ms per task in V arms, including trace-mark cost; 0 unattributed):

| Class | K5V | K5EV | B-02 KEEP-only arm |
|---|---|---|---|
| fill | 1.6% | 1.9% | K5V 1.6% |
| toggle | 22.1% (cold excess 22.32 ms + admission 2.34 ms) | 32.4% (cold excess 25.48 ms + admission 2.44 ms) | K5V 22.1% |
| modal | 2.2% | 2.8% | K5 0.0% |

The K5V rows for toggle and the KEEP-only rows reproduce B-02's own E2 numbers. That is a cross-check of the re-analysis: same code, same raw data. The B-02 KEEP-only modal arm K5 carries one row labelled NOT_MATERIAL (admission 18.9 ms, 15.4%; V's T_oracle CI touches 0). NOT_MATERIAL is B-02's label and not one of E2's terminal verdicts. It does not occur in the spec-literal K5EV arm, where V is on.

**Fill caveat.** Part 1 cites B-02's accepted fill verdict. Part 2's fill positive replication did **not** reproduce its mechanism (see below). If fill's cold excess were reclassified UNDECIDED, fill's untested share would be (34.25 + 2.49) / 155.1 = 23.7% (K5V) and (31.22 + 2.39) / 126.8 = 26.5% (K5EV). The next lane must re-decide fill together with toggle.

## Part 2 results (REAL + BENCHMARK)

**Gates.**

| Gate | Result | Evidence class |
|---|---|---|
| Validity ≥ 95% per cell | 20/20 in every toggle cell and in nc; 10/10 in every fill cell (220/220 valid; 0 failures) | REAL |
| Stale dispatches (amendment 1) | 0: every actionN directly follows snapshotN; no refusal, no call error | REAL |
| Duplicate completion mutations | 0 (exactly 1 per trial, server journal) | REAL |
| Unverified successes | 0 | REAL |
| Non-loopback connects (runner) | 0 | REAL |
| Negative control: nc excess CI includes 0 | **FAIL**: excess 1.9 [0.5, 2.6] ms (mean 2.0). nc pre-snapshot 29.6 ms, snapshot1 7.5 ms, snapshot2 5.3 ms (medians) | BENCHMARK |
| Positive replication: fill reproduces "moved only" | **FAIL**: per-process 6.6 ms [1.7, 14.7] = 28% of fill's excess 23.7 ms (needs ≥ 50%) | BENCHMARK |

**Toggle cells** (median ms, n = 20 each, all valid; excess with its 95% CI):

| K | Cell | T_oracle | cold excess | snapshot1 | snapshot2 | warm-up | task navigate |
|---|---|---|---|---|---|---|---|
| K5V | cold D0 | 81.5 | 19.3 [15.1, 26.3] | 25.5 | 6.8 | — | 46.3 |
| K5V | cold D80 | 162.4 | 1.3 [0.4, 3.0] | 8.2 | 6.8 | — | 46.5 |
| K5V | warm D0 | 99.3 | 11.0 [7.6, 20.2] | 20.8 | 7.3 | 86.8 | 38.5 |
| K5V | warm D80 | 150.9 | 0.9 [0.4, 1.6] | 7.1 | 5.6 | 77.2 | 28.0 |
| K5EV | cold D0 | 76.3 | 27.4 [21.3, 33.1] | 34.3 | 5.7 | — | 28.0 |
| K5EV | cold D80 | 115.5 | 1.3 [0.7, 1.8] | 6.6 | 5.8 | — | 26.6 |
| K5EV | warm D0 | 53.5 | 8.0 [6.4, 12.1] | 17.2 | 7.8 | 68.0 | 20.7 |
| K5EV | warm D80 | 109.6 | 0.5 [−0.3, 1.1] | 5.7 | 5.1 | 50.5 | 17.1 |

**Producer of the excess** (median snapshot1 − snapshot2 per CDP step, toggle cold D0, K5V / K5EV): `DOM.getDocument` 10.0 / 11.4 ms, attach 4.3 / 6.7, frame tree 1.0 / 1.8, layout snapshot 1.0 / 1.2, AX tree 1.0 / 1.5; total 19.0 / 26.5. In warm D0, attach 4.8 / 3.4 and `DOM.getDocument` 3.2 / 3.8 remain. At D80 every step is below 0.7 ms in both P.

**Pre-registered contrasts** (round-paired medians [95% CI]):

| Contrast | K5V | K5EV |
|---|---|---|
| E = excess(cold, D0) | 19.3 [15.1, 26.3] | 27.4 [21.3, 33.1] |
| per_process = excess(cold, D80) − excess(warm, D80) | 0.4 [−0.2, 2.6] (1.9% of E) | 1.3 [0.2, 3.3] (4.7% of E) |
| per_document = excess(warm, D0) − excess(warm, D80) | 10.6 [7.4, 18.7] | 8.0 [6.2, 11.8] |
| doc_cold = excess(cold, D0) − excess(cold, D80) | 18.1 [13.8, 27.4] | 21.7 [19.5, 30.4] |
| floor = excess(warm, D80) | 0.9 [0.4, 1.6] | 0.5 [−0.3, 1.1] |
| T_oracle(D80 incl. wait) − T_oracle(D0), cold | +64.7 [58.1, 70.9] | +53.8 [41.6, 58.8] |
| T_oracle(D80 incl. wait) − T_oracle(D0), warm | +57.2 [33.3, 71.1] | +63.2 [51.6, 70.1] |
| T_oracle(cold, D0) − (warm-up + T_oracle(warm, D0)) | −124.1 [−144.6, −55.6] | −53.6 [−92.1, −24.4] |
| T_oracle(cold, D0) − T_oracle(warm, D0), warm-up excluded | 3.8 [−32.0, 17.1] | 15.1 [4.7, 21.8] |

**Verdicts under the pre-registered analysis.** The negative-control gate failed, so for both K:

- per_process: **UNDECIDED (gate failed)**;
- per_document: **UNDECIDED (gate failed)**.

Before the gate is applied, the rules evaluate as follows:

- per_process does not fire: its CI includes 0 (K5V), or it is only 4.7% of the excess (K5EV). The fill replication also failed.
- per_document is IRREDUCIBLE at both P levels (dT ≥ −2 ms by a wide margin).
- The warm-pool clause (OWNER_DECISION) does not fire: warm-up plus warm T_oracle is slower than cold.

**Accounting** (means, cold D0 cell of this block; parts are additive):

| K | mean excess | doc_cold | per_process | floor | admission residual | mean T_runner | untested share (block) | restated on B-02 E2 |
|---|---|---|---|---|---|---|---|---|
| K5V | 26.9 | 25.8 UNDECIDED | 1.3 UNDECIDED | −0.2 (median 0.9, CI excludes 0; counted as 0 ms) | 2.0 | 105.0 | **27.7%** | **22.3%** |
| K5EV | 29.0 | 26.3 UNDECIDED | 2.4 UNDECIDED | 0.3 (CI includes 0) | 2.0 | 81.1 | **37.7%** | **32.1%** |

"Restated on B-02 E2" means: B-02's toggle E2 row with the UNDECIDED cold excess scaled by this block's untested fraction of the excess (1.007 / 0.988), plus the admission residual. The K5V fraction is above 1 because the UNDECIDED parts (doc_cold 25.8 + per_process 1.3 = 27.1 ms) exceed the mean excess 26.9 ms: the floor's mean is negative (−0.2 ms) and, as the partition rule says, a negative part is reported and not counted.

**Fill positive replication** (K5V, n = 10 per cell, all valid):

| Cell | Result |
|---|---|
| cold D0 excess | 23.7 [22.5, 31.9] |
| cold D80 excess | 2.7 [0.9, 13.5] |
| warm D0 excess | 21.8 [15.5, 32.7] |
| warm D80 excess | −1.2 [−4.2, 0.1] |
| per_process | 6.6 [1.7, 14.7] (28%) |
| per_document | 24.3 [17.1, 35.3] |
| T_oracle(D80) − T_oracle(D0), cold | +62.5 [46.7, 98.9] |

The warm-up on fill's origin (`/state`, a JSON document) leaves the D0 excess almost unchanged. It does not reproduce B-02's "per-process first use" for fill. B-02's STEP 0 "B" probe re-navigated to the *same* page, so what B-02 called per-process for fill may be first use of that page's content in the process, not process start-up (Limits).

**Post hoc (computed after seeing the data; no verdict depends on it).**

- Per-process contrast at D0, excess(cold, D0) − excess(warm, D0): toggle 5.3 [3.6, 11.5] (K5V) and 17.5 [13.7, 21.8] (K5EV, 64% of E); fill 4.8 [−5.9, 8.6].
  - So the per-process share is real at D0, but an 80 ms wait absorbs it as well. That is why the pre-registered contrast, taken at D80, cannot see it.
- With the negative-control gate waived (validity and invariants only):
  - per_document: IRREDUCIBLE for both K;
  - per_process: UNDECIDED (K5V 1.3 ms, K5EV 2.4 ms);
  - toggle untested share: 3.1% (K5V) and 5.4% (K5EV) in this block; 3.1% and 5.3% restated on B-02.

## Component timings and the five kvnloo/cua#73 requirements

| Requirement | This packet |
|---|---|
| Forced path | B-01 forced path + B-02 knob path checked on every trial (0 invalid reasons); clicks `dom_event` through the CDP engine; D wait and P warm-up stamped by the harness |
| Actual route / producer | the Driver's envelope route (`dom`, `trusted_input`) per action; CDP producer per snapshot from `snap.*` marks (table above) |
| Independent target-owned outcome | fixture server state, re-read every 2 ms by an independent thread, plus the server mutation journal (exactly 1 completion mutation per trial) |
| Negative / fallback case | nc same-document re-snapshot (gate **failed**, reported); fill positive replication (**failed**, reported); invariants 0/0/0 |
| Exact provenance | the Provenance table; `provenance.json`; binary re-hashed at the start and the end |

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved (T_oracle) | Evidence class |
|---|---|---|---|
| Snapshot 80 ms after navigate (D80) | none deleted. The excess (`DOM.getDocument`, attach) is absorbed by waiting for document readiness | negative: +64.7 (K5V) / +53.8 (K5EV) ms | BENCHMARK |
| Pre-warm the process (P warm, harness-side) | none deleted. Part of the first-snapshot work moves before task start | inside T: 3.8 [−32.0, 17.1] / 15.1 [4.7, 21.8] ms; including the warm-up: −124.1 / −53.6 ms | BENCHMARK |

## Deviations

1. **Amendment 1 (stale-dispatch definition).** PREREG.json counted an action with `effect` refused or unverifiable as stale. The shakedown showed that every dom_event action returns `effect: unverifiable` in its normal envelope: the oracle verifies, not the Driver. B-02's measured trials show the same. The amendment, committed before the measured block, defines staleness by call order plus refusals.
2. **Post-hoc analysis.** The `post_hoc` block was added after the measured block. It changes no pre-registered key (`verify_artifacts.py` recomputes the summary with the analyzer at `2549fc1e8` and compares every other key).
3. **Telemetry off.** This lane's spec required `CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1`. B-02 ran with telemetry at its default. Absolute times are therefore not compared with B-02. The only B-02 numbers used are Part 1 (B-02's own raw) and the scaling in the restatement, which uses a fraction, not B-03 ms.
4. **Unequal Williams rows.** 20 rounds over `williams(8)` use rows 0–3 three times and rows 4–7 twice.
5. **Floor accounting edge case.** K5V's floor has median 0.9 ms with a CI excluding 0, but a negative mean (−0.2 ms, one outlier). The pre-registered code labels it "UNTESTED (CI excludes 0, > 0)" and counts max(0, mean) = 0 ms. Counting its median instead would add 0.9 ms (0.9% of T).
6. The shakedown waited 34 s for its SHARED lock (another lane's exclusive window). Chunk B queued behind own75r's exclusive windows and acquired the lock at 17:40:33.996Z. No trial ran outside its lock.
7. No unit suite was run, because no Driver or harness-shared code was touched. B-02's harness files are unchanged (verified).
8. Plain-host-shell use was limited to git, gh reads, file reads and edits (including `sed -i`, `cp`, `mv`), `ps` (read-only), and `mkdir` plus `tar -x` of B-02 raw and this lane's raw into the lane temp for inspection and the privacy scan. Every Python, jq and sha256sum command ran under `hostless`. There were no near misses.
9. **Gate rule wording.** `PREREG.json` `gates.failing_gate` names only a failed validity or invariant gate as making verdicts UNDECIDED. The analyzer committed with amendment 1 at `2549fc1e8`, before the measured block, also applies the negative-control gate (`gates_ok = validity and invariants and negative control`), and that is the rule the verdicts above use. The PREREG `negative_control` gate itself is unchanged.

## Limits

- The negative control as designed takes its re-snapshot about 30 ms after navigate, which is still inside the readiness window. Its 1.9 ms excess is close to the 1.3 ms left at cold D80. Why the control failed is undetermined: residual readiness work and an estimator floor (snapshot1 − snapshot2 of a same-document pair is not exactly 0 ms) are equally plausible, and this block cannot tell them apart. Either way, the pre-registered gate failed, and this packet does not reinterpret it.
- The spec's per-process contrast is taken at D80, where the delay has already absorbed the per-process work. The design could not show a per-process part that survives a delay, because there is none to show. The D0 contrast (post hoc) shows a real one.
- The warm-up documents differ by class: `/modal` (HTML + script, similar to the toggle page) and `/state` (JSON). That difference may be why the warm-up reduced the D0 excess for toggle but not for fill. Process warmth and content similarity are confounded.
- n = 20 per toggle cell and n = 10 per fill cell, one binary, one session type, loadavg 13–25. T_oracle spreads are tens of ms.

## Claim boundary

Binary `7e6c0609…` only (B-02 source `f5c991e59` + `560bd8247`, pre-FIX-01), jev-use toggle→confirm and fill→submit, X11 Xvfb under hostless v2, scripted chooser, system Chrome with an isolated new profile, telemetry off.

On it:

- toggle's cold-first-snapshot excess (mostly `DOM.getDocument` and attach) disappears when the first observation comes 80 ms after navigate, in a cold or a warm process;
- waiting that long costs 54–65 ms of T_oracle;
- pre-warming costs more than it saves.

A component verdict transfers to R2-10's source by mechanism only; no number here is added to R2-10's. Nothing here is LIVE_PROVIDER, Wayland, macOS or Windows evidence, and nothing changes a default.

## Disposition

- **Part 1: KEEP** (BENCHMARK re-analysis). K5EV is decomposed for every class. Spec-literal untested share: fill 1.9%, modal 2.8%, toggle 32.4%. KEEP-only: fill 1.6%, modal 0.0%, toggle 22.1%.
- **Toggle H_W: still UNDECIDED.** The pre-registered negative control failed (1.9 ms [0.5, 2.6]). The fill positive replication also failed.
- **Why toggle's untested share stays at or above 5%** (22.3% K5V, 32.1% K5EV on B-02's rows):
  1. the gate failure voids the toggle verdicts under the pre-registered analysis;
  2. the pre-registered per-process contrast sits at D80, where the per-process work is already absorbed.

  The remaining untested 2.0 ms admission residual is below 5% on its own; it is not a reason the share stays at or above 5%.
- **Mechanism (decided by this probe, descriptive):**
  - the excess is document-readiness work that waiting absorbs, and the per-process part seen at D0 (post hoc K5EV 17.5 [13.7, 21.8] ms, 64% of E) is absorbed by the same wait;
  - waiting never pays: +54–65 ms T_oracle;
  - pre-warming moves work, and costs more than it saves.
  - No deletion inside T was found, and no product knob is justified.
- **For kvnloo/cua#73 / kvnloo/cua#10:** the fill W verdict "moved only" (B-02) was not reproduced. Fill's untested share would be 23.7% / 26.5% if it were reclassified UNDECIDED.
- TypeSafe: 0 attempts, 0 reached.

## Next

A follow-up lane (B-04, no provider, same binary) can make both verdicts terminal with three pre-registered changes:

1. **Negative control after readiness:** re-snapshot pairs of the same document with no navigation, at D ≥ 80 ms after navigate, instead of about 30 ms.
2. **Per-process contrast at D0:** excess(cold, D0) − excess(warm, D0), with the warm-pool clause, plus a warm-up of matched content (a sibling page with the same structure) to separate process warmth from content.
3. **Fill and toggle together**, with the same per-document T_oracle rule. This lane's data say that rule gives IRREDUCIBLE in both classes.

If the follow-up's gates hold and its effects match this block's, toggle's untested share would fall to about 3% (K5V) and about 5% (K5EV). The K5EV figure rests on the 2.0 ms admission residual plus any per-process part left UNDECIDED.

## Publication errata (r1b repair, 2026-10-03)

Evidence class: SOURCE (packet hygiene and wording; no new run, no new evidence). Branch `exp/b-03-toggle-cold-snapshot-r1b-20261003`, parent `b34eef71e` (the published head).

- **Logs.** The repository rule `*.log` kept the six session and runner logs cited for the DISPLAY values (`raw/*/…session.log`) out of the published commit. They are now committed from the wave-3 lane worktree, with a packet-local `.gitignore` (`!*.log`, `!build/`). They had already been through the lane's packager (`lane-scripts/package_raw.py` rules); re-applying those rules changed 0 files. `raw/force-added-logs.sha256` lists their sha256.
- **Wording.** Freshness row (437 files locally; 300 was the compare-API cap; the 18 `libs/cua-driver` count stands); R2-10 shake1 lock timing disclosed under Environment; the per-process part at D0 is also absorbed by waiting; the failed negative control's cause is undetermined; disposition reason 3 is no longer listed as a reason; D80 is about 81–82 ms after navigate returns; the K5V untested fraction above 1 is explained; PREREG `failing_gate` vs analyzer wording (Deviation 9); issue references written as kvnloo/cua#N.
- **Unchanged.** Every measured number, raw trial record, summary JSON, analysis script, `verify_artifacts.py`, `PREREG.json` and `PREREG-AMENDMENT-1.json` is the same as at `b34eef71e`. No cited file was missing.

## Files

| File | Contents |
|---|---|
| `PREREG.json`, `PREREG-AMENDMENT-1.json` | pre-registration (never edited) and amendment 1 (before the measured block) |
| `analyze_part1.py`, `part1-summary.json` | Part 1 re-analysis of B-02 raw/ |
| `run_b03.py` | Part 2 runner (imports B-02's `run_b02` / `run_critpath` in place) |
| `analyze_b03.py`, `b03-summary.json` | Part 2 analysis (PREREG rules; `post_hoc` labelled) |
| `headline-numbers.json` | every README number checked by `verify_artifacts.py` |
| `provenance.json` | SHAs, binary, environment, locks, provider |
| `verify_artifacts.py` | standard-library verifier: recomputation, pre-registered analyzer equivalence, headline numbers, PREREG order, locks, trial counts, binary, B-02 harness blobs, provider, privacy |
| `lane-scripts/` | sanitized copies of the lane's session wrapper and raw packager |
| `raw/` | sanitized raw: `measured-trials.tar.gz` (220 trials + Driver traces), `shake-trials.tar.gz` (7, excluded), manifests, `lock-ledger.jsonl` |
| `raw/measured/measured-a.session.log`, `raw/measured/measured-a.stdout.log`, `raw/measured/measured-b.session.log`, `raw/measured/measured-b.stdout.log`, `raw/shake/shake.session.log`, `raw/shake/shake.stdout.log` | session and runner logs (committed since the r1b repair; see Publication errata) |
| `raw/force-added-logs.sha256`, `.gitignore` | sha256 of the six committed logs; packet-local `!*.log`, `!build/` |

Raw outputs are mirrored, unsanitized, in the lane artifacts directory `artifacts/r2/B-03/`.
