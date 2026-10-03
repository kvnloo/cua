# FIX-04: delivery-unknown refusals are `unverifiable`, the runner reconciles instead of re-dispatching, and native index fallbacks stay in the token's window (2026-10-03)

Owners: kvnloo/cua#105, kvnloo/cua#36 (kvnloo/cua#73 invariants, E4 residue). Wave 7 of the CUA RFC loop.
Fork fix candidates on FIX-03's packet head `e300edbd3` (upstream `0f1955d2f`): nothing here is merged
anywhere, and nothing was pushed or posted by this lane.

## Result in one paragraph

- **Part A (effect mapping): KEEP, reviewed product-fix candidate F6a `937ef7cfa`.** Three producers emit a
  refusal *after* the input was acknowledged or assigned, with `refusal.detail = {delivery: unknown,
  retryable: false}`: browser_click and browser_pointer (trusted input acknowledged, focus-emulation cleanup
  failed) and FIX-03 F5's browser_set_input_files post-assignment check. The legacy action-record mapping
  (`action_record.rs:663-677`) recorded the first two as `effect: refused` (= nothing delivered).
  browser_set_input_files never reaches that mapping (it is not an ActionResult tool): its receipt is the
  raw envelope `{status: refused, refusal}` with no effect at all. F6a maps a refusal that declares a
  delivery other than `not_delivered` to the existing unknown variant `ActionEffect::Unverifiable` (delivery
  `unknown`) and adds `effect: "unverifiable"` to the same envelopes. Pre-dispatch refusals stay `refused`;
  `browser_input_incomplete` with delivered characters stays `partial`. UNIT red 3/3 on F5, green.
