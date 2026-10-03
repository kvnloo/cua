# B-09: fill compiled-routine verify poll on binary B7 (stamped causal A/B + scripted BASE vs composed S), 2026-10-03

Lane B-09, wave 7 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-10 / R2-07 composed fill), kvnloo/cua#10
(accounting), kvnloo/cua#73 (E2 / E3 / E4). Lineage: B-08 Part E, where fill's last untested component is
`runner` (9.82 ms = 14.5% of mean T_runner, C arm, B7). Upstream items are named as plain text (trycua/cua PR 4316).

## Status in one paragraph

**BLOCKED: the measured run did not run.** Everything before the first measured trial is done and committed:

- the measurement-only, env-gated, default-off harness change, with unit red/green;
- the B-09 runner (six arms in a 6x6 Williams square, plus SMOKE and N-W2 controls);
- a 12-trial pilot under the SHARED lock (excluded);
- PREREG.json, committed before any measured trial and never amended;
- the analyzer, the verifier and the provenance.

The first measured chunk queued for the EXCLUSIVE quiet-lane lock at 16:13:05Z and was never granted it. Since
14:59:23Z, an orphaned process outside this loop has held a shared flock on the quiet-lane lock file (an inherited
fd; details in `raw/lock-blocker.json`). Under that lock nothing can ever acquire EXCLUSIVE. No EXCLUSIVE
quiet-timed acquisition has been granted on the host since 14:11:00Z; R2-07g and R2-07f were queued behind it too.

The hard rules forbid timing outside an EXCLUSIVE quiet-timed window and forbid signalling a process this lane did
not start. So the lane stopped its own queued processes at 17:20:30Z and reports BLOCKED. It names the exact
blocker and gives a one-command resume.

**No timing number, gate, verdict, S or Part E' share is claimed.** Fill's untested share stays at B-08's
16.9% / 19.0%. Provider: 0 attempts, 0 reached.

## Five mechanism requirements (what is in place; measured rows NOT_RUN)

| Requirement | This lane | Evidence class |
|---|---|---|
| Forced path | Every arm except BASE is the R2-10 scripted COMP fill exactly as B-08 C (see the bullets below the table). BASE = B-04 `DEFAULT` (feedback on, default glide, no guard, 100 ms poll, library validators) | SOURCE (runner + PREREG); measured NOT_RUN |
| Actual route / producer | Recorded per accepted action by `b09_rows.routes_producers`: receipt route, Driver dispatch mark in the call window, and producer. In the excluded pilot (12/12 verified), every compiled arm ran `browser_type` trusted_input + `type.insert_send`, then `browser_click` dom + `click.cdp_send`, both from producer `compiled`. BASE ran the same routes, from producer `provider` (scripted chooser). Not a result | FIXTURE (pilot, excluded); measured NOT_RUN |
| Independent target-owned oracle | The jev-use fixture server: `submitted == token`, and its CLOCK_MONOTONIC journal must show exactly one submit. PRIMARY T_runner = snapshot1 send → return of the first verified oracle read. SECONDARY: T_j (B-08) and T_oracle (2 ms sampler). Per trial, after the last accepted mutation: reads, sleeps, summed poll sleep, effect latency (journal commit − submit dispatch return) | SOURCE; measured NOT_RUN |
| Negative / fallback controls | NC A/A (P10a vs P10b); PC (+15.0 ms CLOCK_MONOTONIC in T after snapshot1); SMOKE ×5 (product default, no lane variable); FIX-01 N-W2 detached-node refusal ×3; E4 counters in every arm | SOURCE; NOT_RUN |
| Exact provenance | The Provenance table below; `provenance.json` | SOURCE |

The forced path in every arm except BASE, in detail:

