# CUA RFC loop: wave 4 synthesis (2026-10-03 UTC)

Wave 4 ran as attempt 2 (lanes `w4-a2-*`). Eight lanes ran:
- **Accepted (5):** R2-10R, B-04, R2-07c, OWN-20G and PKT-01, each on the head its verifier checked.
- **Accepted only as a report (1):** RECERT-FIX's report of its own hard stop. It has no disposition.
- **Rejected (2):** B-05 and N-03. Both need a text-only fix pass; no re-measurement.

No hard-rule breach under the loop's definitions. Two items need an owner or orchestrator ruling (§0).

TypeSafe use this wave was 0 attempts / 0 reached. R2-07c's 20-reached cap went unused because its Phase L precondition failed. The loop total stays at **542 / 600 reached (638 attempts); 58 remain**.

## 0. Stop rules, breach classes, rulings needed

- **Hard-rule breach:** none. Nothing reached the host desktop or session, no secret was exposed, nothing was written upstream, and every reported number came from a quiet-timed window.
- **RECERT-FIX lane HARD_STOP (owner ruling needed).**
  - At 02:44:58Z the lane ran `pkill -f` with a `build-driver.sh` path pattern in the plain host shell, to stop its own broken build loop.
  - The pattern also matched R2-10R's control-build chain, and RECERT-FIX's own waiting flock.
  - **Rule broken:** "never kill a process you did not start". This is not one of the loop's breach classes, and it is not a near miss because it had an effect.
  - **Effect:**
    - R2-10R's control binary landed about 1m47s late. It was rebuilt from source (`e66fac2c`) and is not contaminated.
    - OWN-20G's queued build waited about 2.5 minutes longer.
    - No trial was killed.
  - **Record corrections:**
    - R2-10R's `raw/provenance/builds.log` blames a "120 s tool timeout". That cause is wrong; this is a publish fix.
    - RECERT-FIX's raw builds.log prints rc=0 for every iteration. The capture is wrong; annotate the incident.
  - The synthesizer does not rule on this.
- **Privacy finding on published fork content (owner/orchestrator decision; found at synthesis).**
  - R2-10's `verify_artifacts.py` carries a hex-encoded list `_H` of 5 private names, and one of them is the host name. I confirmed this by counting matches only; the name was never decoded or printed.
  - The list has been on origin since wave 3, in `exp/r2-10-composition-20261002` (`030f6bdbf`).
  - R2-10R copied it verbatim (`caf3d68a7` onward), and PKT-01's `exp/r2-10-composition-r1b-20261003` inherits it.
  - No other origin `exp/*` / `docs/*` branch and no other wave-4 branch contains it.
  - B-05's verifier rejected B-05 for exactly this list. The privacy scans of R2-10, R2-10R and PKT-01 do not decode hex, so they missed it.
  - **Before Publish:**
    1. Rewrite R2-10R's unpublished history and re-verify it.
    2. Add a removal commit on the r1b branch.
    3. The owner decides what to do with the published fork branch.
- **Near misses (no effect):**
  - Stdlib `python3` no-ops and heredocs in the plain host shell: R2-10R, B-05 (4 commands), N-03, B-04 and OWN-20G.
  - One `rustc --version` (B-05).
  - One `git show | grep` script (PKT-01).
  - R2-07c host-shell file operations, plus its verifier's heredoc writes.
  - OWN-20G pilot p04-r1: x11rb tried the host's abstract X socket. hostless v2's Landlock scope refused it and nothing connected.
  - The host name was printed once to an agent's own terminal, by B-05's lane and by R2-07c's verifier. It was never written anywhere.
  - Synthesizer: read-only `jq` reads in the plain shell before switching to hostless.
- **Lock discipline (other tracks):**
  - EXCLUSIVE windows ran at 1-minute loadavg 8–32: R2-07c timing, B-05 Phase A 13.8, R2-10R D1 18.5–25, N-03 a1 32.
  - R2-10R nm2 had another track's unlocked CPU work inside its window. This is disclosed, and sensitivity cuts show the claims survive.
- **Stop-rule counters:**
  - Waves used: 5 of 12.
  - Not stalled: there are 5 new terminal dispositions. The browser untested share rose (§2), but that is a correction.
  - Budget is OK but cannot fund any 30-pair live arm.

