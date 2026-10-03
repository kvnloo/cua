# FIX-05: the native index-fallback residue on current main. scroll and the set_value fallback were pid-wide (one of them even for live tokens); F7 keeps them in the token's window (2026-10-03)

Owners: kvnloo/cua#36, kvnloo/cua#105, kvnloo/cua#73 (E4 invariants). Wave 8 of the CUA RFC loop.
Fork fix candidates on trycua/cua main `a9baa8d10` with the FIX-02/03/04 chain (F6) replayed on top. Nothing
here is merged anywhere, and nothing was pushed or posted by this lane.

## Result in one paragraph

- **E6 recert: the F6 chain replays cleanly onto current main.** All 14 commits were cherry-picked in order
  onto `a9baa8d10`. Patch-ids are equal for 14/14, with no conflicts (`raw/replay.txt`). **CT-recert passes:**
  FIX-04's CT row, run with the blob-identical FIX-04 harness and fixture, shows **F5m 20/20 cross-window**
  (positive control) and **F6m 0/20** (refused `stale_element_token` 20/20). B's tail is 20/20 on both arms.
- **R-SC (scroll -> `scroll_element(pid, idx)`): HOLE, KEEP with fix F7.** On F6m, session A's own token for
  its closed window w1 scrolled session B's window w2 **20/20**, with a success-shaped receipt
  (`effect: unverifiable`). The negative control found a second, larger hole: with **both windows open**, B's
  own **live** w2 Scroll token scrolled **w1** in **20/20** attempts (and w2 in 0/20). The scroll tool resolves
  every element token against a walk of the whole application in the application's window order. Snapshot
  indices come from a walk that visits the snapshot's own window first, so a token for any window except the
  application's first one names the first window's control. **F7m: 0/20 cross-window, refused
  `stale_element_token`, `effect: refused` 20/20. With live tokens each window scrolls only itself (20/20 per
  window).**
- **R-SV (set_value -> `set_value_in` -> `set_value(pid, idx)` fallback): HOLE, KEEP with fix F7.** On F6m,
  A's closed-w1 Note token wrote into w2's Note **20/20**, with receipt `effect: unverifiable`. **F7m 0/20**,
  refused `stale_element_token` / `effect: refused` 20/20. Live tokens are clean on both binaries (the cached
  object path).
- **R-PA (`perform_action(pid, idx)`): KEEP without fix (SOURCE).** No public element-token tool reaches it.
  click, double_click and right_click resolve through `perform_action_observed`, which never re-walks. Only
  the Driver's own browser consent and setup UI call `perform_action(pid, idx)` (a follow-up is listed below).
  REAL through click: F6m 0/20 and F7m 0/20, refused `stale_element_token` (`effect: "none"`, unchanged code).
- **R-CF (focus): discriminating REAL row, KEEP.** The X11-reachable focus-by-token route is hotkey with
  `delivery_mode: foreground`. Its GrabFocus runs *before* the window activation. On **F5m**, A's closed-w1
  checkbox token moved w2's focus to w2's checkbox in **20/20** attempts (the fixture's own focus log), while
  A's receipt said `foreground_unavailable ... no input was sent`. **F6m 0/20** (F6c already scopes
  `focus_element`, but the refusal was a bare tool error: code `tool_invocation_failed`, no effect).
  **F7m 0/20**, refused `stale_element_token` / `effect: refused` 20/20.
- **R-WT (Hyprland / Wayland-inject type_text fall-through): SOURCE + UNIT, KEEP without fix.** On F6m both
  fall-throughs reach F6c's window-scoped `focus_element` and window-targeted delivery, so no pid-wide walk
  remains. The inject route needs a cua-compositor socket, which the sway session does not provide. The
  Hyprland route is BLOCKED (hardware: real Hyprland seat).
