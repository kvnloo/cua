# OWN-20Q: mark-free R1 on the product binaries, AT-SPI reconnect triggers, same_app_dialog fix, 2026-10-03

Owners: kvnloo/cua#20 (focus guard, a11y bus reconnect), kvnloo/cua#93, kvnloo/cua#74 (posting queue). Wave 6, fix lane. Both fixes change default Driver behaviour on purpose and are not env-gated. No new service, thread or connection. Advances E1 (#20 follow-ups) and E4.

## Result

**R1m (mark-free stall on the product binaries): KEEP.**
- The stall now keys on the AT-SPI `DoAction` reply as routed by the private a11y bus, not on a Driver mark.
- Calibration on the marked twins: the mark-free rule held the same request as OWN-20P's mark-keyed rule in **20** of 20 trials (difference 0.0 ms). The reference sat within 0.01 ms of the Driver's `do_action_replied` mark.
- Gate on the product binaries U0 vs G0, 40 each, ABBA:
  - U0 missed the steal silently in **40** of 40;
  - G0 made a verified restore in **40** of 40;
  - the no-steal controls had **0** false restores.
- The gating #20 R1 row therefore no longer needs the marked twins (pending the owner's reading).

**DLG (same_app_dialog under `_NET_ACTIVE_WINDOW` lag), fix 4ac191a7c: KEEP, fork candidate.**
- With the Driver's view of `_NET_ACTIVE_WINDOW` lagged and a steal inside the settle watch, GA classified the steal as the app's own dialog and left the focus on the decoy in **20** of 20 trials (positive control).
- GQ made a verified restore in **20** of 20, with 0 `same_app_dialog` receipts.
- The app's own dialog still stays focused on both binaries: 10 of 10 each.

**A2 (reconnect triggers): REVISE. The named failing gate is r3n.**
- **Name-owner trigger:** REVISE from SOURCE and not implemented. Watching `org.a11y.Bus` needs a persistent session-bus connection, and the X11 Driver keeps none.
  - r3n measured exactly that: after a launcher restart that leaves the old daemon alive and serving, GA and GQ both stayed degraded on the new bus in **20** of 20 each. Live in-process: GQ **0** of 20.
- **NoReply trigger (31318e374), the measured revised claim:**
  - Slow app (r3s): GQ pinged the bus 40 times and made **0** reconnects, with 0 false successes; **20** of 20 trials passed.
  - Wedged old daemon (r3w, supplementary): GQ was live in-process in **10** of 10 and GA in 0 of 10.
  - Carry-over stream-end restart (r3_carry): GQ passed **20** of 20. Counting only trials whose harness really killed the daemon (with the committed supplement), GQ was live in **23** of 23.

**Normal path (GQ, product defaults):** **40** of 40 verified, 0 false restores, 0 spurious reconnects. No KILL.

**UNIT red/green:** the red tree 74acf32c0 fails both new tests (platform-linux lib: 609 passed, 2 failed). GQ passes both, and the platform-linux lib has 611 passed, 0 failed.

Provider: none. TypeSafe cap 0: **0 attempts, 0 reached**.

| Gate (pre-registered) | Result | Class |
|---|---|---|
| r1m: U0 silent miss >= 36/40, G0 verified restore 40/40, 0 false restores | True (40, 40, 0) | REAL |
| calibration (no gate): mark-free hold within 5 ms of the mark-keyed hold >= 18/20 | 20/20 | REAL |
| dlg: GA misclassifies >= 16/20; GQ verified restore 20/20; dialog control GQ 10/10 | True (20, 20, 10) | REAL |
| normal: GQ 40/40 verified, 0 false restores, 0 spurious reconnects | True | REAL |
| r3n: GA degraded >= 18/20 (positive control); GQ live in-process 20/20 | control True (20); gate **False** (0) | REAL |
| r3s: GQ 20/20 (0 reconnects, no false success, ends refused or verified) | True (20) | REAL |
| r3_carry: GQ 20/20 | True (20; 14 with a real kill, 23/23 with the supplement) | REAL |
| UNIT red/green (DLG, A2); platform-linux lib on GQ 0 failed | red 2 failed / green 611 passed 0 failed | UNIT |
| Hyprland/Wayland rows | not run | BLOCKED (seat) |

