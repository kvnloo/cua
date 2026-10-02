# N-01R: native causal wait A/B on the canonical GTK3 checkbox and text tasks, 2026-10-02

Re-plan of N-01 (which hard-stopped with no evidence). Owners: kvnloo/cua#93 (R2-04 follow-up, R2-09 gate), kvnloo/cua#20 (focus/event input), kvnloo/cua#10 (accounting), kvnloo/cua#73 (canonical state).

## Result in one paragraph

On the canonical GTK3 task fixture, all 240 main trials verified against the app's own state file: 6 arms x 2 tasks x 20 Williams-balanced rounds, one fresh Driver and one fresh fixture per trial. Every route check passed and named-span coverage was 1.0. R2-04 had localized three native waits; this packet gives each one a causal verdict:

- **Cursor reveal: OWNER_DECISION.** `set_agent_cursor_motion {glide_duration_ms: 1}` saves **1418.3 ms** on the text task (CI [-1432.1, -1389.4]). It also saves **1236.5 ms** on a warm-cursor checkbox (CI [-1246.7, -1222.7]). In a fresh Driver process the checkbox click has no glide to delete: the first reveal of a process is a pulse, so that cell is NOT_MATERIAL.
- **Fixed 50 ms post-DoAction sleep: DELETED.** It saves 60.6 ms (checkbox) and 42.3 ms (text), both CIs excluding 0. The late-effect control showed 0 receipt-vs-oracle disagreements.
- **Focus-guard settle watch: IRREDUCIBLE.** Dropping it saves about 237 ms. However, with the watch gone the Driver missed **10/10** focus steals that landed 100 ms after the effect, and its receipt reported nothing. With the watch (B), 20/20 steals were restored.

The best composed arm whose gates hold is S0 for the checkbox (median T 307.9 ms, S = 1.19) and X = C+S0 for the text task (334.9 ms, S = 5.37). In both, about 72-78% of T is now the settle watch.

The untested share of T falls from about 93.5% / 98.4% before this packet to **5.8%** (checkbox) and **10.3%** (text). What remains untested is exactly one component: MCP transport of the action calls. There is no native wait worth an event wake: the only R2-09 candidate is the settle watch's 30 ms poll rounding (220 ms configured, about 241 ms observed).

