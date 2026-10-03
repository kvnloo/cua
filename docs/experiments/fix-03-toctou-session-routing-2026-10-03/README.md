# FIX-03: the F4 set_input_files TOCTOU window, the recording-lookup session test, pid-only snapshot routing and the (pid, xid) side index, and discriminating W2c/W2d variants (2026-10-03)

Owners: kvnloo/cua#36, kvnloo/cua#105, kvnloo/cua#73 (E4 residue). Wave 6 of the CUA RFC loop. Fork fix
candidates on upstream `0f1955d2f` only: nothing here is merged anywhere, and nothing was pushed or posted.

## Result in one paragraph

- **F4 (set_input_files): REVISE, IRREDUCIBLE-with-honest-unknown.** The forced race reproduces the hole on
  F'S: 20/20 success receipts for a detached input (positive control). F5 never reports success: 0/20 success
  receipts and 20/20 refusals with `browser_ref_stale` + `{delivery: unknown, retryable: false}`. But Chromium
  still assigns the files to the detached node: in 20/20 F5 cells a generation-0 `change` event reached the
  fixture server. CDP cannot run the connectedness check and `DOM.setFileInputFiles` in one renderer task
  (SOURCE), so the pre-registered A1 gate fails on its third clause, exactly as predicted. A2 (rebind) 20/20
  and A3 (default path, receipts identical to F') 20/20 + 20/20.
- **Part B (recording lookup): KEEP.** The new unit test is red on U' and green on F5.
- **Part C: KEEP, with a fix.** The pid-only `snapshot_id` routing reader is unreachable: the registry refuses
  `snapshot_id` as an unknown argument for every guarded tool before the tool runs (U', F', F5: 20/20 and 30/30,
  0 mutations, 0 X RECORD activation of A's window). The **(pid, xid) side index is a real cross-session hole on
  F'**: a session's OWN valid token wrote text into the other session's window 20/20 attempts (12 + 8, WS) and
  toggled the other window's checkbox 20/20 (10 + 10, WK). F5 passes the token's window to the two readers:
  WS 20/20 and WK 20/20 on the session's own window, 0 cross-window effects.
- **Part D:** W2dX (cross-session dispatch after w1 closes) is **discriminating**: U' lands 20/20, F5 refuses
  20/20 (`stale_element_token`), A's tail verified 20/20. W2cX (cross-session capture) is **non-gating**: U'
  refuses it 20/20 too (`capture_generation_mismatch`), as the SOURCE predicted. W2c/W2d proper are
  non-discriminating by construction.
- **E4 (F5):** 0 on every counter in every row except the seam-forced A1 residue (20 stale dispatches to a
  detached node, the irreducible F4 window). Strict E4 = 20, excluding that residue = 0.
- **Regression (F5):** cua-driver-core `--lib --tests` 862 passed / 0 failed, platform-linux `--lib` 603 / 0,
  jev-use Python 241 OK (1 skipped), TypeScript 116/116, typecheck rc 0.
- **Provider:** TypeSafe not used: 0 attempts, 0 reached (lane cap 0).

## Dispositions (pre-registered rules; `dispositions.json` from `analyze.py`)

| Item | Disposition | Gating evidence | Evidence class |
|---|---|---|---|
| F4 TOCTOU (FIX-02 F4 REVISE) | **REVISE: IRREDUCIBLE-with-honest-unknown** | FS success-for-detached 20/20 (PC); F5 0/20 success, 20/20 refused+unknown; F5 gen0 change reached the server 20/20 (gate clause 3 FAILS); A2 20/20; A3 20/20 + 20/20, one receipt shape | REAL, UNIT, SOURCE |
| B recording lookup | **KEEP** | red on U' (B resolves A's capture), green on F5 | UNIT, SOURCE |
| C routing (`window_for_snapshot`) | **KEEP** (no fix needed) | WR s1/s2 refused `invalid_arguments` on U' 20/20, F' 20/20, F5 30/30; 0 mutations; 0 X RECORD activation of w1 (oracle control s5 observed 20/20, 20/20, 20/20 live) | REAL+FIXTURE, SOURCE |
| C side index (pid, xid) | **KEEP with F5 fix** | F' WS 20/20 and WK 20/20 attempts with a write/toggle into the other session's window; F5 0/20 and 0/20, own-window effect 20/20 each | REAL+FIXTURE, SOURCE |
| D W2dX | **discriminating KEEP** | U' landed 20/20; F5 refused 20/20, tail 20/20 | REAL+FIXTURE |
| D W2cX | **non-gating** | U' refused 20/20 (capture binding predates FIX-02) | REAL+FIXTURE, SOURCE |
| D W2c / W2d proper | **non-discriminating by construction** | capture admission and AT-SPI object liveness are unchanged by FIX-02 (`source-audit.json`) | SOURCE |
| FIX-02 F1-F3 regression | **0 failures** | core 862/0, linux 603/0, jev-use py 241 OK, ts 116/116 | UNIT |

## Provenance (each SHA kept separate)

| Item | Value | Class |
|---|---|---|
| Upstream base | `0f1955d2f1ee2b01b40775aa53ea2af0b5544218` (rust tree `03907b569c54`, libs/cua-driver `df2b49c32e73`) | SOURCE |
| U' | `513e45fee0c5b02c7dd6d41a960f925a164b5066`, binary `cua-driver-fix02r3-u-513e45fee`, sha256 `3d27b55b76bdfa64d8659100f995db23400c3b46c06543832aa3c8acb0b31acd` (equal to RECERT-FIX provenance at `939580fc6`, re-read at lane start) | SOURCE |
| F' | `df4f1edf56a6b1ca01cd2f9facbed3dc4843280c`, binary `cua-driver-fix02r3-f-df4f1edf5`, sha256 `e438980aa6812ac43a63793fca001fc1e2d86515a105eeb099f6a9c269fd64a1` (equal to RECERT-FIX provenance) | SOURCE |
| F'S | `5a1e209aba39b02fdc7b1dfe8f3afbf184405038` = F' + seam; binary `cua-driver-fix03-fs-5a1e209ab`, sha256 `d247ef8d7e3c94709716e6201155ba9e3651468613a9fad230a2d8ff0ba44dda` | SOURCE |
| PREREG + harness | `5827f04d07e96f5ba2a4f9421fb1b7351ef9e2fb`, committed 2026-10-03T13:55:41Z; first counted lock acquisition 14:01:14Z | SOURCE |
| F5 | `2237cf9c6328899583843a48f3a507af5ba0fb1f` = F'S + PREREG + `b235fabef` (F4 post-assignment check) + `37d17e0b3` (Part B test) + `2237cf9c6` (side-index readers); rust tree `4a6f155eb73a` = pre-registration draft `68677a11d`; binary `cua-driver-fix03-f5-2237cf9c6`, sha256 `10d710753ba85454632005cb9a40946abaf40d0ff0571885e08f85e9d7de1dd4` | SOURCE |
| Versions | all four binaries report `cua-driver 0.32.0` inside the private session (every `validity.json` / block header) | SOURCE |
| Builds | `hostless flock cargo-build.lock build-driver.sh <wt> <label> cua-release-fix02r`, 0 Fresh workspace units (`raw/builds/`) | SOURCE |
| Live heads at start (13:04:53Z) | trycua/cua main `c8edda06be53`; trycua/cua PR 4316 head `a0bca7440` (OPEN); kvnloo/cua#105 head `98a45e6c5` (OPEN) | SOURCE |
| Live heads at end (14:50:25Z) | trycua/cua main `65bf638ba6dc` (moved); PR 4316 `a0bca7440` (OPEN, unchanged); kvnloo/cua#105 `98a45e6c5` (OPEN, unchanged). Drift `0f1955d2f...65bf638ba`: 35 files under libs/cua-driver, **0** under cua-driver-core, cua-driver-sdk, cua-driver, cua-driver-contract, platform-linux, jev-use or the Linux fixture (macOS/Windows harnesses, version files) (`raw/heads/`) | SOURCE |
| Publication SHA | set by Publish (`provenance.json`), never equal-by-assumption to the tested SHAs | SOURCE |
| Environment | Linux 7.2.2 x86_64, rustc 1.97.1; `bin/hostless` v2; `cua-x11-session.sh` (private rootless Xvfb, openbox, picom, private D-Bus; AT-SPI for native rows); jev-use venv Python 3.12, Node v22.23.2; GTK3 fixture on system Python + gi; Chrome launched by the Driver (`browser_prepare isolated_new`); X RECORD on python-xlib 0.33 (lane-temp venv, outside the repo); telemetry off; 1-min loadavg at lock acquisition 0.40 to 9.29 | SOURCE |
| Provider | 0 attempts, 0 reached | SOURCE |

## The fixes (commit group 3)

1. **`b235fabef` F4 post-assignment check** (`cua-driver-core/src/browser/tools.rs`). The resolved objectId from
   the existing check is kept; after `DOM.setFileInputFiles` the same object is re-checked. Not connected ->
   `browser_ref_stale` with detail `{delivery: unknown, retryable: false}`. The connected path and its receipt
   are unchanged (A3). Unit: `set_input_files_detached_after_the_check_is_never_a_success` (mock detaches the
   node right after the first isConnected probe) red on F'S, green on F5. Only `isConnected` is re-checked, not
   `files.length`: a page that clears the input in its own change handler would otherwise turn a landed
   assignment into a false unknown.
2. **`37d17e0b3` Part B test only** (`platform-linux/src/recording_hooks.rs`):
   `publish_capture_for_session(A)`, then the recorder's Linux element lookup as B -> `None`, as A -> the window.
3. **`2237cf9c6` side-index readers use the token's window** (`platform-linux/src/atspi/mod.rs`,
   `tools/impl_.rs`). `type_into_editable_at` and `focus_element` take the target window and look the cached
   element up in that window's snapshot (as `set_value_in`, `perform_action_in` and
   `get_element_bounds_for_window` already did). All 13 Linux call sites pass the window they act on.

