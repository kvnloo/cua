# CUA RFC loop: wave 5 synthesis (2026-10-03 UTC)

Wave 5 ran eight lanes, two of which also carried text-only fix passes for lanes rejected in wave 4.

- **Accepted (10 dispositions):** B-06, B-07, B-05 (attempt 3, verified as B-07's Part 0), N-04, N-03 (attempt 3, verified as N-04's Part 0), R2-07d, OWN-78A, RECERT-FIX (attempt 3), OWN-20P and PUB-02.
- **Rejected:** none.
- **Hard-rule breach:** none.
- **Not yet published.** Nothing is on origin (all 15 local heads checked with `git rev-parse` at 12:23Z).

**TypeSafe this wave:** OWN-78A used 20 attempts and 20 reached, inside its cap of 24. R2-07d's cap of 18 went unused because Phase L did not run. Every other lane, every verifier and this synthesis used 0. **Loop total: 562 / 600 reached (658 attempts); 38 remain.**

## 0. Stop rules, breach classes, rulings needed

- **Hard-rule breach:** none.
  - Nothing reached the host desktop or session.
  - No secret was exposed and nothing was written upstream.
  - Every reported timing number came from a quiet-timed window. OWN-20P's settle and T figures ran under SHARED locks and are labelled non-claims.
- **Near misses (none had an effect):**
  - **Lanes:** stdlib `python3` parses and no-ops in the plain host shell in B-06, R2-07d, OWN-78A, RECERT-FIX and OWN-20P. B-07 also ran a `python3 --version` and a `pgrep -f` inside a read-only `ps` listing, with no signal sent.
  - **N-04:** `bash -n` checks; `git config` without `--worktree` (it wrote values identical to the existing ones); a zsh argument error that left one EXCLUSIVE window with no trial.
  - **Verifiers:** one plain-shell `python3` no-op or parse each in B-06, N-04, RECERT-FIX and OWN-20P.
  - **This synthesis:** read-only `jq` / `git` / `gh` reads in the plain shell. One `git rev-parse` loop failed on zsh word-splitting ("no such file or directory"; nothing ran) and was re-run under bash. The STATE update ran under `bin/hostless`.
- **Lock-order interference (not a breach):**
  - R2-07d's Q2 chunk held `cargo-build.lock` for about 30 minutes while it waited for EXCLUSIVE quiet. That stalled every build.
  - OWN-20P's first scripts did the reverse. They held SHARED quiet while waiting for cargo, which made another lane's EXCLUSIVE waiter wait about 2.5 minutes.
  - Both lanes stopped only their own processes, by exact PID.
- **Rulings still open from wave 4:**
  - The RECERT-FIX attempt-2 cross-lane `pkill`. Attempt 3 ran clean.
  - Published-fork privacy:
    - (a) `exp/r2-10-composition-20261002` @ `030f6bdbf` carries the encoded private-name list. PUB-02 has a clean candidate ready: r1c `eaca68df9`.
    - (b) `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0` has the local user name in raw xhost output, 10 times. There is no candidate yet.
- **Stop-rule counters:**
  - Waves used: 6 of 12.
  - Not stalled. There are many new terminal dispositions, and E2 fell for native (3.9/6.9% → 1.19/1.65%) and for browser modal (16.2% → 0.6–5.5%).
  - Budget OK; 38 reached remain.

## 1. What changed this wave

