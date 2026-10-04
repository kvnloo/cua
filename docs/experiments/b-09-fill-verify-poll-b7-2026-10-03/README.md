# B-09 / B-09R: fill compiled-routine verify poll on binary B7 (stamped causal A/B + scripted BASE vs composed S), 2026-10-03

Lane B-09 (wave 7, BLOCKED) and its resume B-09R (wave 8) in the CUA RFC loop. Owners: kvnloo/cua#93 (R2-10 / R2-07
composed fill), kvnloo/cua#10 (accounting), kvnloo/cua#73 (E2 / E3 / E4). Lineage: B-08 Part E, where fill's last
untested component is `runner` (9.82 ms = 14.5% of mean T_runner, C arm, B7). Upstream items are named as plain text
(trycua/cua PR 4316).

## Status in one paragraph

**KEEP: the verify poll is DELETED.** B-09R ran the pre-registered measured run on B7 with PREREG.json unchanged
(blob identical to `b4480de1f`). It ran 4 EXCLUSIVE quiet-timed windows (`b09r-*`), with every trial in a private
Xvfb under `bin/hostless`.

- **Validity:** 216 of 216 measured trials verified, plus SMOKE 5/5 and N-W2 3/3. E4 total 0.
- **Gates:** G0-G3 all pass. The A/A control reads P10a-P10b -0.46 ms, CI [-1.34, 1.43]. The +15 ms positive control
  reads PC-P10a 14.61 ms, CI [13.51, 15.31].
- **Poll verdict (pre-registered rule):** P10a-P1 9.20 ms, CI [8.26, 10.05]. That is at least 3.0 ms with a CI lower
  bound above 0, so poll verdict DELETED and the composed arm is P1.
- **What the poll costs:** only the runner's own return. The target-side clocks do not move: T_j P10a-P1 0.00 ms and
  T_oracle P10a-P1 -0.06 ms. The submit lands at the same time; the runner just sees it sooner.
- **E3:** S = 48.2, S CI [47.6, 48.7], S over 36 pairs. That is median T BASE 3176.1 ms vs median T composed 65.94 ms,
  on one binary.