- **Negative controls on F7m:** NC (both windows open, live tokens, both sessions) gives own-window effect
  20/20 with the other window unchanged 20/20 for each of 4 tools x 2 windows. NS (single window, single
  session): 20/20 own effect for each of the 4 tools (F6m is identical). Suites are green on F6m and F7m (core 868/0; platform-linux 606/0 -> 610/0; jev-use
  Python 245 OK, TS 121/121). UNIT is red on F6m+tests and green on F7m.
- **Provider:** TypeSafe was not used. 0 attempts, 0 reached (lane cap 0).

## Dispositions (pre-registered gates; `dispositions.json` from `analyze.py --write`)

| Item | Disposition | Gating evidence | Evidence class |
|---|---|---|---|
| E6 replay of F6 onto `a9baa8d10` | **recertified** | patch-id equal 14/14, 0 conflicts; CT F6m 0/20, F5m 20/20 | SOURCE, REAL+FIXTURE |
| R-SC scroll_element | **HOLE on F6m -> KEEP (F7)** | F6m 20/20 cross-window (+ live-token NC 20/20 into w1); F7m 0/20, refused 20/20 | REAL+FIXTURE, UNIT, SOURCE |
| R-SV set_value fallback | **HOLE on F6m -> KEEP (F7)** | F6m 20/20; F7m 0/20, refused 20/20 | REAL+FIXTURE, UNIT, SOURCE |
| R-PA perform_action(pid, idx) | **KEEP without fix** | no public token caller (SOURCE); click F6m 0/20, F7m 0/20 | SOURCE, REAL+FIXTURE, UNIT (pin) |
| R-CF focus (hotkey fg) | **discriminating; KEEP (F6c scope + F7 receipt)** | F5m 20/20 cross-window focus; F6m 0/20 (bare error); F7m 0/20 refused 20/20 | REAL+FIXTURE, UNIT |
| R-WT Hyprland / inject fall-through | **KEEP without fix (SOURCE)**; Hyprland BLOCKED | no pid-wide walk on F6m (source-audit.json WT) | SOURCE, UNIT (F6c pin) |
| F7 overall | **KEEP: reviewed product-fix candidate (pending owner review, same ruling class as F6c)** | every pre-registered F7 gate met | REAL+FIXTURE, UNIT |

## The five mechanism requirements

| Requirement | R-SC / R-SV / R-CF / R-PA | CT-recert | NC / NS |
|---|---|---|---|
| Forced path | the token's window w1 is closed by the fixture (SIGUSR1, confirmed on its state file 20/20 every arm), A uses its OWN valid w1 token: the cached AT-SPI object is gone (set_value, focus) or never consulted (scroll), so the index is re-resolved | FIX-04's forcing unchanged | both windows open; live tokens of each session for its own window |
| Actual route / producer | ScrollTool -> `atspi::scroll_element`; SetValueTool -> `set_value_in` -> `native::set_value`; HotkeyTool fg -> up-front `atspi::focus_element`; ClickTool -> `perform_action_observed` (receipts + SOURCE line map) | TypeTextTool -> `type_into_editable_at` | same tools, live path |
| Independent target-owned oracle | the GTK3 fixture's own state file per window, written by the fixture process (`scroll_value`, `note_text`, `agreed`, `focus`, `focus_log`), read before and after every call; B's own tail call on w2 | the same file (`note_text`) | the same file |
| Negative / fallback controls | B's own-token tail on w2 20/20 on every arm; F5m positive control for R-CF and CT; F7m live tokens in NC (no false refusal) | F5m arm | F6m arm (shows the live scroll mismatch) |
| Tested source / binary | F5m `d5447e9d3` / F6m `c07691e09` / F7m `66afb3427`; sha256 below; `cua-driver 0.33.1` in every block header | F5m, F6m | F6m, F7m |

## Provenance (each SHA kept separate)

