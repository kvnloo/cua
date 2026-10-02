# OWN-16W: observation-modality producer truth on headless sway (native Wayland + Xwayland), and the non-boolean selector refusal

Owners: kvnloo/cua#16 (P2 directive: producer-truth matrix only), kvnloo/cua#73 (invariants).
Branch `exp/own-16w-sway-modality-20261002`. Provider: TypeSafe cap 0, so 0 attempts and 0 reached.

## Disposition

<!-- disposition SW: KEEP -->
<!-- disposition SX: KEEP -->
<!-- disposition X11: KEEP -->

| #16 row | disposition | evidence |
|---|---|---|
| wlroots / headless sway, native Wayland (S-W) | **KEEP** | REAL + BENCHMARK + UNIT |
| wlroots / headless sway, GTK3 under Xwayland (S-X) | **KEEP** | REAL + BENCHMARK |
| X11 string-value row, recertified on upstream main 989cc76ce | **KEEP** (refused on F; silently accepted on U) | REAL + UNIT |
| Hyprland | **BLOCKED**: needs a real Omarchy/Hyprland seat | BLOCKED |
| macOS / Windows | **BLOCKED**: hardware | BLOCKED |

This packet replaces the stale "deferred" on the #16 wlroots/headless-sway row with a terminal
disposition. It also closes the OWN-16 follow-up "reject non-boolean selectors" with a one-commit
product fix, `dd205d17b`.

What "KEEP" means here:

- An omitted modality's producer never ran: 0 in 42 of 42 calls per omission row, mode and binary.
  The Driver's marks AND a target-owned oracle both show this.
- The remaining modality was complete in 42 of 42 calls.
- `include_screenshot:"false"` and `"true"` are refused with `invalid_arguments` on F in 42 of 42
  calls per mode, before any producer runs.
- On U (upstream main 989cc76ce + marks only), both string values are silently accepted in 42 of 42
  calls per mode. Both producers run.

The pre-check of upstream trycua/cua PR 4318, which is on 989cc76ce, found that it does not refuse
string selectors. PR 4318 only adds an `element_token` pattern to the schema. So the fix was not skipped.

## Results (2 sessions x 21 calls per row; every call kept, 0 exceptions)

Counts are pooled over U and F unless a row differs between them. "1 (42/42)" means the count was 1 in
all 42 counted calls.

- **marks** = the binary's measurement-only producer marks.
- **oracle cap** = target-owned capture oracle:
  - S-W: the compositor's own protocol log (`zwlr_screencopy_manager_v1.capture_output` requests).
  - S-X: X RECORD on the private Xwayland (GetImage + ShmGetImage).
- **oracle walk** = per-node `Accessible.GetState` calls to the fixture on the private AT-SPI bus.

### S-W: native Wayland (GTK3 `xdg_shell` client, Driver opted in with `CUA_DRIVER_RS_ENABLE_WAYLAND=1`)

| row | class (U / F) | capture marks | walk marks | oracle cap | oracle walk (GetState) | AT-SPI calls to fixture | evidence |
|---|---|---|---|---|---|---|---|
| both | positive_control_pass / same | 1 (42/42) | 1 (42/42) | 1 (42/42) | 15 (42/42) | 148 (83), 149 (1) | REAL |
| screenshot_only | honored_complete / same | 1 (42/42) | **0 (42/42)** | 1 (42/42) | **0 (42/42)** | 6 (83), 7 (1): window-identity lookup, not a walk | REAL |
| accessibility_only | honored_complete / same | **0 (42/42)** | 1 (42/42) | **0 (42/42)** | 15 (42/42) | 148 / 149 | REAL |
| neither | rejected_explicit / same | 0 | 0 | 0 | 0 | 6 (lookup runs before the error) | REAL |
| legacy_omitted | default_honored / same | 1 | 1 | 1 | 15 | 148 | REAL |
| unknown_field | rejected_explicit / same | 0 | 0 | 0 | 0 | 0 | REAL |
| string_false | **U silently_accepted_default / F refused_invalid_arguments** | U 1 / F 0 | U 1 / F 0 | U 1 / F 0 | U 15 / F 0 | U 148 / F 0 | REAL + UNIT |
| string_true | **U silently_accepted_default / F refused_invalid_arguments** | U 1 / F 0 | U 1 / F 0 | U 1 / F 0 | U 15 / F 0 | U 148 / F 0 | REAL + UNIT |

