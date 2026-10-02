# FIX-01: Driver refuses DOM-event dispatch on detached nodes; jev-use runners treat refused as refused; R2-07b compiled-replay re-qualification

**Dispositions.**
- **Fix: REVISE.** Every measured row passes. The unit suites pass at the fix head and on the upstream-applied tree, and both fix commits cherry-pick cleanly onto upstream main `352507b6c`. The one row that fails is the pre-registered requirement that the commits **cherry-pick cleanly onto `f5c991e59`** (the B-01/R2-10 source). There, Part A conflicts in `browser/tools.rs`. The cause is that `f5c991e59`'s measurement-only marks rewrite the same `dom_event` dispatch `match` (`.await {` becomes `.await; mark; return match dispatched {`), and the detached arm sits right next to it. Part B picks cleanly. A one-hunk resolution is recorded in `raw/b01-resolution-tools.rs.diff`, and all 187 `browser::` unit tests pass on the resolved tree. Revised claim: the fix is correct and applies cleanly to upstream main. On the B-01 source it needs that one recorded resolution.
- **R2-07b (compiled replay re-qualification on F): KEEP.** G2–G5 pass with 0 stale dispatches, 0 ambiguous dispatches, 0 duplicates, 0 unverified successes and 0 authority fields. Compiled replay is eligible for the R2-10 fill composed arm, but only on a source that contains this fix (for `f5c991e59`, the resolved tree).
- **G6 (cost of the fix, reported, not gated):** T(F) − T(U) paired median **-4.757 ms** [95% CI -34.391, 20.099], 20 AB/BA pairs. The CI includes 0 and its lower bound is far below +5 ms, so no explanation is triggered.
- Provider: **0** TypeSafe attempts, **0** reached (lane cap 0). The socket guard counted 0 non-loopback connects.

## Planner ruling (verbatim)

> PLANNER RULING (record verbatim in the packet). R2-07's proposed REVISE amendment is NOT adopted: it was written after the shakedown showed N4a, and a lane PREREG cannot amend the binding spec. R2-07 stays KILL at its tested source 031ee5f58 / Driver 8b037961. Compiled replay can re-enter R2-10 only through the R2-07b re-qualification in this lane, on the fixed source.

## Headline (REAL, mock chooser, Xvfb, Chrome 151)

- **C1, N4a with the compiled routine.** The page replaces Submit between bind and dispatch.
  - U accepted the stale-node click **20/20**: the old node's click listener fired in 20/20, journal applied 0, and every trial ended `unknown`.
  - F refused it with `browser_ref_stale` **20/20**: 0 old-node page events and 0 detached submits. The routine then made exactly one rebind from a fresh observation and verified **20/20** (journal applied 1 each, 0 duplicates).
- **C3, the "could land" hazard.** The detached old Submit keeps a JS handler that writes the token itself.
  - On U that handler's submit landed in **10/10**, and the routine reported `verified`. That is a success produced by a stale dispatch, which the oracle confirmed: the hazard is real.
  - On F: refused 10/10, **0** detached-handler submits and **0** old-node events in 10/10, then rebind and verified 10/10 through the fresh node.
- **C2, N4a_ord, re-dispatch after an unverified accepted click.**
  - U + old run.py: **10/10** trials re-dispatched Submit (10 re-dispatches).
  - U + fixed run.py: **0** re-dispatches; 10/10 stopped `unknown` (phase `reconcile`).
  - F + fixed run.py: refusal, then a fresh observation, then exactly one dispatch, verified 10/10, **0** re-dispatches.
- **C5, refused as success (N4b superseding snapshot).**
  - Fixed run.py classified the `browser_ref_stale` result as refused **10/10** (`DriverToolError refused=true`, runner `action_refused`), then made one fresh observation and one dispatch: verified 10/10.
  - Old run.py returned the same `effect: refused` result as success **10/10**.