- **Part B (runner, kvnloo/cua#105): KEEP with fix F6b `bb1e01f7b`.** SOURCE + UNIT rule out a blind
  re-dispatch of the F5 post-assignment refusal on the base tree (`retryable: false` already wins). Two gaps
  were red on the base tree in both runners: the possibly-landed completion was not reconciled (the run
  ended `unknown` without reading state), and a refusal declaring `delivery: unknown` without a
  `retryable` flag WAS re-dispatched (its code is in the pre-dispatch allowlist). F6b puts the refusal's own
  declarations before the allowlist and reconciles a possibly-landed completion with the same bounded
  oracle re-read an accepted completion uses. Python 4 red -> 16/16, TS 4 red -> 16/16.
- **Part C (native pid-wide fallbacks, kvnloo/cua#36): KEEP with fix F6c `802700282`; a new E4 finding on
  F5, closed on F6.** On F5, session A's OWN still-valid element token for its closed window w1 typed into
  session B's window w2 of the same process **20/20** (receipt `effect: unverifiable`, "Typed 6
  character(s) (via targeted AT-SPI)"); U' 20/20. F6 refused it **20/20** `stale_element_token`, **0/20**
  cross-window effects; B's own tail verified 20/20 on every arm. The focus row CF is non-discriminating on
  this X11 session: both F5 and F6 refuse `foreground_unavailable` before the GrabFocus rung (0/20, 0/20).
- **Part D (FIX-03's F5 TOCTOU row on F6): KEEP.** Seam-forced race 20/20; **0/20 success receipts and
  20/20 receipts `status: refused`, `effect: unverifiable`, `delivery: unknown`, `retryable: false`**; the
  runner's own classification never allows a re-dispatch (0/20). The generation-0 change still reached the
  fixture server in **20/20** cells (measured, not prevented: the IRREDUCIBLE CDP atomicity limit). A2 rebind
  20/20; A3 default path 10/10 verified, receipt unchanged (no effect key). W2dX control: U' landed 20/20, F6 refused 20/20 `stale_element_token` (tail 20/20): discriminating.
- **Part E:** FIX-03's verifier matched private names as substrings, so a short private name inside the
  public fork owner token was a hit. One commit `e0fbc8129` (word-boundary match, as B-08's verifier does):
  from a clean shared clone, before (`e300edbd3`) **216/217** (the privacy false positive), after
  **217/217**. The spec expected 215 checks; FIX-03's verifier has 217.
- **E4 (F6):** 0 cross-window effects, 0 blind replays, 0 unverified success, 0 refusal-as-success; the
  seam-forced assignment to a detached node remains (20/20, irreducible) and is now receipted unknown.
- **Provider:** TypeSafe not used: 0 attempts, 0 reached (lane cap 0).

## Dispositions (pre-registered gates; `dispositions.json` from `analyze.py`)

| Item | Disposition | Gating evidence | Evidence class |
|---|---|---|---|
| A effect mapping (F6a) | **KEEP** (reviewed product-fix candidate) | red 3/3 on F5 tree, green; core 865/0, linux 606/0 | UNIT, SOURCE |
| B runner re-dispatch (F6b) | **KEEP (fix F6b)** | base: no blind re-dispatch of the spec row (green), reconcile red, delivery-only red; F6 green Py 16/16, TS 16/16, suites Py 245 OK, TS 121/121 | UNIT, SOURCE |
| C CT type fallback (F6c) | **KEEP** | F6 0/20 cross-window (refused 20/20); F5 20/20, U' 20/20 cross-window | REAL+FIXTURE, UNIT, SOURCE |
| C CF focus fallback | **KEEP (non-discriminating)** | F6 0/20, F5 0/20: `foreground_unavailable` before the GrabFocus rung | REAL+FIXTURE, SOURCE |
| D TOCTOU on F6 | **KEEP** | 0/20 success, 20/20 unknown receipts; gen0 change at the server 20/20 (irreducible) | REAL |
| D W2dX control | **discriminating** | U' landed 20/20; F6 refused 20/20 `stale_element_token`, tail 20/20 | REAL+FIXTURE |
| E FIX-03 verifier | **fixed** | 216/217 -> 217/217 from a clean shared clone | SOURCE (verifier run) |

## The five mechanism requirements

| Requirement | Part A / D | Part B | Part C |
|---|---|---|---|
| Forced path | `CUA_DRIVER_EXP_SET_FILES_GAP_MS=50` (FIX-03 seam `5a1e209ab`, default off) + page re-render released on the seam marker: the input is detached between the check and the assignment (race forced 20/20) | unit runner with a mock Driver whose refused click still lands (or not) | the token's window w1 closed by the fixture (SIGUSR1, confirmed), A uses its OWN valid w1 token: the cached AT-SPI object is gone, so the index is re-resolved |
| Actual route / producer | `browser_set_input_files` post-assignment check (`tools.rs`, F5 `b235fabef`) -> `BrowserRefusal::to_tool_result` envelope; raw `structuredContent` recorded per call | `run.py` / `run.ts` `may_redispatch_after` + refusal branch | `atspi::type_into_editable_at` -> `native::type_into_editable_at` (pid-wide walk on F5; frame-scoped on F6); press_key foreground -> `with_x11_foreground_opts` (refused before `focus_element`) |
| Independent target-owned oracle | the fixture server's journal: page beacons per node generation (gen0 `change` reached the server) | the fixture's HTTP submit journal (`read_oracle`) | the GTK3 fixture's own state file per window (`note_text`, `agreed`, `focus`, `active`) read before and after every call |
| Negative / fallback controls | A2 rebind on the fresh node 20/20; A3 default path 10/10 (no seam, receipt unchanged); pre-dispatch refusals keep `refused` (UNIT) | pre-dispatch `not_delivered` refusal still rebound once; ordinary path unchanged | B's own-token tail in w2 verified 20/20 on every arm (the oracle sees a w2 write); U' and F5 arms discriminate; CF as the reachability control |
| Tested source SHA / binary | F6 `802700282`, sha256 `cb89fe03f6a7…` (seam present, default off) | `bb1e01f7b` (runner files unchanged by F6c) | F6 `802700282`; F5 `2237cf9c6`; U' `513e45fee` |

## Provenance (each SHA kept separate)

| Item | Value | Class |
|---|---|---|
| Upstream base | `0f1955d2f1ee2b01b40775aa53ea2af0b5544218` | SOURCE |
| Lane base (FIX-03 packet head) | `e300edbd318f33b907741ca7aaec2ee666a2dac0` (rust tree `4a6f155eb73a`) | SOURCE |
| F6a | `937ef7cfa969d226dff9ffa97956295c9a1bd897` (action_record.rs, browser/refusal.rs, browser/v2_tests.rs) | SOURCE |
| F6b | `bb1e01f7be6ee37619b08d53453779787f5caf92` (jev-use run.py, run.ts, both refusal test files) | SOURCE |
| F6c = F6 source | `802700282e7302078c3f02c4b35970fd0518cdbb` (atspi/mod.rs, atspi/native.rs, tools/impl_.rs); rust tree `05a52a13b7f9`, libs/cua-driver tree `f879e73c971e` | SOURCE |
| F6 binary | `cua-driver-fix04-f6-802700282`, sha256 `cb89fe03f6a737ce67dd2ef3aecede3ffa3b5e8da13bfcb94f2d14330814df0c`, `cua-driver 0.32.0`; built from the worktree at `e0fbc8129` (= F6 + the Part E verifier commit; identical libs/cua-driver tree); 0 Fresh workspace units | SOURCE |
| F5 (U-control) | `2237cf9c6`, binary `cua-driver-fix03-f5-2237cf9c6`, sha256 `10d710753ba85454632005cb9a40946abaf40d0ff0571885e08f85e9d7de1dd4` (re-hashed at lane start = FIX-03 provenance) | SOURCE |
| U' | `513e45fee`, binary `cua-driver-fix02r3-u-513e45fee`, sha256 `3d27b55b76bdfa64d8659100f995db23400c3b46c06543832aa3c8acb0b31acd` (re-hashed) | SOURCE |
| Part E | `e0fbc8129d91d667368e17f17fa3da52e5f040b0` (FIX-03 verify_artifacts.py only) | SOURCE |
| PREREG + harness | `d73eec78fed3ec726f7d95dccecbf0965246fb8a`, committed 2026-10-03T16:36:31Z; first counted lock acquisition 16:38:42Z | SOURCE |
| Versions | every counted native block header and browser `validity.json`: `cua-driver 0.32.0` | SOURCE |
| Live heads at start (16:36:57Z) | trycua/cua main `4635c0668`; trycua/cua PR 4316 `a0bca7440` (OPEN); kvnloo/cua#105 `98a45e6c5` (OPEN, unchanged) | SOURCE |
| Live heads at end (17:30:53Z) | trycua/cua main `3a784c5c3` (moved); PR 4316 `a0bca7440` (OPEN, unchanged); kvnloo/cua#105 `98a45e6c5` (OPEN, unchanged); the files FIX-04 changes have no upstream commit after `0f1955d2f` at either head (`raw/heads/drift-end.txt`) | SOURCE |
| Upstream drift on the files FIX-04 changes | 0: the last upstream commits touching action_record.rs, refusal.rs, atspi/mod.rs, atspi/native.rs, tools/impl_.rs, run.py, run.ts are ancestors of `0f1955d2f` (`raw/heads/drift-start.txt`) | SOURCE |
| Publication SHA | set by Publish, never equal-by-assumption to the tested SHAs | SOURCE |
| Environment | Linux 7.2.2 x86_64, rustc 1.97.1; `bin/hostless` v2; `cua-x11-session.sh` (private rootless Xvfb, openbox, picom, private D-Bus; AT-SPI for native rows); jev-use venv Python 3.12.13, Node v22.23.2; GTK3 fixture on system Python + gi; Chrome launched by the Driver (`browser_prepare isolated_new`); telemetry off; 1-min loadavg at lock acquisition 1.58 to 11.13 | SOURCE |
| Provider | 0 attempts, 0 reached | SOURCE |

## The fixes

1. **F6a `937ef7cfa`** (`cua-driver-core`). `refusal_delivery_may_have_landed(structured)`: a
   `refusal.detail.delivery` present and not `not_delivered`. `legacy_effect` maps such a refused payload to
   `ActionEffect::Unverifiable` and `actual_delivery_from_legacy` to `Unknown`, so the public ActionResult of
   browser_click / browser_pointer says `effect: unverifiable, delivery: {mode: unknown}` (no error code; the
   code stays in the summary's `refused (<code>)` prefix). `BrowserRefusal::to_tool_result` adds
   `effect: "unverifiable"` to the same envelopes (the receipt of browser_set_input_files). Default behaviour
   changes only for delivery-unknown refusals.
2. **F6b `bb1e01f7b`** (jev-use `run.py`, `run.ts`). `may_redispatch_after`: `retryable: false` or a declared
   delivery other than `not_delivered` -> never re-dispatch, before the code allowlist. A refusal that may
   have landed on the completion candidate is reconciled by `reconcile_from_oracle` (20 x 100 ms re-read of
   the target-owned oracle; `verified`/`refuted`, else `unknown`), never dispatched again. A pre-dispatch
   refusal is still rebound once on a fresh observation (FIX-02 F3).
3. **F6c `802700282`** (`platform-linux`). `atspi::type_into_editable_at` / `focus_element`: with the window
   known, a re-resolution keeps to the top-level frame of the token's cached element (its proven identity);
   a window-scoped index without its snapshot entry is stale (`CachedElementGone`). `native::indexed_node`
   refuses a node outside that frame. `type_text` refuses a `CachedElementGone` as `stale_element_token`
   (the click path's shape) instead of falling through to the blind pid-wide editable searches
   (`type_into_editable(pid)`, `insert_text(pid)`), which would otherwise still write into w2.

No new service, no new effect variant, no new state: the fixes live inside the existing receipt mapping,
runner rule and AT-SPI lookup.

## SOURCE audit (`source-audit.json`, line numbers on `e300edbd3`)

- **A, field path.** `refusal.detail.delivery` / `refusal.detail.retryable`, serialized by
  `browser/refusal.rs:232-238`. Producers: `browser/tools.rs:2573` (set_input_files, F5), `tools.rs:1323`
  (browser_click), `browser/pointer.rs:665` (browser_pointer). `browser_type`'s `browser_input_incomplete`
  carries `delivered_chars` and `retryable: false`, no delivery field (`tools.rs:2097-2116`).
- **A, paths to `legacy_effect`.** `tool.rs:1809-1825` -> `ActionExecutionRecord::from_legacy`
  (`action_record.rs:464`) -> `legacy_effect` (`478 -> 663-677`), only for ActionResult tools
  (`action_record.rs:469`; `cua-driver-contract/src/lib.rs:105-126`: browser_click, browser_pointer,
  browser_type; NOT browser_set_input_files). Then `publish_action_result` (`tool.rs:1862, 3002`), history
  (`history.rs:922-950`), recording `action_truth`. For browser_set_input_files the structured equivalent is
  the envelope's `status: refused` (read by the jev-use runners, the server observer `server.rs:735-741`, and
  the FIX-03 harness). FIX-03's limits text attributed set_input_files to the legacy mapping; this lane
  corrects that and fixes both surfaces.
- **B.** Python `run.py:89-111` (allowlist, `may_redispatch_after`), `151-164` (parse: retryable only),
  `609-634` (refusal branch: unknown without reading state), `669-684` (accepted completion reconcile).
  TypeScript `run.ts:114-138, 185-200, 626-650, 681-694`.
- **C.** `atspi/mod.rs:327-337` and `473-483` fall back to `native::focus_element(pid, idx)` (`native.rs:4861`)
  and `native::type_into_editable_at(pid, idx, ..)` (`native.rs:2837`), which walk every top-level of the
  application (`collect_visited(conn, pid)`). The runtime snapshot store and the (pid, xid) side index are
  published together and a window's re-observation retires every session's older snapshot
  (`impl_.rs:1474-1487`, `snapshot_store.rs:174-210`), so a missing or evicted window snapshot makes the token
  stale first; the reachable condition is a still-valid token whose cached object is gone (window closed,
  widget rebuilt). Callers after F5: `type_into_editable_at` at `impl_.rs:7357` (Hyprland), `7444` (Wayland
  inject), **`7562` (X11 element type_text: reachable here)**; `focus_element` at `3094/3139`, `3115`,
  `4571`, `7127`, `7532`, `7601`, `7698`, `8339`, `8391`, `8780` (Wayland/Hyprland, or X11 inside
  `with_x11_foreground*`, or the background route when a focus-free keyboard exists). Element tokens resolve
  at `impl_.rs:7227` with no window-liveness check. In the same-process fixture both windows' Note fields
  carry element index 6 and both checkboxes index 2, so after w1 closes the pid-wide nth node is w2's
  control. Residue not changed (out of scope, listed): `native::perform_action(pid, idx)`,
  `scroll_element(pid, idx)`, `set_value(pid, idx)` as the `set_value_in` fallback, and the Hyprland /
  Wayland-inject type_text paths' fall-through.

## Method

- **Isolation and locks.** Every code-executing command under `bin/hostless`; REAL rows in private
  `cua-x11-session.sh` sessions (native rows with `CUA_SESSION_ATSPI=1` and `CUA_SESSION_EXTRA_ENV`
  containing `CUA_SESSION_ATSPI=1`). 17 counted blocks, each one SHARED quiet-lane acquisition
  (`harness/qlock_fix04.sh`, 300 s cap): holds 27-60 s, every rc 0, >= 30 s spacing, receipts in
  `raw/lock-ledger.jsonl` and the loop-wide ledger. Builds and unit steps ran under the cargo lock AND a
  shared quiet-lane hold (`harness/unit/sharedq.sh`), units cut at 1200 s (`harness/unit/run_unit.sh`).
- **Topology (native).** T2: one `cua-driver serve` daemon per block, two `mcp --socket` clients = sessions
  A and B; a fresh fixture per attempt (w1 is closed in every attempt); observation order alternates AB/BA.
- **Browser.** FIX-03's method unchanged (fresh Driver + Chrome + fixture server per cell). The harness copy
  calls `browser_set_input_files` once through the MCP session, records the raw `structuredContent`, then
  feeds that same result object to the jev-use runner's `Driver.call` (no second dispatch) to record the
  runner's classification and `may_redispatch_after`.
- **Order.** Plans `plans/1..4` in order, arms interleaved inside each plan; every attempt kept; no block
  needed a re-run.

## Results (N of M, evidence class per row)

**Part C (two-window GTK3, T2; A's own valid token for its closed window w1)**

| Row | Arm | Cross-window effects (w2 changed during A's call) | A's receipt | B's tail in w2 | Class |
|---|---|---|---|---|---|
| CT type_text (background) | F5 | **20/20** (w2 Note = `fix04A`) | accepted, `effect: unverifiable` "via targeted AT-SPI" 20/20 | 20/20 | REAL+FIXTURE |
| | U' | **20/20** | accepted 20/20 | 20/20 | REAL+FIXTURE |
| | **F6** | **0/20** | refused `stale_element_token` 20/20 | 20/20 | REAL+FIXTURE |
| CF press_key space (foreground) | F5 | 0/20 | refused `foreground_unavailable` 20/20 | 20/20 | REAL+FIXTURE |
| | F6 | 0/20 | refused `foreground_unavailable` 20/20 | 20/20 | REAL+FIXTURE |

w1 close confirmed on the fixture's state file in every attempt (100/100).

**Part D**

| Row | Arm | N of M | Result | Class |
|---|---|---|---|---|
| A1 seam-forced race (gap 50 ms) | F6 | race forced **20/20** | **0/20 success; 20/20** raw `{status: refused, effect: unverifiable, refusal.code: browser_ref_stale, detail: {delivery: unknown, retryable: false}}`; runner: refused 20/20, `may_redispatch_after` false 20/20 | REAL |
| A1 server-side | F6 | **20/20** cells with exactly one generation-0 `change` at the fixture server | measured, not prevented (IRREDUCIBLE) | REAL |
| A2 rebind (inside A1 cells) | F6 | **20/20** | fresh ref, gen1 change with the file journaled; receipt `status: ok` | REAL |
| A3 default path | F6 | **10/10** verified | receipt keys `file_count, frame, ref, status, tab_id, target_id`, no `effect` key (unchanged) | REAL |
| W2dX (w1 closed, B dispatches A's w2 token) | U' | **landed 20/20** (w1 close confirmed 20/20) | cross-session mutation; A's own tail 20/20 | REAL+FIXTURE |
| | F6 | **refused 20/20** `stale_element_token` | 0 mutations; A's own tail 20/20 | REAL+FIXTURE |

## E4 counters (`summary.json`)

| Counter | F5 | U' | F6 | Class |
|---|---|---|---|---|
| Cross-session mutations (CT) | **20** | **20** | **0** | REAL+FIXTURE |
| Cross-session mutations (W2dX) | n/a | **20** | **0** | REAL+FIXTURE |
| Blind replays (runner may re-dispatch + > 1 gen0 dispatch + > 1 gen0 change) | n/a | n/a | **0** | REAL |
| Unverified success (D: success receipt for a detached node) | n/a | n/a | **0** | REAL |
| Possibly-landed effect receipted `refused` (D) | (FIX-03: 20/20 `status: refused`, no effect) | n/a | **0** (20/20 `effect: unverifiable`) | REAL |
| Stale dispatch to a detached node (seam-forced residue) | n/a | n/a | 20 (irreducible; now receipted unknown) | REAL |

## Unit evidence (`raw/unit/`)

| Tree | Result | Class |
|---|---|---|
| red A: `e300edbd3` + test-only diff (`raw/unit/red/red-tree.diff`) | the 3 new core tests **FAILED** (`Refused` vs `Unverifiable`; no `effect` key) | UNIT |
| red B: same tree | Python **4 FAIL** / TS **4 not ok**: reconcile (`unknown` without reading state) and delivery-only re-dispatch; the spec row's no-re-dispatch clause passed | UNIT |
| red C: `e300edbd3` + `raw/unit/red/red-c-tree.diff` | `window_scoped_index_without_its_snapshot_is_stale_not_resolved_pid_wide` **FAILED** (it attempted the pid-wide AT-SPI walk) | UNIT |
| green F6: cua-driver-core `--lib --tests` | **865 passed, 0 failed** (FIX-03 F5 862 + 3) | UNIT |
| green F6: platform-linux `--lib` | **606 passed, 0 failed** (F5 603 + 3), 10 ignored | UNIT |
| green F6: jev-use | Python **245 OK** (1 skipped; F5 241 + 4), TS **121/121** (F5 116 + 5), typecheck rc 0, 4 CLI verifiers rc 0; the two `guarded-focused` steps do not apply on this base (as in SETUP, RECERT-FIX, FIX-03) | UNIT |

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Class |
|---|---|---|---|
| F6a | false `refused` statements for possibly-landed effects: D 20 -> 0 | none claimed | REAL, UNIT |
| F6b | blind re-dispatches of a delivery-unknown refusal without `retryable` (UNIT 1 -> 0); unreconciled possibly-landed completions (UNIT) | none claimed | UNIT |
| F6c | cross-session writes from a session's own valid token: CT 20 -> 0 | none claimed | REAL+FIXTURE |

Timing is descriptive only (correctness rows): median cell wall time A1 F6 1694 ms (FIX-03: F5 1659 ms),
A3 F6 567 ms (FIX-03: F5 537 ms). Different runs and load; no timing claim.

## Deviations

1. **Near misses (three commands, no effect possible).** Two plain-shell `python3 -c` one-liners that only
   parsed JSON (loop STATE.json at lane start, SETUP.json at ~16:07Z) and one `python3 -` with an empty
   heredoc (16:06:39Z) ran outside `bin/hostless`. No GUI, display, bus or network import; the shell's Python
   host-display guard also strips desktop variables. Listed in `raw/incidents.txt`. One `perl -0pi -e` text
   substitution edited a test file (a text-editor use, no lane code).
2. **Target dir.** The spec named `cua-release-fix03`; no such dir exists. FIX-03's builds used
   `cua-release-fix02r` (FIX-03 README provenance), so the FIX-03 family dir `cua-release-fix02r` was reused.
3. **Fix F6c is beyond the named F6a/F6b.** Part C's gate ("0/20 cross-window effects on F6; refusals must be
   refused") cannot hold without a fix once SOURCE + shakedown showed the CT hole on F5. F6c is one commit,
   pre-registered with its unit pin and REAL red (F5) / green (F6) rows.
4. **Focus row CF uses foreground.** Shakedown: background press_key is refused `background_unavailable`
   before the GrabFocus rung on this X11 session (no focus-free keyboard backend); foreground is refused
   `foreground_unavailable` (the closed window cannot be activated). Both pre-registered; CF is a
   non-discriminating reachability control, and the focus fallback is pinned by UNIT only.
5. **D receipt naming.** The public effect names are `confirmed, partial, unverifiable, suspected_noop,
   refused`; "effect=unknown" in the spec is the existing unknown variant `unverifiable`. The browser
   envelope keeps `status: refused` (the tool refused to report success) and adds `effect: unverifiable`.
6. **W2dX wording.** The spec says "U' landed vs F6 unknown"; a cross-session token refusal is a
   pre-dispatch refusal and stays `refused` under Part A, so the pre-registered F6 prediction was refused.
7. **Unit red runs took only the cargo lock** (16:08-16:22Z, before the shared-quiet wrapper existed); the F6
   build and green suites held the shared quiet-lane lock as well.
8. **Exclusive-waiter yield.** Every counted acquisition first yielded up to the 120 s cap to a queued
   exclusive waiter of another track (`yield_s` in the receipts), then took the shared lock, as FIX-03's
   wrapper does.
9. **Shakedowns (not counted, `raw/shakedown/`).** F5 CT x2, F5 CF background x2 and foreground x1, F6 CT
   x1, F6 A1 x2 (the first exposed a harness bug: the runner-replay Driver re-sent the launcher's
   feedback-off call through the replay object; fixed before PREREG).

## Limits and claim boundary

- Linux X11 (private Xvfb, openbox) only; macOS and Windows BLOCKED (hardware). Wayland / Hyprland callers of
  the fallbacks are SOURCE-only here.
- F6a does not make the CDP check-and-assign atomic: a page that detaches the input between them still gets
  the files assigned and fires `change` (20/20, IRREDUCIBLE). F6a makes every receipt of that case say
  unknown instead of refused.
- F6b reconciles only the completion candidate (the oracle decides it); a possibly-landed refusal of an
  intermediate action still ends `unknown` (never re-dispatched).
- F6c covers `type_into_editable_at` and `focus_element` and the X11 type_text fall-through. The other
  pid-wide index walkers (`perform_action`, `scroll_element`, `set_value` fallback) and the Hyprland /
  Wayland-inject type_text fall-throughs are listed in `source-audit.json` and unchanged.
- Fork candidates on `0f1955d2f`; not merged anywhere; no new service; the FIX-03 seam stays
  measurement-only and off by default. No timing, latency or wall-clock claim.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed `d73eec78f` before the first counted block |
| `plans/` | the 17 counted blocks in run order |
| `analyze.py` -> `summary.json`, `dispositions.json` | every row, gate and E4 counter from `raw/` |
| `verify_artifacts.py` | independent recomputation (no import of analyze.py), SHAs, binaries, locks, PREREG order, sessions, units, privacy of the packet and of every lane commit; run `CUA_PRIVACY_NAMES_FILE=<file> python3 verify_artifacts.py --git <repo>` |
| `provenance.json` | SHAs, trees, binaries, unit expectations, environment |
| `source-audit.json` | the SOURCE audit with file:line |
| `harness/` | native (`native/fix04_native.py`, reuses FIX-03 `w2_rows.py`, `run_block.py`, `fix03_native.py` unchanged), browser copy + diff, fixture copy + diff, campaign, lock wrappers, unit runners |
| `raw/native/<arm>/<row>/b<block>.jsonl` | every call with pre/post fixture state |
| `raw/browser/<block>-<phase>-F6/` | `validity.json`, `cells.jsonl`, `cells/*.jsonl` (receipts incl. raw, steps, target journal), `end.json` |
| `raw/session-*.log`, `raw/lock-ledger.jsonl` | per-block session output (sanitized at capture), the 17 counted receipts |
| `raw/unit/`, `raw/builds/`, `raw/partE/`, `raw/heads/`, `raw/shakedown/`, `raw/incidents.txt` | unit red/green logs and diffs, build logs, Part E before/after, live heads and drift, shakedowns, incidents |
