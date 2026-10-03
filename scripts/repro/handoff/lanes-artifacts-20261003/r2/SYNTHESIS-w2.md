# CUA RFC loop: wave 2 synthesis (2026-10-02 UTC)

Eight lanes ran. Fresh verifiers accepted seven. They accepted OWN-75 only as a correct hard-stop report, with no evidence. Nothing was rejected. TypeSafe use this wave: 0 reached / 0 attempts. Loop total is unchanged at 236 / 600 reached (332 attempts), leaving 364.

## 0. Stop rule: fired again, needs a ruling

The OWN-75 lane broke the host-isolation rule, and the verifier confirmed it from the lane transcript and the environment:
- **What ran:** at 2026-10-02T04:51:47.502Z the lane ran `/usr/bin/python3 -c "import gi; ... from gi.repository import Gtk ..."` in the plain host shell, which is not sandboxed.
- **Why that touched the host:** that shell has WAYLAND_DISPLAY, DISPLAY, HYPRLAND_INSTANCE_SIGNATURE and DBUS_SESSION_BUS_ADDRESS set. PyGObject 3.56.3 autoinits GTK on import (`Gtk.init_check`), so GDK opened a short-lived connection to the host Hyprland/Wayland session. The accessibility bridge may also have contacted the host session bus.
- **Effect:** no window or input. No secret was exposed and nothing was written upstream. Every reported trial ran under hostless in a private Xvfb.

This matches END_CONDITION's stop rule ("any hard-rule breach (host desktop touched …)"). **It is the second breach of exactly this kind.** Wave-1 N-01 was the first, and after it the owner ruled to continue with structural guards. Those guards (the hostless wrapper, the quiet-timed ledger) wrap only the commands a lane chooses to wrap. The plain host shell is still unguarded. Every wave-2 lane, and one verifier, also logged stdlib-only `python3` near misses in that shell.

**I am not making the stop decision.** STATE.json marks `stop_rules.hard_rule_breach` as FIRED and `waves[2].published` as false. No wave-2 Publish and no wave 3 should happen until the orchestrator or owner rules. If the loop continues, the guard needs to fail closed: a hook that rejects code-executing commands without the hostless prefix, and worker shells started with the display and bus variables unset.

Other breach-class notes (none is a hard breach):
- N-01R pilot: it was refused by the harness guard under hostless v2. Its private Xvfb created a socket in the host `/tmp/.X11-unix`, but there was no display contact.
- FIX-01: two reported values (C4w 24.9 ms, G2 T 314.19 ms) were measured under the SHARED lock while the lane's own cargo run was going. The verifier ruled this not a breach because the spec put Part C under SHARED and the values are not gated. I am flagging the classification for the owner. At publish they must be labelled characterization or dropped.
- B-02: TMPDIR was unset, so possibly system /tmp was used. This was disclosed.

## 1. What changed this wave

- **N-01R native causal A/B: KEEP**, terminal for N-01. 240/240 main trials verified.
  - **Cursor reveal: OWNER_DECISION.** Text saves −1418.3 ms [−1432.1, −1389.4]; the warm-cursor checkbox saves −1236.5 ms. For a fresh-process checkbox it is NOT_MATERIAL, because the reveal only pulses.
  - **50 ms post-DoAction sleep: DELETED,** but **only for GTK3 AT-SPI with background delivery.** It saves −60.6 / −42.3 ms. The "0 receipt-vs-oracle disagreements" result is structural, because click receipts are always `unverifiable`. The real evidence is X2, where the effect was visible at return in 40/40. WebKit/Chromium targets (the reason the sleep exists, per native.rs:3531-3534) and foreground delivery are NOT_RUN. They are required before any default change.
  - **Focus-guard settle: IRREDUCIBLE.** F0 saves ~237 ms but missed 10/10 focus steals with a silent receipt; B restored 20/20.
  - Best composed arms: checkbox S0 307.9 ms, text X = C+S0 334.9 ms.
- **B-01 browser critical-path decomposition: ACCEPTED** through the B-01R text fix (0cd63f786). The admission cost now reads 2.181 ms per tools/call, 4.362 per step and 8.723 per task, and the build-lock row reads "not receipted". These wave-1 verdicts are now accepted:
  - H_V fast glide: KEEP
  - H_T 100 ms insert_text focus settle: OWNER_DECISION
  - H_P completion poll: not material
  - H_C caller-compiled validators: KEEP