No routing fix: SOURCE and the counted WR rows show the routing reader cannot be reached through the registry.
The session-aware routing draft (`ea12e6f86`, not on this branch) stays a follow-up for the day a schema
admits `snapshot_id`.

## SOURCE audit (`source-audit.json`, F' line numbers)

- **Part A path:** `tools.rs:2409` invoke -> 2423 paths -> 2433 per-tab mutation lock (serializes Driver
  calls, not page JS) -> 2441 revalidate -> 2450 resolve_ref -> 2474 `DOM.describeNode` -> 2516
  `DOM.resolveNode` -> 2527-2535 `Runtime.callFunctionOn isConnected` -> 2538 refusal -> **2541-2548
  `DOM.setFileInputFiles` (a separate CDP command = separate renderer task)** -> 2550-2554 success receipt with
  no post-condition. No CDP command checks connectedness and assigns files in one task; pausing the page
  (freeze, script disable, debugger) would change page-visible behaviour. Hence IRREDUCIBLE for the effect, and
  the honest-unknown receipt is the reachable fix.
- **Routing:** `snapshot_store.rs:346-354` (pid-only) <- `impl_.rs:134-142` <- `window_target.rs:186-197`. Every
  one of the 13 guarded tools (`impl_.rs:14026-14109`) has a closed schema without `snapshot_id`, and
  `tool.rs:200-210, 1278, 1442-1447` refuses unknown arguments at the canonical boundary used by the SDK and
  every transport, before the guard runs.
