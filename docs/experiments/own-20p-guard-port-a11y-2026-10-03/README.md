# OWN-20P: guard fix G ported to clean main, and an AT-SPI bus-restart reconnect fix, 2026-10-03

Owners: kvnloo/cua#20 (focus guard, a11y bus restart row), kvnloo/cua#93, kvnloo/cua#74 (posting queue). Wave 5, reviewed product-fix lane: both changes alter default Driver behaviour on purpose and are not env-gated. No new service. Advances E1 (#20: G becomes a fork candidate on current main; the bus-restart liveness FAIL gets a terminal disposition) and E4.

## Result in one paragraph

**G (guard final read), ported to clean upstream main cb685fad7 as a761f1f1f: KEEP, fork candidate.**
- UNIT red/green: the stall test fails on the red tree and passes on the port. The platform-linux lib passes with 0 failed.
- On the gated R1 reply-delay row (the c08-017 reproduction), the port (G0m) restored **40** of 40 steals with 0 silent misses. The base (U0m) missed **40** of 40 silently.
- On the product-default normal path, G0 verified **40** of 40 with 0 false restores. U0 also verified 40 of 40.

**A (reconnect to a restarted AT-SPI bus) as 064d2e4ad: KEEP, fork candidate.**
- On the R3 bus restart, the same GA Driver process verified a new token against the respawned fixture in **20** of 20 trials. G0 managed **1** of 20, and that 1 is a trial in which no restart happened (see Deviations).
- Safety held on both binaries: the pre-restart token was refused and 0 stale mutations occurred, 20 of 20 each.
- noop_direct acted 5 of 5 on both binaries.
- Counting only trials where the bus daemon really was killed (including a pre-committed supplement): G0 was live in 0 of 24 and safe in 24 of 24; GA was live in **25** of 25 and safe in 25 of 25.

The planner's ruling is recorded in PREREG.json: the R1 reply-delay row replaces the XGrabServer row as the gating R1 row for #20. The XGrabServer row stays reported (OWN-20G) as a different path, on which U = G.

Provider: none. TypeSafe cap 0: **0 attempts, 0 reached**.

| Gate (pre-registered) | Result | Class |
|---|---|---|
| R1: G0m restored 40/40 with 0 silent misses; U0m silent miss >= 36/40; control 0 false restores | gate: True (40 / 40, 40 / 40, 0 / 0) | REAL |
| Normal path: G0 verified 40/40, 0 false restores, no added failures | gate: True (40/40; U0 40/40) | REAL |
| R3: GA bus liveness 20/20 (respawned fixture, same process); safety 20/20 on both; noop_direct acts 5/5 on both | gate: True | REAL |

## Provenance (each SHA separate)

