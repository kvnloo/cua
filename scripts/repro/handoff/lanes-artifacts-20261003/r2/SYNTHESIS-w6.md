# CUA RFC loop: wave 6 synthesis (2026-10-03 UTC)

Wave 6 ran eight lanes: five experiment/fix lanes, one privacy lane and two deliverable lanes.

- **Accepted (8):** B-08, R2-07e, OWN-78L, FIX-03, OWN-20Q, PUB-03, DOC-3963, DOC-10-74.
- **Rejected:** none.
- **Hard-rule breach:** none.
- **Not yet published.** All 10 local heads (7 lanes + 3 PUB-03 candidates) were checked with `git rev-parse` at 15:25Z. They match the lane results, and none is on origin.

**TypeSafe this wave:** R2-07e used 15 attempts / 15 reached (cap 18), and OWN-78L used 6 / 6 (cap 6). Every other lane, every verifier and this synthesis used 0. **Loop total: 583 / 600 reached (679 attempts); 17 remain.** Each lane's self-reported loop total was partial: R2-07e said 577 and OWN-78L said 568, each without the other. The STATE ledger sum is the authoritative figure.

## 0. Stop rules, breach classes, rulings needed

- **Hard-rule breach:** none.
  - Nothing reached the host desktop or session.
  - No secret was exposed, and nothing was written upstream or to GitHub.
  - Every reported timing number came from an EXCLUSIVE quiet-timed window: B-08's measured chunks k4–k7 and R2-07e's Q6/L1. OWN-20Q and FIX-03 report wall times only as descriptive figures under SHARED locks.
- **Near misses (none had an effect):**
  - **Lanes.** Stdlib `python3` ran in the plain host shell instead of under hostless, for JSON reads, string patches or empty heredocs: R2-07e (several), OWN-78L (several, plus one empty heredoc), FIX-03 (one empty heredoc), PUB-03 (~16), DOC-3963 (4) and DOC-10-74 (7). DOC-3963 also had one zsh loop clobber PATH; nothing ran.
  - **Verifiers.** The same class in R2-07e, FIX-03, PUB-03 and DOC-3963.
  - **Lock discipline.** OWN-20Q had three SHARED gaps of 29.1–29.2 s (the rule is ≥ 30 s), and a hung UNIT red run held the cargo lock for about 13 minutes; the lane killed only its own processes. FIX-03 took two SHARED acquisitions 0–1 s after the previous release. No timing claim depends on any of these.
  - **DOC-10-74.** Two planted private-name control files sat briefly in the local mirror directory. They were deleted within minutes, never committed or pushed, and a rescan is clean.
  - **This synthesis.** Read-only `git`/`gh` reads in the plain shell. Every `jq`/`python3` run, including the STATE update, ran under `bin/hostless`.
- **Rulings still open:**
  - **Published-fork privacy, now five branches** (PUB-03 census). For four of them, the owner-ruling draft gives a lease-guarded replace sequence; Publish has not run it.
    - `exp/r2-10-composition-20261002` @ `030f6bdbf`: encoded private-name list. Candidate r1c `eaca68df9`.
    - `exp/own-20g-guard-final-diff-a2-20261003` @ `ce7544cc0`: user name ×10. Candidate `cb18ebfbd`.
    - `exp/n-03-native-closure-axfg-a3-20261003` @ `6b70ec902`: tmp session-bus paths ×21. Candidate `a2f7a93ef`.
    - `exp/n-04-native-composition-rprime-20261003` @ `9d7d8d7a5`: tmp session-bus paths ×7. Candidate `32299f857`.
    - **NEW:** `exp/r2-10r-recert-a3-20261003` @ `d22eeb2ec`: tmp session-bus paths ×25. Candidate proposed, not built.
  - The R2-07e forced-fallback substitution (`n7_presat` in place of a rename). Modal is REVISE either way.
  - FIX-03 F4: IRREDUCIBLE-with-honest-unknown, plus the `effect=unknown` mapping follow-up.
  - OWN-20Q's name-owner trigger, which needs a second persistent bus connection.
  - The RECERT-FIX attempt-2 `pkill` (record-keeping only).