- **Side index:** `atspi/snapshot.rs:141-150` returns the first entry for the pid when no window is given.
  Window-less token readers: `focus_element` (`atspi/mod.rs:326`; callers `impl_.rs:3094, 3115, 4566, 7118,
  7522, 7591, 7688, 8329, 8381, 8770`) and `type_into_editable_at` (`mod.rs:468`; callers `7347, 7434, 7552`).
  Window-scoped already: `set_value_in`, `read_value_in`, `get_element_bounds_for_window`, `hit_test`,
  the recording lookup. No side-index reader is keyed by `snapshot_id`.
- **Recording lookup:** `recording.rs:921-936` re-inserts the caller session; `recording_hooks.rs:95-118` ->
  `snapshot_store.rs:395-402` (F1 filter).
- **W2c/W2d:** `capture_registry.rs:842-847` (U') binds generation + session + target before FIX-02 (no capture
  file changes in F'); W2d's closed-window refusal is AT-SPI object liveness (`impl_.rs:5987-5993, 6499-6506`).

## Method

- **Forced path (A1).** The Driver runs with `CUA_DRIVER_EXP_SET_FILES_GAP_MS=50` (seam commit `5a1e209ab`:
  default off, measurement only, one stderr marker). The harness reads the Driver's stderr; on the marker it
  releases the page's re-render, which replaces the input (generation 0 -> 1) inside the gap. Race validity per
  cell: marker inside the first call, re-render acknowledged, and on the page clock the re-render precedes every
  generation-0 file event: 20/20 on both arms.
- **Oracles (target-owned).** Browser: the fixture server's journal of page beacons (input/change on each node
  generation, the generation-0 node's `files` poll, the re-render). Native: the GTK3 fixture's own state file
  (per-window `agreed`, and per-window live `note_text` via an opt-in fixture flag) read before and after every
  call, plus an X RECORD stream (MapWindow, ConfigureWindow, SendEvent `_NET_ACTIVE_WINDOW`, SetInputFocus from
  every client; FocusIn, ConfigureNotify as delivered), attributed to calls by wall clock and to w1 by its
  client, frame and child window ids.
- **Routes.** Browser: the receipt's status / refusal code / detail. Native: `structuredContent` (refusal
  codes; `effect`; `route`).