| Item | Value | Class |
|---|---|---|
| Forced path (R1, normal) | Background `click` on the observed element token via AT-SPI DoAction inside `focus_guard::guarded`. Every click reports route `accessibility`. The marked twins write the `focus_guard` and `atspi_action` marks; the product binaries write none. | REAL |
| Forced path (R3) | `get_window_state` then a background `click` of the pre-restart token, through one Driver process across the restart (r3_harness.py) | REAL |
| Actual route / producer | `route: accessibility` on every click (trial metrics `click_route`); the R1 stall is attributed by the proxy's hold record and the guard's settle-poll marks | REAL |
| Independent target-owned oracle | the fixture's own state file (2 ms sampler); `xprobe.FocusSampler`, a separate X connection that samples `XGetInputFocus` and `_NET_ACTIVE_WINDOW` every 2 ms; the reference is the first sample of the first quiet 300 ms. The `focus_outcome` receipt is checked but is never an oracle. | REAL |
| Negative / fallback controls | R1 `replyonly` (proxy, no hold, no steal); R3 `registry`, `noop`, `noop_direct` (discriminating: the old token must act), `bus_direct`; the normal path is itself the no-steal control | REAL |
| Upstream main at start (07:18:01Z) | `cb685fad7aef1df6a35ffec653295a0cea4daee6`; `libs/cua-driver` tree `df2b49c32e73` = `0f1955d2f`'s | SOURCE |
| Upstream main at end (10:43:18Z) | `154ca5690350217f0824e004d04c031e5c411883`, 12 commits ahead, 6 under `libs/cua-driver`, **none** in platform-linux or cua-driver-core; the branch merges clean (`raw/heads/merge-tree-on-upstream-end.txt`) | SOURCE |
| kvnloo/cua#106 (layout reference) | `c45845797b714ccfd76a9569d3238a0724107a83`, open at start and end | SOURCE |
| Fork main | `da46c4bc85bc43f9641d3ce4b6f319e6d7b6c1a9` (start and end) | SOURCE |
| U0 (tested base) | `cb685fad7` | SOURCE |
| G0 (tested fix G) | `a761f1f1f8850951a446b423c36d2dcce1e18611` = U0 + one commit touching only `platform-linux/src/input/focus_guard.rs` | SOURCE |
| GA (tested fix A) | `064d2e4ad931e7a3b884c4621e3d5cbb4600f7b9` = G0 + one commit (6 files: `atspi/native.rs`, `atspi/snapshot.rs`, `atspi/mod.rs`, `atspi/native/hit.rs`, `tools/impl_.rs`, `cua-driver-core/src/snapshot_store.rs`) | SOURCE |
| U0m (marked twin) | `0944feb31` (detached) = U0 + picks of `28b915ae9`, `b9b357bc7`, `194a6342e` (OWN-20G's measurement picks, default off). Its `libs/cua-driver` tree `79ebebb63849` equals OWN-20G U `bdf33d9fe`'s | SOURCE |
| G0m (marked twin) | `16d21fd56` (detached) = G0 + the same picks (two conflicts resolved as a30cbbc3b did). Its `focus_guard.rs` differs from OWN-20G G `a30cbbc3b` only by the re-anchor-only-on-a-found-change refinement (`raw/source/g0m-vs-own20g-g.patch`); `libs/cua-driver` tree `c6b9910b47c5` | SOURCE |
| Red tree | `c220be6a0` (detached, worktree w5-own20p-red) = U0 + the settle-loop extraction + both settle tests, without the final read = G0 minus `raw/source/red-fix-only.patch` (tree `749b68f49f1d`) | SOURCE |
| Why a port | a30cbbc3b sits on the measurement picks; `git apply --check` on clean cb685fad7 fails at `focus_guard.rs:646` (`raw/source/a30-apply-check-on-cb685fad7.txt`) | SOURCE |
| Driver U0 | `cua-driver-own20p-u0-cb685fad7`, sha256 `45ffb243ae5e2fddc66d452ce55586494e5da71fa1a927299d1158879c3598d4`, `cua-driver 0.32.0` | SOURCE |
| Driver G0 | `cua-driver-own20p-g0-a761f1f1f`, sha256 `77a28152330405eabb0c17cd99ba2594239b3ac82a0484cff772ba865c14a1e4`, `cua-driver 0.32.0` | SOURCE |
| Driver GA | `cua-driver-own20p-ga-064d2e4ad`, sha256 `681627314e2f031641e7579ab8640a3cb673c58b8b029ef7399e277706ccc146`, `cua-driver 0.32.0` | SOURCE |
| Driver U0m | `cua-driver-own20p-u0m-0944feb31`, sha256 `9c5e9fffb3b02fd24cd3ba54d9347153680ed1058c92f9ed66cd24f75b8b6ad1`, `cua-driver 0.32.0` | SOURCE |
| Driver G0m | `cua-driver-own20p-g0m-16d21fd56`, sha256 `1568dc4a63ba4d09e19b4c254fa1c1f806a92ff0ea7f48934be7f26c6b02d13c`, `cua-driver 0.32.0` | SOURCE |
| Builds | `build-driver.sh` into the `cua-release-own20g` family dir, cargo-build lock then quiet-lane shared, rustc 1.97.1, 0 Fresh workspace units each. Versions were read inside a private session at start and end (`raw/build/`). | SOURCE |
| Environment | Linux 7.2.2; `hostless` (v2: env strip, private runtime dir, Landlock scope) + `hostless-strict` (private tmpfs over the X11/ICE/runtime dirs) + `cua-x11-session.sh`: private Xvfb, openbox, picom, private session bus, private AT-SPI bus and registry; telemetry off (`CUA_DRIVER_RS_TELEMETRY_ENABLED=0`, `DO_NOT_TRACK=1`); canonical GTK3 task fixture; a 0-3 s start jitter and an `xdpyinfo` probe before every session; loadavg 0.44-12.85 per trial (medians per cell in the summary) | SOURCE |
| Harness | OWN-20G's packet files at `ce7544cc0`, copied **blob-identically** into `harness/` (8 blob ids in PREREG.json; checked by the verifier) | SOURCE |
| PREREG | `3c88ccc81`, committed 2026-10-03T09:47:07Z, before the first counted trial (block q1, 09:47:20Z). Supplement plan `2a62a0195`, 10:44:39Z, before block r3s | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); never equal by assumption to the tested SHAs | SOURCE |
| Provider | none; TypeSafe cap 0, 0 attempts, 0 reached | NOT_RUN |

