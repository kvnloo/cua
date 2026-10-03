# CUA RFC loop: wave 3 synthesis (2026-10-02 UTC)

Eight lanes ran and fresh verifiers accepted all eight. Three of them (FIX-02, OWN-75R, OWN-16W) were accepted on their fix-pass heads. Nothing was rejected, and no lane or verifier reported a hard-rule breach. TypeSafe this wave: 306 reached / 306 attempts, all from R2-10. The loop total is now **542 / 600 reached (638 attempts), leaving 58**.

## 0. Stop rules and breach classes

- **Hard-rule breach:** none this wave. Nothing reached the host desktop, no secret was exposed, nothing was written upstream, and every reported number came from a quiet-timed window.
- **Near misses** (none had any effect):
  - Stdlib-only `python3` one-liners and edits in the plain host shell: R2-10, N-02, R2-09, FIX-02, OWN-75R and OWN-16W lanes, plus the FIX-02, OWN-09R and OWN-16W verifiers.
  - One `perl -0pi` edit (R2-10).
  - The usercustomize guard from the wave-2 owner ruling strips the desktop environment for that Python. The pattern still recurs in most lanes.
- **Lock etiquette:** N-02 and R2-09 unit jobs held the SHARED quiet lock while they queued for the cargo lock. N-02 stopped its own job; R2-09 kept the aborted attempt. OWN-16W's unit logs do not show whether the cargo lock was taken. No reported number depends on any of these.
- **Observation, not attributed to a lane:** at ~17:28–17:29Z, during the B-03 and OWN-09R windows, `refs/heads/main` in the main clone was reset or fast-forwarded and fork main was pushed. Transcript evidence points to the top-level orchestrator's sync. The orchestrator should confirm this and record it.
- **Stop-rule counters:**
  - Waves used: 4 of 12.
  - Not stalled.
  - Provider budget is OK but nearly spent: 58 reached remain, so no 30-pair live arm that keeps provider decisions in BASE fits.

## 1. What changed this wave

- **R2-10, whole-task composition on one source (E3): KEEP.**
  - **Source:** binary R (`12b9045a`, 989cc76ce + steps 1–8) ran in every arm.
  - **Phase 0 passed:**
    - browser:: 193/193.
    - FIX-01 C1/N4a refused 20/20, then rebound and verified 20/20 (U accepted 5/5).
    - B-02 N-W2 refused 20/20 per class with 0 detached effects (U fired 5/5).
    - Default-off smoke identical to control build Cn.
    - R2-07b gates 5/5.
  - **Validity:** every trial verified (180 live, 384 scripted, 144 native), with 0 E4 violations.
  - **S** (median T_oracle, BASE/COMP):

    | Layer | fill | toggle | modal |
    |---|---|---|---|
    | live TypeSafe | 45.11 [42.43, 51.90] | 5.95 [5.70, 6.25] | 5.73 [5.41, 6.00] |
    | scripted | 45.61 | 47.01 | 46.56 |

    Native X: checkbox 1.18, text 5.85.
  - **The headline depends on owner decisions.** Turning feedback off deletes 2.4–3.0 s of awaited glide (94–97% of BASE T). With only KEEP deletions (COMP_K), median S is 1.01 in every browser class. The verifier recomputed the fill COMP_K amortized ratio of means at 0.98. Native text gains mostly from the OWNER_DECISION cursor reveal; KEEP-only S0 gives 1.18 (checkbox) and 1.03 (text).
  - **T_land (verifier):** native checkbox S_X is 1.00 [0.95, 1.06] on T_land. The 1.18 is Driver waiting after the GTK3 state had already changed. It counts as caller wall-clock under the pre-registered rule, but the target effect itself is not faster.
- **R2-09, native event wake: KILL.** 415/415 cells verified.
  - **Chromium AT-SPI background:** with no sleep (S0), the effect was visible at return 40/40, because the IRREDUCIBLE settle watch follows. S0 saves 69.8 / 67.0 ms per task and is at least as fast as the event wake. The wake's event was the focus change, not the effect (80/80).
  - **GTK3 X11 foreground:** the click goes through XTest, so there is no DoAction and no sleep to remove.
  - **WebKitGTK:** NOT_RUN. There is no host package, and installing one is an owner decision.
  - **Scope change:** the 50 ms sleep's DELETED scope now covers Chromium AT-SPI background as well. Qualifier: the watch stops at the first focus change, so an action that changes X11 focus shrinks the margin (3.1 ms minimum in the F shape).