- **Resolved:** the B-06 Amendment-1 reading is moot, because B-08's fresh pre-registered run gives OWNER_DECISION.
- **Stop-rule counters:**
  - Waves used: 7 of 12.
  - Not stalled. Eight new terminal dispositions; browser scripted toggle untested fell from 19.1–34.9% to 0.4%, and modal from 0.6–5.5% to 0.4%, both on one binary.
  - Budget OK: 17 reached remain.

## 1. What changed this wave

- **B-08: KEEP. The per-process cold first-snapshot excess is OWNER_DECISION in all three browser classes** (`49ae94590`, binary B7 `6f95aef5`, the same binary as B-07). It was pre-registered (`f577426fe`, 13:22:06Z, before the first measured chunk at 13:44:54Z) and never amended. 384/384 measured trials were valid, and E4 was 0.
  - **D = C − Wa** (median T_j, ms): fill **10.58 [9.50, 11.41]**, toggle **3.05 [2.62, 5.38]**, modal **4.56 [2.98, 5.92]**.
  - **Controls:** the NC (Wa − Wb CI inside ±2 ms) and the PC2 (P2 − Wa 14.9–15.9 ms, CI excludes 0) passed in every class. That fixes the failed positive control from B-06.
  - **E1:** the B-04/B-06 lineage is terminal. Per-document is IRREDUCIBLE (B-04), and per-process is OWNER_DECISION (B-08): process or session reuse kept outside T.
  - **E2 one-binary re-read** (Part E, C arm, corrected; the two figures count BELOW_GATE as IRREDUCIBLE / UNTESTED): toggle **0.4 / 3.6%**, modal **0.4 / 3.3%**, fill **16.9 / 19.0%**.
  - Fill's remainder is the compiled routine's 10 ms verify poll, which the harness does not stamp, so the decomposition files it under `runner` (9.82 ms, 14.5%, UNTESTED). If that poll were attributed, fill would be 2.3 / 4.4%. That figure is post hoc and descriptive only.
- **R2-07e: KEEP for toggle, REVISE for modal** (`67b99ddc6`, binary R `12b9045a`).
  - **Part Q, the second alpha-adjusted look at modal:** PASS. CR − COMP is **−0.5 ms [−1.4, +0.5]** at 97.5%, with 60/60 pairs valid. R2-07d's look 1 (+0.6 [−1.4, +2.4]) is reported beside it and not pooled.
  - **Phase L toggle (live TypeSafe):** the provider decision is **DELETED** on admitted COMP+CR warm invocations: 29/29 valid, 0 decisions, 0 provider lines. The forced fallback verified with one live decision.
    - The training invocation's decision is 489.1 ms, 84.2% of that invocation.
    - The amortized mean over 30 invocations is 66.8 ms, or 73.0 ms counting the fallback: 1.41 / 1.54 × the warm mean of 47.3 ms.
    - Compiled replay now enters the composed **toggle** configuration.
  - **Phase L modal:** REVISE. Warm deletion held 29/29 with 0 decisions, but the verdict-bearing forced fallback (`n7_presat`, dialog starts open) did not verify. TypeSafe chose reobserve four times while confirm-choice was offered (n = 1).
  - **Caveats:**
    - The spec's rename fallback was replaced by `n7_presat`. This was pre-registered, and the rename ran as a descriptive LN.
    - A descriptive 10-pair toggle sanity block gave +0.7 [+0.5, +2.6] ms, so toggle non-regression was not re-confirmed in this environment.
    - The paired live BASE vs COMP+CR S is still BLOCKED by budget.
- **OWN-78L: KEEP. kvnloo/cua#78 moves from REVISE to KEEP on fork fix candidate F `61eec0909`** (`d9edde70e`).
  - R1-lite was **3/3** verified on live TypeSafe, and backend == responder held 3/3 (6/6 decision records).
  - 0 replays. MOCK, CAP-0 and STUB passed. UNIT was 109/109 credential-free.
  - n = 3, so the 95% lower bound is 0.29. The step-1 margin is thin.
  - Full-n R1/R4 and the A2-vs-A3 gap are BLOCKED by budget. S1 is BLOCKED pending an owner decision.