## The fixes

**G (a761f1f1f).** The settle watch polls every 30 ms until 220 ms. Its deadline is checked only after each poll, so a read that began before the deadline but stalled past it ended the watch on stale data. That is c08-017: a steal at 217 ms was never seen.
- The port moves the settle loop unchanged into `fn settle(started, watch, diff, windows)` and adds the final read. When the watch ends on its deadline with nothing seen, and its last read began before the deadline, the guard reads once more.
- The restore budget is re-anchored to that read **only when it finds a change**. In a30cbbc3b the re-anchor was unconditional. With no change nothing is restored, so the two behave the same.
- A quiet watch ends on a read that began past the deadline, so the normal path takes no extra read. Settle was 240.8-240.9 ms on both binaries (below).
- Without the measurement picks the loop sleeps `SETTLE_POLL` exactly as clean main does, and writes no marks.

**A (064d2e4ad).** Clean main keeps one AT-SPI connection per process in a `OnceCell`. After a bus restart every call on it fails, so the process returned degraded trees for the rest of its life.

The connection now lives in a small state machine (`Link`), and each connection gets a generation number.
- **Detection.** The connection's event stream ends only when its socket reader stops: EOF, broken pipe or reset when the bus daemon exits. The focus tracker then calls `connection_lost(generation)`.
  - That drops the connection, closes its socket and forgets everything observed through it: the focus and active-descendant maps, the snapshot side index and the cursor-shape frame cache.
  - The next AT-SPI operation reconnects lazily to the bus that serves the session at the same address. It uses the same `AccessibilityConnection::new()` path as process start.
- **While disconnected.** A walk returns the existing structured degraded X11 fallback. Its nodes carry no proven identity and are never addressable (unit test `a_degraded_tree_mints_no_token_that_resolves`).
- **Pre-restart tokens stay refused.** Unique bus names restart on a new bus, so an old (name, path) pair could name another application's object there.
  - Each snapshot records the generation it was observed on. `SnapshotPayload::is_current` (core, default `true`) is false once any connection has been lost since then.
  - `SnapshotStore::resolve` then refuses the token as `stale_element_token`, the same refusal as for a retired snapshot.
  - A walk that finished on a connection lost before publication is refused the same way.
- **Kept small.** Lost connections are leaked so that callers keep their `&'static` borrows. One small handle per bus loss remains; its socket is closed.
- **Not used as triggers.** A NoReply from a slow application is not treated as a dead bus, which would cause reconnect churn. A name-owner change of `org.a11y.Bus` is not watched either: that would need a second, persistent session-bus connection, and the restart under test always ends the old daemon. Both are in Limits.

