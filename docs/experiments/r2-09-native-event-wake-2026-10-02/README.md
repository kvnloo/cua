# R2-09: native post-DoAction event wake on Chromium AT-SPI and GTK3 foreground, 2026-10-02

Owners: kvnloo/cua#93 (R2-09), kvnloo/cua#20 (event fidelity), kvnloo/cua#10 (accounting), kvnloo/cua#73 (canonical state).

## Result in one paragraph

All 415 planned measured cells verified against target-owned oracles on their first attempt (0 failures, 0 re-runs): 240 Chromium AT-SPI trials (families M and F), 120 GTK3 foreground trials (G), 50 event-fidelity control trials and 5 default-off smoke trials. One fresh Driver and one fresh target per trial, binary W, no provider.

- **The sleep's premise is real, its need is not (T1 Chromium AT-SPI, background).** In 240/240 T1 trials the page's own report of the effect reached the oracle **after** the DoAction reply, by 2.5-18.6 ms. That is the renderer lag the sleep's source comment describes. But the effect was already visible at tool return without the sleep: **S0 20/20 on both tasks** (M), because the focus-guard settle watch (IRREDUCIBLE, N-01R) always follows. H1 is false. Deleting the sleep saves **69.8 ms [53.1, 102.3]** (checkbox) and **67.0 ms [52.0, 79.0]** (submit) of whole-task T, with correctness equal to B.
- **The event wake works but is dominated, and its event is not the effect.** EW keeps B's correctness (20/20 verified and visible at return per task) and saves **61.4 ms [36.4, 72.8]** and **46.1 ms [26.1, 67.0]** (H2 holds). It woke in 80/80 EW trials on the acted object's own `state-changed:focused`, which Chromium emits when DoAction moves focus, about 1 ms **before** the page's report of the effect reached the oracle (77/80; median -0.89 ms). It is a wake hint about the object, not evidence of the effect. S0 is at least as fast and needs no event source. Pre-registered rule: **KILL (T1)**, S0 already safe; the sleep's DELETED scope extends to Chromium AT-SPI background.
- **T2 GTK3 foreground: there is no post-DoAction sleep to wake.** On X11 an element click with `delivery_mode: foreground` activates the window and XTest-clicks the element (`route: global_input`); 0 DoAction marks in 120/120 trials, and the knobs were never read (0 `exp_knob` marks). The effect was visible at return 20/20 in every arm, with no T difference attributable to a knob. **KILL (T2)**: nothing to wake.
- **Unguarded shape (F, supplementary).** With the settle watch removed too, the post-DoAction wait is the only post-action wait. S0_F0 still showed the effect at return in 39/40. The one exception was oracle publication lag: the page's report reached the server 6.2 ms before return, but the server published its file 95 ms later. In every S0_F0 trial the page's report arrived before return, with a margin of at least 3.1 ms. EW_F0 shortens the wait to a median of 4.9 ms (checkbox) and 4.4 ms (submit), but again on the focus event.
- **Event-fidelity controls: all pass.** (b) decoys: 0/10 false wakes, despite a median of 15 foreign wake-set events inside each wait. (d) no-op: 10/10 end at the deadline. (a) node replacement: 10/10 end at the deadline, 0 false wakes; weakly discriminating, because Chromium emitted no wake-set event for the new node. (c) registry restart 2-4 ms after the reply: 10/10 completed, and the acted object's events kept flowing, so EW woke on them. (c2) bus drop: 10/10 `stream_closed`, then the wait fell back to the deadline (50.2-51.7 ms). Every verdict came from the oracle. Receipts stayed `effect: unverifiable`.
- **Is any native wait still worth an event wake?** No, on any X11 route measured here. GTK3 background: the sleep is DELETED (N-01R, cited). GTK3 and Chromium foreground: no DoAction. Chromium background: S0 is safe 40/40. The focus-guard settle watch stays IRREDUCIBLE (N-01R, cited). Its wake condition is a later focus change, which no acted-object event can announce, and event absence authorizes nothing (OWN-20, cited). The only remaining DoAction routes without the settle watch (`ax_fg` for non-showing elements, Hyprland foreground semantic clicks) were not run. The F proxy suggests that even there the event would announce focus, not the effect.