### S-X: GTK3 under Xwayland (Driver on its X11 backend, no Wayland opt-in, `WAYLAND_DISPLAY` removed)

| row | class (U / F) | capture marks | walk marks | oracle cap (X RECORD) | oracle walk (GetState) | AT-SPI calls to fixture | evidence |
|---|---|---|---|---|---|---|---|
| both | positive_control_pass / same | 1 (42/42) | 1 (42/42) | 1 ShmGetImage (42/42) | 15 | 142 | REAL |
| screenshot_only | honored_complete / same | 1 | **0 (42/42)** | 1 | **0 (42/42)** | 0 | REAL |
| accessibility_only | honored_complete / same | **0 (42/42)** | 1 | **0 (42/42)** | 15 | 142 | REAL |
| neither | rejected_explicit / same | 0 | 0 | 0 | 0 | 0 | REAL |
| legacy_omitted | default_honored / same | 1 | 1 | 1 | 15 | 142 | REAL |
| unknown_field | rejected_explicit / same | 0 | 0 | 0 | 0 | 0 | REAL |
| string_false | **U silently_accepted_default / F refused_invalid_arguments** | U 1 / F 0 | U 1 / F 0 | U 1 / F 0 | U 15 / F 0 | U 142 in 40 calls, 143 in 2 / F 0 | REAL + UNIT |
| string_true | **U silently_accepted_default / F refused_invalid_arguments** | U 1 / F 0 | U 1 / F 0 | U 1 / F 0 | U 15 / F 0 | U 142 / F 0 | REAL + UNIT |

### X11: private Xvfb, string rows only (recertifies OWN-16 on 989cc76ce)

| row | U | F | evidence |
|---|---|---|---|
| both | positive_control_pass (capture 1, walk 1, X RECORD 1, GetState 15, 42/42) | same | REAL |
| string_false | silently_accepted_default 42/42 (both producers ran) | refused_invalid_arguments 42/42 (0 producers, 0 X image reads, 0 AT-SPI calls) | REAL + UNIT |
| string_true | silently_accepted_default 42/42 | refused_invalid_arguments 42/42 | REAL + UNIT |

The X11 element digest of the `both` row is `3d9d293d57058dce`, the same value OWN-16 recorded on
229b65b28.

Refusal text on F: `get_window_state.include_screenshot must be a boolean (true or false).`, with
structured `code: invalid_arguments`. `neither` keeps its pre-existing generic code
`tool_invocation_failed`. `unknown_field` is refused by the registry.

## The five #73 mechanism requirements

1. **Forced path.** The selector argument(s) of `get_window_state` (pid + window_id of the fixture's
   task window), one MCP stdio session per private session.
   - S-W: `GDK_BACKEND=wayland` for the fixture; the Driver got `CUA_DRIVER_RS_ENABLE_WAYLAND=1`,
     `WAYLAND_DISPLAY` and `SWAYSOCK`.
   - S-X: `GDK_BACKEND=x11`, and `WAYLAND_DISPLAY` removed for both the fixture and the Driver.
   - The window title seen in S-W was `CuaTestHarness GTK3 Tasks [main.py]` (native title suffix).
2. **Actual route / producer.**
   - Marks, ported unchanged from OWN-16 by `cherry-pick -x`:
     - `capture_window` around `screenshot_dispatch_for_pid`. On native Wayland this is the output
       screencopy + crop path; on Xwayland and X11 it is the X path.
     - `capture_root_region` (never invoked).
     - `atspi_walk` around `walk_tree_bounded_within`.
   - Full-trace audit, per truth session: every producer mark lies inside a `get_window_state`
     dispatch (0 outside), and the ordinals are gap-free for every scope.