## Method

All runs used the plan in `plan.json` (`make_plan.py`), AB/BA order within each pair, one fresh Driver and one fresh fixture per trial, at most 10 trials per block, and one shared quiet-lane acquisition per block, with a receipt in `raw/lock-ledger.jsonl`.

**R1** (`replystall`, blocks q1-q8)
- U0m vs G0m, 20 per binary per task: checkbox on arm S0 and text on arm X, as OWN-20G.
- `xstall_proxy.py` holds for 2000 ms the reply to the guard's first new-client read issued >= 80 ms after `do_action_replied`. The decoy steals at mark + 217 ms on its own connection.
- Control `replyonly`, 5 per binary per task (qc1, qc2).

**Normal path** (`nosteal`, n1-n8)
- U0 vs G0 on arm D, with no `CUA_DRIVER_EXP_*` variable (product defaults), 20 per binary per task.
- The product binaries write no marks, so the stealer waits out its 20 s deadline ("mark not seen") in every trial, as pre-registered.
- Settle comes from the marked twins (m1-m4, U0m vs G0m on the R1 arms, 10 per binary per task).

**R3** (r3a-r3h, `r3_harness.py`)
- G0 vs GA, run exactly as OWN-20G R3: bus 20 per binary; registry, noop, noop_direct and bus_direct 5 per binary each.
- The restart signals only this session's a11y bus daemon and registry. They are found through the harness's own parent process tree; nothing is matched by name pattern.

**UNIT**
- Run with `unit_run.sh` and `unit_in_session.sh` inside a private session, under the cargo-build lock.
- Red is `c220be6a0` (target dir separate from green); green is `a761f1f1f` (from worktree w5-own20p-g0) and `064d2e4ad`.

## Results (N of M, evidence class per row)

### UNIT

| Tree | Result | Class |
|---|---|---|
| red `c220be6a0` | `a_steal_during_a_read_stalled_past_the_watch_is_seen` **FAILED** ("the steal went unseen"); platform-linux lib 603 passed, 1 failed | UNIT |
| green A `a761f1f1f` | both settle tests 2/2; `input::focus_guard` 11/11; platform-linux lib **604 passed, 0 failed** | UNIT |
| GA `064d2e4ad` | settle tests 2/2; `atspi::native::link_tests` + `atspi::snapshot` 12/12 (4 link tests, 1 new snapshot test); platform-linux lib **609 passed, 0 failed**; cua-driver-core `snapshot_store` 32/32 (1 new test), core lib **821 passed, 0 failed** | UNIT |

### R1: c08-017 reproduction (gated)

| Task / binary | attempted | valid | pass (restored, final = reference, verified) | silent miss | receipt | settle median (ms) | class |
|---|---|---|---|---|---|---|---|
| checkbox / U0m | 20 | 20 | 0 | **20** | none 20 | 2091.329 | REAL |
| checkbox / G0m | 20 | 20 | **20** | 0 | restored 20 | 2247.297 | REAL |
| text / U0m | 20 | 20 | 0 | **20** | none 20 | 2091.395 | REAL |
| text / G0m | 20 | 20 | **20** | 0 | restored 20 | 2247.38 | REAL |
| control `replyonly` U0m / G0m | 10 / 10 | 10 / 10 | 0 false restores, 10/10 verified each | | | | REAL |

- The hold started a median 91.0-91.2 ms after the mark, on the read right after the third poll (last poll 90.9-91.2 ms), exactly c08-017's trace. The steal was issued 217.0 ms after the mark.
- U0m's guard ends on the stalled read and reports nothing. G0m takes the final read and restores, including the verified restore.

### Normal path (gated; product binaries)