- feedback off, focus settle 0, caller-compiled validators, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`;
- guarded completion + compiled replay (R2-10R scripted COMP artifact);
- phase trace on with the B-05/B-07 marks, and the B-07 stamped stdio client (default variant);
- scripted chooser, telemetry `false`, no provider key forwarded;
- per trial: a fresh `cua-driver mcp`, a fresh Driver-launched system Chrome (`isolated_new`, sandbox on), fresh
  fixture servers, a fresh token and session label. Every trial is cold.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Tested source SHA | `ac319cbe90d6cdf0cc8cd8984f99f5b04b68fdac` = R' 45dff8f32 + B-05 marks + the default-off POST_FAST knob. Its libs/cua-driver Linux tree = upstream 0f1955d2f. Nothing was built in this lane | SOURCE |
| Driver binary | B7 `cua-driver-b07-231f6e8bb`, sha256 `6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa`, `cua-driver 0.32.0`. Re-hashed on the host at lane start (15:56:45Z) and end (17:21:01Z): identical. Read inside the private session at start and end (`raw/logs/versions-start.log`, `raw/logs/versions-end.log`): identical. The runner refuses on a mismatch, and it writes name, sha256 and version into every trial record, every control (SMOKE, N-W2) record and every manifest | REAL |
| Browser | Driver-chosen Google Chrome 151.0.7922.71, read in session | SOURCE |
| Base / harness | Branch from `49ae94590` (B-08 packet head). The first commit `13defc3f1` copies B-08's harness and lane code blob-identically (blob ids and a per-file B-08 comparison in `provenance.json`). Every harness file except `harness/b04/harness/compiled_routine.py` still has its 49ae94590 blob (`provenance.json`: `untouched_harness_blob_identity_vs_49ae94590`, all identical) | SOURCE |
| Harness change | The single reviewed commit `9d0138653`, made before PREREG and described in the bullets below this table | SOURCE + UNIT |
| Unit | `raw/unit/unit-red.log`: the new tests against the unmodified routine give 9 errors and 6 skipped, while the R2-07 suite passes. `raw/unit/unit-green.log`: 32/32 OK. Suites: `tests/test_b09_poll.py` (new) and `tests/test_compiled_routine_r207.py` (R2-07's suite, blob `e9c7ff81e` from 2d71548b4) | UNIT |
| PREREG commit | `b4480de1f` at 2026-10-03T16:10:35Z, before any measured trial. Never amended (one commit touches it; see Deviation 2) | SOURCE |
| Live heads (read-only gh) | Start 15:56Z: trycua/cua main `9a2b1d99e`; trycua/cua PR 4316 `a0bca7440`, open. End 17:21Z: main `3a784c5c3`; PR 4316 `a0bca7440`, open, unchanged | SOURCE |
| Upstream drift | c8edda06b (B-08's head) → 9a2b1d99e touches `platform-linux/src/overlay.rs` (trycua/cua PR 4529: idle X11 cursor overlays stay unmapped, on the feedback-on path BASE uses) and `cua-driver-core/src/expectation.rs` (trycua/cua PR 4531, macOS verify_state). 9a2b1d99e → 3a784c5c3 touches only platform-macos and the Skills docs. B7's tested source is fixed; carrying a claim to current main needs recertification | SOURCE |
| Publication SHA | Set by Publish (`provenance.json: publication_sha`). Never equal-by-assumption to the tested SHA or the lane head | SOURCE |
| Provider | None (scripted chooser). TypeSafe cap 0: 0 attempts, 0 reached | NOT_RUN |

The harness change (commit `9d0138653`), in `harness/b04/harness/compiled_routine.py`:

- `CUA_LANE_EXP_ROUTINE_POLL_MS` sets the verify `bounded_read` interval. Unset = 10 ms, the current behaviour; 0 =
  `asyncio.sleep(0)`, a yield only. Reconcile reads are unaffected.
- A `STAMP` hook, None by default, records `routine_read_send` / `routine_read_return` around each routine oracle
  read and `poll_sleep_start` / `poll_sleep_end` around each poll sleep (time.monotonic_ns).
- `CUA_LANE_EXP_PC_SLEEP_MS` is read by `run_b09.py`. Lane variables are set in the runner process only, and an
  assert per trial checks that they never reach the Driver environment.

## Method (pre-registered; PREREG.json)

- **Arms (fill only), all from one Williams square.** A 6x6 square `rc.williams(6)`; round r runs row r mod 6;
  36 rounds = 6 squares, so every contrast has 36 pairs and there are 216 measured trials.
  - BASE: R2-10 BASE.
  - P10a / P10b: the current 10 ms poll; the A/A pair.
  - P1: 1 ms poll.
  - P0: yield only; descriptive.
  - PC: P10a + 15 ms in T.
- **Controls.** After the measured rounds: SMOKE ×5 and N-W2 ×3. Toggle and modal are not run (their runner gap is
  0.13-0.15 ms).
- **Gates.**
  - G0: ≥ 95% valid per arm and identical verified outcomes.
  - G1: CI(P10a − P10b) contains 0 and |median| ≤ 1.0 ms.
  - G2: CI(PC − P10a) lies inside [12, 18] ms.
  - G3: E4 = 0 in every arm and N-W2 3/3.
- **Poll verdict.** Computed only when G0-G3 pass.
  - DELETED (KEEP) iff median(P10a − P1) ≥ 3.0 ms and its CI lower bound > 0.
  - IRREDUCIBLE (KILL) iff the CI upper bound < 3.0 ms.
  - Otherwise UNDECIDED, which is not terminal.
- **Statistics.** Paired within-round medians of T_runner; percentile bootstrap, 10 000 resamples, a fresh
  `random.Random(20261003)` per contrast.
- **S (E3).** S = median T(BASE) / median T(P1 if DELETED, else P10a), with a pair bootstrap; the gate is CI lower
  bound > 1. The floor ratio uses T_irreducible from Part E'.
- **Part E'.** B-08 Part E on P10a and on the best arm, plus a split view built on the stamps.
  - The split view separates `runner` into poll_sleep, read_hop (the routine's thread hop) and runner_other.
  - The target-effect tail rule runs first, so effect_wait stays target_effect_lag.
  - Fill's untested share is reported in both BELOW_GATE views, against the < 5% target.
- **Locks and environment.**
  - Each chunk: the cargo-build lock is seen free first; then one EXCLUSIVE `bin/quiet-timed b09-<chunk>`; inside
    it, `flock -w 60` on the cargo lock (exit 74 = nothing ran) and `timeout 900`.
  - A round starts only at 1-min loadavg ≤ 4.0.
  - Every trial runs in a private Xvfb (`cua-x11-session.sh`) under `bin/hostless`, with 0-3 s start jitter and an
    xdpyinfo probe.

## Results (N of M, evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| Harness change default-off / env-gated | 32 of 32 unit tests | green; red-before = 9 errors, 6 skipped against the unmodified routine | UNIT |
| Pilot (excluded, SHARED lock, load rule off, 1-min loadavg 11-12) | 12 of 12 verified, exactly one submit each, E4 0, every Driver (pid, start time) unique | pipeline and receipt check only; sets no gate and no number | FIXTURE (excluded) |
| Measured A/B (BASE/P10a/P10b/P1/P0/PC, 36 rounds) | 0 of 216 | not run: the EXCLUSIVE quiet-lane lock was never granted (`raw/lock-blocker.json`) | BLOCKED |
| G0-G3, poll verdict, S, floor ratio | — | not computed | BLOCKED |
| SMOKE ×5, N-W2 ×3 | 0 of 8 | not run (scheduled after the measured rounds) | BLOCKED |
| Part E' (untested share, < 5% target) | — | not computed; fill stays at B-08's 16.9% / 19.0% (B-08 @ 49ae94590) | BLOCKED |

## Work deleted vs wall-clock saved

| item | work deleted | wall-clock saved | evidence class |
|---|---|---|---|
| verify-poll interval 10 → 1 ms (caller runner setting) | not measured (P1 would add reads; P0 adds more) | not measured | BLOCKED |
| this lane | none (measurement only; env-gated, default-off caller stamps and interval) | none | SOURCE |

## Disposition

**BLOCKED, not terminal for E1/E2.** The blocker is infrastructure on this host, not hardware, an owner decision or
paid budget: an orphaned non-loop process holds a shared flock on the quiet-lane lock. This is a resume item; the
packet does not claim a verdict.

- **E2:** fill's `runner` stays UNTESTED on B7 (16.9% / 19.0%, B-08).
- **E3:** S is not measured.
- **E4:** no measured arm ran. The pilot had 0 E4 events (excluded).

### Resume (one command once the lock frees)

With the B09_* environment (lanes dir, worktree, lane temp, binary path, expected sha256, lock dir) and
CUA_PRIVACY_PATTERNS_FILE set, run `hostless python3 lane-scripts/run_all.py --chunk-rounds 12` from this packet.
It first waits until the 1-min loadavg ≤ 4.0 and the cargo lock is free. Then it runs rounds 0-35 and the control
chunk, each under EXCLUSIVE quiet-timed.

The pilot raw stays excluded. PREREG.json, the runner and the analyzer stay as committed. After the run, write
`b09-summary.json` with `analyze_b09.py` (SHARED, label `b09-analyze-final`), then `make_headlines.py`, then
`verify_artifacts.py`.

## Deviations and disclosures

1. **Measured run not run.** The lock blocker above. The lane stopped only its own processes: run_all.py,
   run-chunk.sh, its quiet-timed, and that quiet-timed's `flock -x` waiter, which had been reparented when
   quiet-timed exited. The waiter would otherwise have stayed queued as an orphan. No ledger line exists for the
   never-granted chunk.
2. **PREREG commit rewritten once before any data.** The first PREREG commit (`bfed36749`, 16:10:27Z) said
   `written_utc` 16:20Z, later than the commit itself. It was amended 8 s later to 16:10Z, as `b4480de1f`, on the
   unpublished branch and before any measured trial. Nothing else changed.
3. **Cargo-lock pre-check timing.** run_all.py checks that the cargo lock is free before it queues for EXCLUSIVE,
   but the queue wait can be long. The bounded `flock -w 60` inside the acquisition still decides.
4. **BASE has the phase trace on** (as B-08 SMOKE did). This is measurement-only. Had S been measured, it would
   carry the per-mark cost in both arms.
5. **Pilot.** 12 trials (rounds 0-1, SHARED, load 11-12) ran before PREREG. The analyzer ran once on them
   (`b09-analyze-pilot`) to check the pipeline. They are excluded from every number (`raw/pilot-trials.tar.gz`).

Near misses (none had an effect):

- One stdlib `python3` string patch of `compiled_routine.py` ran in the plain host shell (a file edit; no GUI, no
  network). Every later Python run used `bin/hostless`.
- One host-side `flock -s -n <cargo lock> true` probe ran in the plain shell (read-only lock probe).
- Hard-rule breaches: none.

## Limits and claim boundary

- One shared Linux host, private Xvfb, Google Chrome as Driver-chosen, binary B7 only, scripted chooser.
- No measured claim is made.
- The poll is a caller runner setting. Its jev-use product default (100 ms in run.py) is not changed; any proposal to
  change that default is an OWNER_DECISION row, not this lane's claim.
- Absolute T would never be compared with B-06 / B-08 / R2-10R.

## Files

- **Pre-registration and provenance:** `PREREG.json`, `provenance.json`.
- **Verifier:** `verify_artifacts.py` (blocked mode when no measured raw exists; `hostless python3 verify_artifacts.py`
  with CUA_PRIVACY_NAMES_FILE and CUA_PRIVACY_PATTERNS_FILE set to untracked files), `verify_helper.py`.
- **Lane code:** `run_b09.py`, `b09_rows.py`, `analyze_b09.py`, `make_headlines.py`, `lane-scripts/run_all.py`,
  `lane-scripts/run-chunk.sh`, `lane-scripts/run-pilot.sh`, `lane-scripts/session-retry.sh`,
  `lane-scripts/in-session.sh`, `lane-scripts/shared-locked.sh`, `lane-scripts/package_raw.py`.
- **Tests:** `tests/test_b09_poll.py`, `tests/test_compiled_routine_r207.py`.
- **Harness copies:** `harness/b04/` (with the one changed file `harness/b04/harness/compiled_routine.py`),
  `harness/b05/b05_spans.py`, `harness/b07/b07_stdio.py`, `harness/r2-10r/r2_10_browser.py`,
  `harness/r2-10r/scripted-COMP.json`, `harness/r2-10r/analyze_r2_10.py`,
  `harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/b01_analysis.py`,
  `harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/analyze_browser.py`.
- **Raw:**
  - Blocker and locks: `raw/lock-blocker.json`, `raw/lock-ledger.jsonl`.
  - Pilot (excluded): `raw/pilot-trials.tar.gz`, `raw/pilot/run-manifest-pilot-pilot-a1-r00-01.json`.
  - Unit: `raw/unit/unit-red.log`, `raw/unit/unit-green.log`.
  - Logs: `raw/logs/versions-start.log`, `raw/logs/versions-end.log`, `raw/logs/b09-pilot-r00-01.log`,
    `raw/logs/b09-run_all.log`, `raw/logs/b09-main-a1-r00-11-k1.log`.