Evidence classes are given per row; runtime rows are REAL (real Driver, real GTK3 app, private AT-SPI bus, isolated X11 session), with no provider (scripted task steps).

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Base | `28b915ae9ec2b1330ad3104f281e0bf4bfde2c49`: the R2-04 measurement-only phase marks on upstream main `229b65b28` |
| Tree check | `git diff --quiet 229b65b28 352507b6c -- libs/cua-driver` returns rc 0, so `libs/cua-driver` at the tested main equals upstream main `352507b6c03162ab286b21d5ed509125cc3daece`; the base differs only by the R2-04 marks |
| Measurement commit (tested source) | `b9b357bc72fe0627b841f66a2d0812fafca8711f`: exactly one commit, two env-gated, default-off knobs (see [Knobs](#the-measurement-commit)) |
| Pre-registration commit | `8ff42418df2390821d03fdd059ce5598652a77fc`, committed 05:37:49Z. The first measured trial started at 05:38:07Z (`n01r-d01`). `verify_artifacts.py` checks this order and that `PREREG.json` is unchanged |
| Driver | `cua-driver-n01r-b9b357bc7`, sha256 `c2a9978eb2b579d500a8fe4829e17fa9cfd2a19ec5d53e333e2b5582bdd3ff95`, `cua-driver 0.32.0` (read inside `cua-x11-session.sh`, `raw/build/driver-version.txt`). Built with `build-driver.sh` into `cua-release-n01r` under `flock -s` quiet + cargo-build lock (receipts in `raw/build/build-lock-receipts.jsonl`); logged `head=b9b357bc7`, 0 Fresh workspace units, 215 s. Every block's meta row records this sha256 |
| Harness origin | R2-04 packet `exp/r2-04-atspi-profile-20261001` @ `9bfd437390571985870a66d941f43dbe417f31c0`, copied verbatim to `r2-04-harness/`. Blobs: profile_atspi.py `b3cfae3b9e62`, run_in_session.sh `79683b616942`, run_batch.sh `b554d43c6f34`, analyze.py `57d834e67e12`, verify_artifacts.py `7111bb10780c` (full SHAs in `provenance.json`) |
| Live heads (gh read-only, 05:38:54Z) | upstream main `9ab9e890ac63`: 4 commits ahead of `352507b6c`, 0 files under `libs/cua-driver`. trycua/cua PR 4316 `a0bca7440` (open; not this source). kvnloo/cua#106 `c45845797b71` (packet-format reference). N-01R has no PR |
| Publication SHA | set by the Publish agent (`provenance.json: publication_sha`) |

## Environment

- **Isolation.** Every code-executing command ran as `hostless hostless-strict <cmd>`:
  - `hostless` (v2 since 05:06:31Z) scrubs the environment and applies a Landlock scope;
  - `hostless-strict` is the v1 bwrap mask of the host runtime and X11 socket dirs. See Deviations for why both were used.
- **Session.** GUI, Driver and AT-SPI work ran inside `cua-x11-session.sh`:
  - private rootless Xvfb 1920x1080, `-nolisten tcp`;
  - private dbus session, openbox + picom;
  - `env -i` scrub;
  - `CUA_SESSION_ATSPI=1` (private `at-spi-bus-launcher` + `at-spi2-registryd`).
- **Harness guards.** Before any trial, the harness refuses to run if host desktop sockets are visible or `XDG_RUNTIME_DIR` is the host's.
- **Locks.**
  - Measured blocks e01-e04 (90 trials each) ran under `bin/quiet-timed` (EXCLUSIVE quiet-lane lock, taken before the session and so before any Driver MCP session opened).
  - Controls ran under `flock -s` with at most 10 trials per acquisition.
  - All receipts are in `raw/lock-ledger.jsonl`.
- **Machine load.** The machine was shared with other lanes. Load came from processes outside the lock: the median 1-minute loadavg over main trials was 17.1 (range 13.8-20.4, 10 CPUs), against 0.76-0.95 in R2-04. MCP transport spans are therefore about 1.7x R2-04's (click MCP out 11.3 vs 6.5 ms), and tails are wider. Every comparison here is paired within a round on one source, binary and environment.
- **Displays.** The block meta rows record DISPLAY (:99, :100, :101) and show no foreign X client at block start.
- **Driver defaults** apart from the arm knobs: no permission-mode override, no approval bypass, telemetry default, fresh HOME per session, no `*-e2e` wrapper.

## STEP 0: source facts at base (class SOURCE)

| Item | Finding (file:line at `28b915ae9`, under `libs/cua-driver/rust/crates/`) |
|---|---|
| Reveal path | The click route calls `reveal_pointer_action_for(..., click_pulse=true)` at `platform-linux/src/tools/impl_.rs:6364`, between the marks `placement_done` and `reveal_done`. `set_value` calls `position_named_session_keyboard_cursor(..., Some(idx), None, true)` at `impl_.rs:8916`, which also ends in `reveal_pointer_action_for`. `overlay_glide_to_for` (`impl_.rs:5272`) awaits `overlay::animate_cursor_to_for` (`platform-linux/src/overlay.rs:644`; arrival cap 5500 ms at `overlay.rs:714`). If the cursor has no prior position it sends a `ClickPulse` and does not wait (`impl_.rs:5287`). `glide_duration_ms` governs both spans: default 0 = speed-based, clamp [0, 5000] (`cursor-overlay/src/motion.rs:47, 84-87`), set through `set_agent_cursor_motion` |
| Post-DoAction sleeps | `platform-linux/src/atspi/native.rs:3658` (`perform_action_ref`, the cached-ref route) is the site that executes on the checkbox click and on the Save note click: the phase marks `do_action_replied` and `post_sleep_done` fall inside every click. `native.rs:3535` (index re-walk fallback) has the same sleep but runs only if the cached ref fails, which the route check would mark invalid; it is unchanged. The set_value path (`atspi/mod.rs:491` -> `native.rs:5311` -> `5234` -> `5217`) has **no** post-action sleep. `native.rs:4212/4324` belong to other routes |
| Focus guard | `platform-linux/src/input/focus_guard.rs:40` SETTLE_WATCH 220 ms; `:47` SETTLE_POLL 30 ms, so a quiet watch ends after 8 polls (about 240 ms); `:52` RESTORE_BUDGET 600 ms; `:53` RESTORE_POLL 50 ms; `:55` STABLE_POLLS 3. `:597` `watch_until = started + SETTLE_WATCH`. The guard runs only for background delivery (`impl_.rs:6431` `guard_pid = (!delivery.is_foreground())...`, `impl_.rs:6440`); set_value is not guarded |
| `dwell_after_click_ms` | No Linux runtime reader. It is clamped and stored (`motion.rs:89-90`), set by the tool (`impl_.rs:12476`) or the overlay CLI (`cursor-overlay/src/lib.rs:146`) and echoed (`impl_.rs:12495, 12638`), but nothing waits on it |
| C_off excluded | Every reveal re-enables the cursor: registry `set_enabled(true)` (`impl_.rs:5310`) and overlay `SetEnabled(true)` (`impl_.rs:5277`). So `set_agent_cursor_enabled(false)` only skips the glide wait if the render thread has not yet processed the re-enable (`overlay.rs:653`). It is race-only and was excluded |
| Read once per process | `CUA_DRIVER_PHASE_TRACE_FILE` (`cua-driver-core/src/phase_trace.rs:25`) and both new knobs (OnceLock). ARRIVAL_DEGRADED latches per process (`overlay.rs:697/717`). Cursor motion is per session at runtime. Hence one fresh Driver per trial |

## The measurement commit

`b9b357bc7` (+118/-2, two files):

- `CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS` applies only at `native.rs:3658`. Unset keeps 50 ms; `0` skips the sleep.
- `CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS` replaces `SETTLE_WATCH`. Unset keeps 220 ms; `0` drops the watch, while the capture, the immediate diff and the restore loop still run.

Both knobs:
- are read once per process;
- write an `exp_knob` phase mark (`post_action_sleep_ms=0`, `focus_guard_settle_ms=0`) when set;
- treat unparsable values as unset.

Unit tests (class UNIT, inside the session under the locks, `raw/unit/unit-in-session-2.txt`):
- 4 new knob tests: unset/invalid keeps the constants 50/220 (and RESTORE_POLL 50); set uses the value;
- touched suites `platform-linux` `input::focus_guard atspi:: tools::`: **181 passed** (R2-04's 177 + the 4 new);
- `cua-driver-core` `phase_trace`: 3 passed.

## Method

- **Fixture and oracle.** `libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py`, task window. The oracle is the app's own state file, read by an independent harness thread every 2 ms. Driver receipts are logged, never the oracle.
- **Tasks.**
  - Checkbox: `get_window_state` (tree + screenshot), then the jev-use `eligible_controls` lookup of "I agree", then `click(element_token, background)`.
  - Text: the same observation, then lookup of Note and Save note, then `set_value(Note, unique value)`, then `click(Save note, background)`.
- **Forced path.** The R2-04 background element-token AT-SPI route.
- **Producer check, per trial.** `route == accessibility` on every action. The full click mark chain is present and ordered (`element_resolved ... reveal_done, ax_start, focus_guard captured, atspi_action connected/live_checked/metadata_done/do_action_replied/post_sleep_done, focus_guard body_done/restored, ax_joined`), or the set_value chain for set_value. `exp_knob` marks are present exactly for the arm's knobs, and the cursor motion and enabled state match the arm. All 528 non-stale trials passed; the 30 stale-token trials are refused before any route by design.
- **Arms.**

  | Arm | Change |
  |---|---|
  | B | defaults |
  | C | `set_agent_cursor_motion {glide_duration_ms: 1, dwell_after_click_ms: 0}`, cursor enabled |
  | S0 | sleep knob 0 |
  | F0 | settle knob 0 |
  | X | C + S0 |
  | X2 | C + S0 + F0 |

  Every arm sends `set_agent_cursor_motion` before T (B with `{}`) and records `get_agent_cursor_state`.
- **Design.** 20 rounds. Each round runs both tasks, the first task alternating by round; each task runs the 6 arms in Williams row (round mod 6). This gives n = 20 per arm per task, paired within the round.
- **Per trial.** Fresh fixture (state file published, then 1.0 s AT-SPI settle as in R2-04), fresh Driver, phase trace on, 1-minute loadavg recorded. Every trial is kept.
- **Metrics (pre-registered).**
  - T runs from the send of the first `get_window_state` to the read-end of the first oracle sample that started at or after the last action's tool return and shows the expected state.
  - T_land is the first matching sample regardless of return; T_return is the return stamp.
  - Decomposition uses contiguous boundaries. Driver marks (wall clock) are mapped onto the caller monotonic clock with the trial's median offset.
- **Statistics.** Medians, nearest-rank p95, paired within-round differences, percentile bootstrap over rounds (10000 resamples, seed 9101).
- **Supplementary blocks (pre-registered; added after the pilot, see Deviations).**
  - **W:** 20 rounds of {B, C} on the checkbox after a pre-T `set_value(Note, "")`. This changes no app state and leaves the cursor at Note, so the click glides as it would in a long-lived Driver.
  - **O:** 20 rounds per task of {X2, X2o}, where X2o is X2 with an accessibility-only task observation.
- **Commands.**
  - `make_plan.py measured plan.json`;
  - `hostless hostless-strict env N01R_LANES=<lanes> run_all.sh <wt> <driver> <sha256> plan.json <runs> <tmp> n01r [blocks]`, which runs `run_block.sh` and `n01r_harness.py` inside `cua-x11-session.sh`;
  - `package.py` (copies and scrubs raw outputs), then `analyze.py`, then `verify_artifacts.py`.

## Results

### Denominators

| Block / cell | Attempted | Valid route | Verified (oracle) | Class |
|---|---|---|---|---|
| Main, 6 arms x 2 tasks | 240 (20 per cell) | 240 | 240 | REAL |
| W warm checkbox {B, C} | 40 | 40 | 40 | REAL |
| O observation {X2, X2o} x 2 tasks | 80 | 80 | 80 | REAL |
| (a) Decoy focus steal, B/F0 x 100/20 ms x 2 tasks | 80 | 80 | 80 | REAL |
| (b) Late effect, B/S0 x 30/80 ms x 2 tasks | 80 | 80 | 80 | REAL+FIXTURE |
| (c) Stale token after fixture restart, 6 arms x 5 | 30 | 30 | 30 refused, 0 mutations | REAL |
| (d) Default-off smoke | 5 | 5 | 5 | REAL |
| Superseded attempt `n01r-a07` (orchestrator killed by its 2 h job limit mid-block) | 3 | 3 | 3 | REAL; superseded by `a07-r1` |
| Failed attempt `n01r-a01` (private Xvfb died at start, "cannot open the private DISPLAY") | 10 planned, 0 run | | | kept; re-run as `a01-r1` |

There were no failures, timeouts or unknown outcomes in any cell. All 555 planned cells verified on their latest attempt.

### Main: whole-task T per arm (medians, ms; n = 20 each; class REAL)

| Arm | Checkbox T | p95 | T_land | Text T | p95 | T_land |
|---|---|---|---|---|---|---|
| B | 365.4 | 442.1 | 65.5 | 1798.3 | 1829.3 | 1493.9 |
| C | 360.2 | 490.5 | 58.0 | 388.8 | 475.9 | 90.8 |
| S0 | 307.9 | 345.3 | 54.9 | 1753.8 | 1812.7 | 1504.9 |
| F0 | 129.5 | 219.8 | 63.9 | 1558.4 | 1733.9 | 1488.4 |
| X | 315.9 | 336.9 | 66.9 | 334.9 | 382.7 | 84.9 |
| X2 | 84.1 | 192.3 | 76.2 | 93.2 | 296.1 | 82.8 |

In every trial the effect had landed before the tool returned (T_land < T_return; `effect_visible_at_return` 240/240). Whatever B spends after T_land is the Driver's own waiting.

### Paired differences vs B (median of within-round differences, 95% bootstrap CI, ms)

| Arm | Checkbox | Text |
|---|---|---|
| C | -1.0 [-12.1, 4.5] | **-1418.3 [-1432.1, -1389.4]** |
| S0 | **-60.6 [-70.2, -46.2]** | **-42.3 [-54.2, -32.4]** |
| F0 | **-236.8 [-253.1, -228.2]** | **-236.1 [-245.0, -231.1]** |
| X | **-52.0 [-66.5, -43.3]** | **-1461.5 [-1477.4, -1445.1]** |
| X2 | **-290.4 [-294.4, -277.8]** | **-1699.0 [-1712.1, -1690.7]** |

Speedup S = median T_B / median T_arm (round bootstrap CI):

- checkbox: S_C 1.02 [0.98, 1.06], S_S0 1.19 [1.15, 1.24], S_F0 2.82 [2.68, 3.26], **S_X 1.16 [1.12, 1.22]**, **S_X2 4.34 [3.84, 5.72]**;
- text: S_C 4.63 [4.42, 4.74], S_S0 1.03 [1.02, 1.04], S_F0 1.15 [1.14, 1.16], **S_X 5.37 [5.22, 5.56]**, **S_X2 19.30 [15.49, 22.37]**.

### Component decomposition, main B (median ms; coverage 1.0 in every cell)

| Component | Checkbox B | Text B | R2-04 localization |
|---|---|---|---|
| Observation (`get_window_state` body) | 18.5 | 16.3 | 9.6-9.9 |
| MCP transport, observation (in / out) | 3.3 / 25.8 | 3.4 / 26.3 | 1.8 / 13.9 |
| Runner (caller lookup and gaps) | 0.3 | 0.3 | 0.16 |
| Resolution (registry admission + token resolve) | 2.0 | 2.1 | 1.2 + 0.0 |
| **Reveal** (click glide / set_value cursor) | **0.01** (pulse) | **1420.8** + 0.05 | 254.6-1416.4 |
| Dispatch (gates + guard capture + AT-SPI live/metadata + DoAction; set_value write + read-back) | 2.3 | 3.7 | 0.8 + 0.1 |
| **Post-DoAction sleep** | **50.8** | **51.0** | 51.1-51.3 |
| **Focus-guard settle** | **241.4** | **241.2** | 241.2-241.4 |
| MCP transport, action calls (total; in / out sub-span medians) | 15.1 (3.8 / 11.4) | 30.2 (7.5 / 21.2, two calls) | 1.8 / 6.5 per call |
| Effect lag / verification read | 0 / 0.3 | 0 / 0.3 | |

Fresh-process note: the checkbox's only click is the first reveal of its Driver process, so it pulses instead of gliding (`impl_.rs:5287`); the 254.6 ms R2-04 figure came from a long-lived process. Block W reproduces the glide: B's reveal is 1255.0 ms, from Note to I agree.

### Supplementary W: warm-cursor checkbox (n = 20 pairs; REAL)

- B T median 1611.1 ms (reveal 1255.0 ms), C 374.0 ms (reveal 8.3 ms).
- Paired C-B **-1236.5 ms [-1246.7, -1222.7]**, S = 4.31 [4.20, 4.43].

### Supplementary O: observation modality inside the composed arm (n = 20 pairs per task; REAL)

- X2o-X2 paired T: checkbox -4.0 ms [-10.4, 10.7], text -11.1 ms [-20.3, 3.5]. Both CIs include 0.
- Work removed inside the observation body: 4.4 ms (checkbox) and 5.2 ms (text). The observation's MCP transport did not shrink (it was 24-27 ms out in both arms). So the observation transport is not the screenshot payload, and the screenshot is **not material** at T level here.

### Controls (REAL; shared lock, at most 10 trials per acquisition)

**(a) Decoy focus steal.**

A pre-mapped harness X window activates itself 100 ms or 20 ms after the app's state changes. The oracle is an independent 2 ms X focus sampler (`XGetInputFocus` + `_NET_ACTIVE_WINDOW`). Results, 10 trials per cell:

| Task / delay | B restored | B receipt | F0 restored | F0 missed | F0 receipt | Steal timing |
|---|---|---|---|---|---|---|
| checkbox / 100 ms | 10 | `focus_outcome=restored` 10/10 | 0 | **10** | none reported 10/10 (disagrees with oracle) | B: inside the guard window 10/10; F0: after tool return 10/10 |
| checkbox / 20 ms | 10 | restored | 10 | 0 | restored | before `body_done` 10/10, so the immediate check catches it |
| text / 100 ms | 10 | restored | 0 | **10** | none reported 10/10 | as checkbox |
| text / 20 ms | 10 | restored | 10 | 0 | restored | as checkbox |

Two further results:

- **Main arms.** Focus (focus, active) was unchanged across every main, W and O trial (360/360).
- **Sampler cadence.** The focus sampler's worst gap was 18.0 ms. Every steal stayed visible to the sampler until the final state.

**(b) Late effect.**

`fixture_late.py` (test-fixture code; the Driver is unchanged) applies the app state 30 ms or 80 ms after the GTK signal. Measured median delay: 46-49 ms for the checkbox at 30 ms (GLib timer under load) and 30.5 ms for text at 30 ms; 80.6-82.8 ms at 80 ms.

- **Disagreements.** Success claims before the oracle changed: 0. False failures: 0. This holds for B and for S0 in all 8 cells.
- **Why that is structural.** The AT-SPI click receipt is `effect: unverifiable` and never claims success, so a disagreement of this kind cannot occur.
- **Effect visible at the first sample after return.** B 40/40; S0 39/40. In the one exception (checkbox, 80 ms) the GLib timer slipped to 243 ms, which is longer than the 240 ms settle that remains in S0; the effect landed 5.1 ms after return.

What protects a late effect from being observed after return is the settle watch, not the 50 ms sleep: in S0 the effect still landed a median 168-219 ms before return.

**(c) Stale token after fixture restart.**

The protocol: observe fixture A, terminate it, start a fresh fixture B, then click B's pid and window with A's token.

- Refused 30/30, `status: refused`, `refusal.code: stale_element_token`.
- 0 mutations of B, and 0 `do_action_replied` marks after the restart. The Driver expresses `effect=refused` as status `refused` with no `effect` field.

**(d) Default-off smoke** (knobs unset, 5 trials):

- no `CUA_DRIVER_EXP_*` in the Driver environment and no `exp_knob` marks;
- post-action sleep 50.7-51.5 ms and settle 240.9-242.1 ms, i.e. the constants 50/220 (+30 ms poll rounding);
- 5/5 verified.

### Receipt-vs-oracle and invariants (E4), every arm

- 0 stale-ref dispatches (control c).
- 0 duplicate mutations: the final sampled state has seq exactly before+1 in all 555 latest-attempt cells.
- 0 unverified successes: T always ends on the independent oracle, and click receipts are `unverifiable`.
- 0 authority from passive state or event absence: phase marks and the focus sampler are measurement only.
- No replay of a possibly landed effect.
- Refusals are refused (control c), and the controls discriminate: F0 vs B at 100 ms is 10/10 vs 0/10 missed.

## Pre-registered gates

| Gate | Result | Verdict |
|---|---|---|
| Validity | 20/20 valid and verified in every arm and task; identical verified outcomes | holds |
| Coverage | median 1.0 (min 1.0) in every main cell | holds |
| H_C checkbox (fresh process) | B reveal 0.013 ms (< 5% of T and < 50 ms); C-B -1.0 [-12.1, 4.5] | **NOT_MATERIAL** |
| H_C checkbox warm (supplementary W) | saving 1236.5 ms >= 0.5 x 1255.0; CI excludes 0 | **OWNER_DECISION** |
| H_C text | saving 1418.3 ms >= 0.5 x 1421.1; CI excludes 0 | **OWNER_DECISION** (feedback default change, consistent with browser H_V) |
| H_S checkbox / text | savings 60.6 / 42.3 ms, both >= 25 ms with CIs excluding 0; late control adds 0 disagreements | **DELETED** / **DELETED** (KEEP; a default change goes to a reviewed fix candidate) |
| H_F checkbox / text | savings 236.8 / 236.1 ms, CIs exclude 0; B restored 10/10 in both variants; F0 missed 10/10 at 100 ms | **IRREDUCIBLE** / **IRREDUCIBLE** (background non-invasiveness contract) |
| Composition | F0 and X2 excluded (H_F IRREDUCIBLE). Eligible: B, C, S0, X. Best: checkbox **S0** 307.9 ms, text **X** 334.9 ms | S_X 1.16 / 5.37; S_X2 4.34 / 19.30 (X2 not eligible) |

For R2-10, the native composed arm is X = C+S0. On the fresh-process checkbox, C adds nothing measurable: X 315.9 vs S0 307.9 ms medians, within paired noise. On a warm cursor, C deletes the glide (block W).

## E2: critical path of the best composed arm

Median per-trial share of T. Verdicts are from this packet unless noted.

| Component | Checkbox S0 (T 307.9 ms) | Text X (T 334.9 ms) | Verdict |
|---|---|---|---|
| Focus-guard settle | 241.1 ms, 78.2% | 241.1 ms, 71.7% | IRREDUCIBLE (H_F + decoy control) |
| MCP transport, observation | 28.4 ms, 9.2% | 27.3 ms, 8.0% | IRREDUCIBLE by invariant (a fresh observation binds the token); screenshot not material (O) |
| Observation body | 16.9 ms, 5.5% | 16.9 ms, 5.2% | IRREDUCIBLE by invariant; screenshot delta 4.4-5.2 ms not material at T level (O) |
| **MCP transport, action calls** | **15.5 ms, 5.05%** | **32.2 ms, 9.55%** | **untested (no verdict)** |
| Reveal | 0.01 ms (fresh pulse) | 10.6 ms, 3.0% | OWNER_DECISION (H_C, H_C warm) |
| Dispatch | 1.7 ms, 0.5% | 4.2 ms, 1.3% | IRREDUCIBLE (effect producer, liveness check, set_value read-back; SOURCE) |
| Resolution | 2.0 ms, 0.6% | 2.1 ms, 0.7% | untested |
| Runner, result | 0.3 ms, 0.1% | 0.5 ms, 0.1% | untested |
| Verification read | 0.5 ms, 0.2% | 0.4 ms, 0.1% | IRREDUCIBLE (independent confirmation read, E4) |
| Post-DoAction sleep | 0.01 ms | 0.01 ms | DELETED (H_S) |
| Effect lag | 0 | 0 | ZERO (lands before return) |

**Untested share** (pre-registered: components without a verdict, plus unattributed time, over T): **5.8%** checkbox and **10.3%** text.

That is down from about 93.5% and 98.4%: the three waits, together about 292 ms of checkbox T and about 1713 ms of text T in B, now all have verdicts. The only component above the 5% / 50 ms threshold without a verdict is **MCP transport of the action calls**:

- click: caller send to registry `dispatch_enter`, 3.1-3.6 ms; registry `dispatch_exit` to caller receipt, 11.3-12.4 ms;
- set_value: 4.5 / 10.8 ms;
- what this covers: Driver post-dispatch result handling, JSON-RPC serialization, stdio and the Python MCP client;
- R2-04 measured 1.8 / 6.5 ms per call for the same span at loadavg about 0.9;
- no arm in this packet tests deleting it.

A conservative reading also counts the observation transport as untested, since the invariant requires that an observation reach the caller, not that its transport be minimal. Under that reading the shares are about 15% (checkbox) and about 18% (text): the sums of the two median shares.

## R2-09 gate

H_S is DELETED with no receipt degradation in both tasks. One fixed native wait of at least 5% of T remains in the best composed arm, the **focus-guard settle watch**, and it is IRREDUCIBLE. The pre-registered rule therefore names it for R2-09.

Exact wait: `focus_guard.rs:40` `SETTLE_WATCH` 220 ms, polled every 30 ms (`:47`), observed as 241.1 ms. The configured window is the safety net (H_F) and cannot be ended early by an event wake: under E4, event absence never mints authority, so a quiet window must still run its full 220 ms.

The only part an event wake could touch is the poll rounding, from 220 ms configured to about 241 ms observed. Waking on the X focus/`_NET_ACTIVE_WINDOW` change instead of polling would save at most about 21 ms per guarded action, about 6-7% of T in the best composed arm. That figure is SOURCE arithmetic from this packet's spans, not measured.

R2-09 input: no native wait is worth an event wake beyond that bounded ~21 ms poll-rounding candidate. The 50 ms post-DoAction sleep is DELETED, not event-replaceable.

## Work deleted vs wall-clock saved

| Arm | Work deleted (median paired component, ms) | Wall-clock saved (paired median T, ms) |
|---|---|---|
| S0 | post-DoAction sleep 50.8 (checkbox), 51.0 (text) | 60.6 [46.2, 70.2] / 42.3 [32.4, 54.2] |
| C | awaited glide 0.0 (checkbox, fresh pulse) / 1409.0 (text); warm checkbox 1255.0 to 8.3 | 1.0 (n.s.) / 1418.3; warm 1236.5 |
| F0 | settle 240.8 (safety net removed; not eligible) | 236.8 / 236.1 |
| X | sleep 50.8 + glide 0 / 51.0 + 1409.7 | 52.0 / 1461.5 |
| X2 | sleep + glide + settle (not eligible) | 290.4 / 1699.0 |

## Evidence classes by row

| Row | Class |
|---|---|
| Main, W, O trials: T, decomposition, paired stats, gates | REAL (BENCHMARK-style paired timing, no provider) |
| Decoy, stale-token, default-off smoke controls | REAL |
| Late-effect control (fixture-side delay) | REAL+FIXTURE |
| Knob unit tests and touched suites | UNIT |
| STEP 0 file:line facts; R2-09 poll-rounding estimate; dispatch IRREDUCIBLE rationale | SOURCE |
| Provider decisions | NOT_RUN (TypeSafe cap 0: 0 attempts, 0 reached; the harness refused 0 non-loopback connects in every block) |
| Wayland, macOS, Windows | NOT_RUN |
| Deleting action-call MCP transport | NOT_RUN (named untested) |

## Deviations

1. **Host-shell Python edit (near-miss, no effect).** One text edit of `n01r_harness.py` ran `python3` in the plain host shell. It was pure file I/O: no GUI import, no display or bus contact, and no Driver or fixture. That breaks the "all Python under hostless" rule without effect, so it is logged as a near-miss. All later edits used the editor tool.
2. **hostless replaced mid-lane.** The shared `bin/hostless` was replaced at 05:06:31Z by v2 (env scrub + Landlock, no mount mask) by another track.
   - Pilots p01-p05 ran under v1.
   - One pilot attempt (`n01r-pilot2-p06`) ran under v2. The harness refused on visible host sockets before any fixture or Driver started, and the private Xvfb created its socket in the host `/tmp/.X11-unix` (no host display contact).
   - From then on every command ran as `hostless hostless-strict` (v2 plus the v1 mask), the pilots' environment.
3. **Supplementary blocks added after the pilot.** W and O were added after the pilot showed that the fresh-process checkbox reveal is a pulse, and that observation and MCP transport dominate once the waits are gone. Both were pre-registered before any measured trial and are labelled supplementary. The six-arm design, gates and controls are the spec's.
4. **Plan regrouped.** The plan was regrouped into 4 exclusive acquisitions (90 trials each) because the exclusive lock was heavily contended. A queued pilot was stopped by this lane before it acquired the lock, and an orphaned `flock` waiter it left was removed (both this lane's own processes).
5. **Interrupted block.** The orchestrating job hit its 2 h background limit during control block `a07`, after 3 trials. That shared acquisition has no release receipt (`verify_artifacts.py` reports it as open). The 3 trials are kept as superseded, and the block was re-run as `a07-r1`.
6. **Xvfb start failure.** Control block `a01`'s private Xvfb died at start: "cannot open the private DISPLAY", most likely a display-number collision with another lane. Its 10 planned cells are kept as not run (`failed_block_attempts`), and the block was re-run as `a01-r1`.
7. **Unit script parameterized.** `unit_in_session.sh` was parameterized (no local paths) after its first run and re-run with identical commands. Both logs are in `raw/unit/`, and both show 4 + 181 + 3 passed.
8. **Lock modes.** The default-off smoke `d01` ran under the shared lock as a control. The `e` blocks ran under the exclusive lock.
9. **Focus receipt source.** The flat `focus_*` receipt fields are reduced away by the public action contract, so the Driver's focus outcome is taken from the click result text (`focus_outcome=...`).
10. **Raw scrubbing.** Raw outputs are copied into `raw/` by `package.py`, which replaces local path prefixes and the host name with tokens (`<tmp>`, `<lanes>`, `<systmp>`, ...). No numeric field changes, and `analyze.py` reproduces the summary from the scrubbed raw.

## Limits

- **Load.** The machine was heavily loaded by other lanes (loadavg about 17). Absolute MCP and observation spans are about 1.7x R2-04's, and X2 tails are wide (p95 192-296 ms). The paired within-round design controls for this, but absolute numbers are not a quiet-machine benchmark.
- **Fresh processes.** One fresh Driver per trial means the checkbox measures the cold (pulse) reveal. A long-lived agent session glides, which block W measures.
- **Oracle cadence.** The oracle sampler is nominally 2 ms. Under load the per-trial worst gap had a median of 3.2 ms, with a worst of 12.1 ms; it enters T only through the verification read (median 0.4-1.0 ms).
- **Receipt truth for S0 is weak evidence.** Click receipts never claim success (`unverifiable`), so "no receipt degradation" is structural. The operational effect of removing the sleep is shown by the oracle timing instead: effect visible at return 39/40 vs 40/40, the one miss being a 243 ms GLib slip.
- **The decoy is a synthetic stealer.** It is a separate client using an EWMH source-2 request. Real steals (a target dialog mapped late, a WM policy) may differ in timing and attribution.
- **Scope.** One fixture window (9 elements); X11 (Xvfb, openbox, picom) only.

## Claim boundary

On the canonical GTK3 fixture task window, in X11 Xvfb/openbox/picom with a private AT-SPI bus, with Driver 0.32.0 at base `28b915ae9` plus the measurement knobs `b9b357bc7`, with scripted task steps (no provider) and a fresh Driver per trial:

- the cursor reveal is deletable by a feedback setting (OWNER_DECISION);
- the 50 ms post-DoAction sleep is deletable without receipt degradation (DELETED);
- the focus-guard settle watch is required by the background non-invasiveness contract (IRREDUCIBLE).

Not Wayland, macOS or Windows. No default change: the knobs are measurement-only and default-off, and dropping the sleep by default would be a separately reviewed fix.

## Disposition

**N-01R: KEEP (terminal for N-01).**

- H_C OWNER_DECISION (text; warm checkbox), NOT_MATERIAL on the fresh-process checkbox.
- H_S DELETED (both tasks).
- H_F IRREDUCIBLE (both tasks).
- Native composed arm for R2-10: X = C+S0, with S_X 1.16 [1.12, 1.22] on the checkbox and 5.37 [5.22, 5.56] on text.
- E2 untested share: 5.8% / 10.3%. The remainder is named: action-call MCP transport.
- R2-09: the only remaining fixed native wait is the IRREDUCIBLE settle watch. An event wake could at most replace its ~21 ms poll rounding.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | Pre-registration, committed before the first measured trial |
| `plan.json`, `make_plan.py` | The deterministic trial plan |
| `n01r_harness.py`, `xprobe.py`, `fixture_late.py`, `run_block.sh`, `run_all.sh`, `unit_in_session.sh` | Harness, X focus sampler and decoy, late-effect fixture wrapper, orchestration |
| `r2-04-harness/` | The R2-04 harness, verbatim (origin blobs above) |
| `package.py` | Raw copy and scrub |
| `analyze.py` | Recomputes `n01r-summary.json` and `n01r-trial-metrics.jsonl.gz` from `raw/` |
| `verify_artifacts.py` | Recompute check, lock ledger, PREREG order, default-off smoke, stale control, README numbers, privacy |
| `provenance.json` | Every SHA, binary, build and environment fact |
| `raw/n01r-<block>[-rN]/trials.jsonl.gz`, `session.txt` | One ledger per block attempt: meta, every trial (caller stamps, oracle samples, marks, receipts, focus samples), end |
| `raw/lock-ledger.jsonl` | quiet-timed (exclusive) and shared-lock receipts for every packaged label |
| `raw/unit/`, `raw/build/` | Unit logs, build output, build lock receipts, Driver version |