| Item | Value | Class |
|---|---|---|
| Upstream base (trycua/cua main at lane start) | `a9baa8d107fba8b0aef5a4ed6233e498e88d14d0` (libs/cua-driver tree `98aaae2c1afa`) | SOURCE |
| F6 chain source | kvnloo/cua branch `exp/fix-04-unknown-delivery-effect-20261003` @ `2b59a66f7` (commits `0fd76ecc5` .. `802700282`) | SOURCE |
| F5m (replay through `2237cf9c6`) | `d5447e9d3d7ba41c25bd43ca132ff01371b98df8`; binary `cua-driver-fix05-f5m-d5447e9d3`, sha256 `4778ada19ae343aed9ebae4ff43db36921bf65459094df535694a658aa0e37e1` | SOURCE |
| F6m (full chain) | `c07691e09ec4c5e1edcb790057ae9480ec9e2505`; sha256 `b8efb6ec89a2920128e3100364d8aa3999fa1decb111eae0540bbfceb9767830` | SOURCE |
| F7 = F7m | `66afb3427943dd41ad3db5985835506429e852f9` (atspi/mod.rs, atspi/native.rs, tools/impl_.rs); sha256 `220b5e11145f74539739967dbfc5ddaca5ccfef3574b3d302dc2714dc13d806a` | SOURCE |
| Versions | `cua-driver 0.33.1` in every counted block header (read inside the private session) | SOURCE |
| Builds | `build-driver.sh` under hostless, shared quiet hold then the cargo lock, target dir `cua-release-fix02r`, 0 Fresh workspace units each (`raw/builds/`) | SOURCE |
| PREREG + harness | `04665bd2d688bd3709ef83a991cdc6c1e96e0169`, committed 2026-10-03T21:38:12Z; the first counted lock acquisition was 21:47:44Z | SOURCE |
| Live heads at start (20:59:39Z, `git ls-remote`) | trycua/cua main `a9baa8d10`; trycua/cua PR 4316 `a0bca7440`; kvnloo/cua#105 `98a45e6c5`; kvnloo/cua#106 `c45845797` | SOURCE |
| Live heads at end | 23:35:50Z: trycua/cua main `a597517d8` (moved; `a9baa8d10..a597517d8` touches only `libs/cua-driver/scripts/_install-rust.sh` and `install.ps1`, none of the files FIX-05 or the F6 chain touch: `raw/heads/drift-end.txt`); trycua/cua PR 4316 `b2ae7cb93` (moved from `a0bca7440`; not an input of this lane); kvnloo/cua#105 `98a45e6c5` (unchanged); kvnloo/cua#106 `c45845797` (unchanged); FIX-04 branch `2b59a66f7` (unchanged) | SOURCE |
| Publication SHA | set by Publish, never equal-by-assumption to the tested SHAs | SOURCE |
| Environment | Linux 7.2.2 x86_64, rustc 1.97.1; `bin/hostless` v2; `cua-x11-session.sh` (private rootless Xvfb, openbox, picom, private D-Bus, AT-SPI); system python3 + gi fixture; jev-use Python 3.12.13 / Node v22.23.2; telemetry off | SOURCE |
| Provider | TypeSafe: 0 attempts, 0 reached | SOURCE |

## The fix (F7 `66afb3427`)

- `atspi/mod.rs`: `scroll_element(pid, xid, ..)` now takes the token's window and computes F6c's
  `token_frame`. A window-scoped token with no snapshot entry is `CachedElementGone`. The `set_value_in`
  fallback passes the window and the frame the same way.
- `atspi/native.rs`: `collect_visited_in(conn, pid, xid)` walks in the snapshot's index space (the token's
  window first, as the snapshot walk does). `scroll_element` and `set_value` resolve the index through F6c's
  `indexed_node(.., frame)`, so a node outside the token's window is `CachedElementGone`. Window-less callers
  (xid 0) keep the application walk.
- `tools/impl_.rs`: scroll, set_value and hotkey refuse `CachedElementGone` before any dispatch with
  `{code: stale_element_token, effect: refused}`. Scroll no longer falls through to the pixel or wheel routes
  for such a token.

No new service, state, effect variant or seam. Default behaviour changes only for an element token whose
element is not in its own window, which is the same class as F6c. F7 is a reviewed product-fix candidate
pending owner review.

