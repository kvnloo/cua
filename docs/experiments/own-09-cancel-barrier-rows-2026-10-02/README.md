# OWN-09: cancellation and admitted-native-work barrier rows (Linux core, SDK level)

**Disposition: KILL** under the pre-registered rule, for "#84 as-is satisfies the kvnloo/cua#9 Linux core rows".
P (main + kvnloo/cua#84) fails two gating rows: **R6** (shutdown and session end report readiness while a
cancelled call's native work is still running, 40/40 per variant) and **R1** (a queued call was admitted and
entered native work after its caller had abandoned it and the cancel request had returned, 1 of 40 counted
iterations, stress pass). P passes R4 and R5, and passes R2 and R7 **for a tool that adopts #84's
`spawn_blocking_owned`** (the barrier tool does; no production tool does, and on the #84 tree the
production-style plain `spawn_blocking` closure fails R2 and R7 40/40). On upstream main (M), R2, R6 and R7
are **CONFIRMED_GAP**s. R3 is BLOCKED (macOS). R8 (MCP `notifications/cancelled`) is characterized at
SOURCE+FIXTURE level as IGNORED; REAL stdio is NOT_RUN.

The KILL is a statement about #84 as a complete answer to the #9 Linux core rows. For a tool that opts into
`spawn_blocking_owned`, #84's AdmissionHold does what it claims (R2: 40/40 PASS on P vs 40/40 FAIL on M; R7:
1 effect vs 2). What it does not cover is listed under "What a revision needs".

Owners: kvnloo/cua#9 (canonical upstream owner: trycua/cua 3796), kvnloo/cua#36 (R5 is its cancellation
cross-session row), kvnloo/cua#105 / R2-05 (R7), kvnloo/cua#10 (accounting).

## Provenance (each SHA kept separate)

| what | SHA |
|---|---|
| upstream main base (arm M production code) | `352507b6c03162ab286b21d5ed509125cc3daece` |
| kvnloo/cua#84 head, read live with gh at start and at end | `566b9c73245266005c958d40e93d46ee5d463325` (PR base `c3941497a`) |
| arm M tree: base + OWN-09 test files only | `143a47c796bbb3a145085e3dd9658fd7b5cd0ee2` |
| arm P tree: separate `--no-ff` merge of #84 into this branch | `98cdf5415616a88fe2ecb91ade7e7878ba6412c9` |
| PREREG commit (before the first counted run); P ran at this head, `libs/cua-driver` tree identical to the merge | `34674f3c3756fd76cf60f1dc8cb16ef7115e4b24` |
| publication SHA | the commit that adds this README (not self-referential) |

- System under test: the in-process embedded SDK runtime linked into each integration-test binary. **No
  `cua-driver` executable, no Driver session, no GUI, no provider.** Driver binary sha256: not applicable.
  Test binaries: `own09_arm_m` sha256 `8c542d7a…ff073bc`, `own09_arm_p` sha256 `3c7567b2…97f2a003`
  (full values in `provenance.json`); crate version 0.32.0; rustc 1.97.1; Linux 7.2.2 x86_64.
- Environment: every cargo invocation ran under the lanes' `hostless` wrapper, version 2 (in place from
  05:06:31Z, before the PREREG commit and every counted run), holding the shared quiet-lane lock and the
  exclusive cargo-build lock. hostless v2 removes the desktop and session variables (display, Wayland,
  compositor, session D-Bus, AT-SPI, X authority), points `XDG_RUNTIME_DIR` at a private per-invocation
  directory, and applies a Landlock scope that blocks `connect()` to abstract unix sockets bound outside the
  scope and signals to processes outside it. It does not use bwrap and does not mask socket directories
  (that was v1). Other lanes were running (loadavg about 11-20). No timing claims are made.
- Live PR head vs tested source vs publication: #84 head was `566b9c732` at start and at end, and that is
  exactly what was merged; upstream main was not re-pinned (`352507b6c`); this packet is published from the
  lane branch only (no push, no GitHub write by this lane).

## STEP 0: SOURCE (file:line at base `352507b6c`, `libs/cua-driver/rust/crates/`)

**(a) C ABI cancel path. Confirmed.**
- `cua-driver-sdk/src/abi.rs:108-138` `OperationState { cancelled, changed }`; `:121-127` `cancel()` sets the
  flag and `notify_one`.