- **C4, trusted route with the same injection.** Refused `browser_ref_stale` 10/10 on U and 10/10 on F. `DOM.getBoxModel` already fails for a detached node, so this route was never affected. Nothing landed on the old node. Rebind, then verified 10/10 each.
- **C4w, residual window on the trusted route** (F, re-render d ms after the click request is sent):
  - d 0–12 ms: refused (5/5).
  - d 15–39 ms: **accepted, and the click landed on the replacement node** (9/9). The effect lands, but on a node the caller did not bind.
  - d 42–60 ms: landed on the old node before it was replaced (7/7).
  - Window lower bound: **24.9 ms** from replacement to the page's first `pointerdown` on the new node. That matches the Driver's fixed 25 ms focus-emulation settle between the box read and `Input.dispatchMouseEvent`.
- **C6, positive controls on F.** fill→submit with fixed run.py 20/20, toggle→confirm 10/10, modal→act 10/10, and re-attached node (the same node detached and put back before dispatch) 10/10. All are verified by the journal with **0 refusals**, so there were no false refusals.

## What changed

### Part A: Driver (commit `8cfa8c1dbd281da84f9acf8745dc8bea73da96e3`, `libs/cua-driver/rust` only)

Audit of every browser mutation that resolves a ref to a DOM node and dispatches on it:

| Mutation | Dispatch | Before | After |
|---|---|---|---|
| `browser_click` `input_route=dom_event` | `Runtime.callFunctionOn` `this.click()` | a detached node was clicked: listeners ran, and the result was `ok`/`effect unverifiable` | the same call runs `if (!this.isConnected) return false; this.click(); return true;` with `returnByValue`. `false` gives a refusal with `browser_ref_stale` (isError false; public effect `refused`). Nothing is dispatched |
| `browser_pointer` `dom_event` (hover, right/double click, scroll, drag) | `Runtime.callFunctionOn` dispatching synthetic events on `this` | events were dispatched on a detached origin or drag destination | the same call is wrapped: `if (!this.isConnected \|\| (args[0] != null && args[0].isConnected === false)) return 'detached'` gives `browser_ref_stale`. Otherwise the original function runs unchanged |
| `browser_download` activation | `Runtime.callFunctionOn` `this.click()` | a detached node was clicked | the same guarded click; `false` takes the existing `browser_ref_stale` "could not be activated" path, which also resets the download behaviour |
| `browser_click` trusted route | `DOM.getBoxModel`, then `Input.dispatchMouseEvent` | already refuses `browser_ref_stale`: a detached node has no layout box, and that check runs **before** any coordinates exist | unchanged. Characterized by a unit test and by C4 (10/10 refused on U and on F) |
| `browser_pointer` trusted route | `point_for_ref`, which uses `DOM.getBoxModel` | same as the trusted click | unchanged |
| `browser_type` (insert_text / keystrokes, focus) | `DOM.focus`, then the `EDITABLE_AND_FOCUSED_CHECK` callFunctionOn (`activeElement === this`), then `Input.insertText` or key events | `DOM.focus` fails for a detached node (gives `browser_ref_stale`), and a detached node can never be `activeElement` | unchanged. Text is trusted input into the focused element, not a dispatch on the ref's node |
| `browser_set_input_files` | `DOM.setFileInputFiles` | not a `callFunctionOn` dispatch; outside this audit's scope | unchanged. **Residual:** a detached `<input type=file>` is not checked. Recorded as a follow-up, not measured |

**Why there is no new vocabulary.** The existing code `browser_ref_stale` already means "the ref no longer designates a live element, re-snapshot". A detached node is exactly that. The only new text is the refusal message ("the ref's node is no longer connected to the document; nothing was dispatched"). Prose is not public vocabulary. No new code, field or sub-reason was added. `'detached'` is a value private to the page→Driver call and never leaves the Driver.

**Why the check is in the dispatching call.** A separate pre-check round trip, for example `DOM.scrollIntoViewIfNeeded` (which also fails for detached nodes), would leave a window between check and dispatch. Here the check and `this.click()` run in one synchronous JS function on the page's main thread. No page script can run between them.

