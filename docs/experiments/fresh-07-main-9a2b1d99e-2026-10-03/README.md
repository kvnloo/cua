# FRESH-07: freshness of the surviving claims on upstream main 9a2b1d99e

Lane FRESH-07, wave 7 of the CUA RFC loop (E6 freshness). Owners: kvnloo/cua#73 (freshness),
kvnloo/cua#93, kvnloo/cua#20 / #36 / #16 (X11 rows). Provider: TypeSafe cap 0; 0 attempts, 0 reached.

This packet assigns a disposition to every Linux-relevant `libs/cua-driver` change between
`0f1955d2f` (the tested line of the surviving claims) and upstream main `9a2b1d99e`. It calls each
surviving claim UNAFFECTED (with SOURCE and UNIT or FIXTURE evidence) or AFFECTED, and recertifies
the AFFECTED rows on the new source. Upstream items are written as plain text, for example
trycua/cua PR 4529.

## Result in one paragraph

Three Linux-relevant changes landed:

- trycua/cua PR 4529 (`5e13eb777`, platform-linux `overlay.rs`): the idle X11 agent-cursor overlay
  now stays unmapped until a frame is painted.
- trycua/cua PR 4531 (`15c6c24e2`, cua-driver-core `expectation.rs`): `verify_state` handles rows
  marked `display_only`.
- The 0.33.0 version bump.

`expectation.rs` and the version bump are **UNAFFECTED** for every claim (SOURCE + UNIT). On the
default-off smoke, the tools/list reply is byte-identical to R2-10R's on the old line (sha256
`33772fab...`).

`overlay.rs` changes the X11 window tree in every arm that runs the overlay.
- On the old line the overlay is mapped at idle.
- On 9a2b1d99e it is unmapped at idle and gets mapped by the first cursor reveal.

The probe found a side effect. The Driver's own focus guard counts the newly mapped overlay as an
application popup. Its `mapped_popups()` has no own-overlay filter. The guard therefore reports
"A popup menu is open, so pid N holds a keyboard grab" on a plain background click:
- M (plain 9a2b1d99e): 5/5;
- every old binary: 0/15.

Phase 2 re-ran the guard rows on 9a2b1d99e replays of the original commits:

| Row | Restore result on the new source | Gate |
|---|---|---|
| OWN-20P R1 (G0m'') | 20/40: checkbox 0/20 (`focus_outcome=grab_held`, focus left on the decoy), text 20/20 | **FAILS** |
| OWN-20Q R1m (G0'') | 20/40, same pattern | **FAILS** |
| OWN-20Q DLG (GQ'') | 0/20 restored (grab_held 20/20) | **FAILS** |

The positive controls, the no-steal normal paths and the dialog control still hold. The timing rows
(R2-10R scripted and native, N-04) are AFFECTED by SOURCE. Their recertification is
**BLOCKED_PENDING_LOCK** (see Blockers) unless the Phase 2 timing section below reports numbers.

B-07, B-08, FIX-03, RECERT-FIX, OWN-16W X11, OWN-20P R3, OWN-20Q A2 and R2-10R D1 are UNAFFECTED by
SOURCE, with the probe facts cited.

## Five mechanism requirements

| Requirement | This packet |
|---|---|
| Forced path | Phase 1 probe: product-default Driver (`mcp` over stdio, no `CUA_DRIVER_EXP_*`). Background `click` of the GTK3 fixture's "I agree" check box by `element_token`, the N-03/N-04/OWN-20 route through `focus_guard::guarded`. Run with the cursor on, then again after `set_agent_cursor_enabled {enabled:false}`. Phase 2: each original harness on its original forced path (orig/<lane>/, blob-identical). |
| Actual route / producer | Click receipts report `route: accessibility` (probe `S2_on_click.guard.route`). The overlay producer is the X11 owner thread `Cua.AgentCursorOverlay.<session>` (WM_NAME read by the probe). |
| Independent target-owned oracle | Probe: the private Xvfb's window tree, read by a separate libX11/libXext client (`harness/xtree.py`). It reads map state, shape rectangle counts, input focus, `_NET_ACTIVE_WINDOW`, the top of `_NET_CLIENT_LIST_STACKING`, mapped override-redirect children and the XQueryPointer child. The fixture's own state file confirms each click (20/20 per binary). Phase 2 uses the original oracles: the 2 ms X focus sampler, the fixture state files and X RECORD. |
| Negative / fallback controls | Old binaries R', B7, R'n in the same probe (0/15 grab reports). Live overlay tests run on both lines in the same session (fail on both, so they do not discriminate; environment). Phase 2: U0m''/U0'' silent-miss positive controls, `replyonly` / `qc*` no-false-restore controls, GA'' DLG positive control, the dialog control, and no-steal normal paths. Default-off smoke R'' = Cn''. |
| Exact provenance | provenance.json: every source SHA and libs tree, every binary sha256 and version, replay patch-ids (raw/build/patch-ids.txt), live heads (raw/heads-start.txt), environment, and lock receipts. |