- `abi.rs:488-541` `spawn_completion`: the work runs in a nested `tokio::spawn` (`:505`) on the ABI executor;
  `tokio::select!` (`:506-525`) races the join against `state.cancelled()` and on cancel calls
  **`work.abort()` (`:519`)** and completes the callback with `Cancelled`.
- `abi.rs:987-995` `cua_driver_operation_cancel_v1` only calls `state.cancel()` ("Request cancellation").
- The Rust embedded SDK reaches the same path: `CuaDriver::call_tool` -> `NativeAbiDriver::invoke`
  (`abi.rs:1373-1423`) -> `ffi::invoke` = `cua_driver_invoke_v1` (`abi.rs:710-782`, `spawn_completion` at
  `:765`). Dropping the caller's future drops `OperationGuard` (`abi.rs:1152-1176`), whose `Drop` calls
  `ffi::operation_cancel` (`:1171`). Trusted sessions use `cua_driver_session_invoke_v1` (`:874-946`, same
  `spawn_completion` at `:929`).
- What `work.abort()` drops: the runtime's lifecycle read guard (`cua-driver-sdk/src/runtime.rs:310`, held in
  the invoke frame; shutdown waits on the write side at `:225-227`), the core session dispatch guard
  (`cua-driver-core/src/tool.rs:1661-1701`, normally dropped at `:1804`) and the desktop action coordinator
  guard (`tool.rs:1730-1747`, normally dropped at `:1849`). A native closure started with plain
  `tokio::task::spawn_blocking` keeps running after the abort.
- Adjacent, not measured: `platform-linux/src/tools/impl_.rs:2442-2455` `spawn_blocking_bounded` returns an
  error at its budget while the blocking closure keeps running; the same abandonment shape without any cancel.

**(b) Direct stdio MCP. Confirmed.** `cua-driver/src/proxy.rs:80-162`: one line at a time; each request is
awaited inline (`handle_request_with_transport_session`, `:133-139`) before the next line is read, and
`Ok(request) if request.is_notification() => continue` (`:94`) drops every notification, including
`notifications/cancelled`, before dispatch. The opt-in envelope transport (`CUA_DRIVER_MCP_ENVELOPES=1`) also
drops ordinary notifications (`cua-driver/src/mcp_envelope.rs:213-217`); it has its own typed
`cua/driver/v1/cancel` control, which is out of scope here. If a notification does reach core dispatch,
`cua-driver-core/src/server.rs:975-978` answers `-32601 Unknown method` with `id: null` (observed in R5/R8).

**(c) Existing fixture.** `cua-driver-sdk/src/tests/snapshot_lifecycle.rs:178-224`
`sdk_shutdown_drains_snapshot_publication_and_retires_the_result` proves, for an **uncancelled** admitted call
on a non-desktop tool (`health_report`, no coordinator), that shutdown closes admission at once, does not
return while the native capture runs, refuses a new call, and leaves the published token stale afterwards.
It says nothing about cancellation or desktop capacity. Its sibling `:226-269`
(`sdk_cancelled_capture_does_not_publish_after_shutdown`) explicitly tolerates shutdown returning before
native work finishes after a cancel (`:249-261`) and asserts only that nothing is published.

**(d) What #84 changes** (merged-tree lines): `cua-driver-core/src/tool.rs:74-110` makes the coordinator an
`Arc<tokio::sync::Mutex<()>>`, adds `AdmissionHold` (`:86`), the `ADMISSION_HOLD` task-local (`:89`),
`current_admission_hold()` (`:93`) and `spawn_blocking_owned()` (`:98`); dispatch takes an owned guard
(`:1774`) and scopes the invocation with it (`:1824`). `cua-driver-sdk/src/lib.rs` registers its fixture
`src/tests/cancellation_slice_a.rs`. **What it does not do or claim:** no production tool calls
`spawn_blocking_owned` (the only callers are tests; the Linux tools file still has 153 `spawn_blocking`
sites), the hold covers only the desktop coordinator (not the lifecycle read guard or the session dispatch
guard), `spawn_completion` is unchanged, and there is no MCP or C ABI cooperative cancellation, no held-input
cleanup and no session cancellation.

## Method