- **B-03, toggle cold first snapshot.**
  - **Part 1: KEEP.** K5EV, the spec's literal best arm, is now decomposed for every class:

    | | fill | modal | toggle |
    |---|---|---|---|
    | K5EV untested share | 1.9% | 2.8% | 32.4% |
    | K5V untested share | 1.6% | 2.2% | 22.1% |

  - **Part 2: toggle H_W stays UNDECIDED.** The pre-registered negative control failed (1.9 ms [0.5, 2.6]), and so did the fill positive replication.
  - **What the probe settles:** an 80 ms wait after navigate removes the excess but costs +64.7 / +53.8 ms of T_oracle. Pre-warming costs more than it saves. No product knob is justified.
  - **Flag:** B-02's fill W verdict "moved only" was not reproduced, so fill's share is provisional (23.7% / 26.5% if fill were UNDECIDED).
- **N-02, native MCP transport.**
  - **HC (caller-compiled validators): KEEP.** Transport cost is mostly the Python client's per-call output-schema validation. HC saves 21.3 / 25.9 ms per task, with 80/80 equivalence. Not in the headline: eager compilation costs 107.5 ms per session, so HC is net negative for one task per session unless compilation is lazy.
  - **CL (settle clamp): KILL** under the pre-registered steal rule. None of the 4 misses is attributable to the clamp, and the 216–245 ms steal band was never tested.
  - **Untested share on the N-02 source:** checkbox 1.6–1.9%, text 3.2% (standard reading). It would be about 9–10% if the ~21 ms settle overshoot counted as UNTESTED.
- **FIX-02, reviewed fixes (fork candidates): F1/F2/F3 KEEP, F4 REVISE.**
  - **F1:** native tokens are bound to their session. I2 and I2d refused 40/40 each (U landed 40/40).
  - **F2:** runtime generation. I5p refused 20/20 and I5pt 10/10 (U dispatched I5pt to "Zoom out" 10/10).
  - **F3:** the runner re-dispatches only after pre-dispatch refusal codes: 0 blind re-dispatches, against 10 duplicates on U.
  - **F4:** the set_input_files detached check refused 20/20, but it is REVISE because the check is a separate call before `DOM.setFileInputFiles`.
  - **Owner row:** the #36 native token-ownership row moves from KILL to KEEP.
  - **Rebase needed:** trycua/cua PR 4375 has since changed `snapshot_store.rs`.
- **OWN-09R, revised kvnloo/cua#84: KEEP.**
  - **Gating rows:** P' passes R1 (R1D 40/40), R2, R4, R6 80/80 and R7 with 0 failures. M reproduces the gaps 40/40.
  - **R8:** OWNER_DECISION. REAL stdio `notifications/cancelled` is ignored 40/40 on both arms.
  - **Owner decision before any upstream proposal:** after a timeout, the guards stay with a leaked closure. The coordinator wait has no bound, so the next action, end_session or shutdown can block indefinitely.
  - **Claim narrowed:** three `spawn_blocking` sites remain unconverted.
- **OWN-75R, exact-head validation of trycua/cua PR 4336: KEEP.**
  - All 160/160 REAL trials verified, with one behaviour digest per cell shared by head and M0.
  - S2: the new fields appear on 160/160 head steps and 0/160 M0 steps.
  - S1 is clean, and 16/16 mutants were caught.
  - This supersedes the wave-2 hard stop. The lane first stopped PARTIAL because the permission classifier denied its status reads; the resume finished it.
- **OWN-16W, #16 on headless sway: S-W KEEP, S-X KEEP, X11 string row KEEP.**
  - The omitted producer ran 0 times in 42/42 calls in every row, by a compositor-side or X RECORD oracle.
  - Fix `dd205d17b` refuses non-boolean selectors 42/42; U accepts them 42/42. The fix is Linux-only and also refuses JSON null.

## 2. Per-reference-task decomposition (best known)

Rules:
- **Source boundaries.** R2-10 is the only one-source composition. Its rows (R `12b9045a`, 1-minute loadavg 2–17) must not be added to, or ratioed with, B-02/B-03 (`7e6c0609`), N-02 (`893646ab`) or R2-09 (`156338f7`).
- **Metrics.** T is median T_oracle; component values are mean ms (share of mean T_runner) from R2-10's decomposition.

### Browser: R2-10 COMP (best verified composed configuration)