- **FIX-03: F4 REVISE, the rest KEEP** (`e300edbd3`).
  - **F4 (TOCTOU in `set_input_files`):** F5 makes the receipt honest: 0/20 success receipts, and 20/20 refused `browser_ref_stale` with delivery unknown and retryable false. It cannot stop the effect: the detached node's change event reached the server in 20/20 cells, because CDP cannot make the check and the assignment atomic.
  - **NEW E4 finding:** on F' (the recertified FIX-02 candidate), a session's own valid token wrote into or toggled the other session's window through the (pid, xid) side index in **40/40** attempts. F5's `2237cf9c6` fixes this (0/40). The #36 native ownership candidate is therefore F5, not F'.
  - The recording-lookup test is red on U' and green on F5. `snapshot_id` routing needs no fix because the path cannot be reached. W2dX now discriminates; W2cX does not.
- **OWN-20Q: R1m KEEP, DLG KEEP, A2 REVISE** (`44116546d`, GQ `2dbe3cd2`).
  - **R1m:** the mark-free stall runs on product binaries: U0 misses silently 40/40, G0 restores verified 40/40, with 0 false restores. This replaces OWN-20P's marked-twin substitution.
  - **same_app_dialog fix `4ac191a7c`:** GA misclassifies 20/20, GQ restores 20/20, and the app's own dialog stays focused 10/10.
  - **A2:** the org.a11y.Bus name-owner trigger needs a second persistent bus connection, so it was not implemented (r3n 0/20). The NoReply + Peer.Ping trigger `31318e374` holds r3s, r3w and r3_carry; cite r3_carry as 23/23 real restarts.
- **PUB-03: KEEP.** Three clean candidates are built and held. They differ from the published heads only in redactions, manifest entries and a note, and they pass their verifiers exactly as the published heads do (277/277, 8/8, 10/10). The census found one new published finding, on R2-10R a3 (above).
- **DOC-3963 and DOC-10-74: KEEP (E5 staged).** Both are on fork docs branches and not pushed.
  - **DOC-3963:** the trycua/cua issue 3963 rewrite, with 70 rows, 15 deltas and 65 cited numbers. Verifier: 0 FAIL.
  - **DOC-10-74:** the kvnloo/cua#10 accounting, with 1661 numbers re-read from packets, and the #74 queue, with 44 entries. Verifier: 762 checks, 0 failed. READY NOW is 0/44 until a fresh review.
  - Both list the wave-6 lanes as PENDING and must be refreshed.

## 2. Per-reference-task decomposition (best known)

Rules: components are mean ms with their share of mean T_runner, and T is median T_j or T_oracle. Never add or take ratios across binaries. "Cross-lane reading" combines verdicts, not numbers.

### Browser, scripted: one binary B7 (`6f95aef5`), B-08 Part E, C arm (fresh process), corrected at c_m 31.72 µs

| Component | fill | toggle | modal | Verdict (source) |
|---|---|---|---|---|
| Endpoint revalidation | 20.41 (30.2%) | 20.47 (49.9%) | 20.47 (49.7%) | OWNER_DECISION (B-02 H_E) |
| Cold excess, per process | 12.37 (18.3%) | 4.29 (10.4%) | 4.41 (10.7%) | OWNER_DECISION (B-08) |
| Runner (fill: unstamped 10 ms verify poll) | 9.82 (14.5%) | — | — | **UNTESTED** (R2-10) |
| Observation rest | 5.24 (7.8%) | 3.62 (8.8%) | 4.26 (10.3%) | IRREDUCIBLE (B-04) |
| Cold excess, per document | 4.44 (6.6%) | 3.58 (8.7%) | 2.99 (7.3%) | IRREDUCIBLE (B-04) |
| MCP transport | not in fill's top five (< 4.44 ms) | 2.47 (6.0%) | 2.38 (5.8%) | terminal by sub-span; largest are c_in.prep and d_out.post, both IRREDUCIBLE (B-05/B-07) |
| **Median T_j, C / Wa** | 61.55 / 51.37 | 48.52 / 44.31 | 48.59 / 44.16 | warm-up outside T: 37.7 / 30.1 / 29.6 |
| **Untested share** (BELOW_GATE as IRR / UNT) | **16.9% / 19.0%** | **0.4% / 3.6%** | **0.4% / 3.3%** | |