3. **Independent target-owned outcome.**
   - Capture, S-W: sway itself logs protocol requests (`WAYLAND_DEBUG=server` passed through
     `CUA_SESSION_EXTRA_ENV`; the session script was not edited). This oracle is compositor-side, not
     library-level, so the S-W capture claim is not REVISE-bounded.
   - Capture, S-X and X11: X RECORD on the X server.
   - Walk, all modes: dbus-monitor on the private AT-SPI bus.
   - All oracles ran for the whole truth block, so they cover every counted call, not a sample. Calls
     were separated by 100 ms, and attribution used [call start, call end + 30 ms].
   - The 1 s idle windows before and after each block showed 0 capture events and 0 GetState calls.
     There were 0 unattributed capture events and 0 unattributed GetState calls in all 12 truth
     sessions.
   - Usability, verified only by the fixture's own state file: in all 12 of 12 truth sessions, an
     `element_token` from an accessibility-only observation ("Increment") was clicked with
     `delivery_mode: background`. The Driver's response was route `accessibility`, effect
     `unverifiable`, and the state file recorded counter 0 to 1 and seq 1 to 2.
4. **Negative / fallback.**
   - **No-AT-SPI sessions (SW-U-N1, SX-U-N1): PASS.** 12 of 12 accessibility-requesting calls per mode
     returned walk = 1 (the attempt is counted) with an explicit `degraded: true`,
     `degraded_reason: "atspi_walk_failed: AT-SPI connect failed: ZBus Error: ... NameHasNoOwner ..."`,
     `elements_complete: false` and a 1-element fallback. That is never the omission shape.
     `screenshot_only` ran no walk in 6 of 6.
   - **Fallback refusals:** `neither` and `unknown_field` were refused in 42 of 42 per mode and
     binary, with 0 producers by marks and oracles.
   - **Default-off smoke (SW-D1): PASS.**
     - U with the marks unset or empty created no trace file; marks on created one. F (unset) created
       none.
     - The per-row response shape sets are identical across U unset, U empty and U on.
     - F equals U for every non-string row.
5. **Exact provenance:** see below and `provenance.json`.

## Timing (BENCHMARK, quiet-timed, U binary, marks on, no oracles)

Each session ran 1 warm-up call per row (excluded), then 21 pairs per comparison. AB/BA alternated per
pair and was flipped between B1 and B2, giving 42 paired calls per comparison and mode. The statistic is
the median of per-pair differences (row - both), with a seeded stratified bootstrap 95% CI (10000
resamples, seed 1616).

| mode | comparison | median paired diff | 95% CI | AB / BA medians | warm wall median (p95) |
|---|---|---|---|---|---|
| S-W | screenshot_only - both | **-8.29 ms** | [-11.78, -2.26] | -7.37 / -9.25 | 197.6 (300.2) vs both 203.4 (304.3) |
| S-W | accessibility_only - both | **-166.00 ms** | [-170.15, -161.27] | -161.26 / -167.38 | 37.7 (64.8) vs 203.4 |
| S-X | screenshot_only - both | **-5.98 ms** | [-7.30, -4.33] | -6.05 / -5.95 | 168.3 (174.5) vs both 173.2 (187.6) |
| S-X | accessibility_only - both | **-150.27 ms** | [-152.68, -148.57] | -148.72 / -151.28 | 22.6 (25.6) vs 173.2 |

Per-session medians of the paired differences (21 pairs each; checked against raw/ by
`verify_artifacts.py`). The pooled CI resamples within session, so it describes the pooled median of
these two sessions only. In S-W the two sessions differ by more than the pooled CI is wide
(accessibility_only: -179.73 vs -157.97 ms), so the session-to-session spread is the better guide to
reproducibility than the CI.

| mode | comparison | B1 | B2 | pooled |
|---|---|---|---|---|
| S-W | screenshot_only - both | -10.68 | -7.45 | -8.29 |
| S-W | accessibility_only - both | -179.73 | -157.97 | -166.00 |
| S-X | screenshot_only - both | -5.95 | -6.00 | -5.98 |
| S-X | accessibility_only - both | -153.85 | -149.62 | -150.27 |