| Class | Layer | BASE → COMP T | Material components (verdict) | T_irr / floor | Untested |
|---|---|---|---|---|---|
| fill→submit | live | 3647.2 → 80.9 ms | observation 29.0 (30.8%) IRREDUCIBLE; endpoint reval 24.6 (26.2%) OWNER_DECISION; sleeps/polls 9.1 (9.7%) IRREDUCIBLE; provider 6.0 (6.4%, training row only) DELETED; MCP transport 5.8 (6.1%) **UNTESTED** | 48.2 ms / 1.95x | **14.0%** |
| fill→submit | scripted | 3187.6 → 69.9 ms | observation 26.2 (32.9%); endpoint 22.4 (28.2%); sleeps/polls 9.0 (11.3%); MCP transport 5.2 (6.6%) UNTESTED | 43.3 / 1.84x | **15.2%** |
| toggle→confirm | live | 2928.3 → 491.8 ms | **provider decisions 434.8 (88.3%) UNTESTED** (guarded completion binds 0; compiled replay qualified for fill only) | 21.9 / 22.5x | **90.4%** |
| toggle→confirm | scripted | 2507.4 → 53.3 ms | endpoint 22.8 (41.6%) OWNER_DECISION; observation 16.0 (29.2%) IRREDUCIBLE in R2-10's mapping (B-03 keeps the cold excess UNDECIDED); MCP transport 4.7 (8.7%) UNTESTED; reval other 2.7 (5.0%) | 21.2 / 2.59x | **16.4%** (more if the cold excess counts) |
| modal→act | live | 2930.2 → 511.0 ms | provider decisions 462.4 (89.0%) UNTESTED | 22.2 / 23.4x | **90.9%** |
| modal→act | scripted | 2483.6 → 53.3 ms | endpoint 22.6 (41.6%); observation 15.7 (29.0%); MCP transport 4.8 (8.9%) UNTESTED | 20.9 / 2.59x | **16.4%** |

B-02/B-03 rows on the older binary still stand as within-lane evidence: K5V / K5EV untested share fill 1.6 / 1.9% (provisional), modal 2.2 / 2.8%, toggle 22.3 / 32.1%. The scripted share is higher in R2-10 mainly because R2-10 splits out MCP transport in/out (4.7–5.8 ms) and marks it UNTESTED, which B-02 did not. Browser **MCP transport attribution** is therefore the main remaining scripted E2 item, along with the B-04 toggle decision. For live toggle and modal, the remaining item is the two provider decisions.

### Native GTK3: R2-10 arm X (one source), with N-02 as a separate-source attribution

| Task | BASE → X T | X components | T_irr / floor | Untested (R2-10) | N-02 source (separate) |
|---|---|---|---|---|---|
| checkbox | 334.9 → 283.0 ms (S 1.18; T_land S 1.00) | settle 240.9 IRREDUCIBLE; observation transport 18.7; observation 10.9; action transport 9.9 **UNTESTED**; resolution 1.4 | 272.2 / 1.04x | **4.1%** | S0+HC 1.7% standard / 3.4% conservative; transport mostly client validation (HC DELETED) |
| text entry | 1760.9 → 300.9 ms (S 5.85) | action transport 20.6 **UNTESTED**; reveal residual 4.3 OWNER_DECISION; resolution 1.6 | 274.9 / 1.10x | **7.5%** | X+HC 3.2% / 5.0%; residual Driver admission ~8.6 ms per trial UNTESTED |

Chromium AT-SPI (R2-09, separate source):
- Task T: checkbox B 531.1 / S0 439.0 / EW 470.9 ms; submit 510.3 / 440.3 / 455.2 ms.
- The sleep is DELETED in scope, and the event wake is KILL.

## 3. Dispositions (this wave)