## Provenance (summary; full list in provenance.json)

- Old line: `0f1955d2f1ee2b01b40775aa53ea2af0b5544218` (libs/cua-driver tree `df2b49c32e73`).
- New main: `9a2b1d99ec8044ff58b2a2b46802edd2609c057b` (tree `42ce4dfcc493`). At start (16:10:57Z), gh read trycua/cua main = `9a2b1d99e`.
- Probe binaries:
  - R' `922111c5` (R2-10R a2), 0.32.0;
  - B7 `6f95aef5`, 0.32.0;
  - R'n `78a1137d`, 0.32.0;
  - M `795dca5a`, plain 9a2b1d99e, 0.33.0.
- Phase 2 binaries. Each is 9a2b1d99e plus a replay of the original commits; the patch-id of each replay equals the original's.

  | Binary | sha256 | Source |
  |---|---|---|
  | R'' | `4d95eb4f` | cec1a5b92 |
  | Cn'' | `015e2f54` | 82e6d5227 |
  | R''n | `e48487ae` | bbe2bd6e6 |
  | U0'' | M | plain 9a2b1d99e |
  | G0'' | `f3c7eb0c` | c99fcb3cf |
  | GA'' | `18f9aeaf` | 6f850b558 |
  | GQ'' | `62406b3c` | 8abd5789f |
  | U0m'' | `914b585d` | 8d6d4189a |
  | G0m'' | `686f72a6` | 270ca36b2 |

- Live heads read-only at start: trycua/cua PR 4316 `a0bca7440`, PR 4336 `8391cf802` and PR 4394 `039257811`, all open and unchanged; PR 4529 merged as `5e13eb777`; PR 4531 merged as `15c6c24e2`. kvnloo/cua#84 `566b9c732`, #105 `98a45e6c5` and #106 `c45845797`, all open. End-of-lane reads are in raw/heads-end.txt.
- Publication SHA: set by Publish; never assumed equal to a tested SHA.

## Method

### Phase 1a: diff inventory (SOURCE)

`inventory.py` classifies all 39 changed paths under `libs/cua-driver` by explicit rules. The result
is complete: no path is unclassified or matched twice (raw/source/inventory.json).
- Linux-relevant (exactly the expected set): `overlay.rs`, `expectation.rs`, `Cargo.lock`, `Cargo.toml`, `VERSION`, `tests/fixtures/shared/scenarios.json`.
- `scenarios.json` only adds a scenario to its `appkit` section, which no Linux fixture, core or jev-use file reads.
- The other 33 paths are non-Linux: platform-macos (8), platform-windows (5), the AppKit/WinUI3/WPF e2e tests and their WinUI3/WPF-only support module (4), macOS/Windows fixtures (5), docs/Skills/CHANGELOG (5), and binding/installer version strings (6).

### Phase 1b: overlay.rs map (SOURCE)

Where the overlay is created, mapped and painted:
- **Creation.** The X11 overlay thread starts at registration whenever the cursor template is enabled (the default) and `WAYLAND_DISPLAY` is unset (`lib.rs:243-246`, `overlay.rs:751-797`).
- **Startup.**
  - Old line: maps the full-root override-redirect window with empty bounding and input shapes.
  - 9a2b1d99e: prepares the same shapes and leaves the window unmapped (`overlay.rs:1286-1299`).