## Provenance (each SHA separate)

| Item | Value | Class |
|---|---|---|
| Forced path | Background `click` on the observed element token, sent through AT-SPI `DoAction` inside `focus_guard::guarded`. Every click reports route `accessibility`. A2 rows add a bus perturbation between observing and clicking. | REAL |
| Actual route / producer | `route: accessibility` on every focus-row click. The stall is attributed by the proxy's hold record (request held, ms after R). Steals are attributed by X RECORD (the steal connection's `SetInputFocus`). Reconnects are attributed by the bus daemon (`GetConnectionUnixProcessID` of each new unique name). | REAL |
| Independent target-owned oracle | The fixture's own state file (2 ms sampler). X RECORD on the private display: SetInputFocus, the WM's `_NET_ACTIVE_WINDOW` / `_NET_CLIENT_LIST_STACKING` writes, EWMH requests, restacks, FocusIn/Out. The 2 ms `xprobe.FocusSampler`. A dbus-monitor of the private a11y bus. Driver receipts are compared with these oracles and never trusted alone. | REAL |
| Negative / fallback controls | `mfonly` (proxy, no hold, no steal); `nosteal` (normal path); `dlgdialog` (the app's own dialog under lag); GA as positive control (dlg, r3n, r3w); U0 as positive control (r1m) | REAL |
| Upstream main at start (14:00:29Z) | `c8edda06be53e13a759c69de125ce37189023954`: 21 commits after the tested base, 33 files under `libs/cua-driver`, none in platform-linux or cua-driver-core | SOURCE |
| Upstream main at end (15:11:38Z) | `5e13eb7777172587fa32ce2af1d78d7572b77f1a`: 27 commits after the base. The only platform-linux file in that drift is `overlay.rs` (trycua/cua PR 4529, idle cursor overlays), which neither fix touches. The branch merges clean (`raw/heads/heads-end.json`). | SOURCE |
| Fork main / kvnloo/cua#106 | `da46c4bc85bc43f9641d3ce4b6f319e6d7b6c1a9` / `c45845797b714ccfd76a9569d3238a0724107a83` (open), unchanged start to end | SOURCE |
| Tested base | clean upstream main `cb685fad7aef1df6a35ffec653295a0cea4daee6`, `libs/cua-driver` tree `df2b49c32e73` (0f1955d2f lineage) | SOURCE |
| U0 / G0 / GA | `cb685fad7` / `a761f1f1f8850951a446b423c36d2dcce1e18611` / `064d2e4ad931e7a3b884c4621e3d5cbb4600f7b9` (OWN-20P) | SOURCE |
| Branch base | `64081dded4e0a3ddf144e68ab1ea43579f85f572` (OWN-20P packet head; `libs/cua-driver` = GA's) | SOURCE |
| A2 fix | `31318e3741a5bd1ff131fda83f1fcccf5d058664`: one commit, `platform-linux/src/atspi/native.rs` only | SOURCE |
| DLG fix = GQ source | `4ac191a7c1d5a77cf4ed98474b4d3ebf76cc27c2`: one commit, `platform-linux/src/input/focus_guard.rs` only. GA→GQ is `raw/source/gq-vs-ga.patch` | SOURCE |
| Red tree | `74acf32c0` (detached) = GQ with both fix bodies set to GA behaviour (`raw/source/red-vs-green.patch`); the tests are kept | SOURCE |
| Driver U0 / G0 / GA | `cua-driver-own20p-u0-cb685fad7` `45ffb243ae5e2fddc66d452ce55586494e5da71fa1a927299d1158879c3598d4`; `cua-driver-own20p-g0-a761f1f1f` `77a28152330405eabb0c17cd99ba2594239b3ac82a0484cff772ba865c14a1e4`; `cua-driver-own20p-ga-064d2e4ad` `681627314e2f031641e7579ab8640a3cb673c58b8b029ef7399e277706ccc146`. All equal the OWN-20P provenance; every harness refuses a mismatch. | SOURCE |
| Driver U0m / G0m (calibration only) | `cua-driver-own20p-u0m-0944feb31` `9c5e9fffb3b02fd24cd3ba54d9347153680ed1058c92f9ed66cd24f75b8b6ad1`; `cua-driver-own20p-g0m-16d21fd56` `1568dc4a63ba4d09e19b4c254fa1c1f806a92ff0ea7f48934be7f26c6b02d13c` | SOURCE |
| Driver GQ | `cua-driver-own20q-gq-4ac191a7c`, sha256 `2dbe3cd27f8258fdaf5f225d40235d64ae87b58a1cb50c4da41d62d41860b885`, `cua-driver 0.32.0`. Built with `build-driver.sh` into the `cua-release-own20p` family dir, cargo-build lock only, rustc 1.97.1, 0 Fresh workspace units (`raw/build/build-gq.log`). Versions were read inside each session (`[session] versions` in every `session.txt`). | SOURCE |
| GD (G0 + DLG only) | Not built. GA→GQ changes no focus-guard code besides the DLG commit, so the GA/GQ DLG pair isolates it, and the UNIT red/green isolates each fix. | SOURCE |
| Environment | Linux 7.2.2. `hostless` + `hostless-strict` + `cua-x11-session.sh` (private Xvfb, openbox, picom, private session bus, private AT-SPI bus served by dbus-broker, plus a registry). `CUA_SESSION_ATSPI=1`; telemetry off. Canonical GTK3 task fixture. loadavg (1 min) per trial: 0.36-26.78, median 1.71. | SOURCE |
| PREREG | `186f4435c` (14:02:15Z), before the first counted trial (14:02:21Z). Supplement plan `3c4c49051` (15:12:56Z), before block rs1 (15:13:01Z). | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); never assumed equal to the tested SHAs | SOURCE |
| Provider | none; TypeSafe cap 0, 0 attempts, 0 reached | NOT_RUN |

## The fixes

**A2 NoReply trigger (31318e374).**
- OWN-20P's reconnect (GA) acts when the connection's event stream ends. A bus daemon that hangs keeps its socket open, so the stream never ends and every call times out.
- When an AT-SPI call goes unanswered within its budget (`call()` timeout), a background task on the existing AT-SPI runtime pings the bus daemon: `org.freedesktop.DBus.Peer.Ping`, 1 s, over the existing connection, at most one check at a time.
- Only when the daemon does not answer is the connection lost. The next operation then reconnects through the same `AccessibilityConnection::new()` path; generations and stale-token refusal work as in GA.
- A slow application leaves the daemon answering, so it never causes a reconnect.

**Name-owner trigger: REVISE from SOURCE (not implemented).**
- A launcher restart changes the owner of `org.a11y.Bus` on the session bus.
- `AccessibilityConnection::new()` (atspi-connection 0.14.0, lib.rs 58-90) opens a session connection only to call `GetAddress`, then drops it.
- platform-linux's other session connections are either one-shot (the accessibility-advertise thread, the health report) or Wayland-only.
- So the watch needs a second persistent connection, which this lane may not add.
- Proposed revision for a later lane (SOURCE only): on an observation that finds no application for the pid, check `org.a11y.Bus` once, on demand, over a one-shot connection.

**DLG (4ac191a7c).**
- The window manager writes `_NET_ACTIVE_WINDOW` a beat after the core focus moves.
- A settle read in that gap saw the core focus on the decoy while the active window still named the target. The same-app rule then took the steal for the app's own dialog.
- `same_app_move` now requires an attributable core focus to belong to the target too. A core focus that is PointerRoot/None, or on a window no pid owns, leaves the decision to the active window, as before.

## Method

All runs used `plan.json` (`make_plan.py`): ABBA within each pair, one fresh Driver and one fresh fixture per trial, at most 10 trials per block.
- Each block held one SHARED quiet-lane lock acquisition, with a receipt in `raw/lock-ledger.jsonl`. The longest hold was 113 s.
- The orchestrator waits 30 s between blocks (see Deviations).

**R1m** (`mfstall`, blocks q1-q4 checkbox arm P, qt1-qt4 text arm PX; U0 vs G0)
- The trigger reference R is the time `markfree_proxy.py`'s own bus monitor (dbus-monitor `--binary`, BecomeMonitor) receives the reply to the first `DoAction` after the harness issued the click. The harness writes the click time on the proxy's stdin.
- The guard's first new-client X read issued >= 80 ms after R has its reply held 2000 ms. The decoy steals at R + 217 ms on the proxy's own X connection.
- Measured: hold median 81.7 ms after R, steal 217.0 ms after R.
- Why this option, recorded in PREREG.json:
  - It matches the Driver's mark to 0.01 ms.
  - The X-only option keys on a 30 ms poll grid that drifts with click latency.
  - An in-path D-Bus proxy would change the forced path: the bus would attribute the fixture's connection to the proxy's pid, and the Driver resolves applications by pid.

**Calibration** (`mfcal`, c1-c2, U0m vs G0m): the proxy also tails the Driver trace and records the request OWN-20P's mark-keyed rule would hold, without acting on it.

**Controls** (`mfonly`, qc1/qct1): proxy in pass mode, decoy mapped, no hold, no steal.

**DLG** (`dlgsteal`, d1-d4, GA vs GQ)
- The proxy serves every `GetProperty(_NET_ACTIVE_WINDOW)` reply to the Driver with the value from 1500 ms earlier. The history comes from its own PropertyNotify subscription; the true value is quiet for 1800 ms before the click.
- The decoy steals at R + 100 ms, inside the settle watch.
- Dialog control (`dlgdialog`, dd1-dd2): `harness/dlg_fixture.py` (the canonical window plus "Open dialog", a transient window of the same process), lag on, no steal.

**Normal path** (`nosteal`, n1-n2 checkbox, nt1-nt2 text): GQ only, product defaults (arm P, no `CUA_DRIVER_EXP_*`).

**A2** (`harness/r3q_harness.py`; only this session's launcher, daemon and registry are signalled, with the runtime dir checked before every signal)
- r3n (`launcher_keep`, k1-k5): SIGKILL the launcher. The old dbus-broker stays alive and serving (state S in 20/20 per binary). A new launcher (same socket path) and a new registry start. Fixture B registers on the new bus, and the same Driver process observes B up to 5 times.
- r3w (`launcher_wedge`, w1-w5, supplementary): the old daemon is SIGSTOPped first (state T).
- r3s (`slow`, s1-s5): A is SIGSTOPped during the click. It is SIGCONTed when the click returns (3.45 s), followed by a 4 s oracle window, a fresh observation and a click.
- r3_carry (r1-r2 + supplement rs1): OWN-20P's stream-end restart, run with the blob-identical `harness/r3_harness.py`.

**Reconnect oracle:** the bus monitor attributes every new unique name to its pid through the bus daemon, asked over one persistent helper connection (`harness/bus_pid_helper.py`).

**UNIT:** `unit_run.sh` + `unit_in_session.sh` inside a private session, cargo-build lock only.

## Results (N of M, evidence class per row)

### UNIT

| Tree | Result | Class |
|---|---|---|
| red `74acf32c0` | `a_steal_seen_before_the_active_window_follows_is_not_the_apps_dialog` FAILED; `an_unanswered_call_keeps_the_bus_while_its_daemon_answers_and_loses_a_hung_one` FAILED (the hung-daemon assertion); platform-linux lib 609 passed, 2 failed (`raw/unit/unit-red.log`) | UNIT |
| GQ `4ac191a7c` | both pass; focus_guard 12/12; link + unanswered-call 5/5; platform-linux lib 611 passed, 0 failed, 10 ignored (`raw/unit/unit-green.log`) | UNIT |

### Calibration (no gate; marked twins)

| n | mark-free hold within 5 ms of the mark-keyed hold | R minus mark | U0m silent miss | G0m verified restore | class |
|---|---|---|---|---|---|
| 20 | **20** | median -0.003 ms, max abs 0.01 ms | 10/10 | 10/10 | REAL |

### R1m (gated; product binaries)

| Task / binary | n | valid | silent miss | verified restore | receipts | class |
|---|---|---|---|---|---|---|
| checkbox / U0 | 20 | 20 | 20 | 0 | none 20 | REAL |
| checkbox / G0 | 20 | 20 | 0 | 20 | restored 20 | REAL |
| text / U0 | 20 | 20 | 20 | 0 | none 20 | REAL |
| text / G0 | 20 | 20 | 0 | 20 | restored 20 | REAL |
| control `mfonly` U0 / G0 | 10 / 10 | 10 / 10 | | | verified 10/10 each, **0** false restores | REAL |

A verified restore means all of the following:
- the receipt says `restored`;
- the sampler's final focus and active window equal the reference;
- X RECORD shows a restore request from a non-WM client after the steal, and the WM's last `_NET_ACTIVE_WINDOW` write is the reference;
- the state file confirms the task.

### DLG (gated)

| Binary | n | misclassified (same_app_dialog, focus left on decoy) | verified restore | receipts | dialog control: dialog left focused | class |
|---|---|---|---|---|---|---|
| GA | 20 | **20** | 0 | same_app_dialog 20 | 10/10 | REAL |
| GQ | 20 | 0 | **20** | restored 20 | **10/10** | REAL |

Lag evidence: the median trial served 2 (GA) / 3 (GQ) stale `_NET_ACTIVE_WINDOW` replies to the Driver.

### Normal path (gated; GQ, product defaults)

| Task | n | verified | false restores | spurious reconnects | Peer pings | T median (ms, descriptive, SHARED) | class |
|---|---|---|---|---|---|---|---|
| checkbox | 20 | 20 | 0 | 0 | 0 | 332.127 | REAL |
| text | 20 | 20 | 0 | 0 | 0 | 1760.937 | REAL |

### A2 (gated rows and the supplementary row)

| Row / binary | n | pass | reconnects (bus oracle) | Driver Peer pings | key facts | class |
|---|---|---|---|---|---|---|
| r3n / GA | 20 | 0 | 0 | 0 | old daemon alive 20/20; B never truthful in 5 tries 20/20 (positive control); stale click refused 20/20 | REAL |
| r3n / GQ | 20 | **0** | 0 | 0 | same as GA: the name-owner trigger is not implemented (REVISE from SOURCE) | REAL |
| r3s / GA | 20 | 20 | 0 | 0 | stalled click `effect: unverifiable` (x11_xsendevent) 20/20, no effect landed; bus answered Ping 20/20; fresh click verified 20/20 | REAL |
| r3s / GQ | 20 | **20** | **0** | 40 | same receipts and outcomes; the trigger pinged twice per trial and the bus answered, so no churn | REAL |
| r3w / GA (supplementary) | 10 | 0 | 0 | 0 | old daemon stopped (state T) 10/10; the stale click got no AT-SPI reply and ended `effect: unverifiable` (fallback), no mutation; B never truthful 10/10 | REAL |
| r3w / GQ (supplementary) | 10 | **10** | 10 (one per trial, by design) | 10 | same stale-click receipt, no mutation; the unanswered call's Ping went unanswered, the connection was lost, and B was truthful on the first observation, its click verified 10/10 | REAL |
| r3_carry / GQ | 20 | **20** | | | safety 20/20; 14 trials with a real daemon kill, live 14/14 | REAL |
| r3_carry restart-happened view (with supplement rs1) | 23 killed | live **23**/23, safe 23/23 | | | respawned fixture verified in the same process 23/23 | REAL |

### E4 counters per arm (`own20q-summary.json` `e4`)

- 0 unverified successes, 0 false restores, 0 duplicate mutations, 0 false successes and 0 stale mutations in every arm.
- "Silent miss reported as success" is 40 on U0 (r1m) and 10 on U0m (calibration), and 0 in every other arm. Those are the positive controls of the hole G closes; it is 0 on every G0, G0m, GA and GQ arm.

## Component timings, work deleted vs wall-clock saved

| Change | Work deleted | Wall-clock saved | Class |
|---|---|---|---|
| R1m (harness only) | n/a | n/a | REAL |
| A2 NoReply trigger | none per action. It adds one background Ping only after an unanswered call (0 pings on the normal path) | none claimed. It removes a Driver restart after a hung bus daemon (r3w) | REAL (descriptive) |
| DLG | none | none claimed. Correctness fix: GQ T on the normal path is 332.1 ms (checkbox) under SHARED, descriptive only | REAL (descriptive) |

## Deviations

1. **Observation point of the trigger.** The spec named a private D-Bus proxy. The trigger instead observes the reply through a BecomeMonitor connection on the same private bus, which alters no bytes. An in-path proxy between the fixture and the bus would make the bus report the proxy's pid for the fixture, and the Driver resolves applications by pid (forced-path change). The reasons are recorded in PREREG.json before any counted trial.
2. **r3_carry restart fragility** (blob-identical harness, OWN-20P deviation 2).
   - In r2-004 the harness did not see the new launcher's daemon within its 5 s wait. In r2-005..010 it found no daemon under that launcher and skipped the kill, so no restart happened.
   - Those trials stay counted (gate cell 20/20).
   - A supplement block rs1 was committed (`3c4c49051`) before it ran: 10 GQ trials, of which 9 were real kills. It enters only the restart-happened view: live 23/23.
3. **Lock spacing.**
   - Two counted gaps were 29.1 s instead of >= 30 s: s2→s3 (29.113 s) and w3→w4 (29.107 s).
   - The orchestrator measured the gap from its own whole-second timestamp, taken after the session teardown, while the receipt's release time is written earlier. One pilot pair had the same 0.8-0.9 s shortfall.
   - No measurement depends on it (SHARED lock, no timing claim). The verifier checks that these are the only short gaps, and that both are >= 29 s.
4. **r3s reading.** Both binaries report the stalled click as `effect: unverifiable` (an honest receipt). That outcome is neither refused nor verified, so the strict per-click reading cannot be met by any binary. The pre-registered reading applies: no false success, and the trial ends refused or verified.
5. **First UNIT attempt hung** (`raw/unit/unit-red-first-attempt-hung.log`).
   - The A2 test's first private-bus config (type session) never completed a connection, so the test waited on `build()` for ~13 minutes under the cargo lock. It was stopped (own processes only).
   - The test now uses a custom-type config and a 5 s connect timeout. The fix commits were rewritten before anything was published, and GQ was rebuilt from 4ac191a7c.
   - The pilots partly ran the earlier GQ 2368a3425 (`raw/build/build-gq-2368a3425-pilot-only.log`). Pilots are excluded from every count.

## Limits

- Linux X11 only (private Xvfb + openbox; the a11y bus is dbus-broker under at-spi-bus-launcher). Wayland/Hyprland: BLOCKED (seat).
- The DLG lag (1500 ms) and the R1 hold (2000 ms) are harness amplifications of real races: OWN-20G's 10 counted same_app_dialog cases, and N-02's c08-017. They make the races deterministic; they do not measure how often the races occur.
- The A2 NoReply trigger is only as fast as the call budget: the stale click took ~3.45 s before the ping, and the ping waits up to 1 s.
- The launcher-restart case with a healthy orphaned daemon (r3n) stays unrecovered on GQ. That is the REVISE.
- In the pilots, the old and new launchers used the same socket path, so a reconnect lands on the new daemon. That is not guaranteed on other systems.

## Claim boundary

- Fork fix candidates on the clean main 0f1955d2f lineage (`cb685fad7`, `libs/cua-driver` Linux tree `df2b49c32e73`); Linux X11; the canonical GTK3 fixture; the exact SHAs and binaries above.
- Nothing was written upstream or to GitHub.
- Upstream items are cited as plain text (trycua/cua PR 4529).

## Disposition

- **R1m: KEEP.** The mark-free stall reproduces c08-017 on U0 and G0 (40/40, 40/40, 0 false restores). The marked-twin substitution can be retired for the gating row (owner reading pending).
- **DLG (4ac191a7c): KEEP**, fork candidate.
- **A2: REVISE.** The named failing gate is r3n: the name-owner trigger needs a persistent session-bus connection (SOURCE), so it was not implemented. The revised claim was measured: the NoReply + Peer.Ping trigger (31318e374) holds r3s (no churn), r3w (wedged daemon recovered 10/10) and r3_carry (20/20; 23/23 real restarts), with UNIT red/green.
- **Hyprland/Wayland: BLOCKED (seat).**

## Files

| File | Contents |
|---|---|
| `PREREG.json`, `plan.json`, `make_plan.py`, `plan-pilot.json`, `plan-supp.json`, `make_plan_supp.py` | Pre-registration, frozen plan, pilot plan, committed supplement |
| `harness/own20g_harness.py`, `harness/r3_harness.py`, `harness/harness_common.py`, `harness/stealer.py`, `harness/xstall_proxy.py`, `harness/xprobe.py`, `harness/run_block.sh`, `harness/driver_versions.sh` | OWN-20G/OWN-20P harness, blob-identical |
| `harness/markfree_proxy.py`, `harness/q_common.py`, `harness/bus_pid_helper.py`, `harness/own20q_harness.py`, `harness/r3q_harness.py`, `harness/dlg_fixture.py` | New harness files |
| `run_all.sh`, `session_entry.sh`, `unit_run.sh`, `unit_in_session.sh` | Orchestration, locks, units |
| `analyze.py`, `package.py`, `verify_artifacts.py`, `verify_helper.py` | Recompute, raw copy and scrub, verifier, helper (blob-identical to OWN-20P's) |
| `own20q-summary.json`, `own20q-trial-metrics.jsonl.gz`, `provenance.json` | Results and provenance |
| `raw/own20q-m-c1/trials.jsonl.gz` ... `raw/own20q-m-w5/trials.jsonl.gz` and each `session.txt` | One ledger per counted block (39) |
| `raw/own20q-supp-rs1/trials.jsonl.gz` | Supplement (restart-happened view only) |
| `raw/own20q-pilot-pc1/trials.jsonl.gz` ... `raw/own20q-pilot-pw1/trials.jsonl.gz` | Pilots, excluded |
| `raw/lock-ledger.jsonl` | Every quiet-lane receipt of this lane |
| `raw/unit/unit-red.log`, `raw/unit/unit-green.log`, `raw/unit/unit-red-first-attempt-hung.log` | UNIT logs |
| `raw/build/build-gq.log`, `raw/build/build-gq-2368a3425-pilot-only.log`, `raw/build/lane-deps.log` | Builds |
| `raw/source/gq-vs-ga.patch`, `raw/source/red-vs-green.patch` | Source records |
| `raw/heads/heads-start.json`, `raw/heads/heads-end.json`, `raw/runs/run_all-main.txt`, `raw/runs/run_all-supp.txt` | Live heads, orchestration logs |