- **B-07: REVISE. Every browser MCP transport sub-span now has a terminal verdict** (`eab1e87a3`, binary B7 `6f95aef5` = R' plus marks plus an env-gated knob, loadavg ≤ 4.0).

  | Sub-span | Fill / toggle / modal (ms) | Verdict |
  |---|---|---|
  | c_out.route | 0.39 / 0.34 / 0.35 | BELOW_GATE |
  | adm.inner | 0.09 / 0.10 / 0.10 | BELOW_GATE |
  | d_out.post | 0.91 / 0.57 / 0.59 | IRREDUCIBLE (the POST_FAST validator prewarm is KILL in every class) |
  | c_in.prep | 0.63 / 0.60 / 0.61 | IRREDUCIBLE for toggle and modal (PREP_FAST KILL). For fill, the pre-registered gate gives DELETED. |

  - The fill DELETED is **fragile**: 3.94 [0.09, 10.07] ms, median 0.04 ms, work deleted 0.48 ms.
    - Without round 0 it is 1.25 [−0.25, 2.90], which is KILL.
    - Round 0 is a training invocation, not compiled replay.
    - Each of the verifier's alternative readings also gives KILL.
    - Neither knob is carried forward.
  - **E2 untested on B7** (R2-10 mapping, corrected):
    - 1.6 / 0.6 / 0.6% when BELOW_GATE counts as IRREDUCIBLE.
    - 4.0 / 3.5 / 3.5% when BELOW_GATE counts as UNTESTED.
    - Modal is 5.5% at the measured-overhead scale. That view is conservative.
  - With the cold excess counted as untested (B-04's mapping), fill and toggle are 26.2% and 19.1%.
- **B-05 (attempt 3): accepted, REVISE** (`705238282`). B-07's verifier gave 73/73 from a clean clone.
  - The headline now says transport is 44/48/35% instrumentation at c_m (about 30/33/24% measured). Only the admission residual is mostly instrumentation.
  - PARSE_FAST and VALIDATE_FAST are KILL, so c_out.parse and c_out.validate are IRREDUCIBLE.
- **B-06: REVISE. The per-process cold excess is still UNDECIDED** (`31bc98a95`, R' `922111c5`, Chrome 151, 559/559 valid, E4 0).
  - **Primary (PREREG) result:** the positive control failed. A 15 ms sleep placed before snapshot1 moved T_oracle by only 10.0 / 10.9 ms, outside the [12, 18] window, because it overlaps the first snapshot's wait. The A/A negative control passed.
  - Under the primary reading, R' shares stay lower bounds: **36.70% fill, 34.93% toggle**.
  - **Secondary result:** Amendment 1 is post hoc. It was committed after the main-block look and before block x. It moved the sleep to after snapshot1 and used 16 pairs per class. Both controls pass.
    - Per-process D is **10.0 [8.0, 12.0] ms fill and 4.0 [3.9, 6.0] ms toggle**, which would make it OWNER_DECISION (process or session reuse kept outside T).
    - Under that reading the shares return to R2-10R's 15.18 / 16.65%.
    - Accepting this reading is the owner's call.
  - T_oracle is quantised at 2 ms.
- **N-04: KEEP. Native composition is closed on one source** (`9d7d8d7a5`, R'n `78a1137d` = R' plus N-02 marks, one binary; 528/528 tasks valid and oracle-verified; Williams-balanced).
  - **V (admission tools-list cache): DELETED.** It saves 2.94 [2.02, 3.46] ms on checkbox and 3.04 [2.01, 3.91] ms on text.
  - **HCL (lazy validators): OWNER_DECISION.** About 0 at k=1, and 82.22 / 73.69 ms per 5-task session.
  - **Best arm X+V+HCL:** S 1.196 [1.189, 1.198] checkbox and 5.941 [5.938, 5.957] text. KEEP-only S0 is 1.180 / 1.030.
  - **E2 untested:** 1.19% / 1.65%; conservative 2.23 / 2.62%.
  - The default-off smoke shows R'n equal to R'. Focus steal was restored 19/20 (no gate).
- **N-03 (attempt 3): accepted** (`6b70ec902`). N-04's verifier confirmed every Part 0 fix and gave VERIFY OK from a clean clone.
  - ax_fg S0 is DELETED, scoped to GTK3 on X11 ax_fg at the default config.
  - Part B is disclosed as not order-counterbalanced, with a bound of about 0.6 / 0.25 ms.
  - The focus-steal control is a pre-registered FAIL at 39/40.
- **R2-07d: REVISE** (`79f6dd299`; the lane record's SHA is a placeholder). Binary R, quiet window at loadavg ≤ 2.96, 40 pairs per class.
  - **Toggle** CR − COMP: +0.5 [−1.3, +0.8] ms, **PASS**.
  - **Modal** CR − COMP: +0.6 [−1.4, +2.4] ms, **FAIL**: the upper bound exceeds +2.0 by 0.4 ms. Do not reinterpret this.
  - Every correctness gate passed. G3 84/84 fresh, E4 0 over 164 cells, controls 35/35.
  - **Phase L: NOT_RUN** (pre-registered precondition). The compiled routine is excluded from the composed toggle/modal configuration.
- **OWN-78A: REVISE for kvnloo/cua#78** (`6f6c67955`, fix candidate F `61eec0909`, 20 live TypeSafe step-1 decisions).

  | Arm | Request | Correct step 1 |
  |---|---|---|
  | A0 | PR | 0/5 (abstained 5/5) |
  | A1 | PR + form | 1/5 |
  | A2 | F: PR + form + page + outline | 5/5 |
  | A3 | pre-PR | 5/5 |

  - **Attribution:** PAGE_OUTLINE_ALSO_NEEDED. Form alone is a large contributor (P(type) 0.09–0.12 → 0.34–0.45) but is not sufficient.
  - A2's margin over abstain is thin: +0.08 to +0.12.
  - TS tests: 107/109 on the PR, 109/109 on F, both credential-free.
  - R1-lite NOT_RUN (lane cap). Full-n R1/R4 BLOCKED (budget). S1 BLOCKED.
- **RECERT-FIX (attempt 3): RECERTIFIED on 0f1955d2f** (`939580fc6`; the lane record's `e53833ca6` is stale).
  - **FIX-02:** F1–F3 RECERT_PASS (KEEP). F4 RECERT_PASS but stays REVISE (TOCTOU window).
  - **OWN-09R (the kvnloo/cua#84 revision):** RECERT_PASS under Deviation 6. A strict PREREG reading makes its head-core unit row REVISE: the first run was 818/2, and the re-run rule was committed after that, before the 847/0 re-run.
  - **OWN-16W dd205d17b:** RECERT_PASS.
  - **New kvnloo/cua#36 same-process two-window row: KEEP.**
    - On F', W2a/W2c/W2d are refused 20/20, positives pass 20/20, and there are 0 cross-session mutations.
    - On U', the W2a cross-session token landed 20/20.
    - U' also refuses W2c and W2d, so those two rows do not discriminate.
  - **E4:** F' 0. U' had 100 cross-session mutations, 50 stale dispatches and 20 duplicates.
- **OWN-20P: KEEP, both as fork candidates** (`64081dded`).
  - **G ported to clean main** (`a761f1f1f`).
    - Red/green; lib 604/0.
    - R1 on the marked twins (with the post-action-sleep knob at 0): G0m restored 40/40, U0m missed 40/40 silently.
    - Product G0 normal path: 40/40 verified, 0 false restores.
  - **A, a11y bus reconnect** (`064d2e4ad`).
    - GA is live in-process 20/20; G0 1/20, and that one is a harness artifact with no restart.
    - In the restart-happened view: GA 25/25, G0 0/24.
    - Safety 20/20 on both.
  - The kvnloo/cua#20 R3 row becomes "safe and live in-process with A".
- **PUB-02: KEEP (publish gate).**
  - **A:** R2-10R a3 `d22eeb2ec`, which replaces the never-pushed a2. 189/189 checks both ways.
  - **B:** R2-10 r1c `eaca68df9`. 133/133. **Hold for the owner ruling.**
  - **C:** template scanner with hex/base64 decoding (`c4342323b`). It catches the dummy name 3/3; the old scanner caught 0/3.
  - **Origin audit:** private-class hits on only 2 of 133 tips, (a) and (b) above.

## 2. Per-reference-task decomposition (best known)

Rules:
- **Sources** (never add or ratio across them):

  | Lane | Source | Binary |
  |---|---|---|
  | R2-10R | R' 45dff8f32 | `922111c5` |
  | B-06 | R' | `922111c5` |
  | B-07 | B7 = R' + marks + knob | `6f95aef5` |
  | N-04 | R'n = R' + N-02 marks | `78a1137d` |
  | R2-07d / B-04 / R2-10 | R | `12b9045a` |
  | B-05 | B5 | `f4149bdd` |
  | N-03 | N3 | `b1843871` |

- **Metrics:** T is the median T_oracle, unless the table says mean. Components are mean ms.
- **"Cross-lane reading"** means combining verdicts across lanes, never numbers.

### Browser (scripted COMP)

| Class | T (lane) | Material components (verdict) | Untested, cold excess not untested | Untested, cold excess untested |
|---|---|---|---|---|
| fill→submit | 63.9 ms (B7); 64.2 cold / 54.1 warm (R', B-06) | observation 23.5 IRREDUCIBLE; endpoint reval 22.0 OWNER_DECISION; cold excess 16.8 (B7) / 17.4 (R') — per-document IRREDUCIBLE, per-process **UNDECIDED**; transport 3.35 corrected (all sub-spans terminal); resolution 1.98; admission residual 0.11 | **1.6%** (4.0% with BELOW_GATE as UNTESTED), B7 | 26.2% (B7); **36.70%** (R', B-06 primary; R2-10R's transport still untested there) |
| toggle→confirm | 49.4 ms (B7); 50.2 / 46.1 (R') | endpoint 21.6 OWNER_DECISION; observation 12.5 IRREDUCIBLE; cold excess 7.7 / 9.8 per-process **UNDECIDED**; transport 2.45 terminal | **0.6%** (3.5%), B7 | 19.1% (B7); **34.93%** (R') |
| modal→act | 49.4 ms (B7) | endpoint 21.3; observation 12.8; cold excess 7.5 (not in the B-04/B-06 gates); transport 2.48 terminal | **0.6%** (3.5%); 5.5% conservative measured-overhead view | — |

- **B-06's amended reading (owner's call):** per-process D is about 10 ms (fill) and 4 ms (toggle), as OWNER_DECISION.
  - On R2-10R's own mapping, where transport was still untested, the shares are 15.18% (fill) and 16.65% (toggle).
  - Combined with B-07's transport verdicts (cross-lane reading), fill and toggle would fall to about 1.6% and 0.6%.
- **Live:**
  - Toggle and modal provider decisions (R2-10: 434.8 / 462.4 ms, 88–89% of live COMP T) stay **UNTESTED**. Live untested is about 92.7% (toggle) and 90.9% (modal).
  - R2-07d passed toggle non-regression but failed modal, so Phase L did not run. The remaining live work is BLOCKED by paid budget.
- **Work deleted vs wall-clock saved:** unchanged from R2-10R. Fill COMP deletes 3000.3 ms of visualization plus 101.1 ms of settles, and saves 3118.4 ms.
  - Wave 5 deleted nothing in the browser: PREP_FAST is not carried, and it was worth 0.48 ms.
- **Owner-decision dependency (unchanged):** with KEEP-only deletions, S is about 1.01.

### Native GTK3 (N-04 on R'n, best arm X+V+HCL)

| Task | T | Components (verdict) | S (best / S0) | Untested |
|---|---|---|---|---|
| checkbox | mean 280.30 ms | settle 241.6 (86.2%) IRREDUCIBLE; observation transport 16.6 (13.5 of it is client validation, OWNER_DECISION via HCL); observation 10.5; action client validation 6.30 OWNER_DECISION; dispatch 0.97; untested 3.33 | 1.196 [1.189, 1.198] / 1.180 | **1.19%** (conservative 2.23%) |
| text entry | mean 296.57 ms | settle 241.5 (81.4%); observation transport 16.7; action client validation 12.54; observation 10.6; reveal residual 6.69 OWNER_DECISION; dispatch 2.50; untested 4.91 | 5.941 [5.938, 5.957] / 1.030 | **1.65%** (conservative 2.62%) |

- **V DELETED:** 2.94 / 3.04 ms of T, and 2.84 / 4.35 ms of admission work.
- **HCL OWNER_DECISION:** k=1 −0.04 / 0.34 ms; k=5 82.22 / 73.69 ms per session.
- **BASE → best wall-clock saved:**
  - Checkbox: 54.27 ms.
  - Text: 1468.03 ms, of which 1410.6 ms is reveal-glide work deleted (OWNER_DECISION).
- **OWN-20P** (descriptive only): the G port costs about 0.1 ms on the quiet-path settle (240.79 → 240.89 ms). It adds about 156 ms only under an R1 stall, and that time is the verified restore.

## 3. Dispositions (this wave)

| ID | Disposition | Class | Branch @ commit |
|---|---|---|---|
| B-06 | REVISE: per-process UNDECIDED (PC failed); amended OWNER_DECISION (owner's call) | REAL+BENCHMARK (FIXTURE); SOURCE | exp/b-06-per-process-cold-snapshot-20261003 @ `31bc98a95` |
| B-07 | REVISE: transport sub-spans terminal; PREP_FAST / POST_FAST not carried | REAL+BENCHMARK (FIXTURE); UNIT (weak); SOURCE | exp/b-07-transport-residual-rprime-20261003 @ `eab1e87a3` |
| B-05 | REVISE (text fix accepted); parse/validate IRREDUCIBLE | REAL+BENCHMARK (FIXTURE); UNIT | exp/b-05-browser-mcp-transport-a3-20261003 @ `705238282` |
| N-04 | KEEP: V DELETED, HCL OWNER_DECISION; native E2 + E3 on one source | REAL+BENCHMARK (FIXTURE); UNIT | exp/n-04-native-composition-rprime-20261003 @ `9d7d8d7a5` |
| N-03 | Accepted (text fix): V DELETED, HCL OWNER_DECISION, ax_fg S0 DELETED (scoped) | REAL+BENCHMARK (FIXTURE); UNIT | exp/n-03-native-closure-axfg-a3-20261003 @ `6b70ec902` |
| R2-07d | REVISE: toggle PASS, modal FAIL; Phase L NOT_RUN | REAL+BENCHMARK (FIXTURE); UNIT; LIVE_PROVIDER NOT_RUN | exp/r2-07d-quiet-timing-phase-l-20261003 @ `79f6dd299` |
| OWN-78A (#78) | REVISE: PAGE_OUTLINE_ALSO_NEEDED; fix candidate F; R1-lite NOT_RUN, R1/R4 and S1 BLOCKED | LIVE_PROVIDER + FIXTURE + UNIT | exp/own-78a-abstain-isolation-4394-20261003 @ `6f6c67955` (F `61eec0909`) |
| RECERT-FIX | RECERTIFIED: FIX-02 F1–F3 KEEP, F4 REVISE, #84 revision (Deviation 6), OWN-16W; #36 two-window KEEP | UNIT + REAL (FIXTURE) + SOURCE | exp/fix-recert-a3-20261003 @ `939580fc6`; candidates `df4f1edf5` / `ba611b51a` / `7e31eae59` |
| OWN-20P (#20) | KEEP: G port + A reconnect (fork candidates) | UNIT + REAL (FIXTURE) + SOURCE | exp/own-20p-guard-port-a11y-20261003 @ `64081dded` |
| PUB-02 | KEEP (publish gate) | SOURCE + UNIT | C docs/packet-template-privacy-20261003 @ `c4342323b`; A exp/r2-10r-recert-a3-20261003 @ `d22eeb2ec`; B exp/r2-10-composition-r1c-20261003 @ `eaca68df9` (HOLD) |

**BLOCKED, with exact blockers** (STATE.blocked_items_w5):
- **Paid budget** (38 reached remain):
  - R2-10 live recertification (≥180).
  - Live BASE vs COMP+CR toggle/modal (≥120; modal also needs a passing gate).
  - Native live arms (≥120, or an owner ruling).
  - kvnloo/cua#78 full-n R1/R4 (~60) and the A2-vs-A3 gap.
  - OWN-78A R1-lite (≤6) fits if allocated.
- **Owner decision:**
  - #78 S1.
  - R2-09 WebKitGTK.
  - B-06's amendment reading.
  - Published-fork privacy (a) and (b).
- **Real Hyprland seat:** #16, #94 with #92/#100/#101, the R2-09 foreground route, and the OWN-20G/20P Wayland rows.
- **macOS/Windows hardware:** #6, #8, #13, #19, #31, #72, the #16/#36 rows, #9 R3, and dd205d17b parity.
- **Owner/orchestrator action:** the fail-closed hostless guard.

**New OWNER_DECISION items:**
- B-06 amendment reading.
- OWN-09R strict unit-row reading.
- OWN-20P marked-twin R1 substitution, and whether A's trigger set is enough.
- OWN-16W analyzer-vs-PREREG reading.
- Allocation of the 38 remaining reached.
- Driver telemetry default-on in sessions.

These join the earlier queue: glide, H_E, reveal, H_T, R2-08, I3s, OWN-09R wait and R8, PR 4336 fields, dd205d17b null, WebKitGTK, HCL session shape, the CL overshoot, the cap, the pkill ruling, and privacy.

## 4. What remains, E1–E6

- **E1 (coverage): nearly met.**
  - **Terminal:** R2-01 to R2-10, R2-10R, B-04 to B-07, N-01 to N-04, and R2-07c/d.
  - **Owner rows:** #9, #16, #36 and #105 are recertified, and #20 has G and A KEEP. #75 is KEEP. #78 is REVISE with its live rows BLOCKED (budget/owner).
  - **Still open:**
    - B-06's per-process part (UNDECIDED unless the owner rules).
    - R2-07 Phase L (NOT_RUN, precondition failed).
- **E2 (critical path): native met; browser scripted depends on one decision; browser live not met.**
  - **Native:** 1.19% / 1.65% on R'n, conservative 2.23 / 2.62%.
  - **Browser scripted:**
    - Modal is below 5% at c_m; the conservative view is 5.5%.
    - Fill and toggle are below 5% (1.6 / 0.6%, cross-lane reading) only if the per-process cold excess is IRREDUCIBLE or OWNER_DECISION. Otherwise they are 19–37%.
  - **Browser live toggle/modal:** about 91–93% untested, all provider decisions. BLOCKED by budget. These are not terminal verdicts, so E2 is not met for the live layer.
- **E3 (composition):**
  - **Browser:** met on R (R2-10) and recertified on R' (R2-10R) for scripted and native.
  - **Native:** met with the surviving deletions on one source (N-04, R'n).
  - **Compiled replay:** excluded for toggle/modal (R2-07d modal FAIL).
  - **Live:** certified only at 989cc76ce.
- **E4 (invariants):**
  - 0 violations in every accepted arm.
  - RECERT-FIX shows discriminating controls on 0f1955d2f: F' 0 vs U' 100/50/20.
  - OWN-20P adds safe and live bus recovery.
  - Still open: F4 TOCTOU, the recording-lookup test, and OWN-09R's bounded wait (owner).
- **E5 (deliverables): not staged.** The evidence is now stable enough to stage:
  - The kvnloo/cua#10 table.
  - The trycua/cua issue 3963 rewrite draft, with a fresh reviewer.
  - The kvnloo/cua#74 queue.

  Only the browser cold-excess row depends on the pending decision.
- **E6 (stability):**
  - **Freshness:** upstream main is `64a178ed6`, 27 commits past 0f1955d2f. It touches 14 libs/cua-driver files, all macOS, Windows, e2e or Skills, plus a macOS fixture and `tests/fixtures/shared/scenarios.json`. None are Linux or core paths. FIX-02, #84 and OWN-16W are now recertified there.
  - **PR heads unchanged:** trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, #105 `98a45e6c5`, #106 `c45845797`.
  - **Moving targets:** E2 verdicts moved this wave (transport terminal, V DELETED on R'n), so "no moving targets" does not hold yet.
  - No judges have run.

## 5. Shared infrastructure (STATE.infra_followups W5)

1. **SHARED quiet-lane holders starve EXCLUSIVE requests.** B-06 waited up to about 75 minutes. Add writer preference or a maximum SHARED hold.
2. **Lock ordering.** Never wait on one lock while holding the other. The cargo-then-quiet order stalled all builds (R2-07d), and the quiet-then-cargo order stalled an EXCLUSIVE waiter (OWN-20P). Use probe-then-acquire.
3. **Driver telemetry is on by default in sessions.** Set `CUA_DRIVER_RS_TELEMETRY_ENABLED=false` in the session wrapper.
4. **Persist the session probe and jitter line** into raw/.
5. **`/tmp/dbus-*` paths appear in committed session logs** (N-04 has 7, N-03 has 21). Redact them, or move the bus socket.
6. **Lane records carry placeholder or stale SHAs** (R2-07d, RECERT-FIX). Read heads from git.
7. **State oracle resolution in PREREGs.** B-06's 2 ms polling is coarser than its ±1 ms gate.
8. **Plain-shell `python3` near misses persist.** The fail-closed guard is still BLOCKED on owner or orchestrator action.

## 6. Ranked follow-ups (STATE.followups_ranked W5-1..12)

1. **Publish gate:**
   - Push the 10 accepted heads, plus the three RECERT-FIX candidate heads, PUB-02 A (R2-10R a3) and C, and the wave-4 R2-10R control.
   - **Hold PUB-02 B** until the owner rules.
   - Re-scan every commit before pushing.
   - Fix the wave-4 comment links that point at the never-pushed R2-10R a2 branch.
2. **Browser per-process cold excess:** an owner ruling on B-06's amendment, or a fresh pre-registered run (≥30 pairs per class, PC after snapshot1, 0 provider).
3. **One-binary browser E2 re-read** with B-07's verdicts and the W5-2 mapping.
4. **E5:**
   - kvnloo/cua#10 final table.
   - trycua/cua issue 3963 rewrite draft, with a fresh reviewer.
   - kvnloo/cua#74 queue with READY NOW checks.
5. **Budget (38 reached):**
   - OWN-78A R1-lite (≤6).
   - A new pre-registered quiet modal block (0 reached) before any Phase L (≤18).
6. **E6:** two independent judges after W5-2, plus a freshness re-check.
7. **#20:**
   - Widen A's triggers (NoReply, name-owner change).
   - Fix the same_app_dialog misclassification.
   - Find a mark-free stall method so R1 can run on product binaries.
8. **#36 / #9 residue:**
   - F4 TOCTOU.
   - A dedicated recording-lookup test.
   - Session checks for window_for_snapshot and the side index.
   - Discriminating U rows for W2c/W2d.
9. **#78:** the A2-vs-A3 gap and full-n R1/R4 (budget); S1 (owner).
10. **Publish-time text fixes per lane:** see `dispositions.<id>.verifier_advisories` / `publish_fixes`.
11. **Owner decision queue.**
12. **Shared infrastructure** (§5).

Fork comment drafts are in `drafts/w5/`: 93, 10, 73, 74, 20, 78, 36, 9, 16, 84 and 105, plus PUBLISH-NOTES.md, which is not for posting.