| Task / binary | n | verified | false restores | failures | T median (ms, descriptive) | class |
|---|---|---|---|---|---|---|
| checkbox / U0 | 20 | 20 | 0 | 0 | 332.947 | REAL |
| checkbox / G0 | 20 | 20 | 0 | 0 | 332.953 | REAL |
| text / U0 | 20 | 20 | 0 | 0 | 1758.911 | REAL |
| text / G0 | 20 | 20 | 0 | 0 | 1758.934 | REAL |

The text task on arm D includes the default cursor glide (~1.5 s); arm D is the product default.

**Settle (descriptive, marked twins m1-m4, 10 per cell, all verified, 0 false restores):**

| Task | U0m median | G0m median | polls | class |
|---|---|---|---|---|
| checkbox | 240.786 | 240.894 | 8 | REAL |
| text | 240.779 | 240.848 | 8 | REAL |

G0m's range on checkbox was 240.667-244.482 ms. No extra read appears on the quiet path.

### R3: a11y bus restart (gated)

| Variant / binary | n | pass | safety | re-observe of A | stale token | stale mutations | new token verified (same process) | fresh process sees B | perturbation median (ms) | class |
|---|---|---|---|---|---|---|---|---|---|---|
| bus / G0 | 20 | **1** | **20** | structured degraded 19, truthful 1 (r3b-010, no restart) | refused 20 (`stale_element_token`) | 0 | 1 (A, r3b-010); B never | 19 | 1096.528 | REAL |
| bus / GA | 20 | **20** | **20** | structured degraded 20 | refused 20 (`stale_element_token`) | 0 | **20, all from the respawned fixture B on the first same-process observation** | 20 | 1116.196 | REAL |
| registry / G0, GA | 5, 5 | 5, 5 | 5, 5 | truthful 5, 5 | refused (supersession) | 0 | 5, 5 (A) | | ~27 | REAL |
| noop / G0, GA | 5, 5 | 5, 5 | 5, 5 | truthful 5, 5 | refused (supersession) | 0 | 5, 5 (A) | | 0 | REAL |
| noop_direct / G0, GA (discriminating) | 5, 5 | expected to act | | not observed | **acted 5/5 each** | 5, 5 (expected) | 5, 5 | | 0 | REAL |
| bus_direct / G0, GA | 5, 5 | 0, 5 | 5, 5 | not observed | refused 5, 5 | 0 | 0, **5** | 5, 5 | ~1100-1120 | REAL |

- GA's stale-token refusals come from the snapshot generation check at resolve time. G0's come from snapshot supersession (bus) or the broken cached connection (bus_direct), as in OWN-20G.
- **Restart-happened view** (post-hoc, Deviation 2; bus trials of r3a-r3d plus the supplement r3s):
  - G0: the daemon was killed in 24 trials; live 0, safe 24, stale mutations 0.
  - GA: the daemon was killed in 25 trials; live (respawned fixture verified, same process) 25 of 25, safe 25, stale mutations 0.
- **Gate (pre-registered): GA liveness 20/20, safety 20/20 on both, noop_direct 5/5 on both: holds.** G0 reproduces OWN-20G's liveness failure on every trial that had a restart.

### E4 counters per arm

| Arm | silent steal misses | stale-token actions | stale mutations | unverified successes | class |
|---|---|---|---|---|---|
| U0m / S0, U0m / X (R1) | **20, 20** | n/a | n/a | 0, 0 | REAL |
| G0m / S0, G0m / X | 0, 0 | n/a | n/a | 0, 0 | REAL |
| U0 / D, G0 / D (normal) | 0, 0 | n/a | n/a | 0, 0 | REAL |
| G0 / r3, GA / r3 | n/a | **0, 0** | 0, 0 | 0, 0 | REAL |

### Denominators

All 30 counted blocks and the supplement r3s ran on their first session attempt (rc 0, 0 display collisions, 0 harness failures, 0 non-loopback connects). That is 300 counted trials plus 10 supplementary ones. Pilots (pq, pn, pr; 6 trials, before PREREG) are kept under `raw/own20p-pilot-*` and excluded from every count.

## Component timings and work deleted vs wall-clock saved