- **E2 (Part E', corrected view):** fill's untested share is P10a corr BG=IRR 2.7% / P10a corr BG=UNT 4.9%. Both are
  below 5% on the B-08-comparable arm (B-08: 16.9% / 19.0%). On the composed arm the share is P1 corr BG=IRR 3.8% /
  P1 corr BG=UNT 6.5%. The second number misses the 5% target only because the deletion shrinks T. The rest is
  below-gate residue (Part E' below).

Provider: 0 attempts, 0 reached.

## Five mechanism requirements

| Requirement | This lane | Evidence class |
|---|---|---|
| Forced path | `CUA_LANE_EXP_ROUTINE_POLL_MS` forces the compiled routine's verify-poll interval: 10 ms (P10a/P10b; unset also means 10), 1 ms (P1), yield only (P0). PC adds `CUA_LANE_EXP_PC_SLEEP_MS`=15. Every compiled arm is the R2-10 scripted COMP fill exactly as B-08 C. BASE = B-04 `DEFAULT` (feedback on, default glide, no guard, 100 ms poll, library validators). The bullets below the table give the rest of the forced path. Lane variables stay in the runner process: an assert per trial checks that they never reach the Driver environment | REAL (raw/main-trials.tar.gz; `driver_env_lane` empty in every record) |
| Actual route / producer | Per accepted action (b09_rows.routes_producers), every compiled arm ran `browser_type` trusted_input `type.insert_send` and then `browser_click` dom `click.cdp_send`, both from producer `compiled`, 36/36 per arm. BASE ran the same routes from producer `provider` (the scripted chooser), 36/36. Poll / read attribution comes from the committed stamps (`poll_sleep_start/end`, `routine_read_send/return`): P10a sleeps 1.00, P1 sleeps 1.00, P0 sleeps 1.94 per task | REAL |
| Independent target-owned oracle | The jev-use fixture server: `submitted == token`, and its CLOCK_MONOTONIC journal shows exactly one submit. PRIMARY T_runner = snapshot1 send → return of the first verified oracle read. SECONDARY: T_j (B-08) and T_oracle (2 ms sampler). All 224 records are verified with exactly one submit (completion_mutations 1) | REAL |
| Negative / fallback controls | NC A/A (P10a vs P10b): G1 pass. PC (+15.0 ms CLOCK_MONOTONIC in T, PC sleep 15.00 ms): G2 pass. SMOKE 5/5: the product default with no lane variable, same routes and mark set as B-08 SMOKE. FIX-01 N-W2 3/3: the stale envelope is `browser_ref_stale`, effect `refused`; the fresh snapshot carries the marker; exactly one submit; 0 detached effects. E4 counters are 0 in every arm | REAL |
| Exact provenance | The Provenance table below; `provenance.json` (key `b09r`) | SOURCE |

The forced path in every compiled arm, in detail:

- feedback off, focus settle 0, caller-compiled validators, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`;
- guarded completion + compiled replay (R2-10R scripted COMP artifact);
- phase trace on with the B-05/B-07 marks, and the B-07 stamped stdio client (default variant);
- scripted chooser, telemetry `false`, no provider key forwarded;
- per trial: a fresh `cua-driver mcp`, a fresh Driver-launched system Chrome (`isolated_new`, sandbox on), fresh
  fixture servers, a fresh token and session label. Every trial is cold. There are 221 Driver (pid, start time)
  pairs, all unique (`process_identity`).

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Tested source SHA | `ac319cbe90d6cdf0cc8cd8984f99f5b04b68fdac` = R' 45dff8f32 (0f1955d2f + R2-10 steps 1-8) + B-07 picks + the default-off POST_FAST knob. Its libs/cua-driver Linux tree = upstream 0f1955d2f. Nothing was built in either wave | SOURCE |
| Driver binary | B7 `cua-driver-b07-231f6e8bb`, sha256 `6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa`, `cua-driver 0.32.0`, not rebuilt. B-09R re-hashed it on the host at lane start (2026-10-03T21:00:28Z) and at lane end (2026-10-04T03:01:40Z): identical. It also read the version in the private session at start and end (`raw/logs/versions-b09r-start.log`, `raw/logs/versions-b09r-end.log`): identical. Every trial record, every control record and every manifest carries name, sha256 and version | REAL |
| Browser | Driver-chosen Google Chrome 151.0.7922.71 (`isolated_new`, sandbox on), read in session at start and end. This is the same version as B-08 and wave 7. B-09R decomposition numbers are still not combined with B-08's | SOURCE |
| Environment | One shared Linux host; private rootless Xvfb 1920x1080x24 + private dbus + openbox (`cua-x11-session.sh`) under `bin/hostless`; 0-3 s start jitter and an xdpyinfo probe per session; scripted chooser; no provider | SOURCE |
| Harness / runner / analyzer | Branch exp/b-09-fill-verify-poll-b7-20261003 @ `56284782d` (wave 7). The harness change is commit `9d0138653` (env-gated, default-off routine poll knob + poll/read stamps). PREREG `b4480de1f`. B-09R branch exp/b-09r-fill-verify-poll-b7-resume-20261003 from `56284782d`. Its one bookkeeping commit `21a331786` comes before the first measured trial: ledger labels `b09r-`, the lock fd closed inside the window, holder snapshots, verifier receipt names. Nothing measured, analysed or gated changed | SOURCE |
| PREREG identity | `git diff b4480de1f HEAD -- PREREG.json` is empty. sha256 `c2b5f207340a566464ac1a87d6ba2c790cd960366ae52041409ccba9da0b78d4`, blob `d952677a1`. Exactly one commit touches it | SOURCE |
| Unit (wave 7) | `raw/unit/unit-red.log`: 9 errors and 6 skipped against the unmodified routine. `raw/unit/unit-green.log`: 32/32 OK. Suites: `tests/test_b09_poll.py`, `tests/test_compiled_routine_r207.py`. B-09R touched no tested code, so it did not re-run them | UNIT |
| Quiet-lane receipts (B-09R) | EXCLUSIVE `b09r-main-a1-r00-11-k1` 23:05:30Z-23:08:03Z, `b09r-main-a1-r12-23-k2` 23:57:25Z-23:59:59Z, `b09r-main-a1-r24-35-k3` 01:27:10Z-01:29:43Z, `b09r-ctl-a1-r36-36-k4` 02:58:50Z-02:59:26Z, all rc 0. SHARED `b09r-versions-start`, `b09r-versions-end`, `b09r-analyze-final`. The lines are verbatim in `raw/lock-ledger.jsonl` and listed in `provenance.json` | REAL |
| Live heads (git ls-remote, read-only) | **Start 21:02Z:** trycua/cua main `a9baa8d10`; trycua/cua PR 4316 `a0bca7440`; kvnloo/cua#105 `98a45e6c5`; kvnloo/cua#106 `c45845797`. **End 03:03Z:** main `fbec9eece`; PR 4316 `b2ae7cb93`; #105 and #106 unchanged. PR 4316 was rebased onto newer main (merge base 345ff6d9d → 8fdcd83ed). Its 12 changed files have identical blobs at both heads | SOURCE |
| B7 source vs upstream main | 0f1955d2f → a9baa8d10 (77 commits): the Linux-relevant libs/cua-driver changes are `platform-linux/src/overlay.rs` (trycua/cua PR 4529: idle X11 cursor overlays stay unmapped, on the feedback-on path BASE uses) and `cua-driver-core/src/expectation.rs` (trycua/cua PR 4531, macOS verify_state). The rest is version/changelog/docs/macOS/Windows/installer churn. jev-use is unchanged. a9baa8d10 → fbec9eece (20 commits): macOS invoke_menu, installers, a doc-only contract comment. B7's tested source is fixed, so carrying a claim to current main needs recertification | SOURCE |
| Publication SHA | Set by Publish (`provenance.json: publication_sha`). Never equal-by-assumption to the tested SHA or the lane head | SOURCE |
| Provider | None (scripted chooser). TypeSafe cap 0: 0 attempts, 0 reached; no key forwarded | NOT_RUN |

The harness change (commit `9d0138653`, wave 7), in `harness/b04/harness/compiled_routine.py`:

- `CUA_LANE_EXP_ROUTINE_POLL_MS` sets the verify `bounded_read` interval. Unset = 10 ms, the current behaviour; 0 =
  `asyncio.sleep(0)`, a yield only. Reconcile reads are unaffected.
- A `STAMP` hook, None by default, records `routine_read_send` / `routine_read_return` around each routine oracle
  read and `poll_sleep_start` / `poll_sleep_end` around each poll sleep (time.monotonic_ns).
- `CUA_LANE_EXP_PC_SLEEP_MS` is read by `run_b09.py`.

## Method (pre-registered; PREREG.json, unchanged)

- **Arms (fill only), one Williams square.** A 6x6 square `rc.williams(6)`; round r runs row r mod 6; 36 rounds = 6
  squares, so every contrast has 36 within-round pairs and there are 216 measured trials.
  - BASE: R2-10 BASE.
  - P10a / P10b: the current 10 ms poll; the A/A pair.
  - P1: 1 ms poll.
  - P0: yield only; descriptive.
  - PC: P10a + 15 ms in T.
- **Controls.** After the measured rounds: SMOKE ×5 and N-W2 ×3 (round index 36).
- **Gates.**
  - G0: ≥ 95% valid per arm and identical verified outcomes.
  - G1: CI(P10a − P10b) contains 0 and |median| ≤ 1.0 ms.
  - G2: CI(PC − P10a) lies inside [12, 18] ms.
  - G3: E4 = 0 in every arm and N-W2 3/3.
- **Poll verdict.** Computed only when G0-G3 pass.
  - DELETED (KEEP) iff median(P10a − P1) ≥ 3.0 ms and its CI lower bound > 0.
  - IRREDUCIBLE (KILL) iff the CI upper bound < 3.0 ms.
  - Otherwise UNDECIDED.
- **Statistics.** Paired within-round medians of T_runner; percentile bootstrap, 10 000 resamples, a fresh
  `random.Random(20261003)` per contrast.
- **S (E3).** S = median T(BASE) / median T(P1 if DELETED, else P10a), pair bootstrap; the gate is CI lower bound > 1.
  The floor ratio uses T_irreducible from Part E'.
- **Part E'.** B-08 Part E on P10a and on the best arm, plus a split view built on the stamps (poll_sleep / read_hop
  / runner_other). The target-effect tail rule runs first. Untested share in both BELOW_GATE views, target < 5%.
- **Locks and environment (B-09R).**
  - Each chunk: the cargo-build lock is seen free and the 1-min loadavg is ≤ 4.0 before queueing. Then one EXCLUSIVE
    `bin/quiet-timed b09r-<chunk>`. Inside it: `flock -w 60` on the cargo lock (exit 74 = nothing ran) and
    `timeout 900`.
  - A round starts only at 1-min loadavg ≤ 4.0.
  - At most one EXCLUSIVE waiter is queued at a time.
  - While waiting, a read-only holder snapshot every 15 min goes to `raw/locks/holders.jsonl` (pid, ppid, elapsed,
    executable name, lock type; nothing else).

## Results (N of M, evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| Measured A/B (BASE/P10a/P10b/P1/P0/PC, 36 rounds, 4 EXCLUSIVE windows) | 216 of 216 verified, exactly one submit each | every arm 36/36: BASE 36/36, P10a 36/36, P10b 36/36, P1 36/36, P0 36/36, PC 36/36; identical verified outcomes; E4 total 0 | BENCHMARK (REAL raw) |
| G0 validity | 6 of 6 arms | valid share 1.0 in every arm | BENCHMARK |
| G1 A/A (NC) | P10a-P10b n=36 | P10a-P10b -0.46 ms, CI [-1.34, 1.43]: contains 0, \|median\| ≤ 1.0. Pass | BENCHMARK |
| G2 positive control | PC-P10a n=36 | PC-P10a 14.61 ms, CI [13.51, 15.31]: inside [12, 18]. Pass | BENCHMARK |
| G3 invariants | 6 arms + 3 N-W2 | E4 0 in every arm; N-W2 3/3. Pass | REAL |
| **Poll verdict** | P10a-P1 n=36 | P10a-P1 9.20 ms, CI [8.26, 10.05] → poll verdict DELETED (KEEP) | BENCHMARK |
| P0 (descriptive) | P10a-P0 n=36; P1-P0 n=36 | P10a-P0 9.55 ms, CI [8.65, 11.12]. P1-P0 0.87 ms, CI [-0.52, 1.46]: yield-only is not distinguishable from 1 ms, and P0 adds 0.94 reads per task vs P1 (P1 adds 0.00 reads per task vs P10a) | BENCHMARK |
| Secondary clocks (target side) | 36 pairs each | T_j P10a-P1 0.00, T_oracle P10a-P1 -0.06: the submit lands at the same time. T_j P10a-P10b -0.26, T_oracle P10a-P10b 0.00. T_j PC-P10a 14.75, T_oracle PC-P10a 14.02 (the PC sleep sits before dispatch, so it moves both) | BENCHMARK |
| Load sensitivity | 34 of 36 rounds (every trial ≤ 4.0) | POLL median 9.22 ms, CI [8.37, 10.27]; NC -0.46; PC 14.61. Unchanged | BENCHMARK |
| **E3: S** | S over 36 pairs | S = 48.2, S CI [47.6, 48.7] (median T BASE 3176.1 ms, median T composed 65.94 ms, composed arm P1); gate CI lower > 1 passes. S on T_j 48.9, S on T_oracle 48.0 | BENCHMARK |
| SMOKE (knob unset = B-08 behaviour) | 5 of 5 | SMOKE 5/5: verified, lane variables unset, no experimental marks, same routes as BASE | REAL |
| N-W2 (forced stale-ref fallback) | 3 of 3 | N-W2 3/3: `browser_ref_stale` refused, fresh snapshot then one submit | REAL |
| Part E' P10a (B-08-comparable) | 36 of 36 decomposed, 0 failed | P10a corr BG=IRR 2.7%, P10a corr BG=UNT 4.9%; P10a raw BG=IRR 2.7%, P10a raw BG=UNT 9.3% | BENCHMARK |
| Part E' P1 (composed) | 36 of 36 decomposed, 0 failed | P1 corr BG=IRR 3.8%, P1 corr BG=UNT 6.5%; P1 raw BG=IRR 3.7%, P1 raw BG=UNT 11.2% | BENCHMARK |
| Floor ratio (E3) | P1 | P1 floor ratio (excl cold excess) 3.37; P1 floor ratio (incl cold excess) 1.75 (T_irreducible 17.47 / 33.70 ms, corr BG=IRR) | BENCHMARK |
| Wave 7 pilot (SHARED lock, before PREREG) | 12 of 12 | excluded from every number; labelled excluded (`raw/pilot-trials.tar.gz`) | FIXTURE (excluded) |

### Per-arm component timings (T_runner, ms; means except T and effect latency, which are medians)

| Arm | T median | reads | sleeps | poll sleep | effect latency | load max |
|---|---|---|---|---|---|---|
| BASE | BASE T 3176.05 | BASE reads 1.00 | BASE sleeps 0.00 | BASE poll sleep 0.00 | BASE effect latency 0.25 | BASE load max 4.40 |
| P10a | P10a T 75.06 | P10a reads 2.00 | P10a sleeps 1.00 | P10a poll sleep 10.08 | P10a effect latency 1.35 | P10a load max 4.12 |
| P10b | P10b T 75.55 | P10b reads 2.00 | P10b sleeps 1.00 | P10b poll sleep 10.08 | P10b effect latency 1.38 | P10b load max 4.55 |
| P1 | P1 T 65.94 | P1 reads 2.00 | P1 sleeps 1.00 | P1 poll sleep 1.04 | P1 effect latency 1.34 | P1 load max 3.72 |
| P0 | P0 T 65.10 | P0 reads 2.94 | P0 sleeps 1.94 | P0 poll sleep 0.02 | P0 effect latency 1.42 | P0 load max 3.72 |
| PC | PC T 89.69 | PC reads 2.00 | PC sleeps 1.00 | PC poll sleep 10.08 | PC effect latency 1.37 | PC load max 3.87 |

Every round started at 1-min loadavg ≤ 4.0, as pre-registered. The per-trial maximum ("load max") can be higher
because load rises inside a round. The load-sensitivity row keeps only the rounds where every trial was ≤ 4.0, and
the verdict holds there.

## Part E' (decomposition; corrected view primary, raw view shown)

c_m = 31.92 us. The target-effect tail rule runs first, so the effect wait inside the poll sleep stays
`target_effect_lag`.

| Split of R2-10's `runner` (ms per task) | P10a | P1 |
|---|---|---|
| B-08 `runner` label | P10a corr runner_b08_labels 9.82 | P1 corr runner_b08_labels 0.72 |
| poll_sleep (after the effect) | P10a corr poll_sleep 9.60 | P1 corr poll_sleep 0.55 |
| read_hop (routine thread hop) | P10a corr read_hop 0.07 | P1 corr read_hop 0.04 |
| runner_other | P10a corr runner_other 0.15 | P1 corr runner_other 0.13 |
| target_effect_lag | P10a corr target_effect_lag 1.42 | P1 corr target_effect_lag 1.39 |
| effect wait inside the poll sleep | P10a corr effect_wait_inside_poll_sleep 0.48 | P1 corr effect_wait_inside_poll_sleep 0.50 |
| raw view (same split) | P10a raw runner_b08_labels 9.82; P10a raw poll_sleep 9.60; P10a raw read_hop 0.07; P10a raw runner_other 0.15; P10a raw target_effect_lag 1.42; P10a raw effect_wait_inside_poll_sleep 0.48 | P1 raw runner_b08_labels 0.72; P1 raw poll_sleep 0.55; P1 raw read_hop 0.04; P1 raw runner_other 0.13; P1 raw target_effect_lag 1.39; P1 raw effect_wait_inside_poll_sleep 0.50 |
| mean T (corr) | mean T P10a 67.72 | mean T P1 58.89 |
| floor ratio excl / incl cold excess | P10a floor ratio (excl cold excess) 3.82; P10a floor ratio (incl cold excess) 2.04 | P1 floor ratio (excl cold excess) 3.37; P1 floor ratio (incl cold excess) 1.75 |

These components carry at least 5% of T (or at least 50 ms), corr view:

- **P10a:**
  - reval_endpoint, 21.87 ms, 32.3%: OWNER_DECISION (B-02 H_E);
  - cold excess, 15.55 ms, 23.0%: OWNER_DECISION per process (B-08) + IRREDUCIBLE per document (B-04);
  - observation (rest), 5.68 ms, 8.4%: IRREDUCIBLE (B-04);
  - **poll_sleep, 9.60 ms, 14.2%: DELETED (this lane).**
- **P1:**
  - reval_endpoint, 21.75 ms, 36.9%: OWNER_DECISION;
  - cold excess, 16.23 ms, 27.6%;
  - observation (rest), 5.74 ms, 9.7%: IRREDUCIBLE;
  - mcp_transport, 3.26 ms, 5.5%: per unit (B-05/B-07).

Every component at or above the gate now has a terminal verdict on both arms.

**Fill's untested share against the < 5% target:**

- **P10a, the B-08-comparable arm:** P10a corr BG=IRR 2.7% and P10a corr BG=UNT 4.9%. Both views meet the target
  (B-08: 16.9% / 19.0%).
- **P1, the composed arm:** P1 corr BG=IRR 3.8% meets it; P1 corr BG=UNT 6.5% does not. The residue is about
  2.2-3.8 ms of below-gate items, and deleting 9 ms shrinks the denominator. The residue:
  - input_prep 0.85 ms (R2-10) and c_in.prep 0.66 ms (B-07: fill's fragile DELETED is not carried);
  - the remaining 1 ms poll sleep, 0.55 ms;
  - read_hop 0.04 ms and runner_other 0.13 ms;
  - in the BG=UNT view, about 20 MCP transport / admission / resolution units of 0.01-0.42 ms each.
- **Raw views (no c_m correction):** P10a raw BG=IRR 2.7% / P10a raw BG=UNT 9.3%; P1 raw BG=IRR 3.7% /
  P1 raw BG=UNT 11.2%.

## Work deleted vs wall-clock saved

| item | work deleted | wall-clock saved | evidence class |
|---|---|---|---|
| verify-poll interval 10 → 1 ms (P10a → P1, caller runner setting) | 9.04 ms of poll sleep per task (P10a poll sleep 10.08 → P1 poll sleep 1.04); 0 reads added (P1 adds 0.00 reads per task vs P10a). No target work is deleted: the effect lands at the same time | P10a-P1 9.20 ms (median paired T_runner, CI [8.26, 10.05]). On the target-side clocks: T_j P10a-P1 0.00, T_oracle P10a-P1 -0.06 | BENCHMARK |
| yield-only poll (P0, descriptive) | the sleep is gone, but P0 adds 0.94 reads per task vs P1 (oracle reads become the wait) | P1-P0 0.87 ms, CI [-0.52, 1.46]: not distinguishable from P1 | BENCHMARK |
| BASE → composed P1 (all R2-10 deletions + this poll, scripted, B7) | the R2-10 composed deletions (feedback/glide, guard, compiled replay, validators, admission cache) + this poll | median T BASE 3176.1 → median T composed 65.94 ms; S = 48.2 | BENCHMARK |
| this lane's code | none (measurement only; env-gated, default-off caller stamps and interval) | none | SOURCE |

## Disposition

**Disposition: KEEP.** B-09 moves from BLOCKED to a terminal row.

- **E2:** fill's last untested component (R2-10 `runner`, the compiled-routine verify-poll sleep) is DELETED on B7.
  Fill's untested share is below 5% in both corrected BELOW_GATE views on P10a. On the composed P1 arm it is below
  5% with BELOW_GATE as IRREDUCIBLE (3.8%) but not with BELOW_GATE as UNTESTED (6.5%). The rest is below-gate
  residue, with no single item at or above the gate.
- **E3:** one-binary scripted fill S = 48.2 with CI [47.6, 48.7], 36 pairs, with floor ratios 3.37 (excl cold excess)
  / 1.75 (incl cold excess).
- **E4:** 0 in every arm; N-W2 3/3.
- **Product boundary:** the poll is the caller runner's setting in the compiled routine (lane harness). The deletion
  is measured, not shipped. Changing a product default (the jev-use run.py 100 ms poll, or the routine default) is a
  separate reviewed fix or an OWNER_DECISION row, not this lane's claim.

## Deviations and disclosures

1. **Wave 7: measured run not run.** The first measured chunk (`b09-main-a1-r00-11-k1`) queued at 16:13:05Z and was
   never granted EXCLUSIVE. An orphaned non-loop process held a shared flock (`raw/lock-blocker.json`). Wave 7 stopped
   only its own processes; no ledger line exists for that chunk. B-09R resumed with fresh lane temp, so no wave-7
   trial file exists in the measured raw.
2. **PREREG commit rewritten once before any data (wave 7).** `bfed36749` → `b4480de1f`, 8 s later, `written_utc`
   only, before any measured trial. B-09R did not touch PREREG.json.
3. **B-09R bookkeeping commit `21a331786` (before the first measured trial):**
   - ledger labels `b09r-`;
   - `run-chunk.sh` closes fd 9 inside the window, so no child can inherit the quiet-lane lock;
   - `run_all.py` logs to `b09r-run_all.log`;
   - `package_raw.py` keeps `b09-`/`b09r-` ledger lines and copies `raw/locks/`;
   - `lock-snapshot.sh` (new);
   - the verifier's SHARED receipt names.
4. **EXCLUSIVE wait.** Cumulative waiting was 5963 s host-side (load ≤ 4.0 and cargo-lock checks) plus 14979 s
   queued for EXCLUSIVE, about 5.8 h, under the 8 h cap.
   - The queue waits came from long SHARED holders of other tracks (the holder snapshots show python3 processes
     holding SHARED for 50-90 min each).
   - No holder was signalled. One EXCLUSIVE waiter was queued at a time.
   - Windows: 152.9 s, 153.3 s, 152.2 s and 36.1 s.
5. **Load inside rounds.** Every round started at 1-min loadavg ≤ 4.0. Two rounds had a trial above 4.0 (max 4.55),
   and the load-sensitivity row without them leaves the verdict unchanged. In round 23 the runner held the round for 2 s:
   load was 4.12 at its first check, and the round started at 3.87.
6. **BASE has the phase trace on** (as B-08 SMOKE did). This is measurement-only and is carried in S.
7. **Pilot.** 12 trials (wave 7, rounds 0-1, SHARED, load 11-12) ran before PREREG. They are excluded from every
   number and labelled so (`raw/pilot-trials.tar.gz`, `raw/pilot/run-manifest-pilot-pilot-a1-r00-01.json`).

Near misses (none had an effect):

- Wave 7: one stdlib `python3` file patch and one `flock -s -n` probe ran in the plain host shell.
- B-09R: one empty `python3 -` heredoc (no program text) ran in the plain host shell while the lane looked up label
  usages; it executed nothing.
- Every other B-09R Python run used `bin/hostless`.

Hard-rule breaches: none.

## Limits and claim boundary

- Scripted fill → submit on B7 in a private Xvfb + Driver-launched Chrome on the jev-use fixture. One shared Linux
  host. No live provider.
- No comparison with any other binary. Absolute T is never compared with B-06 / B-08 / R2-10R. B-09R decomposition
  numbers are not combined with B-08's, even though the Chrome version is the same.
- The poll knob is measurement-only. Any product change is a separate reviewed fix.
- S includes every R2-10 composed deletion and the cold (per-trial fresh Driver + Chrome) start. It is a
  one-binary scripted number, not a provider-in-the-loop speedup. PreAct / SkillDroid are references only, with
  different benchmarks and scope.

## Files

- **Pre-registration and provenance:** `PREREG.json`, `provenance.json`.
- **Results:** `b09-summary.json` (analyze_b09.py), `headline-numbers.json` (make_headlines.py).
- **Verifier:** `verify_artifacts.py` (`hostless python3 verify_artifacts.py`, with CUA_PRIVACY_NAMES_FILE and
  CUA_PRIVACY_PATTERNS_FILE set to untracked files), `verify_helper.py`.
- **Lane code:** `run_b09.py`, `b09_rows.py`, `analyze_b09.py`, `make_headlines.py`, `lane-scripts/run_all.py`,
  `lane-scripts/run-chunk.sh`, `lane-scripts/run-pilot.sh`, `lane-scripts/session-retry.sh`,
  `lane-scripts/in-session.sh`, `lane-scripts/shared-locked.sh`, `lane-scripts/package_raw.py`,
  `lane-scripts/lock-snapshot.sh`.
- **Tests:** `tests/test_b09_poll.py`, `tests/test_compiled_routine_r207.py`.
- **Harness copies:** `harness/b04/` (with the one changed file `harness/b04/harness/compiled_routine.py`),
  `harness/b05/b05_spans.py`, `harness/b07/b07_stdio.py`, `harness/r2-10r/r2_10_browser.py`,
  `harness/r2-10r/scripted-COMP.json`, `harness/r2-10r/analyze_r2_10.py`,
  `harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/b01_analysis.py`,
  `harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/analyze_browser.py`.
- **Raw (B-09R measured):**
  - Trials: `raw/main-trials.tar.gz` (224 trials × event log + Driver trace).
  - Manifests: `raw/main/run-manifest-main-m-a1-r00-11-k1.json`, `raw/main/run-manifest-main-m-a1-r12-23-k2.json`,
    `raw/main/run-manifest-main-m-a1-r24-35-k3.json`, `raw/main/run-manifest-ctl-m-a1-r36-36-k4.json`.
  - Locks: `raw/lock-ledger.jsonl` (wave 7 + B-09R lines), `raw/locks/holders.jsonl`.
  - Final checks: `raw/final/verify-b09r-1.txt` (verify_artifacts.py 20/20 on `33deb4f2a`, SHARED `b09r-verify-1`),
    `raw/final/scan-range-b09r.json` (PUB-04 scanner, range 56284782d..33deb4f2a: 2 commits, 0 private findings),
    `raw/final/scan-census-b09r.json` (PUB-04 census of the branch tip: 28 commits not in upstream main, 0 private;
    2 generic-path hits in upstream PR 4316 commits, not lane commits).
  - Logs: `raw/logs/b09r-run_all.log`, `raw/logs/b09r-main-a1-r00-11-k1.log`, `raw/logs/b09r-main-a1-r12-23-k2.log`,
    `raw/logs/b09r-main-a1-r24-35-k3.log`, `raw/logs/b09r-ctl-a1-r36-36-k4.log`,
    `raw/logs/versions-b09r-start.log`, `raw/logs/versions-b09r-end.log`.
- **Raw (wave 7):**
  - Blocker: `raw/lock-blocker.json`.
  - Pilot (excluded): `raw/pilot-trials.tar.gz`, `raw/pilot/run-manifest-pilot-pilot-a1-r00-01.json`.
  - Unit: `raw/unit/unit-red.log`, `raw/unit/unit-green.log`.
  - Logs: `raw/logs/versions-start.log`, `raw/logs/versions-end.log`, `raw/logs/b09-pilot-r00-01.log`,
    `raw/logs/b09-run_all.log`, `raw/logs/b09-main-a1-r00-11-k1.log`.
