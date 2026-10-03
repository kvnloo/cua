# OWN-20G: focus-guard final diff on the deadline exit, the CL clamp re-test, and the AT-SPI bus restart row, 2026-10-03

Owners: kvnloo/cua#20 (focus/event input, bus restart row), kvnloo/cua#93 (N-02 follow-ups: CL, settle overshoot). Wave 4, attempt 2. Advances E1 (#20: three open items get terminal outcomes), E2 native (a valid CL verdict on the ~21 ms settle overshoot) and E4 (the default guard's silent steal miss).

## Result

| Item | Verdict | Evidence |
|---|---|---|
| **Guard fix G** (final diff when the settle watch ends on its deadline after a stalled read) | **KEEP, fork candidate.** It closes the c08-017 hole: on the faithful reproduction, G restored **20/20 + 20/20** steals; U missed **20/20 + 20/20** silently | UNIT red/green; REAL R1 (reply-delay stall); default path unchanged (settle 241 ms in both binaries) |
| R1 as the planner specified it (XGrabServer stall) | gate **fails for G and for U alike**: the grab exercises a different path that G does not change (see R1) | REAL |
| **CL** (settle-poll clamp, deletes the ~21 ms overshoot) | **KILL** (pre-registered gate). The saving is real: 21.012 ms on checkbox and 20.236 ms on text, both CIs excluding 0. But valid trials have misses in both arms, and validity is not 100%. The overshoot buys real coverage: band steals landing 225-240 ms are restored by G and left on the decoy by G+CL | REAL + BENCHMARK |
| **R3 a11y bus restart** (#20, new) | gate **fails on liveness, safety holds**. In 40/40 trials (U and G): a structured degraded tree, the pre-restart token refused, 0 stale mutations. In 0/40 did the same Driver process recover a usable tree. A fresh Driver process does (40/40) | REAL |
| E4 | default guard (U): **40 silent steal misses** in R1. G: 0 in R1, 1 near-boundary in R2. 0 stale-token actions. 0 unverified successes | |

Provider: none (TypeSafe cap 0: **0 attempts, 0 reached**). Evidence classes per row are in the last section.

## Provenance (each SHA separate)

| Item | Value |
|---|---|
| Upstream main at planning / live at start (2026-10-03T02:40:19Z) | `41c34cb0d704d816e612dd3f9d0c816cdfacf178` (committer 02:09:19Z); its `libs/cua-driver` tree `df2b49c32e73` equals `0f1955d2f`'s |
| Upstream main live at end (05:26:14Z) | `67c2f39af41edc832642178868c567a1afd8d240`, 1 commit ahead of `41c34cb0d`, 0 files under `libs/cua-driver` |
| kvnloo/cua#106 (layout reference) | `c45845797b714ccfd76a9569d3238a0724107a83`, open (start and end) |
| Fork main | `da46c4bc85bc43f9641d3ce4b6f319e6d7b6c1a9` (start and end) |
| **U** (tested base) | `bdf33d9fe4d716033089244a6571db21934374d6` = `0f1955d2f` + `74d178575` (pick of `28b915ae9`, R2-04 marks) + `20243ea20` (pick of `b9b357bc7`, N-01R knobs) + `bdf33d9fe` (pick of `194a6342e`, N-02 settle_poll marks + `CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP`). All measurement-only, default off. `git range-diff` shows every pick `=` its source, with identical stable patch-ids (`raw/source/range-diff.txt`). trycua/cua PR 4375 overlaps only `platform-linux/src/tools/impl_.rs`, which merges clean, with 0 conflict markers (`raw/source/pr4375-overlap-a2.txt`; attempt 1's record in `raw/source/attempt1-u-assembly-pr4375.txt`) |
| **G** (tested fix) | `a30cbbc3b230e8bad7d86ae1e89866d4f9cdd1af` = U + one commit, touching only `libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs` |
| PREREG | `d17a8c0b4`, committed 2026-10-03T04:08:00Z, before the first counted trial (block `s01`, 04:08Z+). Supplement plan `5c9a97e2c` (05:15:28Z), committed before its first trial |
| Driver U | `cua-driver-own20g-a2-u-bdf33d9fe`, sha256 `f0fe3219e5e0d4227d57128f3f4f2c487f54462d206d0fbe3ea9317c56eb41eb`, `cua-driver 0.32.0` |
| Driver G | `cua-driver-own20g-a2-g-a30cbbc3b`, sha256 `66e303c7167d6bd912b628f5d2558f9fafa6695bb1b7cafdafba2914595aa6ff`, `cua-driver 0.32.0` |
| Builds | `build-driver.sh` into the `cua-release-n02` family dir, under the cargo-build lock, 0 Fresh workspace units, rustc 1.97.1 (`raw/build/`). Versions were read inside a private session (`raw/build/driver-versions-session.txt`) |
| U rebuild vs attempt 1 | not bit-identical (attempt 1: `b4ef51d4...`). Same HEAD and rustc; cargo hashes the path-package source path into symbol metadata, and the worktrees differ (`raw/build/u-rebuild-compare.txt`). Attempt 1's binary is used nowhere |
| Publication SHA | set by the Publish agent (`provenance.json: publication_sha`) |

**Attempt 1 (aborted).** It built U, left an unreviewed rewrite of `focus_guard.rs` (−36/+16 in the settle watch), and ran **no counted row**. That draft was not used. It refactored the restore loop too, and it re-anchored the restore budget for every late change, which adds a second behaviour (see "The fix"). Attempt 1's branch and worktree were not touched.

## The fix (G)

The settle watch polls every 30 ms until 220 ms and stops at the first change. The deadline is checked after each poll. A poll whose X reads began before the deadline but returned after it, because an X call stalled across the deadline, ended the watch on stale data. N-02 trial `c08-017` is exactly this case: polls at 30, 60 and 90 ms; the next X call stalls until 2.4 s; the steal lands at 217 ms; nothing is reported.

G adds, at the end of the settle watch:

```rust
// The watch ended on its deadline with nothing seen, but its last read
// began before the deadline (an X call stalled across it): read once
// more, so a change that landed during the stall is not missed, and give
// its restore the whole budget from this read.
let mut restore_from = started;
if changes.is_empty() && own_window.is_none() && read_at < watch_until {
    restore_from = Instant::now();
    changes = diff();
}
```

and `let deadline = restore_from + RESTORE_BUDGET;` in the restore loop.

- **One behaviour.** After G, a quiet watch always ends on a read that began at or after its deadline. Without a stall the last poll already starts about one poll past the deadline (241 ms), so the normal path takes **no extra read**. The default-off smoke confirms it: settle 240.8-242.5 ms on both binaries, no `exp_knob` marks.
- **Restore budget.** It is re-anchored **only for a change found by this final read**: otherwise the 600 ms budget from the guard's start has run out after a 2 s stall, and the restore could not be verified.
- **Unchanged.** No new timer, constant, knob or service. The watch window, poll period, restore budget, same-app rule, popup rule and every other path are unchanged.
- **The settle loop moved, unchanged,** into `fn settle(started, watch, diff, windows)` so that a test can drive it with a fake, stalling read. The extraction is checked by the red tree: every existing test passes there.

**UNIT (red/green; `raw/unit/unit-red-green.log`, cargo-build lock, private session).**
- *Red* = G with only the fix hunk reverse-applied (`raw/unit/fix-only.patch`). `a_steal_during_a_read_stalled_past_the_watch_is_seen` FAILS ("the steal went unseen"); the platform-linux lib has 610 passed, 1 failed.
- *Green* = G. Both new tests pass (2/2), `input::focus_guard` 16/16, platform-linux lib **611 passed, 0 failed**.
- The second new test pins that a quiet watch ends on a post-deadline read without an extra read, and that `watch=None` reads once.
- An earlier red run on the pre-rustfmt tree gave the same result (`raw/unit/unit-red-first-pre-format.log`). A queued pre-commit green job was cancelled before it got the lock (`raw/unit/unit-green-precommit-cancelled.txt`).

## Method

- **Fixture and tasks** (as N-02). The canonical GTK3 task window, one fresh Driver and one fresh fixture per trial.
  - Checkbox, arm S0 (post-DoAction sleep 0): `get_window_state` (tree + screenshot), the jev-use `eligible_controls` lookup, then `click(I agree token, background)`.
  - Text, arm X (S0 + 1 ms cursor glide): the same observation, `set_value(Note)`, then `click(Save note, background)`.
- **Forced path and producer.** AT-SPI DoAction on the cached identity, inside `focus_guard::guarded`. Route `accessibility` in every click; the `focus_guard body_done/settle_poll/restored` marks are present.
- **Oracles.**
  - Task: the app's own state file, read every 2 ms.
  - Focus: `xprobe.FocusSampler`, N-02's module verbatim (blob `f17d83691faa`). It is an independent X client sampling `XGetInputFocus` and `_NET_ACTIVE_WINDOW` every 2 ms.
  - Reference: the sampler's first sample of the first quiet 300 ms after the pre-trial placement, so GTK has settled. This avoids N-02's one-shot snapshot artefact.
  - Receipt: `focus_outcome=` in the click's text. It is checked, never used as an oracle.
- **Steal triggers** are separate processes keyed on the Driver-side `atspi_action do_action_replied` mark. They tail the phase trace and schedule from the mark's own `wall_ns`. Their stamps are schedule records, not oracles.
- **Isolation.** Every code-executing command ran under `hostless` (v2: env scrub + Landlock abstract-unix/signal scope), `hostless-strict` (private tmpfs over the X11/ICE/runtime dirs) and `cua-x11-session.sh`: private Xvfb, openbox, picom, private session bus, private AT-SPI bus + registry, telemetry off.
- **Locks.** Safety blocks used `flock -s` on the quiet-lane lock, ≤ 20 trials per acquisition, with one receipt per block (lane, label, mode, pid, acquired, released, rc, loadavg_at_acquire). Timing used `quiet-timed` (EXCLUSIVE). Builds and units took the cargo-build lock first. Receipts: `raw/lock-ledger.jsonl`.

### R1: why two stall rows (pilots, excluded; `raw/pilots/`)

- **XGrabServer does not reproduce c08-017.** The planner's mechanism is a harness client holding `XGrabServer` for ~2.0 s from ~100 ms, with the steal issued at ~217 ms on another connection. In 8/8 pilot stalls, the server served the guard's queued read **after** the queued steal, so the stalled read *saw* the steal. U then re-asserted once with its restore budget spent and reported `not_restored` (7/8) or `same_app_dialog` (1/8). Opening the steal connection after the guard's (p03) did not change the order.
- **c08-017's own marks** (polls 30/60/90 ms, next mark at 2404 ms, steal at 217.5 ms seen by the sampler in real time) place the stall in the X call **after** the 90 ms poll's diff, the new-client read, with the server answering in real time.
- **The faithful reproduction** is `xstall_proxy.py`, a transparent forwarder of bytes and SCM_RIGHTS between the Driver and the private Xvfb.
  - It parses the guard connection's requests. It holds for 2000 ms the reply to the first new-client read (2nd `GetProperty(_NET_CLIENT_LIST_STACKING)` after a `GetInputFocus`) issued ≥ 80 ms after the mark.
  - The decoy steals at mark + 217 ms on a direct connection. The proxy never delays the decoy or the sampler.
  - It listens on `/tmp/.X11-unix/X<M>` on the session's private tmpfs, with no abstract `@/tmp/.X11-unix/X<M>` anywhere (checked per trial), and the Driver gets `DISPLAY=:M`. See Deviations for the near miss that led here.
- Both rows were pre-registered. The reply row is the gated R1 row; the grab row was run exactly as specified, with its gate reported.

## Results

### Denominators

| Block(s) | Attempted | Valid | Class |
|---|---|---|---|
| s01 default-off smoke (U, G × checkbox, text × 2) | 8 | 8 verified | REAL |
| R1 reply `r1qa-r1, r1qb-r1qd` | 80 | 80 | REAL |
| R1 reply control `r1qe` (proxy on, no hold, no steal) | 20 | 20 | REAL |
| R1 grab `r1ga-r1gd` | 80 | 80 | REAL |
| R1 grab control `r1ge` (grab, no steal) | 20 | 20 | REAL |
| R2 steals (band rounds 1-10, edge + `ecs`, d100 + `dts`) | 484 | 348 (136 invalid by the window rule, every one kept) | REAL |
| R2 no-steal control `nc`, `nt` | 40 | 40 | REAL |
| R2 timing `t01` (EXCLUSIVE, 2 min 57 s held) | 96 | 96 verified | REAL + BENCHMARK |
| R3 `r3a-r3d` | 80 | 80 (0 harness failures) | REAL |
| Failed session start `own20g-r1qa` ("cannot open the private DISPLAY", 0 trials run) | 20 planned, 0 run | | kept; re-run as `own20g-r1qa-r1` |
| Pilots `own20g-pilot0-*` (before PREREG) | excluded | | `raw/pilots/` |

0 non-loopback connects in every block.

### R1: the c08-017 reproduction (REAL; gated)

| Task / binary | valid | pass | silent miss | receipt | final focus | task verified |
|---|---|---|---|---|---|---|
| checkbox / U | 20 | 0 | **20** | none 20 | on the decoy 20 | 20 |
| checkbox / G | 20 | **20** | 0 | restored 20 | = reference 20 | 20 |
| text / U | 20 | 0 | **20** | none 20 | on the decoy 20 | 20 |
| text / G | 20 | **20** | 0 | restored 20 | = reference 20 | 20 |

- The hold starts a median 91.4-91.7 ms after the mark: the read right after the 3rd poll, as in c08-017. Hold 2000.1-2000.2 ms; steal issued 217.0 ms after the mark.
- U's guard ends after the stalled read (settle median 2091.843 ms on checkbox), with polls at 30/60/91 ms only, exactly c08-017's trace.
- G takes the final read and restores (settle 2248.513 ms on checkbox, including the verified restore).
- Control `replyonly`: 0/20 false restores and 0 focus changes; 20/20 verified.
- **Gate (G passes every valid trial, ≥ 20 per task): holds.**

### R1 as specified: XGrabServer (REAL; reported)

| Task / binary | valid | pass | receipt outcomes | final = reference | left on the decoy |
|---|---|---|---|---|---|
| checkbox / U | 20 | 0 | not_restored 19, same_app_dialog 1 | 19 | 1 |
| checkbox / G | 20 | 0 | not_restored 18, same_app_dialog 2 | 18 | 2 |
| text / U | 20 | 0 | not_restored 18, same_app_dialog 2 | 18 | 2 |
| text / G | 20 | 0 | not_restored 18, same_app_dialog 2 | 18 | 2 |

- The grab blocks every client, so the guard's queued read is served after the steal. The read sees it at ~2102 ms; the restore budget (600 ms from the guard's start) is spent; the guard re-asserts once without verification and reports `not_restored`. The focus did return in 18-19/20 per cell.
- In 7/80 trials the stalled read caught core focus on the decoy while openbox had not yet moved `_NET_ACTIVE_WINDOW`. The same-app rule then read the move as the app's own dialog (`same_app_dialog`) and left the focus on the decoy.
- G changes neither path (it is not a deadline exit), so U and G match. The specified gate fails; Next 2 and 3 name the two behaviours involved.
- Control `stallonly`: 0/20 false restores.

### R2: the CL re-test (REAL; pre-registered window-validity rule)

Valid trials, misses (pre-registered rule) and steals left on the decoy outside the arm's window ("uncovered"), per group:

| Task / arm | band valid / attempted | band misses | band uncovered | edge valid, misses | d100 valid, misses | no-steal false restores |
|---|---|---|---|---|---|---|
| checkbox / G (S0) | 55 / 70 | 1 (`xc08-011`) | 12 | 31/31, 1 (`ecs-003`) | 20/20, 0 | 0/10 |
| checkbox / G+CL | 19 / 70 | 2 (`bc02-001`, `xc10-013`) | 51 | 28/31, 0 | 20/20, 0 | 0/10 |
| text / G (X) | 60 / 70 | 0 | 10 | 21/21, 0 | 30/30, 0 | 0/10 |
| text / G+CL | 14 / 70 | 3 (`bt01-003`, `bt06-008`, `xt10-013`) | 56 | 21/21, 0 | 29/30, 0 | 0/10 |

Band steals restored per delay (n = 10 per cell; delays from `do_action_replied`, which precedes the guard's start by ~0.01 ms):

| Delay (ms) | 216 | 220 | 225 | 230 | 235 | 240 | 245 |
|---|---|---|---|---|---|---|---|
| checkbox G | 10 | 10 | 8 | 10 | 9 | 8 | 1 |
| checkbox G+CL | 10 | 7 | 0 | 0 | 0 | 0 | 0 |
| text G | 10 | 10 | 10 | 10 | 10 | 10 | 0 |
| text G+CL | 10 | 1 | 0 | 0 | 0 | 0 | 0 |

**Every valid miss, classified only by the rule and explained (all kept):**
- **Near-boundary (4).** The steal landed after the guard's last read but before its `restored` mark (0.2-1.9 ms before window end). No guard read could see it, but the pre-registered window ends at the `restored` mark. Cases: `bc02-001`, `xc10-013`, `xt10-013` (G+CL, last read at 220.1-220.5 ms) and `xc08-011` (G, last read at 240.995 ms, steal at 241.407 ms).
- **`same_app_dialog` misclassification (3).** `bt01-003` and `bt06-008` (G+CL at 220 ms); `ecs-003` (G, edge 205 ms, loadavg 43.3). The guard read the core focus on the decoy while `_NET_ACTIVE_WINDOW` still named the GTK window. The same-app rule took it for the app's own dialog and left the focus on the decoy. Same mechanism as the 7 grab-row cases.
- **Band extension (pre-registered).** After round 6 G+CL had 11 (checkbox) and 9 (text) valid band steals, so rounds 7-10 ran per task. The final counts are 19 and 14: a **shortfall** against ≥ 20, reported. Every G+CL band steal ≥ 225 ms lands after its 220 ms watch and is invalid by construction.
- **Supplements (pre-registered).** checkbox edge (G+CL 18/21 valid) and text d100 (G+CL 19/20 valid) got 10 supplementary pairs each (`ecs`, `dts`, plan committed at `5c9a97e2c` before they ran).

**Timing (`t01`, EXCLUSIVE quiet-timed, 24 AB/BA pairs per task, no steals; REAL + BENCHMARK):**

| Task | T median G | T median G+CL | saving (median of pair diffs) [95% CI] | settle G → G+CL | settle deleted [95% CI] | loadavg (median) |
|---|---|---|---|---|---|---|
| checkbox | 280.951 | 259.942 | **21.012** [20.461, 23.494] | 240.971 → 220.125 | 20.816 [20.694, 20.965] | 9.83 |
| text | 296.955 | 276.886 | **20.236** [19.975, 21.246] | 240.881 → 220.125 | 20.764 [20.698, 20.943] | 9.165 |

48/48 verified per task; 0 false restores.

**CL gate:** 0 misses in both arms: **no**. Saving ≥ 10 ms with the CI excluding 0: **yes**. Validity 100%: **no**. **CL: KILL.**

The settle loop ends at 240.925 ms (S0) vs 220.148 ms (S0+CL), and 240.886 ms vs 220.137 ms on text (median, quiet guards). The ~21 ms overshoot is not idle time: G restored 35/40 (checkbox) and 40/40 (text) band steals scheduled 225-240 ms after the mark; G+CL restored 0/80 of them.

### R3: AT-SPI accessibility bus restart (REAL)

| Variant / binary | n | pass | pass (safety) | step 3: truthful / structured degradation | stale token refused (code) | stale mutations | new token verified (same Driver) | fresh Driver sees fixture B / A |
|---|---|---|---|---|---|---|---|---|
| bus / U | 20 | 0 | **20** | 0 / 20 | 20 (`stale_element_token`) | 0 | 0 | 20 / 0 |
| bus / G | 20 | 0 | **20** | 0 / 20 | 20 (`stale_element_token`) | 0 | 0 | 20 / 0 |
| registry / U, G | 5, 5 | 5, 5 | 5, 5 | 5 / 0, 5 / 0 | 5, 5 | 0 | 5, 5 | n/a / 5, 5 |
| noop / U, G | 5, 5 | 5, 5 | 5, 5 | 5 / 0, 5 / 0 | 5, 5 | 0 | 5, 5 | n/a / 5, 5 |
| noop_direct / U, G (discriminating) | 5, 5 | expected act | | not observed | 0 (the old token **acted**, 5/5 each) | 5 (expected) | 5, 5 (respawn path) | |
| bus_direct / U, G (exploratory) | 5, 5 | 0 | 5, 5 | not observed | 5, 5 (`stale_element_token`: cached element gone, Broken pipe) | 0 | 0 | 5 / 0 |

- **The restart.** The harness kills the a11y bus daemon (`dbus-broker-launch`, the child of `at-spi-bus-launcher`). The launcher then exits by itself. The old registry does not, so the harness kills it. A new launcher and registry are started (median perturbation 1115.756 ms on U and 1122.065 ms on G). The new bus has the same address.
- **Step 3.** Every re-observation of the still-running fixture is a success payload with `degraded: true` and `degraded_reason: "x11_property_fallback_partial: AT-SPI was unavailable ..."`, carrying the window element only and no control tokens. That is the pre-registered structured degradation.
- **Steps 4 and 5.** The pre-restart token is refused, and 0 stale mutations occur in 50/50 restart trials (bus, bus_direct). But the same Driver process returns degraded trees for the respawned fixture in all 5 tries, so no new token verifies (0/40), while a fresh Driver process sees it truthfully (40/40).
- **Gate (bus pass 20/20 per binary): fails on liveness; safety 40/40.**
- **Controls.**
  - Every re-observation invalidates the older snapshots, so the refusal in `noop`/`registry` comes from snapshot supersession, not from the restart.
  - `noop_direct` is the discriminating control: the old token, used without a re-observation, acts (10/10). The mutation detector therefore works, and refusal is not the harness default.
  - `bus_direct`: after a restart the old token is refused even without a re-observation, with the cached AT-SPI connection broken (10/10).

### E4 counters per arm

| Arm | silent steal misses (valid) | stale-token actions | unverified successes |
|---|---|---|---|
| U / S0, U / X (R1 reply) | **20, 20** | 0 | 0 |
| G / S0 | 1 (`xc08-011`, near-boundary) | 0 | 0 |
| G / X | 0 | 0 | 0 |
| G / S0+CL, G / X+CL | 2, 1 (all near-boundary) | 0 | 0 |
| U, G (R3) | n/a | **0** | 0 |

## Work deleted vs wall-clock saved

| Change | Work deleted | Wall-clock saved |
|---|---|---|
| G | none on the normal path (no extra read: settle 240.8-242.5 ms on both binaries in the smoke). One extra 3-read diff only after a stall across the deadline | none claimed. G is a correctness fix; after a stall it *adds* the verified restore (~150 ms) to recover the focus |
| CL (KILLed) | settle 20.816 ms (checkbox) / 20.764 ms (text) | 21.012 / 20.236 ms of T. Not taken: it removes real coverage (above) |

## E2 (native)

The focus-guard settle is ~84-91% of T in the best composed native arms (N-02). Its ~21 ms poll overshoot past the 220 ms window now has a **valid CL verdict: KILL**. The overshoot is measured coverage for steals landing 220-241 ms, so it stays inside the **IRREDUCIBLE** settle. This closes N-02's "until a valid re-test" item. No other component changes here.

## Deviations

1. **R1 redesign (pre-registered).** The planner's XGrabServer stall does not reach the deadline-exit path (pilots, then 80 counted trials). The gated R1 row uses the reply-delay proxy that matches c08-017's marks. The grab row ran exactly as specified, and its failing gate is reported above.
2. **Near miss (pilot p04-r1, excluded).**
   - What happened: the first proxy design gave the Driver `DISPLAY=<path>`. x11rb 0.13.2 maps a path to `/tmp/.X11-unix/X0` and tries the **abstract** socket `@/tmp/.X11-unix/X0` first; the host has one.
   - Why nothing escaped: the run was under `hostless`, whose Landlock scope (it refuses to start below ABI 6) blocks connecting to abstract sockets bound outside the domain. x11rb fell back to the path on hostless-strict's private tmpfs, where it does not exist. Driver stderr shows ENOENT in all 4 trials; the proxy accepted 0 connections; no guard ran. Nothing reached the host.
   - The fix: the proxy moved to `/tmp/.X11-unix/X<M>` (private tmpfs), with the abstract name checked absent before every trial (`raw/near-misses.txt`).
3. **Near miss (no effect).** One stdlib `python3` heredoc (a string replace in a packet file, pure file I/O) ran in the plain host shell instead of under hostless. Every other code-executing command ran under hostless (`raw/near-misses.txt`).
4. **Private-server ACL.** For proxy trials the harness ran `xhost +si:localuser:<user>` on the private Xvfb only, so the Driver's connections through the proxy authenticate without copying the session cookie.
5. **R3 additions.**
   - `noop_direct` (discriminating) and `bus_direct` (exploratory) were added, from the pilots, before PREREG.
   - The step-5 retries and the fresh-process diagnostic are pre-registered, and the diagnostic never enters a verdict.
6. **Analysis-only change after PREREG:** none; `analyze.py` is unchanged since `d17a8c0b4` (checked by the verifier).
7. **Shared host.** Other tracks kept the 1-minute loadavg at 2.4-46.0 over all counted trials (3.4-27.1, median ≈ 9.5, in the timing block), recorded per trial. Timing ran under the EXCLUSIVE lock; every comparison is paired.
8. **Failed session start.** `own20g-r1qa` hit the known private-DISPLAY collision; it is kept and was re-run as `own20g-r1qa-r1`.

## Limits

- **Window rule.** The R2 window ends at the `restored` mark, up to ~2 ms after the guard's last read. Steals in that gap count as misses (4 of the 7). The rule was pre-registered and was not changed.
- **Synthetic stalls.** The reply-delay proxy reproduces c08-017's observable; it does not reproduce its unknown root cause. One stall position (the read after the 90 ms poll) and one length (2.0 s) were tested.
- **Not fixed by G.** The `same_app_dialog` misclassification (core focus moved while `_NET_ACTIVE_WINDOW` lags) and the unverified `not_restored` after a stall seen by the stalled read.
- **R3.** `dbus-broker` a11y bus, at-spi2-core 2.60.6, GTK3. The same address is reused after the restart.
- **Scope.** X11 only (Xvfb, openbox, picom); one fixture window; fresh processes per trial.

## Claim boundary

On Linux X11 (private Xvfb, openbox, picom) with the GTK3 task fixture, and binaries U and G built from `0f1955d2f` (libs tree identical to `41c34cb0d`):
- G closes the c08-017 silent miss: 40/40 restored vs U 40/40 silent on the faithful reproduction. It does not change the normal path. It is a **fork candidate only**, not merged or posted anywhere.
- CL is KILLed under a valid control.
- After an a11y bus restart the Driver stays safe (degraded, refuses stale tokens, 0 stale mutations) but does not recover in-process.

Hyprland/Wayland focus rows are **BLOCKED** (real seat).

## Disposition

- **#20 guard final diff: KEEP (fork candidate).** It is reviewed product-fix candidate `a30cbbc3b` on this branch, with UNIT red/green and REAL R1 40/40 vs 0/40. The specified XGrabServer row fails its gate for U and G alike, because it exercises a different path.
- **CL (settle-overshoot clamp): KILL.** The ~21 ms overshoot is IRREDUCIBLE (measured coverage).
- **#20 a11y bus restart row: terminal FAIL of the pre-registered gate on liveness, with safety holding.** 40/40 safe and 0 stale actions; 0/40 in-process recovery, 40/40 with a fresh Driver.
- **E4:** default-guard silent steal misses are measured (U 40/40 on R1). G removes them on this path.

## Next

1. **Bus restart liveness (#20).** The Driver should detect a dead AT-SPI connection and reconnect, or return a structured error that says to restart. It must not keep returning degraded trees. Smallest test: this R3 row's step 5 in the same process.
2. **same_app_dialog under WM lag (#20).** Classify a move by the owner of the core focus, or wait for `_NET_ACTIVE_WINDOW` to settle before applying the same-app rule. 10 counted cases here (7 grab-row, 3 R2).
3. **Unverified restore after a late change.** A change first seen after the 600 ms budget gets one re-assert and `not_restored` (the grab row). Anchoring the restore budget at detection, which the module's own 1.5 s bound test implies, would make it verifiable. That is a separate behaviour; G deliberately does not include it.

## Evidence classes by row

| Row | Class |
|---|---|
| UNIT red/green | UNIT |
| s01 smoke; R1 reply, R1 grab and their controls; R2 steal groups and no-steal control; R3 all variants | REAL (FIXTURE) |
| R2 timing `t01` | REAL + BENCHMARK |
| Fix description, mechanism notes (settle loop, restore budget, same-app rule) | SOURCE |
| Provider decisions | NOT_RUN (cap 0; 0 attempts, 0 reached) |
| Hyprland / Wayland focus rows | BLOCKED (real seat) |

## Files

| File | Contents |
|---|---|
| `PREREG.json`, `plan.json`, `make_plan.py`, `plan-supp.json`, `make_plan_supp.py` | Pre-registration, frozen plan, committed supplement |
| `own20g_harness.py`, `r3_harness.py`, `harness_common.py`, `stealer.py`, `xstall_proxy.py`, `xprobe.py` (N-02 verbatim) | Harness |
| `run_all.sh`, `run_block.sh`, `unit_in_session.sh`, `unit_red_green.sh`, `driver_versions.sh` | Orchestration |
| `package.py`, `analyze.py`, `verify_artifacts.py` | Raw copy + scrub; recompute; verifier |
| `own20g-summary.json`, `own20g-trial-metrics.jsonl.gz`, `provenance.json` | Results and provenance |
| `raw/<label>/trials.jsonl.gz`, `raw/<label>/session.txt` | One ledger per block attempt |
| `raw/lock-ledger.jsonl`, `raw/unit/`, `raw/build/`, `raw/source/`, `raw/runs/`, `raw/near-misses.txt`, `raw/pilots/` | Locks, unit logs, builds, source checks, orchestration logs, near misses, excluded pilots |