- **Forced path.** A barrier-backed host tool is registered under the physical-desktop name `press_key`
  through the public `DriverHostOptions::register_host_tools` hook on
  `CuaDriver::try_create_configured_for_host` with an explicit Standard-only authorization ceiling (no
  permission environment variable; the ceiling is what enables trusted sessions). Every call therefore takes
  the production route: `call_tool` -> C ABI `cua_driver_invoke_v1` -> `spawn_completion` -> lifecycle read
  guard -> dispatch desktop coordinator -> `Tool::invoke` -> native closure. Session rows use
  `create_trusted_session` -> `cua_driver_session_invoke_v1`. R8 uses the shared core MCP dispatcher
  (`handle_request_with_transport_session`) over the SDK.
- **Arms.** M: the native closure uses plain `spawn_blocking` (what production tools use). P: it uses #84's
  `spawn_blocking_owned`. P also runs broken controls with the plain closure on the #84 tree.
- **Route attribution.** Cancel = abort of the caller task -> `OperationGuard::drop` ->
  `cua_driver_operation_cancel_v1` -> `spawn_completion` `work.abort()`. The barrier invocation's `Drop` logs
  `invocation-dropped:<id>`. The dispatch frame lives on the ABI executor, so only that abort can drop it
  before `invoke-end`; it was observed in every cancelled R2 and R6 iteration (`cancel_reached_dispatch_frame`).