## 1. What changed this wave

- **R2-10R: RECERTIFIED (E6).** Head `c183b95e3`, which must be rewritten for privacy before push.
  - **Source:** R' = 0f1955d2f + R2-10 steps 1–8.
    - Tested head `45dff8f32`. Binary `922111c5`, cua-driver 0.32.0.
    - The libs/cua-driver tree equals 41c34cb0d's.
    - Upstream main is now `66e0b6652`, with 0 further libs/cua-driver changes.
  - **Phase 0:** (a)–(e) pass.
  - **Validity:** 100% in all 18 cells (384/384 scripted, 144/144 native), with 0 E4 violations.
  - **Scripted COMP S** (median T_oracle):

    | Class | S [CI] | BASE → COMP |
    |---|---|---|
    | fill | 45.65 [44.39, 48.36] | 3189.9 → 69.9 ms |
    | toggle | 46.82 [45.21, 48.69] | 2503.4 → 53.5 ms |
    | modal | 44.86 [43.56, 46.81] | 2491.4 → 55.5 ms |

    COMP_K is about 1.01, with CIs above 1.
  - **Native:**
    - X text 5.89 [5.87, 5.90]; X checkbox 1.18.
    - S0 1.18 (checkbox) and 1.03 (text).
    - T_land S 1.00, as in R2-10.
  - **Gated rows:** all 18 gated S rows exclude 1 in the same direction. The first version checked 15; it was corrected post hoc and disclosed in PREREG-AMENDMENT-2.
    - 0 verdict mismatches. This gate is label-based by construction, so it cannot fail.
    - 16/16 work-deleted signs kept.
  - **D1 first-snapshot grace:**
    - 1 elements digest over 40/40 trials, with truncated=false in 40/40.
    - Grace reports 2000 ms and explicit 1000 ms.
    - Paired T G−E is +4.95 ms [−5.02, +21.37]. This is indicative only; the run was load-contaminated.
  - **Live layer:** BLOCKED on budget. It needs ≥180 reached, and it stays certified at 989cc76ce.
- **B-04: REVISE** (`8620ebfa2`, binary R). It replaces R2-10's browser observation row.
  - **Base observation:** IRREDUCIBLE.
  - **Cold excess E_R, per-document part: IRREDUCIBLE.**
    - It is not deletable by an in-task 80 ms wait (fill +64.0 / +57.9 ms, toggle +64.0 / +56.6 ms, blocks m / x).
    - Nor by an in-task prewarm (+44.7 / +48.2, +37.3 / +53.8 ms).
    - This part is unsized.
  - **Per-process part: UNDECIDED.**
    - Both estimators fail the P1 negative control: after readiness, the first AX-tree fetch still costs about 4.5–4.7 ms on fill.
    - The 20 ms tail-injection positive control also fails, because `browser_navigate` returns at Page.navigate commit (SOURCE).
  - **Consequence:** R2-10's browser untested shares become lower bounds.

    | Layer | Class | Before → after |
    |---|---|---|
    | scripted | fill | 15.2 → 39.1% |
    | scripted | toggle | 16.4 → 36.0% |
    | live | fill | 14.0 → 36.5% |
    | live | toggle | 90.4 → 92.7% |
    | both | modal | unchanged |

  - Block m's P4 order defect is disclosed and was repaired by a Williams block x. The verdict requires both blocks to pass.
- **R2-07c: REVISE** (`7f46edd16`, binary R). The compiled fresh-bound routine for toggle→confirm and modal→act is correctness-qualified.
  - **G1–G4:** G1 2+2 and G2 2+2. G3 292/292 accepted mutations were fresh. G4 105/105.
  - **G5 26/26:** reconcile before replay, 0 duplicates.
  - **G6:** warm 85.6 / 82.0 ms.
  - **E4:** 0.
  - **Timing non-regression gate failed:** CR − COMP is toggle +4.11 [−15.10, +16.94] and modal +6.92 [−3.30, +12.09] ms, at loadavg 8–32. The packet does not claim non-regression, and the lane headline's "noise, not a mechanism" is not supported.
  - **Phase L (live):** NOT_RUN, because its precondition failed.