| Change | Work deleted | Wall-clock saved | Class |
|---|---|---|---|
| G | none on the normal path: no extra read; settle 240.8-240.9 ms on U0m and G0m; T 332.95 ms (checkbox) on both U0 and G0 | none claimed. It is a correctness fix: after a stall across the deadline it **adds** the verified restore (~156 ms: settle 2247 vs 2091 ms) | REAL (descriptive) |
| A | none per action | none claimed. It removes the need to restart the Driver process after a bus restart; the same process sees the new bus on its first observation | REAL (descriptive) |

Component share, descriptive only: the guard settle (~240.8 ms) is ~85% of T on the marked checkbox arm (283.1 ms) and is unchanged by G.

## Deviations

1. **The gating R1 row ran on the marked twins.**
   - The blob-identical harness keys both the stall and the steal on the `atspi_action do_action_replied` mark. Clean main has no phase trace, so with U0/G0 the steal never fires.
   - The spec allowed marked twins U0m/G0m with the same picks "for attribution". They are used for the gated R1 row too.
   - Their sources differ from U0/G0 only by the three default-off measurement picks, verified by tree and patch.
   - The normal path and R3 ran on the product binaries U0, G0, GA.
2. **R3 restart fragility in the harness (blob-identical, not changed).**
   - In r3b-009 (GA), the daemon was killed but the harness did not see the new launcher's daemon within its 5 s wait (`new_daemon: false`, perturbation 6.1 s).
   - In the next trial, r3b-010 (G0), the harness found no daemon under that launcher and skipped the kill ("not this session's process"). No restart happened, and A stayed on the old bus. That is the single G0 "pass" (truthful re-observation of A).
   - Both trials stay counted under the pre-registered rule.
   - A supplement of 5 bus pairs (block r3s) was committed (`2a62a0195`) before it ran. With it, each binary has >= 20 trials with a real kill. It enters only the post-hoc restart-happened view, never the gate cells.
3. **Lock-order inversion (lane interference, no measurement affected).**
   - The first versions of `unit_run.sh` and `build_run.sh` took the quiet-lane lock (shared) before the cargo-build lock. Other lanes take cargo first, then quiet-lane exclusive.
   - For about 2.5 minutes, another lane's exclusive waiter sat behind this lane's shared hold while this lane waited for that lane's cargo lock. No trial of this lane ran then.
   - I stopped my waiting processes and switched both scripts to cargo first. The red and green-A unit runs had already completed under the old order; their receipts are in the ledger.
   - Builds then waited up to ~1 h for the cargo lock behind other lanes' timing chunks. The last four builds ran in one acquisition (`build_run.sh`).
4. **`unit_run.sh` as run vs as committed.** The unit runs had this machine's cargo home inlined. The committed script reads it from `CUA_CARGO_HOME` (privacy). The commands are otherwise identical.
5. **Extra worktrees.** Besides w5-own20p and w5-own20p-red, the lane used detached worktrees w5-own20p-u0, -g0, -u0m and -g0m, so that builds and units of fixed SHAs never compiled a tree being edited. No branch or ref was created for them.
6. **Near misses (no effect, `raw/near-misses.txt`).**
   - One `python3 -c 1` (a no-op, no imports) ran in the plain host shell while I was reading context, before any lane work.
   - One `pkill -P <pid>` aimed at this lane's own just-stopped queue process ran in the plain shell. It matched nothing; the leftover waiter was then stopped by its own pid.
   - No other code-executing command ran outside hostless.

## Limits and claim boundary

- **Environment.** Linux X11 (private Xvfb + openbox), the canonical GTK3 task fixture, and exactly the SHAs and binaries above. Fork candidates only; nothing goes upstream.
- **Timing.** No timing claim beyond the descriptive settle and T.
- **Wayland/Hyprland:** BLOCKED (seat).
- **A: detection.** A detects a dead bus by its connection's event stream ending. Two cases are not exercised:
  - A launcher restart that leaves the old bus daemon alive, which a name-owner watch would catch.
  - A bus that hangs without closing its socket.