- **Oracle (target-owned).** Fixture-owned native entry/exit counters, a target journal written only by the
  native closure (or by the target's delayed-commit thread in the R7 characterization), and an ordered
  ledger. Caller-visible outcomes are used only where a row is about what the caller receives (R4, R5, R8).
- **Phase.** Channels and ledger events only. A 300 ms negative window decides when the harness releases a
  barrier; no verdict depends on it alone (the verdict is an ordering or a count).
- **n.** 20 iterations per variant per pass, each with a fresh Driver runtime, in a main pass
  (`--test-threads=1`) and a stress pass (`--test-threads=8`; tests serialize on the per-process runtime
  lock, so the stress is scheduler contention plus the other lanes' load). Every failure is kept.
- **Order.** PREREG committed 05:11:13Z; counted runs 05:19-05:46Z in the order M main, P main, M stress,
  P stress (`raw/receipts.jsonl`).

## Results (counted, N of 20 per variant; main / stress)

| row | variant | M main | M stress | P main | P stress |
|---|---|---|---|---|---|
| R1 | cancel_while_queued | 20 PASS | 20 PASS | 20 PASS | **19 PASS, 1 FAIL** |
| R1 | cancel_race | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R1 | broken_detach_on_cancel (control) | 20 FAIL | 20 FAIL | 20 FAIL | 20 FAIL |
| R2 | cancel_after_admission | **20 FAIL** | **20 FAIL** | 20 PASS | 20 PASS |
| R2 | control_no_cancel (positive) | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R2 | broken_plain_closure (P control) | - | - | 20 FAIL | 20 FAIL |
| R4 | after_completion | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R4 | after_inflight_cancel | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R4 | broken_name_keyed (control) | 20 FAIL | 20 FAIL | 20 FAIL | 20 FAIL |
| R5 | foreign_session_and_transport | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R5 | broken_session_keyed (control) | 20 FAIL | 20 FAIL | 20 FAIL | 20 FAIL |
| R6 | shutdown_no_cancel | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R6 | shutdown_after_cancel | **20 FAIL** | **20 FAIL** | **20 FAIL** | **20 FAIL** |
| R6 | end_session_no_cancel | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R6 | end_session_after_cancel | **20 FAIL** | **20 FAIL** | **20 FAIL** | **20 FAIL** |
| R6 | broken_ready_on_cancel (control) | 20 FAIL | 20 FAIL | 20 FAIL | 20 FAIL |
| R6 | broken_plain_closure_shutdown_after_cancel (P, informational) | - | - | 20 FAIL | 20 FAIL |
| R7 | ack_lost_guarded_retry | **20 FAIL** | **20 FAIL** | 20 PASS | 20 PASS |
| R7 | control_ack (positive) | 20 PASS | 20 PASS | 20 PASS | 20 PASS |
| R7 | broken_blind_retry (control) | 20 FAIL | 20 FAIL | 20 FAIL | 20 FAIL |
| R7 | broken_plain_closure (P control) | - | - | 20 FAIL | 20 FAIL |
| R7 | delayed_after_native_exit (characterization) | 20 FAIL | 20 FAIL | 20 FAIL | 20 FAIL |
| R8 | notification_in_flight | 20 IGNORED | 20 IGNORED | 20 IGNORED | 20 IGNORED |
| R8 | broken_honoring_transport (control) | 20 HONORED | 20 HONORED | 20 HONORED | 20 HONORED |

Zero harness errors in 1,800 counted iterations (900 per pass). Every broken control was detected 20/20 in both passes.

**Row status (pre-registered rules, recomputed by `verify_artifacts.py`):**

| row | evidence | M | P |
|---|---|---|---|
| R1 queued cancel never enters native | SOURCE + FIXTURE | PASS | **FAIL** (kill gate, 1/40) |
| R2 capacity owned until native exit | SOURCE + FIXTURE | **FAIL = CONFIRMED_GAP** | PASS (tool adopts `spawn_blocking_owned`; plain closure FAIL 40/40) |
| R3 held-input cleanup exactly once | BLOCKED | BLOCKED (macOS-first target oracle) | BLOCKED |
| R4 late cancel cannot reach a later issuance | SOURCE + FIXTURE | PASS | PASS |
| R5 foreign session/transport cannot cancel (#36) | SOURCE + FIXTURE | PASS | PASS |
| R6 no readiness before admitted work exits | SOURCE + FIXTURE | **FAIL = CONFIRMED_GAP** | **FAIL** (kill gate) |
| R7 unchanged read is not authority (#105) | SOURCE + FIXTURE | **FAIL = CONFIRMED_GAP** | PASS (tool adopts `spawn_blocking_owned`; plain closure FAIL 40/40) |
| R8 `notifications/cancelled` | SOURCE + FIXTURE; REAL NOT_RUN | IGNORED | IGNORED |

### Row notes

- **R1.** Holder admitted and in native work; a second call queues; its caller is cancelled; the holder is
  released; a witness must be admitted after the holder's native exit. The P stress FAIL (iteration 4) has
  this trace: `queued:2`, `cancel-requested:2` (seq 5), `waiter-returned:2:cancelled` (seq 6), `release:1`
  (seq 8), `native-exit:1`, **`admitted:2` (seq 12), `native-enter:2` (seq 13)**, `invocation-dropped:2`
  (seq 15); admission came about 0.40 ms after `cancel-requested:2`. Precisely what "cancelled" means here:
  the harness aborted the caller's task, `OperationGuard::drop` synchronously called
  `cua_driver_operation_cancel_v1`, and the harness's tokio `JoinHandle` then reported `is_cancelled`. The
  Driver's own `Cancelled` completion callback is not observed by this fixture. So the claim is: the queued
  work was admitted and entered native work **after the caller had abandoned it and the cancel request had
  returned**, which meets the R1 kill gate. The queued work won the coordinator before the asynchronous
  `work.abort()` landed: the cancel is a request processed on the ABI executor (`abi.rs:518-519`), so between
  the cancel request returning and the abort there is a window in which a released permit can admit the
  work. That code is unchanged by #84, so M has the same window; M simply did not hit it in its 40 counted
  iterations (see the exploratory pass below). #84's own `slice_a_cancel_before_admission_never_enters_native_work`
  passes at its own head (supporting runs), so its fixture does not hit this sub-millisecond window.
  Post-hoc observation: the pre-registered `cancel_race` rule counts an admission winner as PASS; one P main
  race iteration (iter 19) was an admission winner whose waiter had also observed `cancelled`, the same
  phenomenon. The verdict is left as pre-registered.
- **R2.** M: the probe was admitted inside the window and before the owner's native exit 40/40
  (`queued:2 -> admitted:2 -> native-enter:2 -> release:1 -> native-exit:1`). P: 40/40 the probe was admitted
  only after `native-exit:1`. The positive control (no cancel) passes on both arms, so the oracle is not
  always red; the plain-closure control on the #84 tree fails 40/40, so it is not always green.
- **R4.** A late abort of issuance 1 (after completion, or after an in-flight cancel) never reached issuance
  2 (completed ok, dispatch not dropped early, native once). The broken control (cancel registry keyed by
  tool name) aborted issuance 2 every time.
- **R5 (#36 row).** While session A's call was in native work, session B tried: a mutation with
  `session: own09-a` (refused `permission_denied`, "public session substitution does not match the bound
  authorization context", never admitted), `end_session` naming A (refused the same way), an MCP
  `notifications/cancelled` for A's id on another transport (`-32601`), ending itself and closing its handle.
  A completed ok with exactly one effect, 40/40 on both arms. The broken control (cancel keyed by a claimed
  public session) cancelled A every time.
- **R6.** Without a cancel both arms are correct: shutdown returns only after native exit, and `end_session`
  returns `session_cleanup_pending` ("Session is ending after its in-flight action completes") with cleanup
  after native exit. **After a cancel, on both arms:** `shutdown()` returns while native work is still
  running, and `end_session` returns "Session 'own09-end' ended." and the session cleanup hook fires before
  native exit (40/40 each). #84's AdmissionHold keeps only the desktop coordinator; the lifecycle read guard
  and the session dispatch guard still drop with the aborted frame.
- **R7 (#105 row).** Ordinary mutation admitted; ack lost (caller cancelled); first fresh read of the target:
  unchanged (40/40 `first-read:0`); the reconciling caller issues a retry guarded by the target ("only if
  still unchanged", checked at effect time). M: the retry was admitted while the original was stuck and
  both landed (2 effects, 40/40): the unchanged read freed capacity and authorized a second mutation. P: the
  retry waited for the original's native exit, the original landed and the retry was refused (exactly 1
  effect, 40/40). Controls: an unguarded retry duplicates on both arms (the unchanged read is not authority
  even with ownership); the plain closure on the #84 tree duplicates. Characterization: if the target
  commits the effect after native exit, both arms duplicate (40/40): native-exit ownership cannot cover
  late effects; only reconciliation by operation identity can (R2-05).
- **R8.** At SDK/core level a `notifications/cancelled` for an in-flight request, on the same or a foreign
  transport, changed nothing: the in-flight response was delivered and the effect landed (40/40 both arms).
  The control transport that honors the notification by aborting the request future was classified HONORED
  40/40, so the classifier discriminates. **REAL stdio: NOT_RUN.** The stdio binary's registry has only
  platform tools; `register_host_tools` is an embedded-host hook, so no barrier-backed tool is reachable over
  stdio without modifying production, and this lane runs no Driver session. SOURCE (b) shows the direct loop
  drops the notification before dispatch anyway.

## Exploratory (post-hoc, not pre-registered, non-gating)

Added after the R1 FAIL to ask whether the race is #84-specific. Same binaries, same trees, 200 fresh-runtime
iterations per test per arm, `--test-threads=1` (`raw/exploratory/`, receipts in `raw/support-receipts.jsonl`).

| test | M | P |
|---|---|---|
| R1 cancel_while_queued | **3 FAIL** / 200 | 0 FAIL / 200 |
| R1 cancel_race: admission won although the waiter observed `cancelled` | 2 / 200 | 2 / 200 |

Upstream main shows the same violation (a cancelled-while-queued call admitted and entering native work after
its caller had abandoned it and the cancel request had returned). Pooling counted and exploratory runs: M 3/240, P 1/240 for
cancel_while_queued. The race is in `spawn_completion` (unchanged by #84), not in the AdmissionHold. These
numbers do not change any pre-registered verdict: M's R1 stays PASS by rule (no counted FAIL), but that PASS is
not evidence that M is free of the race. Rates are load-dependent and are not a property claim.

## Supporting runs

- **#84's own fixture at its own head** (`566b9c732`, detached worktree, its own base `c3941497a`):
  `cargo test -p cua-driver-sdk --lib cancellation_slice_a -- --include-ignored`: the 4 non-ignored tests
  pass; the `#[ignore]`d `slice_a_rfc_admitted_capacity_is_owned_until_native_exit` fails, as its own doc
  says it must on current main (it runs the plain closure). This matches OWN-09's R2 on both arms.
- **#84 on the moved base:** on the merged P tree, `cargo test -p cua-driver-sdk --lib --no-run` **does not
  compile**: `src/tests/cancellation_slice_a.rs:148` calls `TEST_RUNTIME_LOCK.lock().unwrap()`, but upstream
  main has since changed `TEST_RUNTIME_LOCK` to a tokio mutex. The merge is textually clean; #84 needs a
  rebase of its test file before it can land. OWN-09's integration-test targets do not compile the lib's
  `cfg(test)` modules, so the counted runs are unaffected.

## E1 / E4 accounting

- E1: terminal dispositions for the #9 Linux core rows on this source: R1, R2, R4, R5, R6, R7 measured on
  both arms; R3 BLOCKED (macOS-first held-input oracle); R8 characterized, REAL NOT_RUN with the reason above.
  #36's cancellation cross-session row = R5: PASS on both arms.
- E4 (all arms, all counted iterations): stale-ref dispatches 0 (none possible here); duplicate mutations:
  M `ack_lost_guarded_retry` 40/40 (the CONFIRMED_GAP), P 0/40; the broken and characterization variants
  duplicate by design. Unverified successes: none claimed (the journal is the oracle). Authority from an
  unchanged read: on M it authorized a landed second mutation 40/40; on P, 0/40 for the guarded retry. Blind
  replay: only in the `broken_blind_retry` control. Refusals are refusals: session substitution, foreign
  end and the guarded retry's `effect: refused` entries.
- Work deleted vs wall-clock saved: not applicable; this is a correctness lane with no timing claims and no
  component timings.

## Controls

Discriminating broken controls, each detected 20/20 in both passes on both arms: R1 detach-on-cancel, R2
plain closure (P), R4 name-keyed cancel registry, R5 session-keyed cancel registry, R6 ready-on-cancel, R7
blind retry and plain closure (P), R8 honoring transport. Positive controls (oracle not always red), 20/20 in
both passes: R2 no-cancel, R7 ack received; R6's no-cancel variants also pass on both arms.

Strength of the broken controls: two are harness simulations rather than broken implementations. R6
`broken_ready_on_cancel` logs `shutdown-returned` itself, and R1 `broken_detach_on_cancel` never cancels.
They show that the oracle can go red, but they discriminate weakly. Discrimination for those rows rests
more on the no-cancel positive variants (R6 shutdown/end_session no-cancel, PASS 40/40 on both arms, against
the after-cancel FAILs) and, for R2 and R7, on P's plain-closure controls on the #84 tree (FAIL 40/40). The
remaining broken controls (R4 name-keyed and R5 session-keyed cancel registries, R7 blind retry, R8
honoring transport) are deliberately wrong implementations of the behaviour under test.

## Deviations

1. **Two target dirs.** Cargo gives path packages in different worktrees the same metadata hash, so one
   target dir shared across two source trees silently reused stale `cua-driver-core` artifacts in a
   shakedown. M built into `cua-release-own09-m`, P into `cua-release-own09` (both deleted and rebuilt fresh
   for the counted runs; `raw/logs/build-*.compiled.txt` shows which worktree compiled `cua-driver-core`).
2. **Constructor.** The fixture uses `try_create_configured_for_host` with an explicit Standard-only ceiling
   instead of #84's `try_create_for_host`, because trusted per-session delegation (R5/R6) requires a ceiling.
   It is applied to every row on both arms.
3. **Shakedowns.** Uncounted 2-iteration shakedowns ran on both arms while the harness was developed; they
   are disclosed in PREREG and mirrored outside the packet.
4. **Quiet lane.** Per the lane's RUNNING command, cargo held `flock -s` on the quiet-lane lock directly (not
   `quiet-timed`); no timing is reported.
5. **Verifier edits after PREREG (no decision logic changed):** two git pathspec fixes in
   `verify_artifacts.py` (`git diff 34674f3c3 -- verify_artifacts.py`, 4 lines): the PREREG commit-time lookup
   used a toplevel-relative path under `git -C <packet>` and silently fell back to `written_utc`; the commit
   privacy scan covered only the packet directory and now covers every path of every commit. Verdict
   recomputation, row rules and the disposition rule are byte-identical to the PREREG commit.
6. **Near misses before the hostless rule was applied to them:** at lane start, `python3 -c` (JSON parsing
   of the loop state file) and `cargo/rustc --version` ran on the plain host shell. In the fix round, one
   `python3` heredoc that only rewrote text in `verify_artifacts.py` (no imports beyond the builtins, no
   display, bus or network) also ran on the plain host shell. None touches a display, session bus or
   network; nothing reached the host desktop.
7. **Fix round after the fresh verifier (no new trials, no verdict change).**
   - The cargo logs and build-provenance excerpts were written as `raw/logs/*.log`, which the repository
     `.gitignore` (`*.log`) silently left out of the packet commit, although this README and
     `provenance.json` cite them. They are now written as `raw/logs/*.txt` from the same mirrored sources and
     committed; the other `raw/` files regenerated byte-identical.
   - `verify_artifacts.py` gained two audits that add problems but never change a verdict: a committed-tree
     check (any packet file that is untracked, git-ignored or differs from HEAD is a problem, so the verifier
     no longer passes on files that exist only on disk), and a presence audit (a recorded R1, R2 or R7 PASS
     whose ordering check relies on a later event, `admitted:3` for the R1 witness, `admitted:2` for the R2
     probe and the R7 retry, must contain that event, because `Ledger.before(a, b)` is true when `b` is
     absent). No counted iteration relied on an absent event. Verdict recomputation, row rules and the
     disposition rule are still byte-identical to the PREREG commit.
   - The environment description now describes hostless v2 accurately (it previously said bwrap, which was
     v1), the P R2/R7 PASS claims are qualified to tools that adopt `spawn_blocking_owned`, the R1 wording
     states what the fixture actually observes, and the strength of the broken controls is stated (Controls).

## What a revision needs (non-binding, from the evidence)

1. Make cancellation authoritative before admission: once the cancel request has returned to the caller, the
   queued work must not be admitted (check the operation's cancel state after taking the permit, or abort
   before answering the caller).
2. Own the lifecycle read guard and the session dispatch guard until native exit, like the desktop permit,
   so shutdown and `end_session` cannot report readiness early (or report `cleanup_pending` after a cancel).
3. Adopt `spawn_blocking_owned` (or equivalent) in the production Linux tools; today nothing calls it.
4. Keep reconciliation (#105) as the only answer to effects that land after native exit.

## Limits and claim boundary

SDK/core runtime ownership on Linux at the exact SHAs above, through an in-process barrier tool on the
production dispatch route. Not MCP-transport cooperative cancellation (R8 is not REAL); not held-input
(R3 BLOCKED); nothing for macOS or Windows; no claim about production Linux tools adopting
`spawn_blocking_owned`; no timing. R1's FAIL is a scheduling race observed under concurrent machine load;
its rate is not a property claim.

## Files

- `PREREG.json`: rows, variants, controls, gates, disposition rule, predictions (committed before the first
  counted run).
- `raw/main/{M,P}/*.jsonl`, `raw/stress/{M,P}/*.jsonl`: one line per iteration (events, counters, journal,
  checks, verdict). `raw/receipts.jsonl`: UTC window, command hash, rc, pass/fail counts per run.
- `raw/exploratory/`, `raw/support-receipts.jsonl`: exploratory and supporting runs.
- `raw/logs/*.txt` (sanitized; `.txt` because the repository ignores `*.log`): counted cargo test output
  (`main-{m,p}.txt`, `stress-{m,p}.txt`), build provenance (`build-{m,p}.compiled.txt`: the `Compiling` lines
  naming the source worktree of each crate; `build-{m,p}.provenance.txt`: the rustc invocations for the core,
  SDK and test crates), supporting runs (`support-*.txt`).
- `summary.json`: matrix, row status, disposition (written by `verify_artifacts.py --write-summary`).
- `provenance.json`: SHAs, trees, binaries, environment, commands.
- `verify_artifacts.py`: recomputes every iteration verdict from raw events, the matrix, row status and
  disposition; checks PREREG order, tested trees and test-file blobs; fails if a packet file is untracked,
  ignored or differs from HEAD, or if a recorded PASS relies on an absent later event; scans the packet (and,
  with `--git-range`, every branch commit) for absolute paths, the host name and secret patterns.

Test sources: `libs/cua-driver/rust/crates/cua-driver-sdk/tests/own09_arm_m.rs`, `own09_arm_p.rs`,
`own09_harness/mod.rs`, `own09_harness/rows.rs`. No production code is changed by this lane.