- **OWN-20G (#20): guard final diff G KEEP as a fork candidate** (`ce7544cc0`, fix `a30cbbc3b`).
  - **UNIT:** red/green; 611/611 platform-linux lib tests.
  - **R1 reply-delay reproduction of c08-017:** G restored 40/40, while U missed 40/40 silently.
  - **Specified XGrabServer row:** fails for U and G alike. The grab makes the stalled read see the steal. The planner must accept the pre-registered substitution.
  - **CL clamp: KILL.** In the 225–240 ms band, G restored 75/80 and G+CL 0/80. Keeping the ~21 ms overshoot IRREDUCIBLE is a judgement.
  - **a11y bus restart:**
    - Safety 40/40: degraded tree, stale token refused, 0 stale mutations.
    - Liveness FAIL: 0/40 recover in-process; a fresh process recovers 40/40.
  - **Before publication as a product fix,** G must be ported onto clean main: it does not apply to 0f1955d2f without the measurement picks.
- **PKT-01: KEEP** (`cca59642d` plus four r1b repair heads).
  - All 27 published packets audited from clean clones; 26/27 reproduce.
  - OWN-75R (`e02621fdc`) fails because 48 cited logs were dropped by `*.log`. It is repaired on r1b (`efe36d1a1`, 112/112).
  - R2-10 r1b passes 132/132; B-03 r1b and R2-09 r1b pass.
  - Packet template ships with a packet-local `.gitignore` and an ignored-but-cited check. Helper controls pass 5/5.
- **Rejected:**
  - **B-05:** its headline says the instrumentation made up most of transport and admission. Its own data say transport is 30–48% instrumentation; only the admission residual is mostly instrumentation. The lane record is also stale.
  - **N-03:** Part B ran each element in a fixed order, not AB/BA. This is undisclosed; the impact is bounded at about 0.6 / 0.25 ms.

  Their numbers are recorded as pending only (§2).
- **RECERT-FIX: HARD_STOP before any build.**
  - Work done before the stop: 14/14 rebased commits are patch-identical, and 9 clean worktrees exist.
  - #36, #9, #16 and #105 recertification is still pending (E6).

## 2. Per-reference-task decomposition (best known)

Rules:
- **Sources:**

  | Source | Binary |
  |---|---|
  | R2-10 / B-04 / R2-07c on R | `12b9045a` |
  | R2-10R on R' | `922111c5` |
  | OWN-20G | U `f0fe3219` / G `66e303c7` |
  | B-05 (rejected) | B5 `f4149bdd` |
  | N-03 (rejected) | N3 `b1843871` |

  Never add or ratio across these sources.
- **Metrics:** T is median T_oracle. Components are mean ms (share of mean T).

### Browser (R2-10R on R', scripted COMP; B-04 correction from R)

| Class | BASE → COMP T | Material components (verdict) | T_irr / floor | Untested (R2-10 mapping, R') | Untested with B-04 (on R) |
|---|---|---|---|---|---|
| fill→submit | 3189.9 → 69.9 ms | observation 24.5 (~30%) IRREDUCIBLE except cold excess; endpoint reval 24.2 (~30%) OWNER_DECISION; sleeps/polls 8.8 IRREDUCIBLE; MCP transport 5.3 (6.6%; in 1.35 / out 3.99) **UNTESTED**; resolution 2.5, admission residual 1.6 UNTESTED | 42.6 / 1.90x | 15.2% | **39.1%** scripted, **36.5%** live (lower bounds) |
| toggle→confirm | 2503.4 → 53.5 ms | endpoint 23.2 (~43%) OWNER_DECISION; observation 14.8 (~28%); MCP transport 4.7 (8.8%) **UNTESTED**; reval_other 4.9995% IRREDUCIBLE (flagged) | 19.7 / 2.72x | 16.6% | **36.0%** scripted; live **92.7%** (provider decisions 88%) |
| modal→act | 2491.4 → 55.5 ms | endpoint 23.5 (~42%); observation 15.7 (~28%); MCP transport 4.8 (8.7%) **UNTESTED** | 21.0 / 2.64x | 16.2% | unchanged: 16.4% scripted (R), live 90.9% |

- **Work deleted vs wall-clock saved (R2-10R).**
  - Fill COMP deletes 3000.3 ms of visualization and 101.1 ms of settles per trial, and saves 3118.4 ms (median paired).
  - Toggle saves 2448.4 ms; modal saves 2435.5 ms.
- **Owner-decision dependency (unchanged).** With KEEP-only deletions, S is about 1.01. Almost all of S comes from the glide (feedback off) and from endpoint re-proof.
- **R2-07c, toggle/modal COMP vs COMP+CR on R, scripted.**
  - T_oracle: toggle 94.7 → 85.6 ms, modal 82.9 → 82.0 ms.
  - The paired differences' CIs include 0, and non-regression is not shown.
  - The live provider decisions (434.8 / 462.4 ms in R2-10) stay UNTESTED.
- **Pending only (B-05, rejected):**
  - Corrected transport in/out is 4.51 / 3.95 / 6.75 ms on B5, and the admission residual 0.21–0.36 ms.
  - The caller-side candidates delete under 0.5 ms.
  - E2 for the transport is borderline / not established. Even once accepted, it does not touch B-04's 20–24% cold-excess share.

### Native GTK3 (R2-10R on R', arm X)

| Task | BASE → X T | X components | T_irr / floor | Untested |
|---|---|---|---|---|
| checkbox | 334.3 → 283.0 ms (S 1.18; T_land 1.00) | settle 241.2 (85%) IRREDUCIBLE; obs transport 18.1 (in 2.15 / out 15.95) IRREDUCIBLE (R2-10 mapping); action transport 9.3 **UNTESTED**; post-action sleep 0.1 DELETED (BASE 51.1) | 271.8 / 1.04x | **3.9%** (meets <5%) |
| text entry | 1761.3 → 298.9 ms (S 5.89; S0 1.03) | settle 241.2 (81%); action transport 18.5 (in 4.68 / out 13.83) **UNTESTED**; obs transport 17.8; reveal 5.4 OWNER_DECISION residual (BASE 1415.7) | 273.3 / 1.10x | **6.9%** |

- **Work deleted vs wall-clock saved (native text X).** It deletes 1410.3 ms of reveal and 51.0 ms of sleep, and saves 1462.1 ms.
- **OWN-20G (separate binaries).**
  - CL would delete 20.8 ms of settle (T 280.95 → 259.94 checkbox, 296.96 → 276.89 text), but it is KILL.
  - The ~21 ms overshoot stays IRREDUCIBLE. That is a judgement and is stated as one.
- **Pending only (N-03, rejected).** Best arm X+HCL+V on N3:
  - Untested 1.47% (checkbox) and 2.02% (text); conservative 2.73 / 3.14%.
  - V (admission tools-list cache) DELETED: 3.10 / 5.15 ms.
  - HCL OWNER_DECISION: net 0 at k=1, and 70.9 / 101.4 ms per 5-task session.

  Once accepted, this closes native text below 5%, but only after composition on R'.

## 3. Dispositions (this wave)

| ID | Disposition | Class | Branch @ commit |
|---|---|---|---|
| R2-10R | RECERTIFIED (E6); live layer BLOCKED (budget) | REAL+BENCHMARK (FIXTURE); Phase 0 UNIT+REAL; D1 REAL | exp/r2-10r-recert-a2-20261003 @ `c183b95e3` (rewrite pending); control exp/r2-10r-control-a2-20261003 @ `8a2362770` |
| B-04 | REVISE: per-document IRREDUCIBLE (in-task), per-process UNDECIDED | REAL+BENCHMARK; BENCHMARK re-analysis of R2-10 live raw | exp/b-04-observation-reconcile-a2-20261003 @ `8620ebfa2` |
| R2-07c | REVISE: correctness-qualified; non-regression not shown; Phase L NOT_RUN | REAL; G5 FIXTURE+REAL | exp/r2-07c-toggle-modal-compiled-a2-20261003 @ `7f46edd16` |
| OWN-20G (#20) | G KEEP (fork candidate, port needed); CL KILL; R3 safety PASS / liveness FAIL; XGrabServer row FAIL (U=G) | UNIT + REAL (FIXTURE) + BENCHMARK | exp/own-20g-guard-final-diff-a2-20261003 @ `ce7544cc0` |
| PKT-01 | KEEP (deliverable) | SOURCE+UNIT | docs/packet-template-audit-a2-20261003 @ `cca59642d`; r1b: OWN-75R `efe36d1a1`, R2-10 `36ccdd766` (hex-list removal pending), B-03 `911e20796`, R2-09 `ffb4919a7` |
| RECERT-FIX | PENDING (HARD_STOP; no evidence) | — | branches created, 0 commits |
| B-05 | PENDING (rejected; text-only fixes) | — | exp/b-05-browser-mcp-transport-a2-20261003 @ `a91a86a4a` (never push d1b42db63 / 3cced771f / 92cab8900) |
| N-03 | PENDING (rejected; text-only fixes) | — | exp/n-03-native-closure-axfg-a2-20261003 @ `63d419034` |

Stale lane-result commits:

| Lane | Stale commit | Use instead |
|---|---|---|
| R2-10R | `184b39b43` | `c183b95e3` |
| B-04 | `f7d7be405` | `8620ebfa2` |
| B-05 | `d1b42db63` | `a91a86a4a` |
| N-03 | `960bc20aa` | `63d419034` |

None of the wave-4 branches is on origin.

**BLOCKED (exact blockers), unchanged in kind** (STATE.blocked_items_w4):
- **Paid budget:**
  - R2-10 live recertification (≥180 reached).
  - Live BASE vs COMP+CR for toggle/modal (≥120).
  - Native live arms (≥120).
  - #78 live R1/R4 (≥60).
- **Owner decision or budget:** #78 S1.
- **Owner install decision:** R2-09 WebKitGTK.
- **Real Hyprland seat:** #16 Hyprland; #94 with #92/#100/#101; R2-09 Hyprland foreground; OWN-20G Wayland rows.
- **macOS/Windows hardware:** #6, #8, #13, #19, #31, #72, the #16 / #36 macOS/Windows rows, #9 R3 and #9 held-input cleanup.
- **Owner/orchestrator action:** the fail-closed hostless PreToolUse guard.

**OWNER_DECISION queue:**
- The 12 earlier items: glide default, H_E, cursor reveal, H_T, R2-08 API route, I3s, OWN-09R timeout semantics, #9 R8, PR 4336 unconditional fields, dd205d17b null refusal, WebKitGTK, budget.
- New this wave:
  - The RECERT-FIX pkill ruling.
  - The published hex host-name list.
  - OWN-20G: the R1 substitution and the CL overshoot judgement.
  - B-04: the per-process part.
  - HCL session shape (once N-03 is accepted).
  - Allocation of the 58 remaining reached.

## 4. What remains, E1–E6

- **E1 (coverage):**
  - Terminal: R2-01 to R2-10, R2-10R, B-04, R2-07c and OWN-20G.
  - Open:
    - B-05 and N-03 need a text-only fix pass and a fresh verifier. Their measurements are done.
    - RECERT-FIX attempt 3: the #36 same-process two-window row, plus recertification of FIX-02 / the #84 revision / OWN-16W on 0f1955d2f.
    - B-04's per-process part (UNDECIDED).
    - R2-07c Phase L. It needs a passing quiet-window timing block, then 18–20 reached.
- **E2 (critical path): not met, and the browser share rose.**
  - **Browser, scripted:**
    - Fill is 39.1% and toggle 36.0% untested (lower bounds). B-04 moved R2-10's cold excess (20–24% of COMP T) from IRREDUCIBLE to untested.
    - Modal is 16.2% on R'. MCP transport (4.7–5.3 ms, 6.6–8.8%) still has no accepted verdict; B-05 is pending.
  - **Browser, live toggle/modal:** 91–93%, provider decisions. R2-07c qualified correctness only.
  - **Native:**
    - Checkbox: 3.9% on R' (met on one source).
    - Text: 6.9% on R'. N-03, once accepted, gives 2.0% on N3; one-source composition on R' is still needed.
- **E3 (composition):** met on R (R2-10) and recertified on R' for the scripted and native layers. Live is certified only at 989cc76ce, and most of S still depends on OWNER_DECISION components.
- **E4 (invariants):**
  - 0 violations in every accepted arm.
  - R2-07c adds compiled-routine evidence: refusals refused, reconcile before replay, 0 duplicates, 0 dispatch after unknown.
  - OWN-20G adds two items:
    - It closes a silent focus-steal miss: U had 40 silent misses on R1, G has 0.
    - It finds that a11y bus restart leaves the same process degraded but safe.
  - Still open: F4 TOCTOU, native refusal codes in the runner rule, OWN-09R's unbounded wait. RECERT-FIX did not run.
- **E5 (deliverables):** not staged. The w4 planner deferred them until the evidence is stable. PKT-01's template and repaired heads are the base for a docs/ branch in wave 5.
- **E6 (stability):**
  - **Freshness:** upstream main `66e0b6652` touches no libs/cua-driver path since 0f1955d2f. R2-10's scripted and native claims are recertified there.
  - **Not yet recertified:** FIX-02, the #84 revision and OWN-16W (RECERT-FIX hard stop).
  - **PR heads unchanged:** trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, #105 `98a45e6c5`, #106 `c45845797`.
  - **Moving targets:** E2 verdicts moved this wave (B-04 observation, the CL KILL reaffirmed), so "no moving targets" does not hold.
  - No judges have run.

## 5. Shared infrastructure (STATE.infra_followups W4)

1. **The quiet lock does not keep the host quiet.** EXCLUSIVE windows ran at loadavg 8–32 while other tracks did unlocked CPU work. Either all tracks take the lock for CPU-heavy work, or timing PREREGs carry a load ceiling and an abort rule.
2. **Caps belong inside the lock holder.** R2-10R's outer timeout counted about 40 minutes of queue wait, and measured chunks queued 20–40 minutes each.
3. **zsh does not word-split unquoted variables.** This hit RECERT-FIX's build loop (which led to the pkill), an R2-10R hostless call, and the synthesizer's scan. Run lane scripts under bash.
4. **Never use `pkill -f` / `pgrep -f` with path patterns** on the shared host.
5. **Privacy scanners must decode hex/base64,** and should read private names from an untracked file.
6. **Stamp the Driver sha256 into browser manifests and trial records.** R2-10R and R2-07c both had gaps.
7. **The display race persists.** Move R2-10R's xdpyinfo probe (rc 97) into the shared session wrapper.
8. **dbus socket paths under /tmp** end up in committed session logs.
9. **The orchestrator should re-read branch heads before synthesis and publish.** Four lane records were stale.

## 6. Ranked follow-ups (STATE.followups_ranked W4-1..11)

1. **Publish gate:**
   - Rewrite R2-10R to drop the hex list, re-verify it, and add the builds.log cause note.
   - Add the r1b hex removal commit and the PKT-01 text fixes.
   - Scrub the OWN-20G username from the xhost output.
   - Owner decision on `exp/r2-10-composition-20261002`.
   - Then publish R2-10R (+ control), B-04, R2-07c, OWN-20G and PKT-01 (+ 4 r1b).
2. **Text-only fix passes with fresh verifiers:**
   - B-05: reword the headline and replace the stale record.
   - N-03: disclose the Part B order.
3. **RECERT-FIX attempt 3,** after the owner rules on the pkill. Run it under bash with no `pkill -f`.
4. **Wave-5 one-source composition on R':**
   - Use V and HCL once N-03 is accepted, and G after its port.
   - Include the compiled routine if its timing passes.
   - Report E2 with B-04's observation mapping.
5. **OWN-20G productisation:**
   - Port G onto clean main, then UNIT and a small R1-reply re-run.
   - Fix the same_app_dialog misclassification.
   - a11y bus reconnect.
6. **B-04 per-process part:** redesign the negative control, or get an owner ruling.
7. **R2-07c quiet-window timing block** with a load ceiling. Then Phase L within ≤20 reached.
8. **E5:**
   - kvnloo/cua#10 final table.
   - trycua/cua 3963 rewrite draft, with a fresh reviewer.
   - kvnloo/cua#74 queue.
9. **Owner decision queue.**
10. **Shared infrastructure** (§5).
11. **Carry-over publish_fixes from waves 1–3:** 27 open and 4 partly applied, per PKT-01.

Fork comment drafts are in `drafts/w4/`: 93, 10, 73, 74, 20 and 75, plus PUBLISH-NOTES.md, which is not for posting.