- **Topology (native).** T2: one `cua-driver serve` daemon, two `mcp --socket` clients = sessions A and B.
  WS/WK use a fresh daemon and fixture per attempt (the side index's per-process order is part of the
  condition); W2dX a fresh fixture per attempt.
- **Controls.** FS positive control (A1); A2 rebind; A3 default path on F5 and F'; WR s4/s6 own-token
  positives and s5 X RECORD oracle control; WS/WK own-window effects; W2dX/W2cX tails; U' arms.
- **Isolation and locks.** Every code-executing command ran under `bin/hostless`; browser rows in a private
  Xvfb session; native rows in `cua-x11-session.sh` with `CUA_SESSION_ATSPI=1` and
  `CUA_SESSION_EXTRA_ENV` containing `CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false`. 33 counted
  blocks, each one SHARED quiet-lane acquisition (`harness/qlock_fix03.sh`): holds 26-109 s (cap 300 s), every
  rc 0, receipts in `raw/lock-ledger.jsonl` and the loop-wide ledger; yields to queued exclusive waiters up to
  120 s. Builds and units took only the cargo lock.
- **Order.** Arms interleaved per plan (`plans/`); every attempt kept; no block needed a re-run.

## Results (N of M, evidence class per row)

**Part A (jev-use fixture page in Chrome; fresh Driver + Chrome + fixture per cell)**

| Row | Arm | N of M | Result | Class |
|---|---|---|---|---|
| A1 forced race (gap 50 ms) | F'S | **20/20** success receipts for a detached node (race forced 20/20) | the hole reproduced; 20/20 cells with a gen0 change event | REAL |
| A1 | F5 | 0/20 success; **20/20 refused** `browser_ref_stale` + delivery unknown + retryable false (post-assignment check; 0 pre-check refusals) | **20/20 cells with a gen0 change event on the server** (irreducible) | REAL |
| A2 rebind | F5 / F'S | **20/20** / 20/20 | fresh ref set, gen1 change with the file journaled | REAL |
| A3 default path | F5 / F' | **20/20** / **20/20** | 0 seam markers, 0 re-renders; one receipt shape across all 40: keys `file_count, frame, ref, status, tab_id, target_id`, `{status: ok, frame: main, file_count: 1}` | REAL |