Evidence classes are given per row. The runtime rows are REAL: a real Driver, real Chrome and GTK3 apps, a private AT-SPI bus, an isolated X11 session, and no provider (scripted task steps). TypeSafe: 0 attempts, 0 reached.

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Base | `3bb4a7fc70d1d58984b19a7a357892a7c9af31fa`: the N-01R head (`exp/n-01r-native-wait-ab-20261002`). Its Driver source is `b9b357bc72fe0627b841f66a2d0812fafca8711f` (N-01R knobs on the R2-04 marks `28b915ae9` on upstream main `229b65b28`; `libs/cua-driver` at `229b65b28` equals `352507b6c`) |
| Measurement commit (tested source) | `bff61ddccfa2207abbaed43ece6b9ee95f7f36f6`: exactly one commit, one env-gated default-off knob in `platform-linux/src/atspi/native.rs` (see [The measurement commit](#the-measurement-commit)). `verify_artifacts.py` checks it is the only `libs/` change since the base |
| Pre-registration commit | `ede0320198731687a39bf268e6d004ac2b14ac83`, committed 17:52:06Z. The first measured trial started after it (block `r209-d01`); `verify_artifacts.py` checks the order and that `PREREG.json` is unchanged |
| Driver W | `cua-driver-r2-09-bff61ddcc`, sha256 `156338f75b4d6a55db0387b85c763061809e6cb7aa79fc9c1c8c5343de2e0e52`, `cua-driver 0.32.0` (read inside the session per block, `raw/<label>/driver-version.txt`). Built with `build-driver.sh` into `cua-release-r2-09` under the cargo-build lock, logged `head=bff61ddcc`, 0 Fresh workspace units, 213 s (`raw/driver-build/build-driver.txt`). Every block's meta row records this sha256 |
| Pilot Driver | pilots 1-2 only (STEP 0 exposure and route checks): N-01R binary `c2a9978e...` (no knob of this lane involved; never compared with W) |
| Reused harness code | `xprobe.py` verbatim from N-01R (blob `f17d8369`), `atspi_listener.py` verbatim from OWN-20 `6da15bf35` (blob `374e7a1b`); `r209_harness.py` is derived from N-01R's `n01r_harness.py` |
| Live heads (gh read-only, 17:54:01Z) | upstream main `da46c4bc85bc`: 34 commits ahead of `352507b6c`, 18 files under `libs/cua-driver`, none under `platform-linux/src/{atspi,tools,input}` (the only Linux files are `platform-linux/src/wayland/{hyprland,mod}.rs`, outside this X11 claim). trycua/cua PR 4316 `a0bca7440` (open; not this source). kvnloo/cua#106 `c45845797b71` (packet-format reference). R2-09 has no PR |
| Publication SHA | set by the Publish agent (`provenance.json: publication_sha`) |
| Provider | TypeSafe cap 0: **0 attempts, 0 reached**. The harness refuses any non-loopback TCP connect and counts refusals (0 in every block) |

## Environment

- **Isolation.** Every code-executing command ran as `TMPDIR=<tmp>/w3-r2-09 hostless <cmd>` (hostless v2: env scrub plus Landlock scope). GUI, Chrome, Driver and AT-SPI work ran inside `cua-x11-session.sh` (private rootless Xvfb 1920x1080x24 `-nolisten tcp`, private dbus session, openbox + picom, `env -i`) with `CUA_SESSION_ATSPI=1` (private `at-spi-bus-launcher` + `at-spi2-registryd`) and `CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"`. The harness refuses to run without a private DISPLAY and session bus, or with a host runtime dir.
- **Chrome.** System `/opt/google/chrome/chrome`, version read inside the session in every block: `Google Chrome 151.0.7922.71` in all 25 measured blocks. A fresh `--user-data-dir` per trial under the lane tmp dir (deleted after the trial), `--force-renderer-accessibility`, background networking, sync, component updates and first-run UI disabled, `--disable-gpu`; the Chrome sandbox stays on. `org.a11y.Status IsEnabled=true` is set on the private session bus at block start and read back `true` in every block.
- **Locks.** Every measured block (including controls) ran under `bin/quiet-timed` (EXCLUSIVE quiet-lane lock, taken before the session opens); receipts are in `raw/lock-ledger.jsonl`. Pilots ran under a shared quiet lock and are not measured.
- **Machine load.** Shared machine: the median 1-minute loadavg per family was 10.7 (M), 15.0 (F) and 5.6 (G) on 10 CPUs (range 2.9-19.3 over all measured trials); other lanes ran outside the lock. Every comparison is paired within a round on one source, binary and environment.
- **Driver defaults** apart from the arm knobs: no permission-mode override, no approval bypass, telemetry off, fresh HOME per session, no `*-e2e` wrapper, no `CUA_E2E_BROWSER_NO_SANDBOX`.

## STEP 0: feasibility and source facts

Pilots ran before the pre-registration, under a shared quiet lock, and are not measured (`raw/pilots/`). Their facts are pre-registered in `PREREG.json: step0_pilot_facts`.

| Item | Finding | Class |
|---|---|---|
| T1 exposure gate | With `--force-renderer-accessibility` and `org.a11y.Status IsEnabled=true` on the private bus, Chrome exposes the page: `check box "I agree" [actions=[check,...]]`, `entry "Note"`, `push button "Save note"` under `document web "R2-09 fixture"` (pilot1, pilot2). OWN-20 G1 saw frame-only exposure without the flag. **T1 is APPLICABLE**; no workaround was needed | REAL (pilot) |
| T1 text task | `set_value` on the Chromium entry is refused in background: `code: set_value_unavailable`, `effect: none`, "cached element exposes neither EditableText nor Value" (pilot2). The AT-SPI `set_value` half of the T1 text task is **NOT_APPLICABLE** on this target; the task was replaced by a submit task (Deviations) | REAL (pilot) |
| X11 foreground route | With `delivery_mode: foreground` on X11, an element click on an on-screen element activates the window and XTest-clicks its centre (`impl_.rs` `foreground_element_click`, receipt `route: global_input`). There is no `DoAction` and no `do_action_replied` mark, on Chrome and on the GTK3 fixture alike (pilots 1-3). The post-DoAction sleep is therefore **not on the T2 path**; the only X11 foreground route that reaches `DoAction` is `ax_fg`, taken for an element that is not showing or has no usable bounds (`decide_foreground_element_placement`) | SOURCE + REAL (pilot) |
| T1 background route | A background element click on Chrome takes `perform_action_ref` (`route: accessibility`) inside the focus guard: capture, DoAction, the 50 ms sleep, then the 220 ms settle watch (about 241 ms, N-01R). So in the default configuration a settle watch always follows the sleep | SOURCE + REAL |
| Chromium events on DoAction | `DoAction` on the native checkbox moves focus to it: the acted object emits `state-changed:focused`, then `state-changed:checked`; on the button only `state-changed:focused` (pilot3 listener). DoAction on a non-focusable ARIA checkbox emits no focus event | REAL (pilot) |
| Sleep site | `perform_action_ref`'s sleep (`native.rs`, `post_sleep_done` mark) is the one the click executes; the commented sibling at the index re-walk fallback ("AT-SPI's doAction acknowledgement can precede the renderer's queued DOM mutation. Give WebKit/Chromium one short event-loop turn...") states the purpose this lane tests | SOURCE |
| T3 WebKitGTK MiniBrowser | **NOT_RUN.** No WebKitGTK host package is installed (`pacman -Qs webkit` lists none). The only MiniBrowser binaries are inside a flatpak GNOME 50 runtime; launching them would add flatpak's own sandbox and its D-Bus/a11y proxies, so it is not a host install. No packages were installed | SOURCE |

## The measurement commit

`bff61ddcc` (+214/-1, one file, `platform-linux/src/atspi/native.rs`):

- `CUA_DRIVER_EXP_NATIVE_POST_ACTION_WAKE=event` (read once per process; anything else, or unset, keeps the sleep). In `perform_action_ref` (the cached-ref route the click takes), an AT-SPI event stream is opened on the shared connection **before** `DoAction`, so an event the toolkit emits while handling the call is kept. After the reply, the 50 ms sleep is replaced by a wait for the first `object:state-changed` (other than `defunct`), `object:text-changed` or `object:property-change` whose sender bus name **and** object path equal the acted object's, bounded by the sleep's deadline. A closed stream sleeps to the deadline. Match rules for text-changed and property-change are added once per process, only when the knob is set (the shared connection already registers `object:` events with the registry and a state-changed match rule).
- Phase marks: `exp_knob post_action_wake=event`; `post_wake_open <bus> <path>`; then exactly one of `post_wake_event <kind>`, `post_wake_deadline`, `post_wake_stream_closed`.
- The event is a wake hint only. The return value and the receipt are unchanged (`effect: unverifiable` for an AT-SPI click) and nothing is claimed from the event.
- Unit tests (class UNIT, inside the session under the cargo-build lock, `raw/unit/unit-in-session.txt`): 3 new tests (knob parsing; acted-object events wake; foreign bus, other object, missing sender, `defunct` and other kinds do not wake) plus N-01R's 2 knob tests: **5 passed**; touched suites `platform-linux` `input::focus_guard atspi:: tools::`: **184 passed** (N-01R's 181 + the 3 new). Two earlier unit attempts were aborted by me and kept (`raw/unit/unit-in-session-aborted-*.txt`, see Deviations).

## Method

- **Targets and oracles.**
  - T1: the harness launches Chrome on a page served by `fixture_server.py` (a lane test fixture, stdlib only). The page reports every effect it applies to itself (`POST /state`); the server stamps each report on arrival (CLOCK_MONOTONIC and wall clock) and republishes the folded state to a file. That journal is the target-owned oracle. The harness samples the file every 2 ms from an independent thread.
  - T2: the canonical GTK3 fixture's own state file, sampled the same way (as N-01R).
  - Driver receipts and AT-SPI events are logged, never the oracle.
- **Tasks.**
  - T1 checkbox: `get_window_state` (tree + screenshot), scripted lookup of "I agree", `click(element_token, delivery_mode: background)`.
  - T1 submit: the page pre-fills Note with a per-trial token; lookup of "Save note", `click(element_token, background)`; oracle `note_saved == token`.
  - T2 checkbox / text: as N-01R, but `delivery_mode: foreground` on every action (`set_value(Note, token)`, then `click(Save note)` for text).
- **Scripted chooser.** jev-use `NativeObservation` + `eligible_controls`, exact unique label match (as N-01R). For T1 only, jev-use rule 5 (web content goes to the browser source) is waived, because T1 acts on web content through the native AT-SPI tools on purpose; rules 1-4 and the token requirement still apply.
- **Forced path and producer check, per trial.**
  - T1: receipt `route: accessibility`, delivery `background`, the marks `do_action_replied` and `post_sleep_done` present, `exp_knob` marks exactly the arm's knobs; EW also needs `post_wake_open` and one wake-end mark.
  - T2: receipt `route: global_input`, delivery `foreground`, knob marks exactly the arm's.
- **Arms and families** (each family compared only within itself):

  | Family | Target | Arms | Role |
  |---|---|---|---|
  | M | T1, background | B (defaults), S0 (`..._POST_ACTION_SLEEP_MS=0`), EW (`..._POST_ACTION_WAKE=event`) | primary for T1 |
  | F | T1, background | B_F0, S0_F0, EW_F0: the same plus `CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS=0` | supplementary: the post-DoAction wait is then the only post-action wait, the shape of the unguarded AT-SPI action routes (`ax_fg`, Hyprland foreground semantic clicks), which are not measured here. The settle watch stays IRREDUCIBLE (N-01R) |
  | G | T2, foreground | B, S0, EW | primary for T2 |

- **Design.** 20 rounds per family. Each round runs both tasks (the first alternates by round) and, per task, the three arms in Williams row (round mod 6), which covers all six orders of three arms. n = 20 per arm per task, paired within the round. One fresh Driver and one fresh target per trial (T1: fresh server, fresh Chrome with a fresh profile; T2: fresh fixture with the 1.0 s AT-SPI settle of R2-04 / N-01R). Phase trace on, 1-minute loadavg recorded per trial, every trial kept.
- **Metrics (pre-registered).**
  - `effect_visible_at_return`: the first oracle sample that starts at or after the last action's tool return shows the expected state.
  - T (T_oracle): first observation send to the read-end of the first such sample at or after return that shows the expected state. T_land: the first matching sample regardless of return. T_return: the last return.
  - Wait: `post_sleep_done - do_action_replied` (Driver marks).
  - Effect after reply (T1): the page journal's arrival stamp of the effect minus `do_action_replied` (same host wall clock).
  - Event latency (EW, wake on an event): the wake mark minus the journal's arrival stamp of the effect. Negative means the AT-SPI event reached the Driver before the page's own report reached the oracle.
- **Statistics.** Medians, nearest-rank p95, paired within-round differences T_B - T_X, percentile bootstrap over rounds (10000 resamples, seed 909); S = median T_B / median T_X with the same bootstrap.
- **Event-fidelity controls** (T1, EW arm, n = 10 each; `atspi_listener.py` records every bus signal independently of the Driver for a, b, c, d):
  - (a) replace: a non-focusable ARIA checkbox; 10 ms after the click the page replaces it with a new node of the same label, checks the new node 15 ms later, then reports.
  - (b) decoy: the acted (non-focusable) ARIA checkbox changes its own state 30 ms after the click; an in-page decoy checkbox toggles every 4 ms and a separate GTK3 decoy app (`decoy_gtk.py`) toggles every 5 ms.
  - (c) reconnect: as (b) without decoys; when the page reports the click, the harness SIGTERMs this session's `at-spi2-registryd` (pid read from the private bus) and starts a new one.
  - (c2, supplementary) bus drop: as (c), but the harness terminates this session's private AT-SPI bus broker; one trial per session.
  - (d) noop: a `role=button` "Do nothing" with no handler.
  - false wake: an EW wake on an event with no acted-object (same bus name and path) wake-set event on the listener at or before the wake mark + 5 ms.
- **Default-off smoke.** W with no knob set, T1 checkbox B, n = 5.
- **Commands.** `make_plan.py plan.json`; blocks ran through `run_all.sh` (d01, m01, m02) and `run_group.sh` (the rest, several blocks per exclusive acquisition), each block inside its own `cua-x11-session.sh` via `run_block.sh` -> `r209_harness.py`; then `package.py`, `analyze.py raw r209-summary.json r209-trial-metrics.jsonl`, `verify_artifacts.py`.

## Results

### Denominators

| Block / cell | Attempted | Valid route | Verified (oracle) | Class |
|---|---|---|---|---|
| M: T1 checkbox + submit x B/S0/EW | 120 (20 per cell) | 120 | 120 | REAL |
| F: T1 checkbox + submit x B_F0/S0_F0/EW_F0 (supplementary) | 120 | 120 | 120 | REAL |
| G: T2 checkbox + text x B/S0/EW, foreground | 120 | 120 amended / 40 as pre-registered (see Deviations) | 120 | REAL |
| Controls a, b, c, d (EW) | 40 (10 each) | 40 | 40 | REAL |
| Control c2 bus drop (EW, supplementary, one session each) | 10 | 10 | 10 | REAL |
| Default-off smoke (W, no knob) | 5 | 5 | 5 | REAL |
| Pilots 1-4 (pre-registration, not measured; N-01R binary for 1-2, W for 3-4) | 24 | | 21 verified (2 T1 `target_not_exposed` before the rule-5 waiver, 1 T1 text `set_value_unavailable`; the first pilot-4 attempt did not find the bus broker, so no bus was dropped) | REAL (pilot) |
| Aborted session starts (private Xvfb died at start: pilot2, pilot3 first attempts) | 2 sessions, 0 trials | | | kept in `raw/pilots/` |

There were no failures, timeouts or unknown outcomes in any measured cell. No block was re-run.

### Whole-task T per arm (medians, ms; n = 20 each; class REAL)

| Family / task | Arm | T | p95 | T_land | Visible at return | Post-DoAction wait (median / p95) | EW wake |
|---|---|---|---|---|---|---|---|
| M checkbox | B | 531.1 | 686.5 | 236.0 | 20/20 | 51.08 / 52.24 | |
| | S0 | 438.96 | 549.2 | 196.1 | 20/20 | 0.01 / 0.01 | |
| | EW | 470.85 | 547.1 | 223.0 | 20/20 | 3.98 / 7.16 | event 20 (`state-changed:focused` 20) |
| M submit | B | 510.27 | 623.3 | 217.0 | 20/20 | 50.89 / 51.6 | |
| | S0 | 440.28 | 492.9 | 195.0 | 20/20 | 0.01 / 0.01 | |
| | EW | 455.17 | 534.8 | 209.0 | 20/20 | 3.39 / 9.13 | event 20 (focused 20) |
| F checkbox | B_F0 | 296.36 | 364.6 | 243.0 | 20/20 | 51.02 / 51.47 | |
| | S0_F0 | 277.28 | 486.5 | 273.7 | 20/20 | 0.01 / 0.01 | |
| | EW_F0 | 294.42 | 373.1 | 287.1 | 20/20 | 4.93 / 10.54 | event 20 (focused 20) |
| F submit | B_F0 | 337.68 | 370.2 | 283.0 | 20/20 | 51.05 / 51.53 | |
| | S0_F0 | 267.62 | 315.1 | 261.9 | **19/20** | 0.01 / 0.02 | |
| | EW_F0 | 277.04 | 377.7 | 270.1 | 20/20 | 4.38 / 9.22 | event 20 (focused 20) |
| G checkbox (fg) | B / S0 / EW | 891.98 / 888.99 / 888.92 | 925 / 937 / 893 | 71.0 / 71.0 / 69.9 | 20/20 each | no DoAction (route `global_input`) | |
| G text (fg) | B / S0 / EW | 2313.37 / 2314.97 / 2314.6 | 2353 / 2347 / 2351 | 1495 each | 20/20 each | no DoAction | |

T1's T is dominated by the observation (Chromium tree walk, about 180-260 ms) and, in M, the settle watch (about 241 ms). G's T is dominated by the cursor reveal/glide (N-01R OWNER_DECISION). The final state's `seq` was exactly the expected value in every cell, so there were 0 duplicate mutations.

### Paired differences vs the family base (median of within-round T_base - T_arm, 95% bootstrap CI, ms)

| Comparison | Checkbox | Submit / text | S (checkbox; submit/text) |
|---|---|---|---|
| M: B - S0 | **69.81 [53.06, 102.25]** | **66.97 [51.99, 78.97]** | 1.21; 1.16 |
| M: B - EW | **61.4 [36.4, 72.78]** | **46.06 [26.06, 66.96]** | 1.13; 1.12 |
| F: B_F0 - S0_F0 | **42.8 [26.66, 51.84]** | **44.06 [26.66, 81.16]** | 1.07; 1.26 |
| F: B_F0 - EW_F0 | 20.98 [-8.62, 34.86] | **44.39 [3.72, 72.39]** | 1.01; 1.22 |
| G: B - S0 | 1.77 [-1.03, 4.53] | -1.01 [-5.25, 3.99] | 1.0; 1.0 |
| G: B - EW | 3.1 [0.98, 6.23] | 0.21 [-3.12, 3.96] | 1.0; 1.0 |

G: the knobs never ran on this path (0 DoAction and 0 `exp_knob` marks in 120/120), so no G difference can be attributed to a knob. The one CI that excludes 0 (B - EW checkbox, 3.1 ms, lower bound 0.98) is one of four G comparisons, and it is far smaller than the 50 ms the knob could act on. It is NOT_MATERIAL.

### Component timings and work deleted vs wall-clock saved (T1, medians, ms; REAL)

| Arm | Observation (`get_window_state` wrapper) | Click tool wrapper | DoAction reply -> `ax_joined` | Post-DoAction wait |
|---|---|---|---|---|
| M checkbox B / S0 / EW | 215.1 / 183.4 / 205.9 | 307.9 / 254.5 / 259.9 | 292.3 / 241.0 / 245.6 | 51.08 / 0.01 / 3.98 |
| M submit B / S0 / EW | 204.5 / 182.6 / 197.0 | 304.7 / 255.0 / 257.5 | 292.1 / 241.1 / 244.5 | 50.89 / 0.01 / 3.39 |
| F checkbox B_F0 / S0_F0 / EW_F0 | 225.6 / 251.6 / 261.3 | 68.4 / 21.2 / 26.9 | 51.4 / 0.4 / 5.8 | 51.02 / 0.01 / 4.93 |
| F submit B_F0 / S0_F0 / EW_F0 | 262.9 / 226.9 / 251.8 | 70.2 / 21.0 / 24.6 | 51.6 / 0.4 / 5.1 | 51.05 / 0.01 / 4.38 |

- **Work deleted (per AT-SPI click).** S0 deletes the whole sleep (51 ms to 0.01 ms; the click tool gets 50-53 ms shorter in M and 47-49 ms shorter in F). EW deletes about 47 ms of it (the wait becomes 3.4-4.9 ms), at the cost of one event stream per action.
- **Wall-clock saved (whole-task T).** The paired table above. The M point estimates (67-70 ms) exceed the work deleted because the observation component, which no knob touches, varies between arms by up to 36 ms under load. Use the click-level figures for accounting (kvnloo/cua#10) and the T-level CIs for significance.
- **Renderer lag (the sleep's premise).** The page's report of the effect reached the oracle after the DoAction reply in 240/240 T1 trials (median 3.75-6.27 ms per cell, range 2.48-18.59 ms). In M the return came at least 229 ms after the effect; in S0_F0, at least 3.1 ms after the page's report.
- **Event latency (EW).** The wake mark minus the page's report arrival: median -0.89 (M checkbox), -0.82 (M submit), -1.29 (F checkbox), -1.09 (F submit) ms; 77/80 negative. The waking event is the focus change. In these tasks it reaches the Driver about 1 ms before the effect reaches the oracle, which is a property of this page, not a guarantee.

### H1-H3 (pre-registered)

| Hypothesis | Result | Verdict |
|---|---|---|
| H1: S0 not visible at return in >= 10% on T1 | M: 0/20 and 0/20. F (supplementary): 0/20 and 1/20; the one miss was oracle publication lag, since the page's report had arrived 6.2 ms before return | **FALSE** (M and F) |
| H2: EW keeps B's correctness and the CI of T_B - T_EW excludes 0 | M: 20/20 and 20/20 verified and visible, as in B; checkbox 61.4 [36.4, 72.78], submit 46.06 [26.06, 66.96]. F: checkbox CI includes 0, submit 44.39 [3.72, 72.39] | **holds in M**; F mixed |
| H3: GTK3 foreground S0 visible at return 20/20 | 20/20 checkbox, 20/20 text, but on the XTest route: the sleep is not on the path | **holds, vacuously** (route `global_input`, 0 DoAction) |

### Event-fidelity controls (EW; REAL; listener independent of the Driver)

| Control | Wake reasons | Wait (ms) | False wakes | Discrimination | Oracle | Verdict |
|---|---|---|---|---|---|---|
| (a) node replaced 10 ms after the click | deadline 10/10 | 51.03-51.08 | 0/10 | weak: the bus carried only `children-changed` (remove/add) on the parent, never a wake-set event from the new node; that the filter rejects another object path is shown at UNIT level (`foreign_defunct_or_other_events_do_not_wake`) | 10/10 verified, seq exact | **PASS (weak)** |
| (b) in-page decoy every 4 ms + foreign GTK3 app every 5 ms; acted state 30 ms after the click | event 10/10, all `state-changed:checked` from the acted object | 32.15-42.45 | **0/10** | strong: foreign wake-set events inside the wait in 10/10 trials (median 15 per wait); EW never woke before the acted object's own change | 10/10 | **PASS** |
| (c) registry restart 2.05-3.99 ms after the reply | event 10/10 (acted `checked`, listener-backed 10/10) | 31.86-34.17 | 0/10 | the restart (new registry pid 10/10) did not stop Chromium's events, so the fallback was not exercised here (see c2) | 10/10 | **PASS** (no error, no hang, no claim) |
| (c2) private AT-SPI bus terminated 2.66-5.44 ms after the reply (supplementary) | `stream_closed` 10/10, then sleep to the deadline | 50.15-51.65 | 0/10 | direct test of the fallback | 10/10 | **PASS** |
| (d) no-op button | deadline 10/10 | 51.03-51.13 | 0/10 | no wake-set event on the bus (listener) | seq unchanged 10/10 | **PASS** |

Receipts were `effect: unverifiable` in 50/50 control trials, so the Driver claimed nothing from the event. The harness verdict is the oracle in every trial.

### Default-off smoke (W, no knob; n = 5; REAL)

No `CUA_DRIVER_EXP_*` in the Driver environment, no `exp_knob` marks, post-DoAction wait 50.31-51.29 ms (the 50 ms constant), 5/5 verified.

### Invariants (E4), every arm

- 0 stale-ref dispatches: every trial's token came from that trial's own observation, and no token was used across a target restart.
- 0 duplicate mutations: the final `seq` was exact in 415/415 cells.
- 0 unverified successes: T always ends on the target-owned oracle, and AT-SPI click receipts are `unverifiable`.
- 0 authority from passive state or event absence: phase marks, the listener and the event are measurement only. An event shortens a wait and decides nothing. In (a) and (d), event absence just ran the wait to the deadline.
- No replay of a possibly landed effect.
- The knob is env-gated and default-off (smoke). No new service: the wait reuses the Driver's existing AT-SPI connection inside the existing call.

## Deviations

1. **T1 text task replaced by a submit task** (pre-registered from the pilot). The Chromium entry exposes neither EditableText nor Value, so `set_value` is refused (`set_value_unavailable`). The submit task keeps the button DoAction, the part the sleep applies to, with the field pre-filled by the page.
2. **jev-use rule 5 waived for T1** (pre-registered). The scripted chooser would otherwise send web content to the browser source.
3. **Family F and control c2 added** (pre-registered as supplementary). The spec's arms run inside the focus guard, so F isolates the sleep. The registry restart (c) cannot close the Driver's stream, so c2 tests the deadline fallback directly.
4. **T2 validity rule amended after the fact.** The pre-registered T2 route check required `exp_knob` marks to match the arm. The knobs are read, and marked, only when `perform_action_ref` runs, so on the XTest route S0 and EW can never show their marks: 40/120 pass the rule as registered (the B cells). The amended rule (`analyze.py`, `valid_route` with `valid_route_prereg` kept alongside) requires the Driver env to carry exactly the arm's `CUA_DRIVER_EXP_*`, with 0 DoAction and 0 knob marks: 120/120. The missing marks are themselves the evidence that the knob code never ran on T2.
5. **Lock grouping.** Blocks d01, m01 and m02 ran under one `quiet-timed` acquisition each. To reduce queueing behind other lanes, the remaining 22 blocks ran in four acquisitions (`run_group.sh`, groups A-D, 3.3-6.2 min each, all under 15 min). Every block's trials fall inside its acquisition window (`raw/groups.jsonl`, `raw/lock-ledger.jsonl`; checked by `verify_artifacts.py`). The stopped `run_all.sh` had block m03 still waiting for the lock. It never acquired it, so there is no receipt and no trial, and its empty attempt dir was removed (`raw/run_all/run_all-1.txt`). A first `run_group.sh` launch passed broken arguments (zsh does not word-split a variable): three calls exited before requesting the lock, and the fourth was stopped while waiting, with no receipt and no trial. That run created one empty directory in the caller's working directory, which was removed (`raw/run_all/run_group-0-argsplit-aborted.txt`).
6. **Unit runs.** Two unit attempts were stopped by me and are kept. The first had no `RUSTUP_HOME`, so rustup began syncing a toolchain into the session's temporary HOME. The second held the shared quiet lock while waiting for the cargo lock, which would have blocked other lanes' exclusive phases. The counted run used the cargo-build lock only (`raw/unit/`).
7. **Pilots used the N-01R binary** for exposure and route checks (pilots 1-2), and W for pilots 3-4. No pilot number is used in a result.
8. **Effect-visible-at-return depends on oracle publication.** The T1 oracle is the page's report as published by the fixture server. In one S0_F0 trial the server published 95 ms after the report arrived (loadavg 13.5). The pre-registered strict metric counts that trial as not visible. The post-hoc arrival stamp shows the report had arrived 6.2 ms before return.

## Limits and claim boundary

- **Claim boundary.** Linux X11 Xvfb in a private session, Chrome 151.0.7922.71, the GTK3 canonical fixture, binary W (`156338f7...`, source `bff61ddcc`). No Hyprland, native-Wayland, WebKitGTK (T3 NOT_RUN), Electron or real-seat row is claimed.
- **Routes not run.** The unguarded DoAction routes are X11 `ax_fg` (a foreground click on an element that is not showing or has no usable bounds) and Hyprland foreground semantic clicks. There the sleep is the only post-action wait. Family F reproduces that shape on the background route by turning the settle watch off. It is a proxy, not those routes.
- **Caller latency.** In S0_F0 the margin between the page's report and the tool return was at least 3.1 ms, over MCP stdio transport. A caller with a much faster return path than MCP could, in principle, observe the pre-effect state if the sleep were deleted on an unguarded route. Neither the sleep nor the event wake gives a guarantee there: the sleep is a fixed guess, and the event that arrived first was a focus change.
- **Event semantics.** In Chromium the first acted-object event after DoAction was the focus change in 80/80 EW trials. On a page where the effect lands later than focus, EW would return before the effect, exactly as S0 would. The event wake never strengthens correctness. Only the oracle does.
- **Shared machine.** Loadavg 2.9-19.3 (other lanes outside the lock). Comparisons are paired within rounds. Absolute T values are load-inflated, and the observation component varies between arms by up to 36 ms.
- **Fixture.** T1's page is a lane fixture (stdlib server, fetch-based reports). Its report latency is part of the oracle path, as with any target-owned oracle.
- **E2 transport gap.** MCP transport of the action calls is measured only inside the click wrapper. It is not decomposed further here (as in N-01R).

## Disposition

Per-target table (pre-registered rules):

| Target | H1 | H2 | Controls | Disposition | Evidence |
|---|---|---|---|---|---|
| T1 Chromium AT-SPI, background | FALSE: S0 visible 40/40 (M) | holds (M), but S0 is at least as fast | a-d pass (a weak), c2 pass | **KILL (event wake)**. S0 is already safe, so the 50 ms sleep's **DELETED** scope extends from GTK3 background (N-01R) to Chromium AT-SPI background. The deletion saves about 47-53 ms of click work, and T by 67.0-69.8 ms (CIs exclude 0) | REAL |
| T2 GTK3, foreground (X11) | vacuous: no DoAction on the path | not applicable (knob never ran) | n/a | **KILL**: X11 foreground element clicks use XTest; there is no post-DoAction sleep to wake | REAL + SOURCE |
| T3 WebKitGTK MiniBrowser | | | | **NOT_RUN**: not a host install (flatpak runtime only); no installs | SOURCE |

**R2-09 overall: KILL.** No native wait measured here is worth an event wake:

- GTK3 background: the sleep is DELETED (N-01R, `exp/n-01r-native-wait-ab-20261002` @ `3bb4a7fc7`, cited, not re-measured).
- GTK3 and Chromium foreground on X11: no DoAction (this packet).
- Chromium AT-SPI background: S0 is safe 40/40 (this packet).
- The focus-guard settle watch is IRREDUCIBLE (N-01R). It waits for a focus steal that may come later, which no acted-object event can announce early, and event absence authorizes nothing (OWN-20, `exp/own-20-atspi-invalidation-census-20261002` @ `6da15bf35`, cited).
- The remaining unguarded DoAction routes (`ax_fg`, Hyprland foreground) are not measured. The F proxy shows the sleep is not needed for an MCP caller there either (39/40 visible; the 1 miss was oracle publication lag), and that the event would announce focus, not the effect.

A default change (delete the post-DoAction sleep on the cached-ref route) remains a reviewed product fix candidate for a separate lane, not this packet. That candidate must state the unguarded-route caveat above. The event-wake knob should not be carried forward.

## Next

- R2-10 / kvnloo/cua#10 accounting: on the Chromium AT-SPI background click, the post-DoAction sleep is DELETED (S0) within this boundary. The click-level work deleted is about 50 ms per AT-SPI click, the same as GTK3 background. The settle watch stays IRREDUCIBLE.
- A reviewed fix-candidate lane (if wanted): remove the sleep in `perform_action_ref` (and its commented sibling on the index re-walk fallback). Test first with a red-before/green-after unit test, then re-run M's S0 cells plus one unguarded route: an `ax_fg` non-showing element on X11, or Hyprland foreground on a real seat (BLOCKED here: hardware).
- E2: the T1 components left are observation (about 180-260 ms on Chromium's tree), the settle watch (IRREDUCIBLE) and MCP transport. None of them is a post-DoAction wait.
- Not carried forward: the event-wake knob (`CUA_DRIVER_EXP_NATIVE_POST_ACTION_WAKE`). It stays on this research branch only.

## Files

- `PREREG.json` (pre-registration), `plan.json` / `make_plan.py` (measured plan), `r209_harness.py` (harness), `fixture_server.py` (T1 page + journal oracle), `decoy_gtk.py` (control b decoy app), `atspi_listener.py` (independent listener, OWN-20 verbatim), `xprobe.py` (N-01R verbatim), `run_all.sh` / `run_block.sh` (session runners), `unit_in_session.sh`, `analyze.py`, `package.py`, `peek.py` (pilot viewer), `verify_artifacts.py`.
- `r209-summary.json` (all tables), `r209-trial-metrics.jsonl.gz` (one row per planned cell, latest attempt), `README_NUMBERS.json` (numbers quoted here that `verify_artifacts.py` checks against the summary), `provenance.json`.
- `raw/r209-*/` (one dir per block attempt: `trials.jsonl.gz`, `session.txt`, `driver-version.txt`), `raw/pilots/`, `raw/unit/`, `raw/driver-build/`, `raw/lock-ledger.jsonl`, `raw/run_all/`. Raw outputs are mirrored at `artifacts/r2/R2-09/` in the lanes directory.