### Browser, live: R2-07e Phase L on binary R (`12b9045a`), TypeSafe, 30 invocations per class

| | Training-invocation decision | Warm decision | Amortized over 30 | Verdict |
|---|---|---|---|---|
| toggle | 489.1 ms (84.2% of 580.5) | 0 (29/29) | 16.3 ms (25.0% of 65.1); total 66.8 ms, 73.0 ms with the fallback | **DELETED on warm**; training cost is counted, not deleted |
| modal | 392.2 ms (87.9% of 446.0) | 0 (29/29) | 13.1 ms (21.6% of 60.7); total 62.3 ms | **REVISE**: fallback not verified, so compiled replay is not admitted |

- Warm T_runner is about 47.3 ms, mostly endpoint revalidation (~20 ms, OWNER_DECISION) and observation (~13.4 ms).
- **Modal Part Q components, COMP / COMP+CR (ms):**

  | Component | COMP | COMP+CR |
  |---|---|---|
  | Observation | 13.1 | 13.3 |
  | Endpoint revalidation | 20.7 | 20.7 |
  | MCP transport | 4.3 | 4.2 |
  | MCP admission | 1.5 | 1.5 |
  | Visualization | 1.7 | 1.7 |
  | Dispatch | 1.2 | 1.2 |
  | Verification reads | 1.0 | 0.5 |
  | T_runner | 48.3 | 47.5 |

- Live fill: provider decisions were already deleted by R2-03.

### Native: unchanged this wave (N-04, R'n `78a1137d`, scripted chooser)

| Task | Untested share | Conservative | Notes |
|---|---|---|---|
| checkbox | 1.19% | 2.23% | E2 met on one source. Settle (~241 ms) dominates and is IRREDUCIBLE. |
| text entry | 1.65% | 2.62% | Same. |

Freshness: upstream main `5e13eb777` changes `platform-linux/src/overlay.rs` (trycua/cua PR 4529): an idle X11 cursor overlay now stays unmapped until it paints. Before the native rows can be called fresh, a SOURCE check must confirm whether N-04's X11 rows ran with a mapped idle overlay (see W6-5).

### Untested share, best known

| Task | Scripted | Live |
|---|---|---|
| fill→submit | **16.9% (19.0%)** on B7, one binary. Not met: the runner's verify poll is untested. | Provider decisions deleted (R2-03); same runner question. |
| toggle→confirm | **0.4% (3.6%)**: met | The provider decision has a verdict (DELETED, warm). A one-binary live share has not been computed, and the paired S is BLOCKED (budget). |
| modal→act | **0.4% (3.3%)**: met | About 89% is provider decisions with no terminal verdict (REVISE): not met. |
| native checkbox | 1.19% (2.23%): met | Native T uses the scripted chooser; an owner ruling or budget is needed. |
| native text | 1.65% (2.62%): met | Same. |

## 3. Dispositions (this wave)