**Part C (two-window GTK3, T2)**

| Row | Arm | N of M | Result | Class |
|---|---|---|---|---|
| WR s1: B click `{snapshot_id: sA, element_token: tB2}` | U' / F' / F5 | 20/20 / 20/20 / 30/30 refused | `invalid_arguments` (unknown argument snapshot_id); 0 mutations; 0 w1 activation (X RECORD live 20/20/20) | REAL+FIXTURE |
| WR s2: B bring_to_front `{snapshot_id: sA}` | U' / F' / F5 | 20/20 / 20/20 / 30/30 refused | same | REAL+FIXTURE |
| WR s3: B click `<sA>:<idx>` | U' | **20/20 landed on w1** | cross-session mutation (as W2a) | REAL+FIXTURE |
| | F' / F5 | **20/20** / **30/30** refused | `stale_element_token` at the F1 filter, 0 mutations | REAL+FIXTURE |
| WR s4 / s6 own tokens | U' / F' / F5 | 20/20 / 20/20 / 30/30 each | verified | REAL+FIXTURE |
| WR s5 oracle control | U' / F' / F5 | 20/20 / 20/20 / 20/20 of live-oracle attempts | w1 activation seen by X RECORD (F5: 10 attempts in block wr4 had no live oracle, Deviation 3) | REAL+FIXTURE |
| WS text, own Note token | U' | B into A's w1 **8/20**, A into B's w2 **12/20** | 20/20 attempts with a cross-session write | REAL+FIXTURE |
| | F' | B into w1 **12/20**, A into w2 **8/20** | 20/20 attempts with a cross-session write; receipts `unverifiable` on the misrouted writes, never `confirmed` | REAL+FIXTURE |
| | F5 | **0/20, 0/20**; own window 20/20 and 20/20 | `confirmed` 20/20 | REAL+FIXTURE |
| WK press_key space (foreground), own checkbox token | F' | B toggled w1 **10/20**, A toggled w2 **10/20** | 20/20 attempts with a cross-session toggle | REAL+FIXTURE |
| | F5 | **0/20, 0/20**; own window 20/20 and 20/20 | | REAL+FIXTURE |

**Part D**

| Row | U' | F5 | Gating | Class |
|---|---|---|---|---|
| W2dX: w1 closed, B dispatches A's w2 token | **landed 20/20** (w1 close confirmed 20/20) | **refused 20/20** `stale_element_token`, tail 20/20 | discriminating KEEP | REAL+FIXTURE |
| W2cX: B presents A's w2 capture in w2 | refused 20/20 `capture_generation_mismatch`, tail 20/20 | refused 20/20, tail 20/20 | non-gating (non-discriminating) | REAL+FIXTURE |

## E4 counters (per arm, `summary.json`)

| Counter | U' | F' | F'S | F5 | Class |
|---|---|---|---|---|---|
| Cross-session mutations | **60** (WR s3 20, WS 20, W2dX 20) | **40** (WS 20, WK 20) | n/a | **0** | REAL+FIXTURE |
| Cross-session routing side effects (X RECORD) | 0 | 0 | n/a | 0 | REAL+FIXTURE |
| Stale dispatch (assignment on a detached node) | n/a | n/a | 20 | **20 (seam-forced residue, irreducible)** | REAL |
| Unverified success | 0 | 0 | **20** (success for a detached node) | **0** | REAL |
| Duplicates | 0 | 0 | 0 | 0 | REAL |
| Blind replay | 0 (harness never re-dispatches; no Driver retry seen) | 0 | 0 | 0 | REAL |
| Refusal-as-success | 0 | 0 | 0 | 0 | REAL |

F5 E4 excluding the seam-forced A1 residue: **0**; strict: **20**.

## Unit evidence (`raw/unit/final/`; pre-registration drafts in `raw/unit/pre-prereg/`)