- **A: fixture A.** A running application that was registered on the old bus (fixture A) is not re-registered by the toolkit. A recovers liveness for applications on the new bus.
- **Out of scope (wave 6).**
  - The `same_app_dialog` misclassification under `_NET_ACTIVE_WINDOW` lag.
  - Restore-budget anchoring after a late change found by a normal poll.
- **R1 binaries.** R1's gating numbers come from the marked twins (Deviation 1).

## Disposition

- **G (guard port, a761f1f1f): KEEP, fork candidate on current main.**
  - UNIT red/green holds, and the platform-linux lib has 0 failures on G0.
  - The R1 gate holds (40/40 restored, 0 silent misses; U0m 40/40 silent misses).
  - The normal-path gate holds (40/40, no added failures).
- **A (AT-SPI reconnect, 064d2e4ad): KEEP, fork candidate.**
  - UNIT holds.
  - The R3 gate holds: GA liveness 20/20 through the respawned fixture in the same process; safety 20/20 on both binaries; noop_direct 5/5 on both.
  - #20's R3 row moves from "safe, not live; restart required" to "safe and live in-process with A".

## Files

| File | Contents |
|---|---|
| `PREREG.json`, `plan.json`, `make_plan.py`, `plan-pilot.json`, `plan-supp.json`, `make_plan_supp.py` | Pre-registration, frozen plan, pilot plan, committed supplement |
| `harness/own20g_harness.py`, `harness/r3_harness.py`, `harness/harness_common.py`, `harness/stealer.py`, `harness/xstall_proxy.py`, `harness/xprobe.py`, `harness/run_block.sh`, `harness/driver_versions.sh` | OWN-20G harness, blob-identical |
| `run_all.sh`, `session_entry.sh`, `unit_run.sh`, `unit_in_session.sh`, `build_run.sh`, `locked.sh` | Orchestration, locks, units, builds |
| `analyze.py`, `package.py`, `verify_artifacts.py`, `verify_helper.py` | Recompute, raw copy + scrub, verifier, template helper (cited files, privacy) |
| `own20p-summary.json`, `own20p-trial-metrics.jsonl.gz`, `provenance.json` | Results and provenance |
| `raw/own20p-q1/trials.jsonl.gz` ... `raw/own20p-r3s/trials.jsonl.gz` and each `session.txt` | One ledger per block (31 counted blocks) |
| `raw/own20p-pilot-pq/trials.jsonl.gz`, `raw/own20p-pilot-pn/trials.jsonl.gz`, `raw/own20p-pilot-pr/trials.jsonl.gz` | Pilots, excluded |
| `raw/lock-ledger.jsonl` | Every lock receipt of this lane (blocks, units, builds, version reads) |
| `raw/unit/unit-red.log`, `raw/unit/unit-green-a.log`, `raw/unit/unit-ga.log` | UNIT logs |
| `raw/build/build-u0.log`, `raw/build/build-g0-ga-u0m-g0m.log`, `raw/build/driver-versions-session-start.txt`, `raw/build/driver-versions-session-end.txt`, `raw/build/lane-deps.log` | Builds and versions |
| `raw/source/red-fix-only.patch`, `raw/source/g0m-vs-own20g-g.patch`, `raw/source/u0m-vs-own20g-u.patch`, `raw/source/source-trees.txt`, `raw/source/a30-apply-check-on-cb685fad7.txt` | Source records (the U0m patch is empty: identical tree) |
| `raw/runs/run_all-main.txt`, `raw/runs/run_all-pilot.txt`, `raw/runs/run_all-supp.txt` | Orchestration logs |
| `raw/heads/heads-start.json`, `raw/heads/heads-end.json`, `raw/heads/merge-tree-on-upstream-end.txt` | Live heads; merge onto upstream main at end |
| `raw/near-misses.txt` | Near misses and the lock interference |