<!-- per-session SW screenshot_only: B1 -10.68 (n=21) / B2 -7.45 (n=21) -->
<!-- per-session SW accessibility_only: B1 -179.73 (n=21) / B2 -157.97 (n=21) -->
<!-- per-session SX screenshot_only: B1 -5.95 (n=21) / B2 -6.00 (n=21) -->
<!-- per-session SX accessibility_only: B1 -153.85 (n=21) / B2 -149.62 (n=21) -->

Component medians come from the marks (descriptive; deviation D2 addendum).

| component | S-W both / screenshot_only / accessibility_only | S-X both / screenshot_only / accessibility_only |
|---|---|---|
| Driver dispatch | 183.7 / 178.3 / 20.4 ms | 157.0 / 152.6 / 7.1 ms |
| capture span (`screenshot_dispatch_for_pid`) | 38.0 / 38.6 / not run | 29.8 / 29.8 / not run |
| AT-SPI walk span | 7.0 / not run / 6.8 | 5.6 / not run / 5.6 |
| MCP response bytes | 62245 / 59033 / 4047 | 62124 / 58456 / 4050 |

**Work deleted** (counted, separate from time):
- `include_screenshot:false` deletes per call:
  - 1 compositor screencopy request (S-W) or 1 `ShmGetImage` (S-X);
  - the crop, the resize from 1920x1053 to 1448x794, the PNG encode and the base64/response work (about
    120 to 125 ms: dispatch(both) - dispatch(accessibility_only) - capture span, from the component
    medians);
  - capture publication;
  - about 58 KB of response.
- `include_accessibility_tree:false` deletes 1 AT-SPI walk per call: 142 AT-SPI method calls to the
  app, 15 of them GetState. In S-W, the 6-call window-identity lookup still runs; see the observations.

**Wall-clock saved:** -166.0 / -150.3 ms per call for `accessibility_only`, and -8.3 / -6.0 ms for
`screenshot_only`, on a sway-tiled 1920x1053 window. The capture cost is dominated by window size.
- The timing numbers are larger than OWN-16's X11 numbers (-2.98 / -7.36 ms) because OWN-16 used a
  480x320 window. They are not compared across modes, binaries or packets.
- They are per-observation numbers, not whole-task savings.

Load: 1-minute loadavg per timed call ranged 4.49 to 6.98 (SW-B1), 8.83 to 10.01 (SW-B2), 2.57 to 3.02
(SX-B1) and 17.41 to 19.51 (SX-B2). SX-B2 held the exclusive quiet-lane lock the whole time, so the load
came from processes outside the lock protocol on this shared machine. AB/BA pairing is within a
session, so drift between sessions does not enter the paired difference, but it does widen the
session-to-session spread above.

## Observations (not fixed here; they belong to the #100 track)

- **Native-Wayland screenshot_only still touches AT-SPI (6 calls, no GetState).**
  - Source: `list_windows_dispatch` enriches wlroots toplevels through `wayland_atspi_windows` and
    `atspi::list_windows`. `get_window_state`'s window-ownership check calls it on every call,
    including `neither` before its error.
  - The walk producer does not run, so the #16 claim holds. "No accessibility traffic at all" is not
    true on native Wayland. S-X and X11 show 0.
- **Element frames and screen scale.**
  - On sway, the tiled window is 1920x1053 and the screenshot is downscaled to 1448x794.
  - The response reports `frame_scale` 0.7542 (S-W) and 0.7557 (S-X). The reciprocal 1.326 is the
    stack track's ratio.
  - Element `frame`s lie inside `window_bounds` (0 outside in 42/42 in both modes).
  - S-W elements carry no `screenshot_frame` (0 of 9); S-X elements carry 9 of 9.
  - Click overshoot was not exercised: the token click used the AT-SPI accessibility route.