- **B-02 browser causal A/B of B-01's three untested Driver sites.** 240/240 measured, one EXCLUSIVE window. Values are listed fill / toggle / modal.
  - **Endpoint re-proof bound check (E): OWNER_DECISION** in every class. The component drops from 42.7/39.0/37.8 to 10.6/8.7/8.9 ms. T_oracle saves 21.9/25.4/33.0 ms (bind + T: 16.0/14.9/29.7). It is a security-policy change, so the owner decides.
  - **MCP admission tools-list cache (V): DELETED (KEEP)** for fill and toggle; NOT_MATERIAL for modal, where the T_oracle CI touches 0 (component saving 14.9 ms, CI excludes 0). The admission component drops from 18.2/17.5/17.4 to 2.4/2.4/2.3 ms, and per call from 1.573 to 0.32 ms.
  - **Cold first snapshot (W): no knob.** Fill NOT DELETED (the work only moves), modal IRREDUCIBLE, toggle UNDECIDED.
  - S = K5/K5EV is 1.35 / 1.49 / 1.54.
  - Every control passed: N-E1 30/30, N-E2 15/15, N-E3 190/190, N-W1 60/60, N-W2 20/20, N-V byte-identical, smoke 5/5.
  - Acceptance covers b282ff389 only. The round-1 "BLOCKED" claim at 0330e34fd was never true for the measured blocks.
- **FIX-01 reviewed Driver fix: fix REVISE; R2-07b re-qualification KEEP.**
  - **Part A:** dom_event `browser_click` / `browser_pointer` / `browser_download` now check `isConnected` inside the dispatching callFunctionOn.
    - C1 N4a: U accepted 20/20; F refused 20/20 with `browser_ref_stale` and 0 old-node events, then rebound and verified 20/20.
    - C3 detached-handler effect: U 10/10, F 0/10.
  - **Part B (run.py/run.ts):** 0 re-dispatches (old: 10/10), and refused is classified as refused 10/10 (old: 0/10). C6 shows 0 false refusals.
  - **Why REVISE:** the pre-registered cherry-pick onto f5c991e59 conflicts. A one-hunk resolution is recorded and passes 187/187.
  - R2-07 stays KILL. Compiled replay is eligible for R2-10 fill only on a source that contains this fix.
  - **Latent risk:** Part B would retry a `browser_input_trust_unavailable` refusal whose delivery is unknown. That path is not reachable today, but it must be fixed before any promotion.