**Residual window (trusted route).** It is not closed and is unchanged. The click point is computed from `DOM.getBoxModel`, then the Driver enables focus emulation and sleeps 25 ms before `Input.dispatchMouseEvent`. A re-render inside that window makes the trusted click land on whatever now occupies the point: here, the replacement node with the same role and name (C4w: 9/21 cells; window ≥ 24.9 ms). A coordinate route hit-tests at dispatch time by nature. Closing the window would need a re-check after the settle, and that still leaves a smaller window. That design choice is out of scope and is recorded as a follow-up.

**Default behaviour** changes only for detached nodes, which is the reviewed fix. Connected and re-attached nodes dispatch exactly as before: C6 had 0 false refusals, and the unit tests cover connected and re-attached nodes.

### Part B: caller (commit `6eb9319fe785a7eb7d5e156a9221edf818a3697f`, `libs/cua-driver/examples/jev-use` only)

Both `python/run.py` and the TypeScript twin `typescript/run.ts`:
1. `Driver.call` treats `effect: "refused"` (isError false) as refused. Before, it recognized only the `status`/`refusal` envelope, so an action result carrying a refusal was returned as success. It now raises `DriverToolError(..., refused=True)`. The code comes from the structured payload, or else from the stable `refused (<code>):` text prefix that the MCP boundary keeps.
2. A refusal landed nothing, so it earns **one** fresh observation and one fresh decision. A second refusal stops as `unknown` (phase `refused`, `action_refused: <code>`).
3. When a completion was accepted but the existing bounded re-read (20 × 0.1 s) does not confirm it, the run stops as `unknown` (phase `reconcile`) instead of re-planning. The click may still land.
4. A mutation already accepted in this run is never dispatched again on a fresh ref (phase `redispatch_blocked`). A negative read does not authorize replay.