- **Seat binding** was not exercised (single seat; the token click needs no seat).
- **AT-SPI noise.** One idle window (SW-U-T1) and three sessions each saw 1 non-GetState AT-SPI call to
  the fixture outside any call window (`atspi_calls_to_fixture_unattributed` = 1 in SW-U-T1, SW-F-T2,
  SX-F-T1 and SX-F-T2). This is not walk traffic: GetState unattributed = 0 everywhere. It is the
  likely reason a few walk calls show 143 or 149 total calls.
- **Contract observations carried over.** `neither` still uses the generic `tool_invocation_failed`
  code. Omission is still signalled only by the absence of fields.

## Method notes

- **n.** For each mode and binary: 2 truth sessions (T1 rotation 0, T2 rotation 3), each with 1 cold
  and 20 warm rounds over every row, so 21 calls per row per session and 42 per row.
  - Totals: S-W and S-X have 8 rows x 2 binaries x 42 = 672 counted calls each. X11 has 3 x 2 x 42 =
    252.
  - Each truth session ends with 1 usability observation and 1 click.
- **Per-call record:** marks, oracle windows, response shape and metadata verbatim, integrity, wall
  time and response bytes (`raw/<MODE>/<BIN>/<ID>/calls.jsonl`).
- **Truth-session wall times are not reported as numbers.** The truth sessions ran under quiet-timed
  too, but their walls are perturbed by the oracles and by the 100 ms gaps.
- **Lock.** Every one of the 19 sessions ran under `quiet-timed`, one exclusive lock acquisition per
  session. `raw/quiet-lane-receipts.jsonl` holds 19 receipts with rc 0, and `verify_artifacts.py`
  checks that every call of a session lies inside its receipt.
- **Session order:** truth1, negative, truth2, timing, smoke, as pre-registered. SX-U-T2, X11-F-T2 and
  X11-U-T2 were run after the D1 interruption.

## Deviations

- **D1 (execution, disclosed).** The background job running `run_batch.sh` hit its own 2-hour limit at
  20:11Z and was killed during SX-U-T2.
  - The quiet-lane lock queue was long; other lanes held it for 10 to 20 minutes at a time.
  - The aborted attempt recorded 127 calls. It is kept unchanged in `raw/aborted/SX-U-T2/`
    (`calls.partial.jsonl`, oracle logs, trace). It has no quiet-lane receipt, because the wrapper was
    killed, and it is excluded from every count and from timing.
  - The remaining sessions (SX-U-T2 again, X11-F-T2, X11-U-T2, then timing and smoke) were run with
    `run_resume.sh`. That script evaluates `run_batch.sh`'s frozen definitions unchanged, in the
    pre-registered order, one background job per phase.
  - No session that completed was rerun.
- **D2 (analysis, disclosed; `analyze-deviation.diff`).**
  - The frozen `smoke()` required a single response shape per row across the union of U unset, empty
    and on. The pre-registered text asks for the per-row shape to be identical across those tags.
  - The first call of every Driver session lacks the "Invalidated snapshots ..." text part, because no
    earlier snapshot exists. `both` therefore shows two positional shapes, the same in every tag and in
    F (see `raw/SW/D1/calls.jsonl`, indices 0, 15 and 22). This is the effect OWN-16 disclosed as its D2.
  - The comparison now checks that the per-tag shape sets are equal. The frozen version reported
    FAIL; the corrected version reports PASS.
  - The same diff adds descriptive component medians to the timing summary and changes no gate.
- **D3.** The unit-test "green" run (`raw/unit/unit-green.log`) ran on the worktree with the fix staged
  but not yet committed (head b39b866f7, dirty). The committed `dd205d17b` is that exact content. The
  full suites (`unit-all.log`) ran on the committed tree.
  - The red run (`raw/unit/unit-red.log`) was not byte-identical to the committed test either. It
    panics at `get_window_state_selector_tests.rs:31:9` with the `invalid_arguments` message; in the
    committed file that assert starts at line 35. The red run used an earlier layout of the same test
    (before formatting). The assertions are the same, but the red evidence is for that earlier layout.