- **Paint.** `paint_x11_tiles` maps the window on the first frame with a visible shape and unmaps it on an empty frame (`overlay.rs:2766-2781`). `blank_x11_overlay_shape` also unmaps (`:2616`) on capture hold and resync.
- **Browser actions.** `browser_platform.rs:501-535` animates and awaits the X11 arrival only when the session cursor is enabled. With it disabled, it sends `SetEnabled(false)` and returns before animating.
- **Native pointer and element actions.** These always revive the cursor (`tools/impl_.rs:5318-5338`, `reveal_pointer_action_for`) before the guarded AT-SPI action (`impl_.rs:6372-6457`). With an unknown start position the reveal sends a ClickPulse without awaiting arrival (`impl_.rs:5303-5309`). The overlay then maps asynchronously while the guard snapshots.
- **Readers of override-redirect map state.** `focus_guard.rs:191-205 mapped_popups()` has no own-overlay filter; its diff at `:621-631` sets `grab_held_by`, and on a seen focus change the guard returns without restoring. `input/foreground.rs:204-212` keeps pid-less popups in its window set. `tools/impl_.rs:976-984` filters `Cua.` titles and is not affected. `input/targeted.rs window_at` uses `_NET_CLIENT_LIST_STACKING`, which never lists override-redirect windows.

### Phase 1c: window-tree probe (FIXTURE)

`harness/probe.py` ran inside `hostless` + `cua-x11-session.sh` with AT-SPI: n = 5 runs × 4 binaries, rotated order, SHARED quiet lock. PREREG.json (`975f31d1e`, 16:06:26Z) was committed before the first probe trial; the pilot at 16:09:52Z is excluded and kept in raw/pilots/.

### Phase 1d: UNIT on 9a2b1d99e

Run under hostless, the cargo lock and the private session.
- `cargo test -p cua-driver-core expectation`: 20 passed, 0 failed (includes the 3 new display_only tests).
- Full cua-driver-core: lib 823 passed, 0 failed; every integration test binary passes.
- platform-linux overlay filter: 106 passed, 3 ignored. Full lib: 602 passed, 0 failed, 10 ignored. Integration: `kwin_helper_contract` 8 passed; the X11 integration tests are ignored by design.
- The 3 ignored live overlay tests were also run explicitly. They fail **on both lines identically** in the openbox+picom session: the tests expect a bare `xvfb-run` without a window manager. They are therefore reported as not discriminating, not as evidence (raw/unit/, raw/unit-old-control/).

### Phase 1d/e: SOURCE greps

- **expectation.rs** (raw/source/expectation-source.txt):
  - `display_only` is produced only by platform-macos.
  - `evaluate_predicates` is called only by VerifyStateTool.
  - No claim harness calls `verify_state`: 0 files in all 10 claim packets.
- **Version bump** (raw/source/version-bump.txt):
  - The Linux crates differ only in the two files above.
  - The 127 `CUA_*` string literals are identical.
  - `tool_schema.rs` (blob `e9420949`) and the contract tree are unchanged.
  - Cargo.lock changes only the 14 workspace package versions.
  - Runtime corroboration: Phase 2 default-off smoke, tools/list sha256 `33772fab...` on both R'' and Cn''. This is the same digest R2-10R recorded on the old line.

### Phase 2

PREREG-P2.json (`f8859411b`, 16:26:26Z) was committed before the first Phase 2 trial (16:37Z).
- **Builds:** 9a2b1d99e plus exactly the original step commits, cherry-picked. The R2-10 step-2 merge of trycua/cua PR 4316 head `a0bca7440` was replayed as a merge, as R2-10R did. Each replay's libs/ patch-id equals the original lane's.
- **Harnesses:** the original files, copied blob-identically: 90/90 blobs match their source commits (raw/source/orig-manifest.tsv, `orig_manifest.sh`).
- **Locks:** guard rows ran through the original `run_all.sh` under the SHARED lock. Timing rows run through `harness/fresh07_chunks.sh`, which:
  1. checks the cargo lock before acquiring;
  2. takes `bin/quiet-timed fresh07-<chunk>`, then `flock -w 60` on the cargo lock inside, then `timeout -k 15 900`;
  3. applies the loadavg ≤ 4.0 round-start rule in `harness/r210r_session.sh` and in N-04's own runner.

## Results

### Phase 1c probe (raw/probe/probe.jsonl → probe-summary.json; FIXTURE)

