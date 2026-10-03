# R2-04: AT-SPI phase and D-Bus RPC profile of the locally built Driver (GTK3 fixture), 2026-10-01

## Result in one paragraph

On the canonical GTK3 fixture, the locally built main Driver spends almost none of its native action time in AT-SPI. All 240 measured action trials verified against the app's own state file (120 per arm, 40 per action type per arm). A click on the AT-SPI path sends **5** D-Bus RPCs to the app, with about 0.2-0.3 ms of bus time. A full tree acquisition sends **145** RPCs with about 3 ms of bus time. The fixture's task window is small: the Driver emits 9 elements per observation (and queries 16 app-side AT-SPI objects), so that is about 16 RPCs and 0.32 ms of bus time per emitted element. All AT-SPI conclusions below are scoped to a tree of this size.

The rest of each tool call goes to three named spans inside the Driver, none of them AT-SPI work:

- **the agent-cursor reveal before dispatch**: 254.6-1416.4 ms, depending on where the cursor was;
- **a fixed 50 ms sleep after `DoAction`**;
- **the focus guard's settle watch**: about 241 ms.

The target app has already changed state about **299 ms before the click returns**.

Discovery and property RPCs take at most **0.5%** of observe+act time (gate D = 0.005, against a 0.5 threshold), so the pre-registered bulk/cache arm (Cache.GetItems / Collection) did **not** run.

Dispositions:

- H_A (bulk/cache is the next tactic): **KILL** for this 9-element fixture and this route only. Large-tree apps were not tested (BULK `NOT_RUN`), and #93 keeps Cache/Collection as a conditional tactic for them.
- H_B (localization): **KEEP**.
- R2-04 overall: **REVISE**. On this fixture, the next experiment is a causal A/B on the cursor reveal, the post-dispatch sleep and the settle watch. This packet does not claim any wall-clock saving.