- **PREREG timestamp.** PREREG's `written_utc` (17:50Z) is earlier than the F build (17:59:26Z) whose
  sha256 it records, so `written_utc` marks when drafting started. The binding bound is the PREREG
  commit time, 18:00:27Z, before the first measured call (18:24Z). `verify_artifacts.py` checks the
  commit time.
- **D4.** build-driver.sh records the binary sha256 on the host. Every session re-read
  `--version`/sha256 in-session (`session-env.txt`), and `verify_artifacts.py` checks them against
  PREREG.
- **D5 (packet completeness, post-review fix).** The first packet commit `1fed0037b` left out 34 raw
  files. The repo-wide `.gitignore` rules `*.log` and `build/` dropped them, so they existed only in the
  worktree and the mirror. Missing were: the 8 S-W/S-X `oracle/wayland-capture-lines.log` files (the raw
  compositor oracle behind S-W KEEP), every `session.log` (including the aborted SX-U-T2 one),
  `raw/batch.log` (D1), `raw/unit/*.log` (red/green), and `raw/build/*.log`.
  - A packet-local `.gitignore` now re-includes `*.log` and `build/`, and the 34 files are committed
    unchanged (same bytes as the mirror).
  - `verify_artifacts.py` gained checks 8 to 10:
    - every cited or promised raw file exists, and no packet file is git-ignored and untracked;
    - the raw compositor log is re-attributed to the recorded windows;
    - the per-session timing medians match raw/.
  - No data, count or disposition changed.
- **Pilots.** Four pilots ran before PREREG; they are disclosed there and excluded. Pilot 2 is why the
  walk oracle is GetState rather than "any AT-SPI call": it found the 6-call lookup.

## Limits and claim boundary

- Covered: headless sway 1.12 / wlroots 0.20.2 (kit), pixman renderer, 1 seat, 1920x1080, Xwayland
  24.1.13, and X11 on a private Xvfb. The fixture is the GTK3 task window (9 elements). The binaries are
  U `b39b866f7` and F `dd205d17b`, both on upstream main 989cc76ce.
- Not covered:
  - Hyprland (BLOCKED, real seat), macOS and Windows (BLOCKED, hardware);
  - other compositors (KWin, GNOME), multi-seat, other toolkits and Chromium trees;
  - floating or small windows on sway, `screenshot_out_file`, and the overlay root-region path (never
    triggered).
- The S-W capture oracle has no per-client id. Attribution relies on time windows and on there being no
  other screencopy client in the private session; idle and non-capturing windows show 0.
- Timing is per `get_window_state` call on this fixture and window size, not whole-task. It was taken on
  a shared machine under the quiet-lane lock.
- Invariants: no new service and no schema change. The marks are measurement-only, env-gated and off by
  default (smoke PASS). The fix is argument validation only: boolean and omitted selectors behave as
  before (F = U on every non-string row). Marks and events are never a success or freshness oracle.