| Read point | R' / B7 / R'n (old line), 15 runs | M (9a2b1d99e), 5 runs |
|---|---|---|
| S1 idle | VIEWABLE, 0 bounding / 0 input rects, 15/15 | **UNMAPPED** 5/5 |
| S2 just before the cursor-on click | VIEWABLE (empty) 15/15 | UNMAPPED 5/5 |
| S2 right after the click reply (oracle-read time) | VIEWABLE (66 rects), 0 input rects, 15/15 | VIEWABLE (66 rects), 0 input rects, 5/5 |
| S2 + 1.5 s | VIEWABLE (57) 15/15 | VIEWABLE (57) 5/5 |
| S3 after `set_agent_cursor_enabled false` | VIEWABLE (empty) 15/15 | **UNMAPPED** 5/5 |
| S3 after the next click (native reveal revives the cursor) | VIEWABLE 15/15 | VIEWABLE 5/5 |
| Overlay in the guard's popup view before the click | 15/15 | 0/5 |
| Click text "A popup menu is open, so pid N holds a keyboard grab" | 0/15 cursor on, 0/15 after disable | **5/5** cursor on, **4/5** after disable |
| Focus / active window / stack top identical at every read | 15/15 | 5/5 |
| XQueryPointer child is the overlay | 0 reads | 0 reads |
| Click verified by the fixture state file | 30/30 | 10/10 |
| Overlay VIEWABLE before the MCP initialize reply (T3) | 15/15 (overlay at 11.0–83.4 ms after spawn; reply at 148.8–222.7 ms) | n/a (never mapped at startup) |

### Per-claim dispositions (claims.json carries the citations)

| Claim (accepted packet) | Change | Disposition | Evidence |
|---|---|---|---|
| every claim | expectation.rs | UNAFFECTED | SOURCE (no Linux display_only producer; no claim calls verify_state) + UNIT 20/20, 823/0 |
| every claim | version bump | UNAFFECTED | SOURCE (env literals, schema blob, contract tree identical) + REAL smoke tools/list digest equal to R2-10R's |
| R2-10R scripted browser S rows (c183b95e3) | overlay.rs | AFFECTED (T1: BASE/COMP_K await the X11 arrival) | SOURCE + probe S1/S2 |
| R2-10R native S rows (c183b95e3) | overlay.rs | AFFECTED (T2: guard post-check inside T) | SOURCE + probe grab text 5/5 |
| R2-10R D1 grace row | overlay.rs | UNAFFECTED | SOURCE: observation only; probe: no transition without an action |
| B-07 (eab1e87a3) | overlay.rs | UNAFFECTED | SOURCE: all arms cursor off on the CDP route, no guard; T3 holds 15/15 |
| B-08 (49ae94590) | overlay.rs | UNAFFECTED | as B-07; the old startup map completes before the initialize reply (B7 5/5), so before T0 |
| N-04 (9d7d8d7a5) all rows | overlay.rs | AFFECTED (T2) | SOURCE + probe |
| N-03 (6b70ec902) | overlay.rs | AFFECTED (T2; ax_fg foreground window set) | SOURCE; not recertified here (superseded for E2/E3 by N-04; ax_fg S0 is a follow-up) |
| OWN-20P R1 / NORMAL (64081dded) | overlay.rs | AFFECTED (T2 counted) | recertified below |
| OWN-20P R3 incl. safety, noop_direct | overlay.rs | UNAFFECTED | SOURCE: token refusal / reconnect decided before the guard post-check; no steal |
| OWN-20Q R1m / DLG / normal (44116546d) | overlay.rs | AFFECTED (T2 counted) | recertified below |
| OWN-20Q A2 r3n/r3s/r3w/r3_carry | overlay.rs | UNAFFECTED | SOURCE: reconnect decisions in atspi/native.rs; no steal |
| FIX-03 (e300edbd3) A1-A3, WS/WK/WR | overlay.rs | UNAFFECTED | SOURCE: refusal before delivery; landings counted by X RECORD; guard post-check not counted |
| RECERT-FIX (939580fc6) all rows | overlay.rs | UNAFFECTED | SOURCE: refusal / landing / duplicate counts precede any guard post-check; OWN-09R has no display action |
| OWN-16W X11 string row (1b9819157) | overlay.rs | UNAFFECTED | SOURCE: refused at argument parsing, no producer runs |