## Method

- **Isolation and locks.** Every code-executing command ran under `bin/hostless`. REAL blocks ran in a private
  `cua-x11-session.sh` with `CUA_SESSION_ATSPI=1` (also in `CUA_SESSION_EXTRA_ENV`). Each of the 30 counted
  blocks held one SHARED quiet-lane lock through `harness/qlock_fix05.sh`: the lock fd is closed for the
  children, the wrapper yields to queued exclusive waiters, and holds are at most 300 s. Actual holds were
  42-136 s, every rc was 0, and acquisitions were at least 30 s apart. The receipts are in
  `raw/lock-ledger.jsonl` and the loop-wide ledger. Builds and unit steps took the shared hold first and the
  cargo lock second.
- **Topology.** T2: one `cua-driver serve` daemon per block and two `mcp --socket` clients (sessions A and B).
  Each attempt used a fresh fixture. Observation order alternated AB/BA, binaries were interleaved inside
  every row (`plans/1-all.txt`), and every attempt was kept.
- **Harness.** The FIX-04 / FIX-03 helpers are copied blob-identically, with git blob ids and sha256 in
  `harness/COPIED_MANIFEST.txt`. CT-recert runs FIX-04's `fix04_native.py --row CT` and FIX-04's fixture
  unchanged. `harness/native/fix05_native.py` imports the FIX-04 copy and adds the FIX-05 rows. The fixture
  copy adds an opt-in scroll region after every task control, so the task indices stay unchanged:
  checkbox 2, Note 6, Scroll 10 in both windows. It also adds a per-window focus log written on
  `GtkWindow::set-focus` and single-window `note_text` (`harness/gtk3_main_two_windows.fix05.diff`).

## Results (N of M, evidence class per row)