| Tree | Result | Class |
|---|---|---|
| red: F'S + `v2_tests.rs` from F5 | `set_input_files_detached_after_the_check_is_never_a_success` **FAILED** (receipt `status: ok`); the 2 existing F4 tests pass | UNIT |
| red: U' + `recording_hooks.rs` from F5 | `recording_element_lookup_resolves_a_capture_publication_only_for_its_session` **FAILED** (B resolved `Some((7, None))`) | UNIT |
| green: F5 cua-driver-core `--lib --tests` | **862 passed, 0 failed** (RECERT F' 861 + the new test) | UNIT |
| green: F5 platform-linux `--lib` | **603 passed, 0 failed** (F' 602 + the new test) | UNIT |
| green: F5 jev-use | Python 241 OK (1 skipped), TS 116/116, typecheck rc 0, 4 CLI verifiers rc 0; the two `guarded-focused` steps do not apply on this base (as in SETUP and RECERT-FIX) | UNIT |
| side-index fix | no unit seam without AT-SPI: red/green is REAL (WS/WK F' vs F5) | REAL |

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Class |
|---|---|---|---|
| F4 post-check (F5) | false success receipts for a detached input: 20 -> 0 (the assignment itself is not deleted) | none claimed | REAL |
| Side-index window (F5) | cross-session writes/toggles: F' 40 -> 0 | none claimed | REAL+FIXTURE |

Timing is descriptive only (correctness rows): median cell wall time A1 F'S 1684 ms, A1 F5 1659 ms, A3 F'
552 ms, A3 F5 537 ms (`summary.json`). No timing claim.

## Deviations

1. **Near miss (13:18:55Z).** While drafting an edit, one plain-shell command ran `python3 -` with an empty
   heredoc (an empty program, no import, no display, bus or network) outside hostless. It could not reach the
   desktop; reported as a near miss (`raw/incidents.txt`). Every other code-executing command ran under
   `bin/hostless`.
2. **Lock spacing at plan boundaries.** The chain runner starts a new campaign per plan, and the campaign's
   30 s spacing is per invocation, so the first block of plan 2 (`fix03-N-U-WR-wr1`) and of plan 3
   (`fix03-N-U-W2dX-dx1`) acquired the shared lock 1 s and 0 s after the previous FIX-03 release. The
   acquisitions still yielded to queued exclusive waiters (`yield_s` in the receipts). Listed in
   `provenance.json` and checked by `verify_artifacts.py`.
3. **Dead X RECORD oracle in block F5-wr4; supplementary block.** The recorder's `RECORD EnableContext`
   failed (XError) right after it printed `ready` (a race: the context was created on one connection and
   enabled on another after only a flush). The block's 10 attempts kept every state-oracle result; their
   X RECORD clauses are reported as `oracle_unavailable`. After the counted plans, the recorder was changed to
   `sync()` before enabling and the harness to fail a block whose recorder dies, and one supplementary F5 WR
   block (`plans/4-supplement-WR-F5.txt`, wr7, attempts 20-29) ran. WR-F5 therefore has 30 attempts (all
   state-oracle rows 30/30) and 20 live-oracle attempts; `analyze.py` evaluates the X RECORD clauses over
   live-oracle attempts only, for every arm (U' and F' had 20/20 live). This analyzer rule was added after the
   counted runs.
4. **analyze.py edits after PREREG:** the WS/WK B-step selector (it first matched B's observation step), the
   symmetric unverified-success count, the dispositions output, gzip reading, and Deviation 3's live-oracle
   rule. The gates and rows are unchanged.
5. **Spec row wording.** "Session B submits A's snapshot_id together with B's own valid token ... refused at the
   F1 token filter": the guard ignores `snapshot_id` when a token is present, and the registry refuses
   `snapshot_id` before the guard, so s1 is refused at the schema boundary, not at F1. The F1-filter variant
   (A's snapshot id inside the token) is s3. Both were pre-registered.
6. **Rows added beyond the spec (pre-registered):** WS and WK (the side-index readers), found by shakedown on
   F' before PREREG; W2cX/W2dX as the Part D variants.
7. **Fixture copy changed:** `harness/gtk3_main_two_windows.py` adds an opt-in `CUA_GTK3_NOTE_TEXT_STATE=1`
   per-window `note_text` (two-window mode only); `harness/gtk3_main_two_windows.fix03.diff` is the exact diff
   against RECERT-FIX blob `0c5821e8b` (BLOBS.txt lists the source blob).
8. **Own build stopped while waiting.** A superseded F5 draft build (`fix03-f5pre2-d12f0669b`) was stopped by
   exact PID while still waiting for the cargo lock (all three PIDs started by this lane; no pkill/pgrep).
9. **Shared-lock and cargo-lock contention.** Other tracks held both locks for long stretches; blocks waited
   (up to the 120 s exclusive-waiter yield, then the flock). No hold exceeded 109 s.
10. **The Driver printed an update notice** ("cua-driver v0.33.0 is available") in a daemon stderr: the
    release check runs with telemetry off. It is not a provider request and does not affect any row.

Shakedowns before PREREG (`raw/shakedown/`, not counted): A1 F'S 1, A1 F5-draft 1, A3 F5-draft 1, WR F'/F5-draft
(first design: `snapshot_id` refused at the schema), WS F' 2 (B's own-token text landed in w1 2/2), WK F' 2,
W2cX U' 1, W2dX U' 2, WS U' 2, WR F'/U' (final design), WS/WK/WR on the F5 draft binary.

## Limits and claim boundary

- Linux X11 (private Xvfb, openbox) only; macOS and Windows rows BLOCKED (hardware). I3s stays OWNER_DECISION.
- F4: the Driver cannot prevent Chromium from assigning files to (and firing input/change on) a node that a
  page detaches between the check and the assignment; F5 makes the receipt honest. The action-record legacy
  mapping (`action_record.rs:663-677`) records every `status: refused` receipt as `effect: refused`, including
  this delivery-unknown one (pre-existing, shared with the trusted-click cleanup case `tools.rs:1316-1324`);
  both jev-use runners honour `retryable: false`.
- The F5 side-index fix covers the cached lookup. The native fallbacks (`native.rs:2837-2849`, `4861-4873`)
  still index the whole application walk by pid when the cached object is missing or fails (not exercised:
  the cache hit is the normal path).
- The routing reader stays pid-only in code; it is unreachable while no guarded tool's schema admits
  `snapshot_id`.
- Fork candidates on `0f1955d2f`; not merged anywhere; no new service; the seam is measurement-only and off by
  default. No timing, latency or wall-clock claim.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed `5827f04d0` before the first counted block |
| `README.md` | this file |
| `plans/` | the counted blocks in run order (`4-supplement-WR-F5.txt`: Deviation 3) |
| `analyze.py` -> `summary.json`, `dispositions.json` | every row, gate and E4 counter from `raw/` |
| `verify_artifacts.py` | independent recomputation (no import of analyze.py), binaries, locks, PREREG order, sessions, units, privacy; run `python3 verify_artifacts.py --git <repo>` |
| `provenance.json` | SHAs, trees, binaries, heads, lock exceptions, unit expectations |
| `source-audit.json` | the SOURCE audit with file:line |
| `harness/` | browser (`browser/`), native (`native/`), campaign + lock wrapper, fixture copy + diff; reused RECERT-FIX files with `BLOBS.txt` |
| `raw/browser/<block>-<phase>-<arm>/` | `validity.json`, `cells.jsonl`, `cells/*.jsonl` (receipts, steps, target journal), `end.json` |
| `raw/native/<arm>/<row>/b<block>.jsonl.gz` | every call with pre/post fixture state, the window/frame map, the block's X RECORD stream |
| `raw/session-*.log` | per-block session output (sanitized at capture) |
| `raw/lock-ledger.jsonl` | the 33 counted receipts |
| `raw/unit/`, `raw/builds/`, `raw/heads/`, `raw/shakedown/`, `raw/incidents.txt`, `raw/campaign-chain*.out` | unit logs and scripts, build logs, live heads and drift, shakedowns, incidents, campaign output |