### Phase 2: guard rows on 9a2b1d99e (REAL, FIXTURE, SHARED lock; original harnesses and analyzers)

OWN-20P (p2/own-20p/own20p-recert-summary.json; 220 focus trials, 0 failed blocks, 0 non-loopback connects):

| Row (original gate) | Old line (accepted) | 9a2b1d99e replay | Gate |
|---|---|---|---|
| R1 G0m pass 40/40, 0 silent misses | 40/40 | **20/40**: checkbox 0/20 (receipts `grab_held` 20, final focus on the decoy 20), text 20/20 restored | **FAIL** |
| R1 U0m silent miss ≥ 36/40 (positive control) | 40/40 | 40/40 | holds |
| R1 control `replyonly`: 0 false restores | 0 | 0 (10/10 verified per binary) | holds |
| NORMAL: G0 verified 40/40, 0 false restores, G0 failures ≤ U0 | 40/40 | 40/40, 0, 0 ≤ 0 | holds |
| m1-m4 marked settle (descriptive) | – | 40/40 verified, 0 false restores | – |

OWN-20Q (p2/own-20q/own20q-summary.json):

| Row (original gate) | Old line (accepted) | 9a2b1d99e replay | Gate |
|---|---|---|---|
| R1m: G0 verified restore 40/40, U0 silent miss ≥ 36/40, 0 false restores | 40/40, 40/40, 0 | **G0'' 20/40** (checkbox 0/20, `grab_held` 20; text 20/20), U0'' 40/40, 0 | **FAIL** |
| DLG positive control: GA misclassifies ≥ 16/20 | 20/20 | 20/20 (`same_app_dialog`) | holds |
| DLG: GQ correct 20/20, 0 same_app_dialog | 20/20 | **0/20 restored** (receipts `grab_held` 20, 0 same_app_dialog) | **FAIL** |
| Dialog control: app's own dialog left focused 10/10 per binary | 10/10 | 10/10 GA'', 10/10 GQ'' | holds |
| Normal path GQ: 40/40 verified, 0 false restores, 0 spurious reconnects | 40/40 | 40/40, 0, 0 | holds |
| Calibration (no gate) | G0m 10/10 restore | G0m'' 0/10 restore, U0m'' 10/10 silent; mark-free hold within 5 ms 20/20 | – |

Mechanism, consistent with the probe and with P2-1 of PREREG-P2:
- **Checkbox task.** The click is the first action in a fresh Driver. Its reveal sends a ClickPulse without awaiting the paint, so the overlay maps after the guard's snapshot. The guard then counts the overlay as a new popup and reports `grab_held`. It does not restore the stolen focus.
- **Text task.** `set_value` reveals the cursor first, so the overlay is already mapped when the click's guard snapshots. Restore works (20/20).

The no-steal normal paths hold because the guard never tries to restore when nothing moved. The click text still carries the false "popup menu is open" sentence.

### Phase 2: default-off smoke (REAL, SHARED, non-timing)

R2-10R phase 0 (d), evaluated with the original `analyze_r2_10.phase0`:
- tools/list identical on R'' and Cn'' (sha256 `33772fab...`, 3 reads each). This equals the digest R2-10R recorded for R' on the old line.
- Browser fill/toggle/modal 5/5 verified on both binaries, with identical receipt shapes.
- Native checkbox/text 5/5 verified on both, with identical receipt shapes.
- 0 trace-like files; native phase files stay empty.
- Verdict: **pass**.

N-04 smoke `smk-rn` (R''n) and `smk-rp` (R'') ran. They are analysed with the N-04 rows in p2/n-04/.

### Phase 2: timing rows (R2-10R scripted + native, N-04)

See the section "Timing rows status" appended at the end of this README. It records whether the EXCLUSIVE windows ran, and either the numbers or the blocker.

## Work deleted vs wall-clock saved

This lane deletes no work and claims no saving. Freshness only.

## E4

E4 (correctness invariants) on the new source:
- Probe: 0 unverified successes (30/30 + 10/10 clicks verified by the fixture state).
- OWN-20P e4 counters: 0 stale mutations, 0 stale token actions, 0 unverified successes in every arm. Silent steal misses occur only in the U0m'' positive control (20 + 20, by design).
- The guard's `grab_held` receipt on G0m''/G0''/GQ'' is a false claim about the desktop: no popup exists. It is reported as a changed claim, not hidden.