Cross-window effect = w2's state changed during A's call (pre/post reads of the fixture's own file).

| Row | Arm | Cross-window effects | A's receipt | B's tail on w2 | w1 close confirmed | Class |
|---|---|---|---|---|---|---|
| CT-recert type_text | F5m | **20/20** (`note_text`) | success, `effect: unverifiable` 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| | **F6m** | **0/20** | refused `stale_element_token` (`effect: "none"`) 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| R-SC scroll | **F6m** | **20/20** (`scroll_value`) | success, `effect: unverifiable` 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| | **F7m** | **0/20** | refused `stale_element_token`, `effect: refused` 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| R-SV set_value | **F6m** | **20/20** (`note_text`) | success, `effect: unverifiable` 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| | **F7m** | **0/20** | refused `stale_element_token`, `effect: refused` 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| R-PA click | F6m | 0/20 | refused `stale_element_token` (`effect: "none"`) 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| | F7m | 0/20 | same (unchanged path) 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| R-CF hotkey fg | F5m | **20/20** (`focus`, `focus_log`) | `foreground_unavailable` "no input was sent" 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| | F6m | 0/20 | bare error (`tool_invocation_failed`, no effect) 20/20 | 20/20 | 20/20 | REAL+FIXTURE |
| | **F7m** | **0/20** | refused `stale_element_token`, `effect: refused` 20/20 | 20/20 | 20/20 | REAL+FIXTURE |

**NC (both windows open, live tokens; own-window effect / other window changed, of 20)**

| Tool:window | F6m | F7m | Class |
|---|---|---|---|
| click:w1 / click:w2 | 20 / 0, 20 / 0 | 20 / 0, 20 / 0 | REAL+FIXTURE |
| scroll:w1 | 20 / 0 | 20 / 0 | REAL+FIXTURE |
| **scroll:w2 (B's live w2 token)** | **0 / 20 (w1 scrolled)** | **20 / 0** | REAL+FIXTURE |
| set_value:w1 / set_value:w2 | 20 / 0, 20 / 0 | 20 / 0, 20 / 0 | REAL+FIXTURE |
| hotkey:w1 / hotkey:w2 (focus) | 20 / 0, 20 / 0 | 20 / 0, 20 / 0 | REAL+FIXTURE |

**NS (single window, single session; own effect of 20 per tool):** click 20/20, scroll 20/20, set_value 20/20, hotkey-focus 20/20 on F7m and on F6m (REAL+FIXTURE).

## E4 counters (`summary.json` e4)

| Counter | F5m | F6m | F7m | Class |
|---|---|---|---|---|
| Cross-window (stale/foreign) dispatches, closed-window rows | CT 20, R-CF 20 | R-SC 20, R-SV 20, CT 0, R-PA 0, R-CF 0 | **0** on every row | REAL+FIXTURE |
| Live-token foreign-window effects (NC) | n/a | **20** (B's scroll -> w1) | **0** | REAL+FIXTURE |
| Success-shaped receipts for a foreign effect | CT 20 | R-SC 20, R-SV 20 | 0 | REAL+FIXTURE |
| Error receipt that hid a landed foreign effect ("no input was sent") | R-CF 20 | 0 | 0 | REAL+FIXTURE |
| Pre-dispatch refusals receipted `effect: refused` | 0 | 0 | R-SC 20, R-SV 20, R-CF 20 | REAL |
| Pre-dispatch refusals receipted otherwise | - | CT/R-PA `"none"` 40, R-CF no effect 20 | R-PA `"none"` 20 (click, unchanged) | REAL |
| Blind replays | 0 | 0 | 0 | REAL (one A call per attempt) |

## Unit evidence (`raw/unit/`)

| Tree | Result | Class |
|---|---|---|
| red-1: F6m + `raw/unit/red/red1-tree.diff` (set_value test + click pin) | `window_scoped_set_value_without_its_snapshot_is_stale_not_resolved_pid_wide` **FAILED** (it tried the pid-wide AT-SPI walk); pin ok | UNIT |
| red-2: F6m + `red2-tree.diff` (+ scroll test) | **does not compile** (`E0061`: F6m's `scroll_element` has no window parameter to scope by) | UNIT |
| green F7m | the 4 FIX-05 tests ok; core 868/0; platform-linux 610/0 (10 ignored); jev-use Python 245 OK (1 skipped), TS 121/121, typecheck rc 0, 4 CLI verifiers rc 0 | UNIT |
| green F6m | core 868/0; platform-linux 606/0; jev-use identical | UNIT |

The two `guarded-focused` jev-use steps do not apply on this base (rc 5 / rc 1: no such test file), as in
SETUP, FIX-03 and FIX-04. `cargo fmt --check` flags 4 hunks in replayed F6c / FIX-03 code (unchanged here).
F7's own lines are formatted.

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Class |
|---|---|---|---|
| F7 scroll | cross-session writes from a session's own closed-window token: 20 -> 0. Live-token foreign-window scrolls: 20 -> 0 | none claimed | REAL+FIXTURE |
| F7 set_value fallback | cross-session writes: 20 -> 0 | none claimed | REAL+FIXTURE |
| F7 hotkey receipt | refusals without a code or effect: 20 -> 0 | none claimed | REAL |

No timing claim. The correctness rows were not timed.

## Deviations

1. **Near miss (no effect possible).** At lane start, two plain-shell `python3 -c` one-liners that only parsed
   loop `STATE.json` ran outside `bin/hostless`. They imported no GUI, display, bus or network module, and
   the shell's Python host-display guard strips desktop variables. Every later code-executing command ran
   under `bin/hostless`.
2. **Lock yield cap.** `qlock_fix05.sh` yields to a queued exclusive waiter for at most 600 s. Five
   blocks hit the cap: `NC-F6m-n3`, `NC-F7m-n4`, `NS-F7m-u1`, `NS-F6m-u3` and `NS-F7m-u4` (`yield_s` 600 in
   the ledger). The exclusive waiters were queued behind another track's hour-long shared hold. After the cap,
   each block took its own shared hold of at most 136 s. The spec asks for an unconditional yield, so this is
   a procedure deviation. No timing is claimed, and every hold is in the ledger.
3. **R-PA through click.** No public element-token tool resolves to `perform_action(pid, idx)`. The row
   measures the public element action (click, via `perform_action_observed`). Per the PREREG this makes it
   KEEP without fix, with the SOURCE reason.
4. **R-CF route.** The focus row uses hotkey with `delivery_mode: foreground`, because its GrabFocus runs
   before the window activation. press_key and type_text activate the closed window first and refuse
   (FIX-04 CF). This makes the row discriminating (F5m 20/20).
5. **Changes after shakedown, before PREREG.** Hotkey's `CachedElementGone` was mapped to the stale refusal,
   and the single-window fixture publishes `note_text`. Both are listed in PREREG `shakedown_before_prereg`,
   and the shakedowns are kept in `raw/shakedown*/`.
6. **Remote-tracking fetch.** For the end drift check, one `git fetch upstream main` updated the main clone's
   remote-tracking ref `upstream/main` (read-only on GitHub). No branch, worktree or `refs/heads/main` was
   changed.
7. **One shakedown block failed to start** (`xdpyinfo` probe failed). It was re-run as `s1R`. This was not
   counted. Every counted block recorded 10/10 attempts with rc 0.

## Limits and claim boundary

- Same-process, two-window GTK3 on X11 (private Xvfb, openbox, AT-SPI) only. macOS and Windows are BLOCKED
  (hardware). Hyprland is BLOCKED (real seat). The Wayland-inject route is SOURCE only.
- Isolation between distinct sessions of one Driver, not adversarial isolation.
- F6c's own fallbacks (`type_into_editable_at`, `focus_element`) still re-resolve against the
  application-order walk. For a live token of a non-first window whose cached object fails they now refuse
  (fail-safe: the frame check) instead of acting. F7's `collect_visited_in` would make them resolve
  correctly. This is not changed here.
- Follow-ups (not measured): (a) `browser_consent_ui.rs` / `browser_setup_ui.rs` pass an index from
  `walk_tree(pid, window_id)` (window-first order) to the pid-wide `perform_action(pid, idx)`. This is an
  index-space mismatch candidate when the browser process has more than one top-level frame. (b) The existing
  click / type_text `stale_element_token` envelopes carry `effect: "none"`. That is not a public effect name,
  and `action_record.rs:693-699` maps it to Unverifiable in the internal record.
- Fork candidates on `a9baa8d10`. Not merged anywhere. No new service. The FIX-03 seam (`5a1e209ab`) is
  present in every binary, stays default-off and is not set by any row.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed `04665bd2d` before the first counted block |
| `plans/1-all.txt` | the 30 counted blocks in run order |
| `analyze.py` -> `summary.json`, `dispositions.json` | every row, gate and E4 counter from `raw/` (`--inspect <jsonl>` for a per-call view) |
| `verify_artifacts.py` | independent recomputation (no import of analyze.py), blob manifest, fixture diff, binaries, locks, PREREG order, units, privacy of the packet and of every lane commit: `CUA_PRIVACY_NAMES_FILE=<file> python3 verify_artifacts.py --git <repo>` |
| `provenance.json`, `source-audit.json` | SHAs, trees, binaries, environment; the SOURCE map with file:line |
| `harness/` | `qlock_fix05.sh`, `campaign_fix05.sh`, `native/fix05_native.py`, the fixture copy + diff, `unit/`, `copied/` (blob-identical FIX-04 / FIX-03 files, `COPIED_MANIFEST.txt`) |
| `raw/native/<arm>/<row>/b<block>.jsonl` | every call with pre/post fixture state and the raw receipt |
| `raw/session-*.log`, `raw/lock-ledger.jsonl` | per-block session output (sanitized at capture), the 30 counted lock receipts |
| `raw/unit/`, `raw/builds/`, `raw/replay.txt`, `raw/heads/`, `raw/shakedown*/` | unit red/green logs and diffs, build summaries and lock receipts, the replay patch-ids, live heads, shakedowns |