| ID | Disposition | Class | Branch @ commit |
|---|---|---|---|
| B-08 | KEEP: per-process cold excess OWNER_DECISION in fill, toggle and modal; lineage terminal | REAL+BENCHMARK (FIXTURE, scripted); SOURCE (Part E) | exp/b-08-per-process-cold-b7-20261003 @ `49ae94590` |
| R2-07e | KEEP for toggle (live decision DELETED on warm; compiled replay in the toggle config) / REVISE for modal (Part Q PASS; forced fallback failed) | REAL+BENCHMARK (FIXTURE); LIVE_PROVIDER; UNIT; paired live S BLOCKED | exp/r2-07e-modal-gate-phase-l-20261003 @ `67b99ddc6` |
| OWN-78L (#78) | KEEP on fork fix candidate F; full-n R1/R4 and A2-vs-A3 BLOCKED (budget); S1 BLOCKED (owner) | LIVE_PROVIDER + FIXTURE + UNIT | exp/own-78l-r1-lite-f-20261003 @ `d9edde70e` |
| FIX-03 (#36/#105) | F4 REVISE (IRREDUCIBLE-with-honest-unknown); recording test KEEP; routing KEEP (no fix); side index KEEP with `2237cf9c6`; W2dX KEEP | REAL+FIXTURE; REAL (X11); UNIT; SOURCE | exp/fix-03-file-input-toctou-session-routing-20261003 @ `e300edbd3` |
| OWN-20Q (#20) | R1m KEEP; DLG `4ac191a7c` KEEP; A2 REVISE (r3n), with `31318e374` measured | REAL (FIXTURE, SHARED); UNIT; SOURCE; Hyprland BLOCKED | exp/own-20q-a11y-triggers-dialog-markfree-20261003 @ `44116546d` |
| PUB-03 | KEEP (publish gate): 3 candidates HELD; new finding on R2-10R a3 | SOURCE + UNIT | exp/own-20g-guard-final-diff-r1c-20261003 @ `cb18ebfbd`; exp/n-03-native-closure-axfg-r1c-20261003 @ `a2f7a93ef`; exp/n-04-native-composition-rprime-r1c-20261003 @ `32299f857` (all HOLD) |
| DOC-3963 | KEEP (E5, staged) | SOURCE | docs/rfc3963-rewrite-draft-20261003 @ `088fe745a` |
| DOC-10-74 | KEEP (E5, staged) | SOURCE | docs/accounting-10-queue-74-20261003 @ `a3e3cb86e` |

**Not accepted:** none.

**BLOCKED, with exact blockers** (`STATE.blocked_items_w6`):

- **Paid budget** (17 reached remain):
  - R2-10 live recertification (≥ 180).
  - Paired live BASE vs COMP+CR S for toggle/modal (≥ 120).
  - Native live arms (≥ 120, or an owner ruling on native T).
  - #78 full-n R1/R4 (~60) and the A2-vs-A3 gap.
  - The R2-07e LN toggle (4) and a modal fallback re-run (n ≥ 3) fit only if allocated.
- **Owner decision:**
  - #78 S1.
  - R2-09 WebKitGTK.
  - The #20 name-owner trigger design.
  - OWN-09R bounded wait and R8.
  - OWN-09R Deviation 6 and the OWN-16W analyzer reading.
  - The five published privacy branches.
  - The R2-07e fallback substitution.
  - FIX-03 F4.
- **Real Hyprland seat:** #16, #94 with #92/#100/#101, the R2-09 foreground route, and the OWN-20G/20P/20Q Wayland rows.
- **macOS/Windows hardware:** #6, #8, #13, #19, #31, #72, the #16/#36 rows, #9 R3, and dd205d17b parity.
- **Owner/orchestrator action:** the fail-closed hostless guard.

## 4. What remains, E1–E6

- **E1 (coverage): met, pending publication.**
  - Every scheduled experiment and Linux owner row now has a terminal disposition or an exact external blocker:
    - #9, #16, #36 and #105 are recertified, plus FIX-03.
    - #20 is KEEP for G, A, R1m and DLG; A2 is REVISE.
    - #75 is KEEP. #78 is KEEP on F.
  - The wave-6 heads are not yet on origin.
- **E2 (critical path):**
  - **Native:** met (unchanged).
  - **Browser scripted:** met for toggle and modal on one binary (0.4%). **Not met for fill:** 16.9%, from the unstamped verify poll (W6-2).
  - **Browser live:**
    - The toggle provider decision has a terminal verdict (DELETED on warm).
    - The modal provider decision does not (REVISE).
    - The live one-binary share and the paired S are BLOCKED by budget.
- **E3 (composition):**
  - **Scripted:** met on R (R2-10), recertified on R' (R2-10R).
  - **Native:** met on R'n (N-04).
  - **Compiled replay:** now in the composed toggle configuration (amortized 66.8 / 73.0 ms over all invocations, including first run and fallback); excluded for modal.
  - **Live paired S:** BLOCKED (budget, ≥ 120).
  - **References** (not gates; not restated here): PreAct and SkillDroid are compared in DOC-10-74.
- **E4 (invariants):**
  - 0 violations in every accepted arm, apart from the residue below.
  - **New:** FIX-03 found and closed (in F5) a cross-session side-index hole on the F' candidate line.
  - **Residue:**
    - (a) F4's post-assignment refusal is mapped to `effect=refused` even though the change landed. It should become `effect=unknown`.
    - (b) Check that the runner's F3 re-dispatch rule honours `delivery=unknown` / `retryable=false` on F5's `browser_ref_stale` (W6-4a).
    - (c) Native AT-SPI pid-wide fallbacks.
- **E5 (deliverables): staged, not final.**
  - The #10 accounting and the 3963 rewrite carry six PENDING wave-6 rows that need a refresh (W6-3).
  - The #74 queue needs a fresh review before any READY NOW can pass.
  - DOC-10-74 needs two fixes: Q14 and PRIV-A.
- **E6 (stability): not met.**
  - **Moving targets:** wave 6 changed rows the rewrite depends on:
    - B-06 UNDECIDED became OWNER_DECISION (B-08).
    - #78 REVISE became KEEP.
    - The #36 candidate moved from F' to F5.
    - Toggle compiled replay entered the composed config.
  - **Freshness:** upstream main `5e13eb777` is 39 commits past 0f1955d2f and touches one Linux path, `overlay.rs` (W6-5). PR heads are unchanged: trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, #105 `98a45e6c5`, #106 `c45845797`.
  - **Judges:** none run yet.

## 5. Shared infrastructure (`STATE.infra_followups` W6)

- **Make the PUB-03 per-commit scanner a mandatory Publish pre-push gate.** It covers every class, gz/tar members, commit messages and path names. Session-bus paths reached three published branches because no scanner rule existed for them.
- **Cargo-lock contention.**
  - B-08 k1–k3 and R2-07e Q1–Q5 each spent a 60 s EXCLUSIVE window on a busy cargo lock and exited 74.
  - OWN-20Q's hung unit run held the lock for about 13 minutes.
  - Fix: add timeouts for unit runs under the lock, and check the cargo lock before taking EXCLUSIVE.
- **Budget reporting.** Lanes should report only their own counts.
- **Lane-result SHAs** matched git this wave.
- **Fail-closed hostless guard:** still BLOCKED (owner/orchestrator).

## 6. Ranked follow-ups (`STATE.followups_ranked` W6-1..12)

1. **Publish gate.** Push the seven accepted heads after the per-commit privacy scan. HOLD the PUB-03 candidates and PUB-02 B. Do not push FIX-03's detached worktrees or OWN-20Q's red tree.
2. **Fill E2.** Stamp the compiled routine's verify poll on B7 and give `runner` a verdict, using a pre-registered, env-gated, default-off knob with no provider.
3. **E5 refresh.** Fold the wave-6 rows into the 3963 draft and the #10 accounting. Fix Q14 and PRIV-A. Get a fresh review of the #74 queue.
4. **E4 residue.**
   - The runner F3 check against delivery=unknown.
   - The `effect=unknown` mapping fix candidate.
   - The native pid-wide fallbacks.
5. **Freshness.** SOURCE check of `overlay.rs` against the X11 native and focus rows.
6. **Budget (17).** At most one small live lane: the modal fallback re-run (n ≥ 3), after the owner rules on the substitution, or the LN toggle. Also re-confirm toggle non-regression in a quiet block (0 reached).
7. **E6 judges** after items 2, 3 and 5.
8. **#20:** the name-owner trigger ruling.
9. **#78:** budget and S1.
10. **Publish-time text fixes**, from `dispositions.<id>.verifier_advisories`.
11. **Owner decision queue.**
12. **Shared infrastructure.**

Fork comment drafts are in `drafts/w6/`: 93, 10, 73, 74, 78, 36, 105 and 20, plus PUBLISH-NOTES.md, which is not for posting.