Consistency with OWN-105 (kvnloo/cua#105 runner rules, packet `b97daa4ba`): G1 (reconcile with fresh reads, never dispatch from a negative read) corresponds to rule 3. G2 (a pending completion is never re-dispatched) corresponds to rules 3 and 4. G3 (failure after an unverified completion ends with a receipt) is not touched here. These are the minimal versions on this source, which does not contain the #105 receipt machinery. No new service.

## Provenance (each SHA separate)

| Item | Value | Class |
|---|---|---|
| Base (R2-07 tip) | `2d71548b46114cd1a1bc58ccdef323ce185c9965` = 031ee5f58 (upstream c4d0c6625 + trycua/cua PR 4316 head a0bca7440) + R2-07 harness/packet. Rust tree `ceadcc0e6…`, equal to 229b65b28 and to upstream main 352507b6c (`git diff --quiet`, re-verified) | SOURCE |
| Fix Part A (Driver) | `8cfa8c1dbd281da84f9acf8745dc8bea73da96e3` (Rust tree `e24808eff…`) | SOURCE |
| Fix Part B (caller) | `6eb9319fe785a7eb7d5e156a9221edf818a3697f` | SOURCE |
| PREREG | `b47b6cc30` committed 2026-10-02T05:05:01Z, before the shakedown and before the first measured block (05:11:30Z). Harness fix after the shakedown: `872790bce` (no row, n, prediction, oracle, gate or rule changed) | SOURCE |
| Upstream-applied tree | upstream main `352507b6c` + cherry-picks of both commits in a detached worktree (no branch): tree `e35efb8e8…`, identical to the `git merge-tree --write-tree` result | SOURCE |
| B-01 source | `f5c991e59`: Part A conflict, Part B clean. Resolution in `raw/b01-resolution-tools.rs.diff`, tested (187/187 `browser::` tests) | SOURCE+UNIT |
| U binary | `cua-driver-r2-main-229b65b28`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `cua-driver 0.32.0` (re-hashed; version read inside the session in every block) | REAL |
| F binary | `cua-driver-fix01-8cfa8c1db`, sha256 `6ce995b8cc7637af0c46d4a67854a73352a437d03c1de1b272a9eadcf942ac04`, `cua-driver 0.32.0`. Built from head 6eb9319fe (Rust tree == 8cfa8c1db) by `build-driver.sh … fix01-8cfa8c1db cua-release-fix01` under hostless + `locked.sh shared` + cargo lock (receipt `build-F-fix01-8cfa8c1db`), 0 Fresh workspace units | REAL |
| Compiled routine artifact | R2-07 `raw/learn/artifact.json`, git blob `4ffbe21d7d105f0ca77ec623c0e53f0180d866b7`, used as logical identity only. 0 authority fields: no refs, element tokens, captures, capabilities, session epochs or coordinates. `verify_artifacts.py` checks it and catches 6/6 injected authority fields | SOURCE |
| Old run.py (C2/C5 control) | base blob `462554e695250cf84f8469751f69965afb9a50e0`, loaded from git inside the session | SOURCE |
| Live heads | Start (05:04:44Z): trycua/cua PR 4316 `a0bca744067d04f05904319d3d919be30c336556` open; upstream main `bc55ff2d2`. End (06:32:29Z): PR 4316 `a0bca744067d04f05904319d3d919be30c336556` (unchanged); upstream main `7b98efd35b50e1ffaa796385c1d35534f8cb5bb2`, 9 commits past 352507b6c with 0 files under `libs/cua-driver` | SOURCE |
| Tested source vs publication | Measured tree = branch head while running (Rust tree `e24808eff`, jev-use = 6eb9319fe; every block records `head`, the Rust tree and clean status in `validity.json`). Publication SHA is set by the Publish agent; this lane pushed nothing | SOURCE |
| Environment | hostless v2 (strips desktop vars, private `XDG_RUNTIME_DIR`, Landlock scope) → lock wrapper → `cua-x11-session.sh` (private rootless Xvfb 1920x1080x24 `-nolisten tcp`, openbox, picom, private dbus, scrubbed env). DISPLAY `:99` for every shared block and `:100` for the G6 blocks (per block in `validity.json`); 0 openbox "already running" collisions. Chrome 151.0.7922.71 launched by the Driver, `isolated_new` profile. Python 3.12.13, Node v22.23.2. Default Driver safety settings. Agent-cursor feedback held OFF per session label (R2-07 wrapper; receipt in every cell) | REAL |

## Method

- **Forced path.**
  - C1, C3, C6-reattach, G4, G5: the R2-07 compiled routine (`docs/experiments/r2-07-2026-10-02/harness/compiled_routine.py`, unchanged), in process. Fresh `semantic_v2` observation and role+name bind before each mutation; `browser_type` then `browser_click` with `input_route=dom_event`; mock chooser fallback.
  - C2, C5, C6-fill: the jev-use `run.py` (`--provider mock`), the fixed version or the old base blob.
  - C4, C4w, C6-toggle and C6-modal: a minimal fresh-bound direct caller in the harness (`fix01_harness.direct_trial`).
  - G2 and G6: subprocess compiled replay through the R2-07 launcher, wrapped by `fix01_launcher.py` (socket guard).
- **Injection.** The page long-polls `/__signal`. The harness triggers the re-render and waits for the page's `/__rerendered` acknowledgement before the dispatch (C1–C4), or d ms after sending the click (C4w).
- **Oracle (target-owned).** The fixture journal: `received`/`applied` per `POST /submit`; `submit_src` (form or detached handler); `page_event` beacons naming which Submit node (old, fresh or same) received click/pointer events; toggle/opened/modal events. Caller records are used only for producer attribution: Driver call results, refusal codes, launcher receipts.
- **Locks.** Every correctness block held `locked.sh shared` (≤10 trials). G6 held the EXCLUSIVE lock through `bin/quiet-timed` around the whole session, so the lock was taken before the Driver session opened. Builds and unit tests used `locked.sh shared` (+ cargo lock). There are 45 receipts in `raw/lock-ledger.jsonl`, and the loop ledger has the same lines. Lock-wait times are visible there; other lanes' exclusive phases sat between my blocks.
- **Denominators.** 29 measured blocks and 282 trials (Part C 201, Part D 81; G4's N4a n=20 reuses the 20 C1-F cells). Every trial is kept, and 0 blocks were invalid. Shakedown blocks live in `raw/shakedown/` (post-PREREG, harness debugging, never analysed): s1 and s2 failed on harness bugs and the hostless v1→v2 switch, s4 and s5 passed.

## Results (every row recomputed by `analyze.py` → `fix01-summary.json`)

### Part C

| Row | Arm | N | Result | Class |
|---|---|---|---|---|
| C1 N4a (routine) | U | 20 | first click **accepted 20/20**; old-node click events in 20/20; journal applied 0; outcome unknown 20/20; dup 0 | REAL |
| C1 N4a (routine) | F | 20 | first click **refused `browser_ref_stale` 20/20**; old-node events 0/20; detached submits 0/20; one rebind and fresh dispatch 20/20 → **verified 20/20** (applied 1 each); dup 0; not-fresh dispatches 0 | REAL |
| C2 N4a_ord | U + old run.py | 10 | re-dispatch after unverified accepted click **10/10** (10 re-dispatches); verified 10/10 by the second click | REAL |
| C2 N4a_ord | U + fixed run.py | 10 | **0 re-dispatches**; 1 click each; outcome unknown, phase `reconcile`, 10/10; old-node events 10/10 (the stale click U still accepts) | REAL |
| C2 N4a_ord | F + fixed run.py | 10 | first click classified refused 10/10, then ≥1 fresh observation, then exactly 2nd click 10/10 → verified 10/10; **0 re-dispatches**; old-node events 0 | REAL |
| C3 hazard | U | 10 | accepted 10/10; **detached-handler submit landed 10/10**; routine reported verified 10/10, the success coming from a stale dispatch | REAL |
| C3 hazard | F | 10 | refused 10/10; **detached submits 0/10, old-node events 0/10**; rebind and fresh dispatch → verified 10/10 | REAL |
| C4 trusted | U | 10 | refused `browser_ref_stale` 10/10 (getBoxModel); old-node events 0; first pointerdown on the fresh node after rebind 10/10; verified 10/10 | REAL |
| C4 trusted | F | 10 | identical: refused 10/10, old-node events 0, verified 10/10 | REAL |
| C4w window | F | 21 | refused 5 (d 0–12), **accepted and landed on the replacement 9 (d 15–39)**, landed on the old node 7 (d 42–60); window lower bound **24.9 ms**; all 21 verified (applied 1) | REAL |
| C5 N4b | F + fixed run.py | 10 | **classified refused 10/10** (`action_refused` events 10); 1 fresh observation; 2nd click → verified 10/10 | REAL |
| C5 N4b | F + old run.py | 10 | refusal **returned as success 10/10** (`effect: refused`, no exception), then re-planned Submit; verified 10/10 | REAL |
| C6 fill | F + fixed run.py | 20 | verified 20/20, refusals 0, 1 click each | REAL |
| C6 toggle→confirm | F | 10 | verified 10/10 (journal toggle checked), refusals 0 | REAL |
| C6 modal→act | F | 10 | verified 10/10 (opened and modal events), refusals 0 | REAL |
| C6 re-attached node | F | 10 | accepted 10/10, click reached the same (re-attached) node 10/10, verified 10/10, refusals 0 | REAL |

### Part D (R2-07b on F)

| Gate | Result | Class |
|---|---|---|
| G2 admission | clean reset, subprocess replay, no fallback: verified 1/1 (journal applied 1, token), T 314.19 ms, 0 provider attempts | REAL |
| G3 fresh binding | 42/42 compiled-routine mutations fresh from **launcher Driver-call receipts** (G2 + every G6 cell, U and F); 178/178 self-recorded fresh in the in-process rows (C1-F, C3-F, C6 reattach, G4, G5) | REAL |
| G4 negatives (3 reps each) | N1, N2, N3, N6 stopped 3/3; N4a refused → rebind → verified 3/3; N4b refused → rebind → verified 3/3; N5 verified 3/3; N7 fallback_verified 3/3; N8 stopped with **0 dispatches**. Plus N4a n=20 = C1-F. **0 stale, 0 ambiguous, 0 duplicates, 0 unverified successes** | REAL |
| G5 reconcile | applied_ack_lost verified_by_reconcile 5/5 (1 read each); delayed verified_by_reconcile 5/5 (2 reads each); withheld_unresolved unknown 3/3 (58–59 reads); faults fired 13/13; **0 duplicates, 0 dispatches after unknown** | REAL |
| G6 cost (EXCLUSIVE) | 20 pairs, AB/BA (UF even pairs, FU odd pairs), 40/40 verified. Median T: U 294.144 ms, F 284.036 ms; paired F − U **-4.757 ms** [95% CI -34.391, 20.099] (seed 20261002, 10000 resamples). 1-minute loadavg at spawn 15.6–24.2 (other non-lane load on the host), recorded per trial | BENCHMARK |

The live C-vs-B saving from R2-07 (-273.0 ms) is **not** re-claimed. R2-10 measures compiled replay live over all invocations. The G6 T values are higher than R2-07's P4 (186 ms) and are not comparable: different binaries and host load, with no live arms.

### Unit evidence (UNIT)

| Tree | Rust `cua-driver-core` | Rust `cua-driver-contract` | jev-use Python | jev-use TS | typecheck / CLI verifiers |
|---|---|---|---|---|---|
| Red = base + new tests (+ the two new symbols as unused stubs, `raw/red-tree.patch`) | lib 813 pass, **3 fail** (the click, pointer and download detached tests; connected/re-attached and trusted characterization stay green, as they should) | 61 pass | 257 run, **5 fail + 2 errors** (7 of the 9 new tests) | 163, **6 fail** (6 of the 8 new tests) | typecheck rc 2 (new test uses `refused`); CLI rc 0 |
| Fix head (6eb9319fe) | **843 pass, 0 fail** (lib 816 + integration) | 61 pass | **257 OK** (1 skipped) | **163/163** | rc 0; 4 CLI verifiers rc 0; guarded-focused rc 0 |
| Upstream-applied (352507b6c + fix) | **843 pass, 0 fail** | 61 pass | **238 OK** (1 skipped) | **113/113** | typecheck rc 0; 4 CLI rc 0; guarded-focused steps not applicable (upstream main lacks PR 4316's guarded tests: rc 5 "no tests", rc 1 missing file) |
| B-01 source + resolution | `browser::` 187/187 | — | — | — | — |

## Work deleted vs wall-clock saved

- **Work deleted:** no performance work was targeted; this is a correctness fix.
  - It removes stale dispatches: C1 20 and C3 10 detached-node clicks on U become 0 on F.
  - It removes the caller's blind re-dispatch: C2 10 → 0.
  - It removes the refused-as-success misclassification: C5 10 → 0.
- **Work added:** none on the success path. The guard runs inside the existing `callFunctionOn`, with `returnByValue` on a boolean. On a detached node the routine adds one observation and one dispatch, the same rebind it already does for `browser_ref_stale`.
- **Wall-clock:** G6 paired F − U -4.757 ms, CI [-34.391, 20.099]. No measurable cost and no saving claimed.

## Controls

- Discriminating controls:
  - U vs F on the same injection: C1 20 vs 0 accepted stale clicks; C3 10 vs 0 detached effects.
  - Old vs fixed run.py: C2 10 vs 0 re-dispatches; C5 10 vs 0 misclassifications.
- Positive controls (C6) prove the guard does not refuse connected or re-attached nodes.
- The trusted-route control (C4) shows the trusted route refused before and after the fix (getBoxModel). C4w measures the residual window that remains.
- Provider cap 0 was enforced by construction: no key in any session (`forbidden_env_present` empty in 29/29 blocks), and a socket guard in the harness and in every launcher subprocess counted 0 non-loopback connects.

## Fresh-verifier review notes (self-review before handoff)

- Correctness:
  - `false` is returned only by the guard. `this.click()` returns `undefined`, so the success path returns `true`.
  - A page-side exception still produces `Ok` with `exceptionDetails` and keeps the previous behaviour, as before (for example `click` on a non-HTMLElement). This is unchanged and out of scope.
  - The pointer wrapper preserves the original function's return value, `this` and arguments.
- Minimality: Driver product diff 3 files, +39/−5 lines outside tests (`tools.rs` +23/−1, `pointer.rs` +10, `download.rs` +6/−4); caller diff `run.py` +68/−2, `run.ts` +66/−4. No new service, code, field or route.
- Not fixed, recorded as follow-ups:
  - the trusted-route residual window (25 ms settle);
  - `browser_set_input_files` on a detached input (not a `callFunctionOn` dispatch).

## Deviations

1. **Cherry-pick onto f5c991e59 conflicts** (Part A). This was known before the PREREG and is disclosed in it. It is the row that makes the fix REVISE.
2. **Unit runs without the lock receipt.** Two early dev runs of the new Python (9) and TypeScript (8) tests ran under hostless but **without** the shared quiet-lane lock receipt. They are not evidence: the receipted runs in `raw/unit/` are.
3. **Stdlib python3 on the plain host shell.** Several stdlib `python3` invocations (file edits, JSON inspection of raw outputs, one partial `analyze.py` run) ran in the plain host shell instead of under hostless. They imported no GUI, display or network modules and touched only files. Reported as a near miss.
4. **hostless switched from v1 (bwrap masks) to v2 (env strip + private runtime dir + Landlock) at 05:06:31Z,** during the post-PREREG shakedown. This was loop infra, not this lane. Shakedown s2 ran under v1 and failed with `browser_route_unavailable` (v1 blocked the Driver's Chrome launch). `run_block.sh` was adapted to check v2's evidence instead (commit `872790bce`). Every measured block ran under v2.
5. **C1 uses an instrumented N4a page** (`n4a_instr` = R2-07 `rerender_on_signal` plus sendBeacon click listeners). G4's 3-rep N4a uses the unmodified R2-07 page. Both refuse on F.
6. **The routine's Driver class is the fixed run.py's `Driver` in every in-process row, including U rows.** The routine treats a refusal raised as an exception and a refusal returned as `effect: refused` identically (`refusal_code`).
7. **Extra rows** beyond the spec, all pre-registered: C4w (residual window) and C6 re-attached.
8. **G6 ran in 2 exclusive acquisitions of 10 pairs.** The first launcher script was killed by the agent's background time limit while it waited for the lock before block 2. Block 2 had not started (no output, no receipt) and was re-run.
9. **Loadavg during the exclusive G6 blocks was 15.6–24.2.** That load came from processes on the host outside the lock protocol. It widens the G6 CI; G6 is not gated.

## Limits

- One fixture page per class; Chrome 151; Linux X11 Xvfb; mock chooser; Driver 0.32.0 U/F only. Nothing is compared across sources.
- The connectedness guard covers `isConnected` (document-connected). A node inside a shadow tree whose host is connected counts as connected, which is correct. Nodes in a detached iframe document were not tested.
- C4w uses one trial per delay. The window bound is a lower bound from the page clock.

## Claim boundary

jev-use fill fixture and #24 pages, X11 Xvfb, Chrome 151, mock chooser, Driver 0.32.0 U (`8b037961`) and F (`6ce995b8`) as hashed. This is a reviewed fix candidate staged downstream only: nothing posted upstream, nothing merged, no PR opened. R2-07 itself stays KILL at 031ee5f58 / 8b037961 (planner ruling). R2-07b KEEP applies to compiled replay on a source containing this fix.

## Files

- `PREREG.json`: frozen before any trial.
- `harness/`:
  - `fix01_harness.py`: phases C1–C6 and G2–G6.
  - `fix01_fixture.py`: the R2-07 fixture extended with page-event beacons, submit-source tags and variants.
  - `fix01_launcher.py`: the R2-07 launcher plus the socket guard.
  - `run_block.sh`, `locked.sh`, `rust_tests.sh`, `package_raw.py`.
- `raw/measured/<block>/`: `validity.json`, `cells.jsonl`, per-cell files with the target journal, `end.json`, and the block log.
- `raw/shakedown/`, `raw/unit/`, `raw/lock-ledger.jsonl`, `raw/red-tree.patch`, `raw/b01-resolution-tools.rs.diff`.
- `analyze.py` → `fix01-summary.json`; `provenance.json`; `verify_artifacts.py`.
- Local paths in `raw/` are replaced with placeholders (`<wt>`, `<lanes>`, `<tmp>`, …).
- Raw mirror: `<lanes>/artifacts/r2/FIX-01/`.