Evidence classes are listed per row in [Evidence classes by row](#evidence-classes-by-row). The runtime rows are **REAL** (real Driver, real GTK3 app, real private AT-SPI bus, inside an isolated X11 session). They are not a provider or cloud-service benchmark.

## Scope, owners and boundary

- Owners: kvnloo/cua#93 `R2-04`, original `E2`; #20 consumes it for invalidation; reported to #10.
- The question #93 asked: separately profile tree acquisition, target lookup, action metadata, `DoAction`, target mutation and verification, with D-Bus RPC counts and wrapper time. Compare bulk interfaces only if discovery dominates.
- #106's Mousepad cloud-service numbers (1024.5 / 1307 ms) are **not** compared with, or attributed to, anything here.
- No new service, store, verifier or batch API. The instrumentation is measurement-only, env-gated and off by default. Events are used only as timing hints; the app's state file is the oracle.

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Tested source (arm M) | `229b65b2849c3a595ddbc85200d7181b18bd2e47`, trycua/cua main as pinned by the R2 setup |
| Live upstream main at execution (gh, 22:20Z) | `effd9b298942d7e9808077adef4ef575d561141d`: 1 commit ahead and changes only `release-please-config.json`. **Not certified** by this packet |
| Live upstream main at revision (gh, 23:00Z) | `021b87ddf0faa0853ba7417303b05a283ca3b491`: 3 commits ahead of the tested source; release, docs and `libs/cua-spacesd` files only, no `libs/cua-driver` file (gh compare). **Not certified**; the orchestrator re-reads at publication |
| Pre-registration commit | `1280a9e5eba7e8804a6bcc9c12f7228636f4150b`; `PREREG.json` sha256 `ff0b076be39f2c0b82e07309bf393228756b77b96b48e89a85042f303ebfefeb` |
| Instrumentation commit (arm P source) | `28b915ae9ec2b1330ad3104f281e0bf4bfde2c49` (parent 1280a9e5e, base 229b65b28) |
| Driver M | sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `cua-driver 0.32.0`, unmodified |
| Driver P | sha256 `940eb2c2da4a92c450ad887be6ffac95d88ead4395df11103ef76b4f16bc161a`, `cua-driver 0.32.0`. Built with `build-driver.sh` into the lane-private target dir `cua-release-r2-04` under the cargo lock. Logged `head=28b915ae9...`, 0 Fresh units |
| R2-04 PR | none |
| Publication SHA | set by the orchestrator after publication (`provenance.json: publication_sha`) |

## Environment

- Every Driver, GTK, dbus-monitor and MCP process ran inside `cua-x11-session.sh`:
  - private rootless Xvfb 1920x1080, private dbus session, openbox + picom;
  - `env -i` scrub, so no Wayland, Hyprland or host runtime dir;
  - `CUA_SESSION_ATSPI=1` with `CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1"`, giving a private `at-spi-bus-launcher` + `at-spi2-registryd`.
- Software: at-spi2-core 2.60.6, dbus 1.16.2, GTK 3.24.52 (system python3 3.14.7 + PyGObject 3.56.3), Linux 7.2.2, 10 CPUs.
- Driver defaults throughout: no permission-mode override, no approval bypass, telemetry at its default with a fresh HOME per session, no `*-e2e` wrapper.
- Every timed session ran while holding `<tmp>/locks/quiet-lane.lock`. Loadavg was recorded per trial; median 1-minute loadavg per arm and type was 0.76-0.95.

## Method

**Fixture.** `libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py` in its opt-in task window (`CUA_GTK3_TASK_STATE`). On every change, the app atomically rewrites its own JSON file (`seq`, `agreed`, `counter`, `note_saved`).

**Action types.** Each trial is one fresh observation followed by the action:

| Type | Steps | Verified when |
|---|---|---|
| checkbox | `get_window_state` (tree + screenshot), then the jev-use `eligible_controls` lookup of "I agree", then `click(element_token, delivery_mode=background)` | `agreed` flipped and `seq` incremented by 1 |
| button | the same, targeting "Increment" | `counter` incremented by 1 and `seq` by 1 |
| text | the same observation, then lookup of "Note" and "Save note", then `set_value(token, unique value)`, then `click(Save note)` | `note_saved` equals the value and `seq` incremented by 1 |

**Forced path.** The background element-token AT-SPI route.

**Actual route.**
- Every action reported `route: accessibility`.
- Every monitored trial shows the Driver connection calling `Action.DoAction` (and `EditableText.SetTextContents` for text) on the fixture's bus name inside the call window.
- In arm P, the `atspi_action` marks fall inside each click.

**Independent oracle.** The app's own state file. A fresh Driver observation after each action is recorded only as a cross-layer agreement check:
- checkbox: the observation's checked state matched the file in 80/80 trials;
- text: the Note value matched in 80/80 trials;
- button: no check, because the counter label is not an eligible control.

**Measurement layers.**
1. **Caller spans** (all trials): back-to-back monotonic and wall-clock stamps around each MCP call, the lookup, the mutation wait, the oracle read and the verification observation.
2. **D-Bus RPCs** (half the rounds, in an ABBA pattern): a `dbus-monitor --monitor` on the private AT-SPI bus for the duration of each trial. Method calls are paired with their replies and attributed to phases by wall-clock window.
3. **Driver-internal phases** (arm P only): the env-gated `CUA_DRIVER_PHASE_TRACE_FILE` marks at:
   - the registry dispatch boundary;
   - the Linux element-click AX route (resolved, placement, cursor reveal, AX start, joined);
   - `focus_guard::guarded` (captured, body done, restored);
   - `perform_action_ref` (connected, live check, metadata, DoAction replied, post-sleep);
   - `set_value` (resolved, cursor, write, readback).

   When the variable is unset, `mark()` reads a `OnceLock` and returns: no file and no behaviour change. Unit tests cover this, and a marks-off smoke run (`raw/controls/`) recorded no marks and verified 13/13 trials.

**Design and interleaving (pre-registered).**
- 8 isolated sessions in the order M,P,P,M,P,M,M,P, with 10 rounds each.
- The action order rotates every round, and the monitor follows an on/off/off/on pattern.
- Per arm and type: 40 measured trials, 20 of them monitored.
- Each session also ran 6 warm-up trials (kept, reported separately) and 4 stale-token negative controls.
- Commands: `run_batch.sh` (sessions), `run_in_session.sh` + `profile_atspi.py` (harness), `analyze.py`, then `verify_artifacts.py`.

## Results

### Denominators

| Arm / type | Attempted | Verified (oracle) | Monitored | Class |
|---|---|---|---|---|
| M / checkbox | 40 | 40 | 20 | REAL |
| M / button | 40 | 40 | 20 | REAL |
| M / text | 40 | 40 | 20 | REAL |
| P / checkbox | 40 | 40 | 20 | REAL |
| P / button | 40 | 40 | 20 | REAL |
| P / text | 40 | 40 | 20 | REAL |
| Warm-up (all sessions) | 48 | 48 | 24 | REAL (excluded from steady state) |
| Stale-token negatives | 32 (16 per arm) | 32 passed | 32 | REAL |

There were no failures, timeouts or unknown outcomes, so every latency median below uses the full denominator.

### Caller view: one observe + act + verify cycle (medians in ms, arm M / arm P)

| Phase | checkbox | button | text |
|---|---|---|---|
| Tree acquisition (`get_window_state` wrapper) | 26.0 / 25.9 | 25.9 / 25.7 | 26.0 / 26.0 |
| Driver-reported AT-SPI walk (`walk_elapsed_ms`) | 5 / 5 | 5 / 5 | 5 / 5 |
| Target lookup (jev-use parser, caller) | 0.16 / 0.16 | 0.16 / 0.16 | 0.16 / 0.16 |
| Action tool call(s) | 559.3 / 558.1 | 686.1 / 686.4 | 3018.6 / 3019.4 (set_value 1300.1 + Save click 1719.9, arm M) |
| Mutation wait after the call returns | 0.05 | 0.05 | 0.05 |
| Independent oracle read | 0.02 | 0.02 | 0.02 |
| Trial start to verified outcome | 585.2 / 583.9 | 711.7 / 711.6 | 3046.2 / 3045.8 |
| Fresh verification observation | 26.3 / 26.2 | 25.9 / 26.1 | 26.4 / 26.1 |

The mutation wait is effectively zero: **the target has always changed before the tool call returns**.

The checkbox p95 (1690.8 ms) is not tail noise. The cursor reveal depends on the previous target (see the reveal table below).

### D-Bus RPCs per phase (arm M monitored, n = 20 per type; arm P agrees)

**Tree acquisition: 145 RPCs, about 2.9 ms bus busy time, inside a roughly 26 ms call.**

| Method | Calls per tree acquisition |
|---|---|
| `Properties.Get` | 50 |
| `Accessible.GetInterfaces` | 35 |
| `Accessible.GetRoleName` | 16 |
| `Accessible.GetState` | 15 |
| `Component.GetExtents` | 10 |
| `Action.GetName` | 9 |
| `Accessible.GetChildren` | 7 (one to the registry) |
| `Text.GetText` | 2 |
| `GetConnectionUnixProcessID` | 1 |

**Click (checkbox, button, Save note): 5 RPCs, about 0.2-0.3 ms bus busy time.**
- The calls are `GetRoleName` (liveness), `GetInterfaces`, `Properties.Get(NActions)`, `Action.GetName(0)` and `Action.DoAction(0)`.
- The Driver reads action names one by one, not through `Action.GetActions`. At 1 action per control, that costs one RPC.

**set_value: 12 RPCs, about 0.7-0.8 ms.** The calls are liveness, 4 `GetInterfaces`, `SetTextContents`, the Action name probe, a `DoAction("activate")` commit on the entry, and the read-back `Text.GetText`.

**Bus share of the action-call time:** median 0.0 (below 0.1%).

**Tree size (supplementary, added after verification review).** The GTK3 task window is small: **9 elements** (`nodes_visited` = `element_count` = 9 in all 288 observed trials, measured and warm-up, both arms). During each tree acquisition the Driver queried 16 distinct app-side AT-SPI objects (7 more than it emits: objects it reads but does not return as elements), plus one registry `GetChildren` and one `GetConnectionUnixProcessID`. The tree acquisition therefore costs about **16.1 RPCs and 0.32 ms of bus time per emitted element** (arm M, n = 60 monitored trials; arm P about 0.34 ms), inside a Driver-reported walk of 5 ms (median).

A linear extrapolation, **not a measurement**, puts discovery traffic at roughly 16,000 RPCs and about 320 ms of bus time per observation for a tree of about 1000 elements. Whether it is linear, and whether gate D would then approach 0.5, is untested: no large-tree app ran, and the BULK arm is `NOT_RUN`.

**Gate D** (discovery and property bus time over tree + action wrapper time): checkbox 0.005, button 0.004, text 0.001. The maximum is 0.005, below the 0.5 threshold, so **G_bulk did not fire** and the BULK arm is `NOT_RUN` by the pre-registered rule.

**Timing of the effect, measured on the bus:**
- From the start of the click call to `DoAction`: 251.9 ms (checkbox), 378.6 ms (button), 1420.5 ms (Save click). This is the cursor reveal.
- From `DoAction` to the first signal the app emits (`StateChanged:checked`, `TextChanged`, `BoundsChanged`): 0.1-0.5 ms.
- From the mutating reply to the caller receiving the tool result: **299 ms**, for every type and both arms.

### Driver-internal phases (arm P, n = 40 per type, all 40 with every mark present; medians in ms)

| Span | checkbox click | button click | Save-note click | set_value |
|---|---|---|---|---|
| MCP in (caller send to dispatch enter) | 1.8 | 1.9 | 2.1 | 1.8 |
| Registry admission (dispatch to tool invoke) | 1.2 | 1.2 | 1.2 | 0.0 |
| Token resolve + placement (cached frame) | 0.0 | 0.0 | 0.1 | n/a |
| **Agent-cursor reveal / keyboard-cursor positioning** | **254.6** | **382.9** | **1416.4** | **1288.4** |
| Focus-guard capture + AT-SPI live check + metadata | 0.8 | 0.8 | 0.7 | n/a |
| `DoAction` round trip / AT-SPI write + read-back | 0.1 | 0.1 | 0.1 | 1.3 + 0.4 |
| **Fixed post-`DoAction` sleep** (`perform_action_ref`, 50 ms) | **51.3** | **51.1** | **51.1** | n/a |
| **Focus-guard restore** (220 ms settle watch + checks) | **241.3** | **241.4** | **241.2** | n/a |
| Result shaping + post-dispatch | 0.0 | 0.0 | 0.0 | 0.0 |
| MCP out (dispatch exit to caller receive) | 6.5 | 6.5 | 6.5 | 6.5 |

The coverage of the tool call by named spans plus MCP in and out is a median of 1.0 for every call. The marks are contiguous, so this is true by construction: the substance is the breakdown, not the coverage figure.

Inside `get_window_state`, the tool body takes 9.6-9.9 ms (of which the AT-SPI walk is 5 ms), and MCP out takes 13.9 ms because the screenshot payload is in the response.

Median per-trial shares of the action time (supplementary, not pre-registered):

| Share | checkbox | button | text |
|---|---|---|---|
| Cursor visual | 45.5% | 55.8% | 89.6% |
| Fixed post-dispatch waits | 52.5% | 42.6% | 9.7% |
| AT-SPI RPC phases | 0.1% | 0.1% | 0.1% |
| MCP transport | 1.5% | 1.2% | 0.6% |

**Cursor reveal by transition (arm P, median ms):**

| Transition | Median reveal | n |
|---|---|---|
| Save note to I agree | 252.8 | 28 |
| I agree to Increment | 381.6 | 28 |
| Save note to Increment | 600.7 | 12 |
| Increment to I agree | 1384.6 | 12 |
| Note to Save note | 1416.4 | 40 |

The first click of every session took about 302-305 ms, because there was no prior cursor position, so the Driver pulses instead of gliding.

### Gates (pre-registered)

| Gate | Result |
|---|---|
| G_validity | Holds: 100% verified for every arm and type; 32/32 stale negatives refused (`stale_element_token`) with **0** `DoAction` on the bus and no app mutation |
| G_distortion | Holds: no comparison beyond ±15%. P vs M action medians differ by -2.2 to +8.3 ms (at most 0.4%). Monitor on vs off differs by -10.1 to +0.9 ms (at most 1.8%) on action calls and +0.9 to +1.3 ms (about 4-5%) on tree acquisition. Stratified by previous target (supplementary), P vs M stays within ±3.3 ms and every 95% CI includes 0 |
| G_coverage | Holds: median 1.0 for every call, contiguous by construction. The largest named span is the cursor reveal (clicks) and keyboard-cursor positioning (set_value) |
| G_bulk | Does not fire: max D = 0.005 against 0.5, **on a 9-element tree**. With about 0.32 ms of discovery bus time per element, D cannot approach 0.5 on a tree this small; the gate says nothing about large trees |

## Evidence classes by row

| Row | Class |
|---|---|
| Denominators, caller spans, oracle verification (240 measured + 48 warm-up trials) | REAL |
| D-Bus RPC counts and bus times per phase (dbus-monitor on the private AT-SPI bus) | REAL |
| Driver-internal phase spans (arm P, measurement-only instrumented build) | REAL |
| Effect timing on the bus (dispatch to `DoAction`, `DoAction` to app signal, landed to return) | REAL |
| Stale-token negatives (32) and the marks-off smoke run (13 trials) | REAL |
| Distortion gates (P vs M, monitor on vs off) | REAL |
| Tree size and per-element cost (supplementary) | REAL |
| Large-tree discovery cost (linear extrapolation) | NOT_RUN (illustrative arithmetic only) |
| BULK arm (Cache.GetItems / Collection) | NOT_RUN (pre-registered gate did not fire) |
| Fallback route (keyboard / pointer) | NOT_RUN |
| Unit tests (`cua-driver-core`, `platform-linux`) | UNIT |
| Instrumentation default-off and no-new-service review (`instrumentation.diff`) | SOURCE |
| Provider / cloud-service latency | NOT_RUN (out of scope; #106's Mousepad numbers are not compared) |

## Work deleted vs wall-clock saved

- **Work deleted: none.** This is a profile, and no Driver behaviour was changed in any arm.
- **Wall-clock saved: none claimed.**
- Candidate waits for a later causal A/B, named here and not claimed:
  - the cursor reveal (about 250-1420 ms before dispatch);
  - the 50 ms post-`DoAction` sleep;
  - the focus-guard settle watch (about 241 ms after the effect has landed).

  Each of these is a safety or UX mechanism: visible agent cursor, toolkit settle, and focus-steal restoration. Removing one requires an intervention arm with the same oracle and focus-steal negatives.

## Negative and fallback controls

- **Stale token:** a token from a replaced snapshot was refused with `stale_element_token`, `effect: none`, in 32/32 trials. The monitor saw no `DoAction` on the bus, and the app `seq` was unchanged. In arm P the marks show the call ended before the AT-SPI route.
- **Monitor perturbation:** ABBA on/off within each arm. Within ±15%; the on/off differences are reported above.
- **Instrumentation perturbation:** arm P vs arm M, interleaved at the session level. Within ±15%; the medians agree to within 0.4%.
- **Instrumentation default-off:** source (a `OnceLock` read, then return), the unit tests `unset_or_empty_env_opens_no_sink` and `unwritable_path_opens_no_sink`, and the marks-off smoke run of the P binary (`raw/controls/smoke-P-marks-off`: no marks, 13/13 verified). The smoke run is a correctness check, not a timing claim.
- **Fallback route: `NOT_RUN`.** Every forced call took the AT-SPI route, and no keyboard or pointer fallback ran (the structured route was `accessibility` in every trial).

## Unit and source checks

These are the suites touched by the change, run as lib unit tests in the lane-private target dir under the cargo lock (class UNIT). All passed:

- `cua-driver-core` `tool::` + `phase_trace`: 77 tests, including the 3 `phase_trace` tests;
- `platform-linux` `input::focus_guard` + `atspi::` + `tools::`: 177 tests.

The authoritative run is `raw/unit/in-session-tests.txt`, run inside `cua-x11-session.sh`. `verify_artifacts.py` checks that it is present and that it records 77 and 177 passed with rc 0.

Disclosure: an earlier run of the same filters (`raw/unit/host-shell-*.txt`, also all passing) ran in the worker's host shell, which had host display variables set, before I noticed the session rule also covers this. Those tests start no Driver binary, browser or GTK app. They were re-run inside the isolated session.

jev-use was not modified, so its unit baseline from setup (Python 229 run / 228 pass + 1 skip, TS 105/105) is unaffected and was not re-run.

## Deviations from PREREG

- `run_batch.sh` (the session orchestrator) and `analyze.py` / `verify_artifacts.py` were written after the pre-registration commit. They implement the pre-registered order and analysis. The harness (`profile_atspi.py`, `run_in_session.sh`) is byte-identical to the pre-registered hashes, which `verify_artifacts.py` checks.
- Supplementary analyses not in PREREG are labelled as such in `r2-04-summary.json` (`supplementary_*`): action-time shares, and distortion comparisons stratified by previous target. These were added because the cursor reveal depends on the transition, so unstratified checkbox and button comparisons mix two populations. The bootstrap CIs on those unstratified comparisons are therefore very wide, although the medians agree.
- The PREREG listed text `mutation_landing` via app signals. For the Save click, the first app signal after `DoAction` is `BoundsChanged`, not a note-specific signal. The landing time for text therefore uses the `DoAction` reply, and the state-file oracle remains the success test.
- None of the 240 measured trials failed, so the "exclude unverified from latency medians" rule never applied.
- Pilot and smoke runs, all excluded from every number here:
  - `pilot1` (M, 2 rounds) and `pilot2` (M, 1 round + 4 negatives) ran before the pre-registration commit and are disclosed in PREREG.
  - `smokeP` (P, marks on, 1 round) and `smokePoff` (P, marks off, 1 round) ran **after** the pre-registration commit (about 22:15-22:17Z) and before the first measured session (22:21:30Z). PREREG does not mention them. `smokeP` checked that the instrumented build wrote marks; `smokePoff` is the marks-off correctness control in `raw/controls/smoke-P-marks-off`. A dry run of `analyze.py` used `smokeP` and `pilot2` data before the batch, to test the code, not to choose the analysis.
  - Their raw data is mirrored with the lane artifacts (`<lanes>/artifacts/r2/r2-04/pilots/`), not in this packet.
- Revision after a fresh verification review (no new trials, no change to any pre-registered number):
  - The unit logs were renamed from `.log` to `.txt`. The repository `.gitignore` ignores `*.log`, so the first packet commit left `raw/unit/` out.
  - `analyze.py` gained the supplementary `supplementary_tree_size` section and `dispositions.H_A_scope`. Re-running it reproduces every other key of `r2-04-summary.json` unchanged.
  - The H_A KILL, the gate D statement, the disposition and the claim boundary are now scoped to this 9-element fixture.
  - `verify_artifacts.py` now checks README numbers in their table row or sentence (not as bare substrings), recomputes the tree size, per-element cost, per-call RPC counts and the landed-to-return time from `raw/`, and checks that the unit evidence is present.

## Limits

- One GTK3 fixture window with 3 action types, one machine, and a private Xvfb/X11 session with picom. The cursor overlay renders and reports arrival here, and glide time depends on overlay settings and distance. Wayland, Hyprland, other toolkits (Qt, VCL, Chromium) and real desktops may differ.
- Monitor timestamps are taken when `dbus-monitor` receives each message. Per-RPC latencies of about 0.1 ms carry that receive skew.
- The state-file `mtime` granularity is filesystem-dependent, so it is not used for headline timing.
- n = 40 per arm and type (20 monitored). A p95 from this sample is an estimate, not a tail guarantee.
- The BULK arm did not run, so this packet says nothing about the absolute cost of Cache.GetItems or Collection on this bus.
- **Tree size.** The fixture window has 9 elements. Large-tree apps (file managers, office suites, browsers with full page trees, IDEs) were not tested. Their discovery cost per observation could be orders of magnitude higher, so the H_A KILL does not transfer to them.
- **Binary per session.** The raw ledger's meta row records the arm label but not the Driver binary's sha256, and the `run_batch.sh` arguments were not saved. P sessions are attested by their phase marks; that M sessions ran the `8b037961` binary rests on `run_batch.sh`'s M→main mapping and on the absence of marks. Both binaries still hash to the values in Provenance. A future harness should write the binary sha256 into each session's meta.
- **Unexplained monitor effect.** In the two larger previous-target strata (button after "I agree", checkbox after "Save note"; 12-16 trials per side), monitor-on action calls are 8.4-9.7 ms faster than monitor-off in both arms, with bootstrap CIs that exclude 0 (`supplementary_stratified_distortion`). The two smaller strata (4-8 trials per side) show no consistent effect. This is within the 15% distortion threshold, but it is not explained.
- **Monitor start traffic.** The Driver connection sends an unanswered `Application.GetApplicationBusAddress` to each new connection on the AT-SPI bus, including `dbus-monitor` itself. This happens when the monitor starts, outside every call window, so it does not enter the per-phase counts.

## Claim boundary

On this fixture (a 9-element GTK3 task window) and environment, with Driver 229b65b28 (and its measurement-only instrumented build), AT-SPI D-Bus traffic accounts for under 1% of native AT-SPI action time. The time goes to the Driver's cursor visualization and its post-dispatch sleep and settle watch.

This is a localization claim. It is not a speedup, not work deletion, not a claim about other toolkits or platforms, not a claim about apps with large accessibility trees, and not a certification of the live upstream heads effd9b298 or 021b87ddf. Cursor-span causality, meaning whether removing the reveal saves that time, still needs an intervention.

## Disposition

- **H_A_bulk_cache: KILL** for this 9-element fixture and the background element-token route only (G_bulk did not fire). Large-tree apps are untested and BULK is `NOT_RUN`, so Cache.GetItems / Collection stays a conditional tactic for large trees as #93 has it.
- **H_B_localization: KEEP.**
- **R2-04: REVISE.** On this fixture and other small trees, redirect native latency work from AT-SPI protocol batching to a causal A/B on the cursor reveal, the post-`DoAction` sleep and the focus-guard settle watch, keeping the same state-file oracle and focus-steal and stale-token negatives. The RFC delta is **none**.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | The pre-registration |
| `provenance.json`, `source-head.txt` | Provenance |
| `r2-04-summary.json` | Every aggregate, gate and disposition |
| `r2-04-trial-metrics.jsonl.gz` | Per-trial derived metrics |
| `raw/s<k>-<arm>/trials.jsonl.gz` | One JSONL ledger per session: meta, every trial with caller stamps, parsed RPC pairs and app signals for monitored trials, and Driver marks in arm P |
| `raw/s<k>-<arm>/session-events.txt` | Lock acquisition and session start/end, with loadavg |
| `raw/controls/` | The marks-off smoke run |
| `raw/unit/*.txt` | Unit test logs (`in-session-tests.txt` is authoritative) |
| `instrumentation.diff` | The measurement-only Driver change |
| `profile_atspi.py`, `run_in_session.sh`, `run_batch.sh`, `analyze.py`, `verify_artifacts.py` | Scripts |

Run `python3 verify_artifacts.py` to recompute the headline numbers from `raw/` and privacy-scan the packet.