## Deviations

1. **Phase-1 preliminary table.** It listed "safety" with the OWN-20P guard rows. In the OWN-20P PREREG, R3 safety means: the pre-restart token is refused and 0 stale mutations occur, which is a token decision. It is therefore UNAFFECTED by SOURCE and was not re-run. The R3 blocks did not run.
2. **E5 field source.** The structured focus-guard fields (`grab_held_by`, `focus_outcome`) are reduced away by the public action contract. The probe therefore reads the guard's summary sentence from the click text (`summarize_probe.py`).
3. **Load rule scope.** `r210r_session.sh` / `fresh07_chunks.sh` gained `FRESH07_NO_LOAD_GATE` for non-timing smoke and tools/list calls after PREREG-P2. No trial had completed: the first 4 tools-list chunks exited 75 on the load rule before any call. The change is commit `4c4e90ae5`.
4. **Native smoke argument error.** The first native smoke attempts (8 chunks) exited at argparse because `--plan-sha256` was missing. No trial ran. The rerun with the argument passed 5/5 + 5/5.
5. **Lock receipts label.** OWN-20P/Q blocks write their receipts with the original lane names ("OWN-20P"/"OWN-20Q") and `fresh07-own20*` labels, because `run_all.sh` is used unchanged.
6. **Probe scope.** Native only. Browser feedback-on/off map behaviour is taken from SOURCE (`browser_platform.rs:501-535`); the overlay owner thread is shared. Browser timing is covered by the R2-10R recert, if it runs.

## Limits and claim boundary

Freshness only; no new product claim. The scope is Linux X11 (private Xvfb + openbox + picom) and the canonical GTK3 fixture. The binaries are the exact sha256s in provenance.json.

The focus-guard regression is shown on the replayed guard ports G0''/GQ'' and on plain 9a2b1d99e (U0'' = M, by the probe's grab text). A fix is out of scope here. The SOURCE-indicated candidate: exclude the Driver's own `Cua.AgentCursorOverlay.*` window (no `_NET_WM_PID`) from `focus_guard::mapped_popups`, as `tools/impl_.rs:976-984` already does.

An UNAFFECTED call never rests on absence of evidence. Each cites SOURCE lines, plus the probe facts for overlay.rs.

## Disposition

E6 freshness for 0f1955d2f → 9a2b1d99e:
- **RECERT_FAIL** for the kvnloo/cua#20 guard claims. changed_claims:
  - OWN-20P R1 (G port restore 40/40 → 20/40);
  - OWN-20Q R1m (40/40 → 20/40);
  - OWN-20Q DLG (GQ 20/20 → 0/20).

  All three change through the overlay's new map transition seen by `focus_guard::mapped_popups`.
- **UNAFFECTED:** every other non-timing claim (table above).
- **Timing rows:** see "Timing rows status".
- **Follow-ups:**
  - a fork fix candidate for `mapped_popups` (#20);
  - N-03 Part B ax_fg recert on 9a2b1d99e;
  - the timing rows, if blocked.

## Timing rows status

p2/timing-status.json gives the machine-readable state.

- **Status:** BLOCKED_PENDING_LOCK.
- **Queued:** the R2-10R scripted chunk `fresh07-S-c01` has waited for the EXCLUSIVE quiet-lane lock since 17:59:21Z.
- **Cause:** long-lived processes of another track hold an inherited fd on `quiet-lane.lock` in SHARED mode, so no `bin/quiet-timed` window can open. These are the z0-wt wiring stub and tdb servers; the oldest has run for more than 2 h 47 min. Another lane's EXCLUSIVE waiter, `r207g-T1`, has waited since about 16:13Z. The processes are listed in raw/locks/lock-holders-*.txt, from read-only /proc scans.
- **What this lane did not do:**
  - It did not kill those processes, because it did not start them.
  - It did not run the timing rows in SHARED mode, because the rule requires EXCLUSIVE windows.
- **Consequence:** R2-10R scripted + native and N-04 stay **AFFECTED (by SOURCE), not recertified** on 9a2b1d99e.
- **Ready to run:** the binaries R'' / R''n, the original harnesses and the chunk runners are in place.