- **OWN-09 (#9 Linux core rows): KILL** for "kvnloo/cua#84 as-is answers #9". 1,800 counted iterations.
  - Main has confirmed gaps on R2, R6 and R7 (40/40 duplicate effects on R7).
  - #84 passes R4 and R5. It passes R2 and R7 only for a tool that adopts `spawn_blocking_owned`, and no production code calls that.
  - #84 fails R6 40/40: readiness is reported while native work is still running.
  - #84 fails R1 1/40: a queued call was admitted after the caller abandoned it. Main shows the same in exploratory runs, 3/200.
  - R3 is BLOCKED (macOS). R8 over REAL stdio is NOT_RUN. #84 also needs a rebase.
- **OWN-36 (#36 native isolation, GTK3/X11): REVISE.**
  - KEEP: capture ownership; session-end retirement; same-label restart; content-free envelopes.
  - KILL: native element tokens are not session-owned. B used A's token to toggle A 40/40, including 20/20 across two separate MCP clients.
  - KILL: tokens carry no runtime generation. A token from the first Driver process was accepted by the restarted one 10/10.
  - Replacement isolation holds for separate windows. It is falsified for a shared window (I3s 20/20, non-gating).
- **OWN-20 (#20 AT-SPI invalidation census): KEEP.** 526/526 REAL forced mutations.
  - child_add is a NOISY_HINT: it was never signalled in 40/40 reps (GtkBox.pack_start).
  - A recreated node is label-identical in 20/20 observations while its identity changed.
  - Every other scope had a typed event in every delta, over a finite number of reps.
  - Event absence authorizes reuse in no scope, so the recommendation is to always observe.
  - Chromium/Electron is NOT_RUN: AT-SPI exposed only the frame.
- **OWN-75 (#75 exact-head validation of trycua/cua PR 4336): HARD_STOP** (§0).
  - The stopped run was not accepted: unit and typecheck were clean at both SHAs, 16/16 mutants were caught, and 42/160 REAL trials verified.
  - Resuming needs at least m05 re-run in full; preferably all 160 trials under the committed PREREG.

## 2. Per-reference-task decomposition (best known)

Rules: never add or ratio rows across sources, binaries or environments. Wave-2 rows come from B-02 (`f5c991e59`+`560bd8247` / `7e6c0609`) and N-01R (`b9b357bc7` / `c2a9978e`). Both ran on a heavily loaded host (1-minute loadavg 17–24 on 10 CPUs), so absolute values are host-state specific. Shares are mean T_runner shares from the packets' E2 tables; T values are median T_oracle.

### Browser (B-02, scripted chooser, feedback off, K5 = B-01 K5)

| Class | K5 / K5E / K5V / K5EV median T_oracle (ms) | Best arm, KEEP knobs only | Material components and verdicts | Untested share |
|---|---|---|---|---|
| fill→submit | 156.5 / 138.7 / 148.3 / 115.9 | K5V (mean 155.1) | observation 35.6% IRREDUCIBLE (cold excess: moved only); revalidate 33.5%, of which the endpoint part is OWNER_DECISION and the rest IRREDUCIBLE; sleeps/polls 5.6% not material | **1.6%** (admission residual 2.49 ms, including trace cost). With OWNER_DECISION knobs (K5EV): 1.9% |
| toggle→confirm | 119.2 / 97.2 / 108.3 / 79.8 | K5V (mean 111.5) | revalidate 48.3% (endpoint OWNER_DECISION); observation 29.8% IRREDUCIBLE; **cold-first-snapshot excess 22.3 ms UNDECIDED** | **22.1%**. K5EV: 32.4% |
| modal→act | 127.7 / 92.2 / 109.9 / 83.0 | K5 (mean 128.1) | revalidate 40.9% (endpoint OWNER_DECISION); observation 24.6% IRREDUCIBLE; pre-dispatch 15.4% (V NOT_MATERIAL); visualization 5.1% OWNER_DECISION | **0.0%**. K5E: 0.0%; K5EV, the spec's literal best arm, is **not decomposed** (publish fix) |

The earlier B-01 rows (`f5c991e59` / `2e0248ad`, quiet host) are now accepted evidence:
- Default-feedback T: 3180.7 / 2487.3 / 2471.7 ms, of which 94–97% is the awaited glide.
- Best composed: 78.7 / 52.2 / 53.2 ms.

The B-01 and B-02 rows must not be combined. Live provider (R2-07, TypeSafe): the provider decision is 46–64% of T. Guarded completion deletes one decision. Compiled replay may return for fill after FIX-01, but only on a source that contains it.

### Native GTK3 (N-01R, scripted)

| Task | Main arm B | Best composed arm | Components of the best arm | Untested share |
|---|---|---|---|---|
| checkbox | 365.4 ms (settle 241.4 = 66%, sleep 50.8 = 13.8%, observation transport 29.1, observation 18.5, action transport 15.1, reveal pulse 0.013) | S0, 307.9 ms | settle 78.2% IRREDUCIBLE; observation transport 9.2% IRREDUCIBLE by invariant (load-sensitive, cause not identified); observation 5.5% IRREDUCIBLE; action-call MCP transport 5.05% **UNTESTED** | **5.8%** (~15% if observation transport counts as untested) |
| text entry | ~1.80 s (derived; reveal 1421.1 = 78.9%, settle 241.2 = 13.5%, sleep 51.0 = 2.8%) | X = C+S0, 334.9 ms | settle 71.7% IRREDUCIBLE; action-call MCP transport 9.55% **UNTESTED**; observation transport 8.0%; observation 5.2%; reveal residual 3.0% OWNER_DECISION | **10.3%** (~18% conservative) |

Speedups: checkbox S_X 1.16. Text S_C 4.63 and S_X 5.37. The S_X2 values (4.34 / 19.30) are excluded because that arm drops the IRREDUCIBLE settle.

Event fidelity (OWN-20): AT-SPI typed events arrive 0.2–1.3 ms after a fixture mutation, and Driver-path events 9–17 ms after one. That is too unreliable for structure (child_add is never signalled) and gives no wait worth an event wake on the GTK3 background path. R2-09's own disposition is still open (§4).

## 3. Dispositions

| ID | Disposition | Class | Branch @ commit |
|---|---|---|---|
| N-01R | KEEP: H_C OWNER_DECISION / NOT_MATERIAL; H_S DELETED (GTK3 AT-SPI background only); H_F IRREDUCIBLE | BENCHMARK+REAL+UNIT (fixture) | exp/n-01r-native-wait-ab-20261002 @ `3bb4a7fc7` |
| B-01 (via B-01R) | KEEP (decomposition): H_V KEEP, H_T OWNER_DECISION, H_P not material, H_C KEEP | REAL+BENCHMARK+UNIT | exp/b-01r-browser-critpath-textfix-20261002 @ `0cd63f786` |
| B-02 | H_E OWNER_DECISION; H_V DELETED fill/toggle, NOT_MATERIAL modal; H_W moved only / IRREDUCIBLE / UNDECIDED | BENCHMARK+REAL+UNIT+SOURCE | exp/b-02-browser-driver-sites-20261002 @ `b282ff389` |
| FIX-01 | fix REVISE (cherry-pick conflict onto f5c991e59, resolution recorded); R2-07b KEEP | REAL+UNIT (+G6 BENCHMARK, not gated) | exp/fix-01-detached-node-refusal-20261002 @ `4a301d32a` |
| OWN-09 (#9) | KILL for kvnloo/cua#84 as-is; main gaps R2/R6/R7 confirmed; R3 BLOCKED; R8 REAL NOT_RUN | UNIT/FIXTURE+SOURCE | exp/own-09-cancel-barrier-rows-20261002 @ `bf07c8fe3` |
| OWN-36 (#36) | REVISE: capture KEEP; native token ownership KILL; runtime generation KILL; shared-window replacement falsified | REAL+FIXTURE | exp/own-36-session-isolation-native-20261002 @ `ff77554f4` |
| OWN-20 (#20) | KEEP (always observe; child_add NOISY_HINT) | REAL+SOURCE | exp/own-20-atspi-invalidation-census-20261002 @ `6da15bf35` |
| OWN-75 (#75) | PENDING: HARD_STOP, no evidence accepted | — | exp/own-75-timing-parity-4336-20261002 @ `cd1878872` (PREREG only; do not publish) |

Earlier: R2-01 KEEP_H1, R2-02 KILL, R2-03 KEEP, R2-04 REVISE (its waits now have causal verdicts from N-01R), R2-05 KEEP, R2-06 KEEP, R2-07 KILL (R2-07b KEEP after FIX-01), R2-08 KEEP, OWN-105 KEEP, OWN-78 REVISE, OWN-16 KEEP, BUG-01 A CONFIRMED_BUG / B ACCUMULATION_ONLY. N-01 is superseded by N-01R. R2-09 and R2-10 are PENDING.

**BLOCKED (external):**
- **Hardware:** #6 (Windows), #8 (macOS, plus the upstream trycua/cua 3904 decision), #13 (macOS), #19 (Windows UIA), #31 (macOS/Windows rows), #72 (macOS), the #16 macOS/Windows rows, the #36 macOS/Windows native rows, and #9 R3 (macOS drag/mouse-up oracle).
- **Real Hyprland seat:** the #16 Hyprland Wayland row, and #94 with #92/#100/#101.
- **Provider or budget:** the #78 S1 row (TypeSafe only). R2-10's native live-provider arms need at least 120 more reached requests, which exceeds the cap, so native R2-10 uses the scripted chooser.
- **Deferred, not blocked:** the #16 wlroots/headless-sway row, until cua-sway-session.sh exists.

## 4. What remains, E1–E6

- **E1 (disposition coverage):**
  - Linux owner rows that are now terminal: #9 (KILL for #84 as-is), #16, #20, #36, #78, #105.
  - **#75 is still PENDING** because of the hard stop.
  - **R2-09:** the GTK3 inputs are complete (N-01R names SETTLE_WATCH IRREDUCIBLE; OWN-20 says event absence never authorizes). Because R2-09 has no packet of its own, the planner must rule: close it as KILL scoped to the GTK3 background path, or schedule the WebKit/Chromium and foreground rows.
  - **R2-10** is the main open item.
- **E2 (critical path):**
  - Browser: met for fill (1.6–1.9%) and for modal on K5/K5E (0.0%). The spec's literal best arm for modal, K5EV, still needs decomposing. **Toggle is not met** (22.1–32.4%), entirely because of the UNDECIDED cold-first-snapshot excess.
  - **Native: not met** (5.8% / 10.3%, or about 15% / 18% conservatively). What remains is MCP transport, both the action call and the observation call; the latter is labelled IRREDUCIBLE but is load-sensitive and its cause is not identified. A quiet-host measurement would settle whether it is real.
  - This wave cut the untested share from 51–70% to 0–22% (browser) and from about 90% or more to 6–10% (native).
- **E3 (composition on one source):** not run. Next step:
  1. Build one source: `f5c991e59` + `560bd8247` + FIX-01 with the resolved hunk.
  2. Re-run FIX-01 C1/N4a and the default-off smoke on it.
  3. Re-base B-01's PREREG draft: V in the composed arm, E as an OWNER_DECISION arm, compiled replay for fill only.
  4. Reserve 330 TypeSafe reached of the 364 remaining.
  5. Native arms: baseline vs X = C+S0 with the scripted chooser, at least 20 pairs per task.
  6. Measure in one window and record loadavg.
- **E4 (invariants):**
  - Fixed on FIX-01 trees: the detached-node dom_event click (R2-07 N4a) and run.py's refused-as-success and re-dispatch bugs.
  - Open:
    1. B-02 N-W2: the default path at the tested source dispatches a stale same-document ref to a detached node, and in toggle/modal the detached handler fired the server effect 12/12. FIX-01 targets this, but N-W2 has not been re-run on a FIX-01 tree.
    2. OWN-36: a cross-session native token mutates another session's window 40/40, and a stale-generation token is accepted after a Driver restart. A session can use another session's authority.
    3. OWN-09: R6 readiness is reported while native work runs, and R1 admits a queued call after cancellation, both on main and on #84.
    4. FIX-01's latent retry of possibly-landed refusals.
  - Each needs a reviewed product fix and a re-run. The controls in every accepted packet were discriminating.
- **E5 (deliverables):** still nothing staged: no #10 final table, no #3963 rewrite and no #74 queue. The wave-2 comment drafts are in `drafts/w2/`.
- **E6 (stability):**
  - Freshness is OK. Upstream main is `ab628e0d1`, 17 ahead of `352507b6c`, with 0 files under libs/cua-driver.
  - Live heads are unchanged: trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802`, PR 4394 `039257811`; kvnloo/cua#84 `566b9c732`, kvnloo/cua#105 `98a45e6c5`.
  - No judges have run.
- **Stop rules:**
  - Waves used: 3 of 12.
  - Not stalled.
  - The provider budget is fine (236/600).
  - **The hard-rule stop rule fired (§0).**

## 5. Shared-infrastructure findings for the loop owner

1. **The plain host shell is unguarded.** It caused the OWN-75 breach and the near misses in every lane. Add a fail-closed hook, and start worker shells with the display and bus variables unset.
2. **`bin/hostless` changed mid-wave.** Another track swapped v1 (bwrap with socket-dir mask) for v2 (Landlock plus an environment scrub, no mask) at 05:06:31Z without notice. v2 fixed Chromium's root-ownership check, but it leaves host socket directories visible, and a private Xvfb socket appeared in the host /tmp/.X11-unix. Version and announce the wrapper, and decide whether the mask is required.
3. **The quiet-lane flock starves writers.** OWN-20 waited about 35 minutes, and N-01R had to regroup its plan. Consider a ticket or queue lock.
4. **"Quiet" EXCLUSIVE windows still ran at loadavg 15–24,** because the parallel tracks keep the host busy. The verifier's re-run at loadavg 12–15 gave smaller absolute endpoint savings. E3 needs a genuinely quiet window or must report load next to every number.
5. **Driver telemetry is on by default in sessions,** and hostless does not block the network. Disable it in the session wrapper so "0 non-loopback connects" also covers the Driver.
6. **TMPDIR is unset.** Set it inside hostless.
7. **Session flakiness is still there:** cua-x11-session display collisions (N-01R a01, OWN-36 I2d 08, FIX-01 C3-U) and one private AT-SPI registry activation failure.
8. **Background runs hit the 2-hour limit** (N-01R a07). Plan runs in chunks with release receipts.

## 6. Ranked follow-ups

1. Rule on the stop rule (OWN-75), and add a structural guard if the loop continues.
2. Run R2-10 on one source (E3), as in §4.
3. Reviewed product fixes for E4 / owner rows: a session check in SnapshotStore::resolve plus a runtime generation in tokens (re-run OWN-36 I2/I2d/I5p); FIX-01 Part B retrying only on pre-dispatch refusal codes; a detached check in `browser_set_input_files`; re-run B-02 N-W2 on a FIX-01 tree.
4. Settle the toggle cold-first-snapshot excess with a decisive probe, and decompose K5EV for modal.
5. Native E2 residue: measure MCP transport on a quiet host, and clamp the settle-loop overshoot.
6. Planner ruling on R2-09.
7. Resume OWN-75 after the ruling.
8. kvnloo/cua#84 revision path, then re-run OWN-09 R1/R2/R6/R7 and the C-ABI late-cancel row.
9. Publish-time packet fixes, listed per lane in `STATE.json` `dispositions.<id>.publish_fixes`. N-01R needs an explicit decision to rewrite or accept two history blobs that contain local directory names (not paths, host name or secrets).
10. Carry-overs: OWN-78 abstain isolation, the OWN-16 non-boolean selector refusal, staging the BUG-01 fixes, and the E5 deliverables.