- Infra note (shared, not this lane's): `cua-x11-session.sh` under hostless puts its D-Bus socket in
  the host `/tmp`, as the stack track also recorded.

## Provenance

| item | value |
|---|---|
| upstream main tested | 989cc76cec262ff8bcf6968b637820340fb9caaa (includes trycua/cua PR 4318, db5573914) |
| live upstream main at analysis | da46c4bc85bc43f9641d3ce4b6f319e6d7b6c1a9 (1 commit ahead, 0 `libs/cua-driver` files) |
| live upstream main at review fix | 0f1955d2f1ee2b01b40775aa53ea2af0b5544218 (6 commits ahead of 989cc76ce). trycua/cua PR 4375 (920a42f10) edits `platform-linux/src/tools/impl_.rs` `get_window_state`: it changes the first-snapshot walk timeout budget, not the selectors. `dd205d17b` merges onto it with no conflict (`git merge-tree`); the selector test has not been re-run on that tree. |
| marks port | 709b0e004 (cherry-pick of 28b915ae9), b39b866f7 (cherry-pick of cd9d6d169) |
| U (tested source) | b39b866f7892677048862e8d5d8539f30b43efc2; sha256 e4ebdff907188f9e84bae9945b1706a6bed4bec3d863e26567bba3eca4899cb4; `cua-driver 0.32.0` in-session |
| F (tested source) | dd205d17b1590a1a48c76d34173d7b2b831de0ff; sha256 066ed4ef1310440dba1592e436006d65513084db42527a15c7439707c089ed8b; `cua-driver 0.32.0` in-session |
| PREREG | bf77bf781cb2c05b74db8bc8692f885e1bd21625, committed 18:00:27Z; first measured call after 18:11Z |
| harness origin | OWN-16 packet 7a4f3252a (frozen in 777149eae); diff in `harness-origin.diff`; `xrecord_capture.py` unchanged |
| unit | red: selector test FAILED on U; green after the fix; F tree: cua-driver-core phase_trace 6/6, platform-linux 603 + 8 passed, 0 failed |
| live PR heads | none relevant (the fix is new on this branch; PR 4318 is merged in the tested main) |
| publication SHA | recorded by the Publish agent; this lane does not push |
| provider | none: 0 attempts, 0 reached |

## Next

- Publish `dd205d17b` as a standalone fix candidate. It applies to 989cc76ce without the marks: it
  touches only `get_window_state`'s invoke and adds one test module. Before publishing:
  - rebase it onto live upstream main (0f1955d2f merges cleanly, see Provenance) and re-run
    `get_window_state_selector_tests` on the rebased tree;
  - say in the PR body that it is **Linux-only**. macOS (`platform-macos/src/tools/get_window_state.rs:250`)
    and Windows (`platform-windows/src/tools/impl_.rs:1331`) still read the selectors with
    `as_bool()`, so a string value still means the default there.
  - say that it also refuses JSON `null`, which used to mean the default. No in-repo client sends null:
    the SDK input skips `None` via `skip_serializing_if`, and the schema says boolean. Third-party
    clients that send null will now get `invalid_arguments`.
- #100 track: the native-Wayland 6-call AT-SPI identity lookup on every `get_window_state` call; S-W
  elements without `screenshot_frame`; frame/scale handling on downscaled sway captures; seat binding.
- #10 accounting: on sway-tiled windows, `include_screenshot:false` is worth about 150 to 166 ms per
  observation (vs about 3 ms on OWN-16's 480x320 X11 window). It should enter only weighted by how
  often a task can skip the image.

## Files

- `PREREG.json`: pre-registration and frozen file hashes.
- Harness: `modality_truth.py`, `run_in_session.sh`, `run_batch.sh`, `run_resume.sh` (D1),
  `xrecord_capture.py`, `collect.py`, `harness-origin.diff`.
- Analysis: `analyze.py` (D2 diff in `analyze-deviation.diff`) recomputes `own-16w-summary.json` from
  `raw/`.
- `verify_artifacts.py` (stdlib) checks:
  - the summary recomputation, and n = 42 with 0 exceptions per row;
  - the frozen hashes, with the D2 change accepted only as disclosed;
  - the in-session binaries, and PREREG-before-trials;
  - the quiet-lane receipts, the README dispositions, and a privacy scan (pass `--host` to also scan
    for the host name);
  - that every cited or promised raw file exists and none is git-ignored (D5);
  - a re-attribution of the raw compositor capture log to the recorded windows;
  - the per-session timing medians.
- `.gitignore` (packet-local): re-includes `*.log` and `build/` (D5).
- `provenance.json`.
- `raw/<MODE>/<BIN>/<ID>/`: `calls.jsonl`, `session-env.txt`, `session.log`, `phase-*.jsonl.gz` and
  `oracle/` (X RECORD events, gzipped dbus-monitor log, compositor capture lines).
- `raw/aborted/SX-U-T2/` (D1), `raw/unit/`, `raw/build/`, `raw/batch.log`,
  `raw/quiet-lane-receipts.jsonl`.