| ID | Disposition | Class | Branch @ commit |
|---|---|---|---|
| R2-10 | KEEP (E3 measured; owner-decision dependency stated) | LIVE_PROVIDER+REAL+BENCHMARK / REAL+BENCHMARK / REAL+BENCHMARK (FIXTURE) | exp/r2-10-composition-20261002 @ `030f6bdbf` (control exp/r2-10-control-20261002 @ `1381014a3`) |
| R2-09 | KILL (event wake); WebKitGTK NOT_RUN (proposed BLOCKED: owner decision) | BENCHMARK+REAL+UNIT; controls REAL+FIXTURE | exp/r2-09-native-event-wake-20261002 @ `3539e34ae` |
| B-03 | Part 1 KEEP; toggle H_W UNDECIDED | BENCHMARK / BENCHMARK+REAL | exp/b-03-toggle-cold-snapshot-20261002 @ `b34eef71e` |
| N-02 | HC KEEP / CL KILL | BENCHMARK+REAL (FIXTURE)+UNIT | exp/n-02-native-transport-20261002 @ `9846ac803` |
| FIX-02 | F1/F2/F3 KEEP, F4 REVISE; #36 native token row KEEP | REAL+FIXTURE / REAL (fault-injected) / UNIT / BENCHMARK | exp/fix-02-token-ownership-retry-scope-20261002 @ `cea02cb74` |
| OWN-09R (#9) | KEEP for the #84 revision; R8 OWNER_DECISION; R3 BLOCKED | UNIT/FIXTURE + REAL (R8) + SOURCE | exp/own-09r-84-revision-20261002 @ `0c2896a53` |
| OWN-75R (#75) | KEEP | REAL+UNIT+SOURCE | exp/own-75r-timing-parity-4336-20261002 @ `e02621fdc` |
| OWN-16W (#16) | S-W KEEP, S-X KEEP, X11 string row KEEP (fix dd205d17b) | REAL+UNIT | exp/own-16w-sway-modality-20261002 @ `1b9819157` |

Rejected: none. The lane-result commits for FIX-02 (`422418998`), OWN-75R (`c7614a2dd`) and OWN-16W (`1fed0037b`) are stale; cite the heads above.

All dispositions so far:

| Group | Items |
|---|---|
| R2 series | R2-01 KEEP_H1, R2-02 KILL, R2-03 KEEP, R2-04 REVISE, R2-05 KEEP, R2-06 KEEP, R2-07 KILL (R2-07b KEEP), R2-08 KEEP, **R2-09 KILL**, **R2-10 KEEP** |
| Follow-up lanes | B-01 KEEP, B-02 (H_E OWNER_DECISION / H_V DELETED / H_W mixed), N-01R KEEP, FIX-01 REVISE |
| Linux owner rows | #9 KEEP (revision), #16 KEEP (X11 + sway), #20 KEEP, #36 native rows KEEP on fork fixes (I3s OWNER_DECISION), #75 KEEP, #78 REVISE, #105 KEEP, #38 BUG-01 CONFIRMED_BUG |

**BLOCKED (exact blockers):**
- **Hardware:** #6, #8 (+ upstream trycua/cua 3904 decision), #13, #19, #31 macOS/Windows rows, #72, #16 macOS/Windows, #36 macOS/Windows native, #9 R3, #9 held-input cleanup.
- **Real Hyprland seat:** the #16 Hyprland row; #94 with #92/#100/#101; the R2-09 Hyprland foreground route.
- **Budget / owner:**
  - #78 S1.
  - R2-10 native live arms (≥120 reached needed).
  - Live toggle/modal compiled-replay re-measure (≥60 reached needed, 58 remain).
- **Owner decision:** R2-09 WebKitGTK install; #9 R8.

**OWNER_DECISION queue:**
- Feedback glide default (largest single component).
- H_E endpoint re-proof.
- Native cursor reveal.
- H_T 100 ms settle.
- R2-08 API route.
- I3s.
- OWN-09R timeout semantics.
- PR 4336 unconditional log fields.
- dd205d17b's JSON-null refusal.
- Provider budget.

## 4. What remains, E1–E6

- **E1 (coverage):**
  - R2-01 to R2-10 are all terminal.
  - The Linux owner rows #9, #16, #20, #36, #75, #78 and #105 are terminal, apart from external BLOCKED rows and OWNER_DECISION items.
  - Still open:
    - B-03's toggle H_W UNDECIDED (B-04 is spawned).
    - #36 same-process-two-windows (NOT_RUN).
    - R2-09 T3, which needs either the owner's BLOCKED ruling or an install.
- **E2 (critical path):** **not met.**
  - Native: checkbox meets it on one source (4.1%). Text is at 7.5% on one source; N-02's separate source shows 3.2% with HC, so a one-source re-run with lazy HC plus an admission cache should close it.
  - Browser scripted: 15–16% untested, mostly MCP transport in/out, plus toggle's cold excess under B-03.
  - Browser live toggle/modal: about 90% untested, because the provider decisions remain.
- **E3 (composition):** **met.** R2-10 measured BASE vs COMP on one source, binary, provider and environment, with ≥30 pairs per browser class (30 live, 32 scripted) and 24 pairs per native task. It reports S with CIs, the decomposition and the floor ratio. The references are compared without gating. Compiled replay is included for fill, over all invocations including the training and admission charge. Caveats:
  - Most of S depends on OWNER_DECISION components.
  - Upstream drift since the run needs recertification (E6).
- **E4 (invariants):**
  - Fixed on fork trees: N-W2 (R2-10 Phase 0), cross-session and cross-generation native authority (FIX-02), OWN-09's R1/R6 (OWN-09R), FIX-01's latent retry for browser codes (FIX-02 F3).
  - Open:
    - F4's TOCTOU window.
    - Native refusal codes in the runner rule.
    - OWN-09R's unbounded wait after a timeout (an availability concern, not a duplicate effect).
  - All accepted arms showed 0 E4 violations.
- **E5 (deliverables):** **now unblocked, and nothing is staged yet.** The kvnloo/cua#10 final table can use R2-10. The #3963 rewrite draft and the #74 queue are still to do. Drafts for this wave are in `drafts/w3/`.
- **E6 (stability):**
  - **Freshness fails.** Upstream main is `0f1955d2f`, 6 commits past 989cc76ce, and changes 8 libs/cua-driver files:
    - trycua/cua PR 4375: `snapshot_store.rs`, `tool_schema.rs`, platform-linux `tools/impl_.rs`.
    - PR 3489: sdk `embedded.rs`.

    These touch FIX-02 F1/F2, OWN-09R, OWN-16W and R2-10's native observation and admission claims. They need a rebase and recertification.
  - PR heads are unchanged: trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, kvnloo/cua#105 `98a45e6c5`.
  - No judges have run.
  - KEEP/KILL calls changed this wave, including #9, #36 and #75, so "no moving targets" does not hold yet.

## 5. Shared infrastructure

1. **The repo-wide `*.log` / `build/` ignore rules silently drop raw evidence.** Affected: R2-10 raw/logs, B-03 session logs, FIX-02 unit logs, and OWN-16W compositor logs until its fix pass. Add a packet-local `.gitignore` to the template and a verifier check for files that are ignored but cited.
2. **Quiet-lane writer starvation:** OWN-75R blocks stretched from about 1 minute to 13–18 minutes, and R2-10 queued behind B-03. Rule: take the cargo lock before the quiet lock. Consider a ticket lock.
3. **The 2-hour background cap** killed the OWN-75R and OWN-16W batches.
4. **The permission classifier denied a lane's read-only status polls of its own batch** (OWN-75R). Lanes need a sanctioned way to poll.
5. **Session start failures persist:** R2-10 N1 (Xvfb never came up) and N-02 c01 (display stolen 3 times).
6. **dbus-run-session puts its socket in system /tmp** (OWN-75R D14).
7. **Shared smoke-gate harness bug** (OWN-16 and OWN-16W D2).

## 6. Ranked follow-ups (STATE.followups_ranked W3-1..12)

1. **E5:** stage the kvnloo/cua#10 final table, the #3963 rewrite draft (fresh reviewer) and the #74 queue.
2. **E6 recertification on `0f1955d2f`:** rebase FIX-02, OWN-09R and OWN-16W. Re-run their red/green units and key REAL rows. Rebuild R and re-run a short Phase 0 plus smoke.
3. **B-04 (no provider):** decide toggle and fill W together, with a valid negative control.
4. **Browser MCP transport in/out attribution** on R2-10's source.
5. **Native one-source closure:** lazy HC plus the admission tools-list cache on R2-10's source.
6. **Reviewed guard fix (#20):** take a final diff on deadline exit. Then re-test CL in the 216–245 ms band.
7. **Revision items before any upstream proposal:**
   - OWN-09R: bounded wait, the remaining `spawn_blocking` sites, TextInputAdmission.
   - FIX-02: F4 in-call check, F3 native codes, recording.rs test.
8. **Live toggle/modal compiled replay:** scripted qualification first. A live re-measure needs an owner budget decision.
9. **R2-09 residue:** the X11 ax_fg route; WebKitGTK after the owner rules.
10. **Owner decision queue** (§3).
11. **Publish-time packet fixes,** per lane in `dispositions.<id>.publish_fixes` / `caveats`.
12. **Shared infrastructure** (§5).
