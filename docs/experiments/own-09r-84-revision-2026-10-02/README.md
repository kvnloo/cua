# OWN-09R: a revision of kvnloo/cua#84 for the kvnloo/cua#9 Linux rows

**Disposition: KEEP** for "revised #84 answers the #9 Linux rows", under the pre-registered rule
(`PREREG.json`, recomputed by `verify_artifacts.py`). This is a candidate revision on a fork branch. It does
not modify #84 or its PR.

On the revision (P'), every gating row passes with 0 failures: R1, R2, R4, R6 and R7, and the R5 (#36)
regression row holds. 2,940 counted iterations, 0 harness errors. On upstream main (M), the same harness
reproduces the gaps: R1 (deterministic admission window) 40/40 FAIL, R2 40/40 FAIL, R6 80/80 FAIL and R7
40/40 FAIL. The cua-driver-core, cua-driver-sdk and cua-driver unit suites are green on P'.

- R3 is BLOCKED: it needs a macOS drag/mouse-up oracle.
- R8 is an **OWNER_DECISION** and is not implemented. The exact question is below. The previously NOT_RUN
  REAL stdio row now runs: both arms IGNORE `notifications/cancelled` sent while native work is in flight,
  40/40 each. The effect lands exactly once and the response is delivered.

Owners: kvnloo/cua#9 (upstream owner: trycua/cua 3796), kvnloo/cua#84 (read only), kvnloo/cua#36 (R5),
kvnloo/cua#105 / R2-05 (R7), kvnloo/cua#73 (packet requirements).

## Provenance (each SHA separate)

| what | SHA |
|---|---|
| base, upstream main (arm M production code) | `989cc76cec262ff8bcf6968b637820340fb9caaa` |
| kvnloo/cua#84 head, read live with gh at start and at end (OPEN, draft) | `566b9c73245266005c958d40e93d46ee5d463325` |
| `--no-ff` merge of #84 into the base | `065ee203b` |
| (1) rebase fix | `aacc7beb6` |
| (2) authoritative cancel before admission | `6024e3e7f` |
| (3) lifecycle and session guards owned until native exit | `890c41d1a` |
| (4) production native work through `spawn_blocking_owned` | `965762041` |
| OWN-09 harness copied byte for byte from `bf07c8fe3` (adds test files only) | `26e97138c` |
| PREREG commit (before the first counted run); P' tested at this tree | `b623d0470` |
| publication SHA | the commit that adds this README (not self-referential) |

- `libs/cua-driver/rust` tree at `26e97138c` and at `b623d0470`: `0748c94e`. From `965762041` to `26e97138c`
  only the three harness test files were added.
- Arm M is `989cc76ce` plus test-only files (`raw/m-tree.patch`): the OWN-09 arm-M harness, `own09r_cabi.rs`
  (blob identical to the branch) and its `cfg(test)` mount line.
- Driver binaries (built for R8 with `build-driver.sh`, under hostless and the cargo lock, recompiled from each
  worktree with 0 Fresh units):
  - M: `own09r-m-989cc76ce`, sha256 `aeb92723…e8fe00`, `cua-driver 0.32.0`.
  - P': `own09r-p-26e97138c`, sha256 `df55093c…ca30ea2c`, `cua-driver 0.32.0`.
- Test binaries were frozen before the first counted run. Full hashes are in `provenance.json`.
- Environment: Linux 7.2.2 x86_64, rustc 1.97.1.
  - Every code-executing command ran under `hostless`. R8 also ran inside `cua-x11-session.sh` (private
    Xvfb, D-Bus and AT-SPI bus) with telemetry off.
  - Every counted invocation held the exclusive quiet-lane lock through `quiet-timed`
    (`raw/quiet-lane-receipts.jsonl`, 14 receipts).
  - No provider was used: TypeSafe attempts 0, reached 0. No timing claims are made.
- Live heads vs tested source vs publication:
  - #84 head was `566b9c732` at start and at end.
  - The local upstream main ref moved one commit, to `da46c4bc8`, which touches no `libs/cua-driver` path.
    `merge-tree` with the branch is clean.
  - The packet is published only on this lane branch. There was no push and no GitHub write.

## STEP 0: SOURCE (revision head; `libs/cua-driver/rust/crates/`)

The OWN-09 packet (`bf07c8fe3`) listed what a revision needed. Each item maps to one commit:

1. **Rebase (aacc7beb6).** Upstream changed `TEST_RUNTIME_LOCK` to a tokio mutex, so #84's
   `cua-driver-sdk/src/tests/cancellation_slice_a.rs:148` `.lock().unwrap()` failed to compile on the merged
   tree with E0599 (`raw/logs/support/c1-red-sdk-lib-no-run.txt`). `Fixture::new` is now async. Green: the
   four non-ignored slice A tests pass.
2. **Authoritative cancel before admission (6024e3e7f).**
   - `cua_driver_operation_cancel_v1` only sets the operation's flag. `spawn_completion` then answers
     `Cancelled` and calls `work.abort()`, which lands asynchronously. In that window a queued call could
     still win the permit and enter native work.
   - `OperationState.cancelled` is now an `Arc<AtomicBool>` (`cua-driver-sdk/src/abi.rs:112`), and the work
     future runs inside `cua_driver_core::tool::with_caller_cancellation` (`abi.rs:508`, `tool.rs:143`).
   - Dispatch checks the flag at the admission point, after the lifecycle, session and desktop-permit waits
     and before `Tool::invoke` (`tool.rs:1833`). If it is set, dispatch returns a `cancelled_before_admission`
     refusal (`status: refused`), exactly as if the abort had landed during the wait.
   - Callers without a flag (the stdio loop, other hosts) are unchanged.
3. **Guards owned until native exit (890c41d1a).**
   - `AdmissionHold` now wraps any existing RAII guard in an `Arc<dyn Any + Send + Sync>` (`tool.rs:89`).
   - Dispatch wraps the session dispatch guard (`tool.rs:1774`) and the desktop permit. The SDK runtime wraps
     its lifecycle read guard: `lifecycle` became an `Arc<RwLock>` and takes an owned read guard
     (`runtime.rs:167,312`).
   - `with_admission_holds` (`tool.rs:107`) scopes the guards for the invocation (`tool.rs:1884`, SDK
     `runtime.rs:333`), and `spawn_blocking_owned` moves clones of all of them into the native closure.
   - The frame still drops its own references at the original points (`tool.rs:1901,1946`), so release order
     on the normal path is unchanged.
   - There is no registry and no new service. The guards are the existing values.
4. **Production native work through `spawn_blocking_owned` (965762041).**
   - `spawn_blocking_owned` (`tool.rs:120`) is now a drop-in for `tokio::task::spawn_blocking`: it returns the
     same `JoinHandle`. Outside a dispatch scope there are no holds and it behaves exactly like
     `spawn_blocking`.
   - Every production `tokio::task::spawn_blocking` on the Linux tool paths was converted, **172 call sites**.
     The full list with file, line, function and shape is in `converted_callers.json`, produced by
     `tools/convert_spawn_blocking.py --check`, which reports 0 unconverted sites.

     | file | sites |
     |---|---|
     | `platform-linux/src/tools/impl_.rs` | 133 |
     | `platform-linux/src/tools/page.rs` | 2 |
     | `platform-linux/src/browser_platform.rs` | 18 |
     | `platform-linux/src/browser_consent_ui.rs` | 3 |
     | `platform-linux/src/health_report.rs` | 8 |
     | `platform-linux/src/atspi/native.rs` | 2 |
     | `cua-driver-core/src/window_target.rs` | 3 |
     | `cua-driver-core/src/clipboard.rs` | 2 |
     | `cua-driver-core/src/recording_tools.rs` | 1 |

   - 163 sites are awaited in place. 4 are the inner future of a `timeout(budget, ..).await` budget helper:
     `bounded_blocking`, `spawn_blocking_bounded` and two element-AX budgets. 5 bind the handle and await or
     join it later in the same tool call: the isolated Hyprland dispatch at `impl_.rs:4433` and the drag paths
     at 10438, 10773, 10788 and 10843. Each of those 5 was reviewed by hand.
   - Precedent already in production: the isolated Hyprland path moved its session dispatch guard into its
     blocking closure by hand (`impl_.rs:4413-4435`).
5. **R8 (`notifications/cancelled`): not implemented, OWNER_DECISION.**
   - The direct stdio loop reads one line and awaits each request inline before reading the next.
     `cua-driver/src/proxy.rs:94` drops every notification before dispatch.
   - The opt-in envelope transport has a typed `cua/driver/v1/cancel`. Its own source records the contract
     decision for plain notifications: "notifications retain the legacy behavior; no cancellation is
     invented" (`cua-driver/src/mcp_envelope.rs:214`).
   - Wiring the plain notification into the same cancellation path needs two contract decisions: concurrent
     stdin reads, and a response contract for the cancelled id. **Owner question:** should the direct stdio
     MCP loop honor `notifications/cancelled` for an in-flight `tools/call`? That would route it into the C ABI
     cancellation path (cancel flag plus abort; owned native work runs to exit; a possibly landed effect stays
     unknown). It requires (a) reading stdin concurrently with an in-flight request, and (b) choosing between
     suppressing the response (MCP's recommendation) and answering with `execution_state=unknown`. The
     alternative is that plain MCP keeps ignoring the notification and cancellation stays envelope-only.

## Method (the five #73 mechanism requirements)

- **Forced path.**
  - SDK rows: a barrier-backed host tool is registered under the physical-desktop name `press_key` through
    `register_host_tools`. Calls take the production route: `call_tool` -> `cua_driver_invoke_v1` ->
    `spawn_completion` -> `DriverRuntime::invoke` (lifecycle hold) -> dispatch (session hold, desktop permit,
    admission point) -> `Tool::invoke` -> native closure. Session rows use trusted sessions.
  - C ABI rows (`own09r_cabi.rs`): the host calls the exported `cua_driver_invoke_v1`,
    `cua_driver_operation_cancel_v1` and `cua_driver_operation_release_v1` with raw tokens it retains, as a C,
    Python or TypeScript embedder does.
  - R8 stdio: the built `cua-driver mcp`, driven with raw JSON-RPC lines, runs production `set_value`
    (AT-SPI `SetTextContents`) on the GTK3 task fixture's Note entry.
- **Actual route and producer.**
  - SDK: cancel aborts the caller task -> `OperationGuard::drop` -> `cua_driver_operation_cancel_v1` ->
    `work.abort()`. The barrier's `invocation-dropped` event proves that the abort reached the dispatch frame.
  - R1D: the queued operation's cancel flag is set while the abort is withheld, which is the exact state
    between the cancel returning and the abort landing. P' records `cancelled_before_admission` in 40/40
    callbacks.
  - R8: the fixture journals `effect-enter` from inside the D-Bus `SetTextContents` handler, and the
    notification is written after that line (phase audited per trial). The response arrives a median of
    3.1 ms (M) and 3.3 ms (P') after `effect-applied`, so the Driver's native call was blocked by the fixture
    barrier.
- **Independent target-owned oracle.**
  - SDK and C ABI: fixture-owned native entry/exit counters, a target journal written only by the native
    closure, and an ordered ledger. C ABI rows add a journal written by the C completion callback.
  - R8: the fixture process's own JSONL effect journal. Driver receipts are never the oracle.
- **Negative and fallback cases.**
  - Every no-cancel variant passes on both arms: R1D control, R2 control, R6 no-cancel, R7 ack, and R8 stdio
    control (10/10 each arm).
  - Every broken control is detected on both arms; see Controls.
  - M reproduces every gap the revision targets, so the oracle discriminates.
- **Exact provenance.** See above. Commands are in `run_rows.sh`, and receipts are in `raw/receipts.jsonl` and
  `raw/quiet-lane-receipts.jsonl`.
- **n and order.**
  - SDK rows: 20 iterations per variant per pass; R1's two gating variants 100 per pass. There was a main pass
    (`--test-threads=1`) and a stress pass (8).
  - C ABI rows: 40 per variant. R8 stdio: 40 plus 10 control per arm. Every iteration used a fresh runtime,
    or a fresh Driver process and fixture.
  - Order: SDK main M, P'; SDK stress M, P'; C ABI M, P'; R8 M, P'. PREREG was committed at 19:00:38Z. Counted
    lock windows ran from 19:18Z to 20:30Z.

## Results (counted; M vs P'; N of N)

| row | variant (route) | evidence | M | P' |
|---|---|---|---|---|
| R1 | cancel_while_queued (SDK) | FIXTURE | 200/200 PASS | 200/200 PASS |
| R1 | cancel_race (SDK) | FIXTURE | 200/200 PASS | 200/200 PASS |
| R1 | **R1D flag_before_admission (C ABI)** | FIXTURE (real C ABI) | **40/40 FAIL** | 40/40 PASS |
| R1 | R1D control_no_cancel (C ABI) | FIXTURE | 40/40 PASS | 40/40 PASS |
| R1 | broken_detach_on_cancel (control) | FIXTURE | 40/40 FAIL | 40/40 FAIL |
| R2 | cancel_after_admission | FIXTURE | **40/40 FAIL** | 40/40 PASS |
| R2 | control_no_cancel | FIXTURE | 40/40 PASS | 40/40 PASS |
| R2 | broken_plain_closure (P' control) | FIXTURE | – | 40/40 FAIL |
| R4 | after_completion (SDK) | FIXTURE | 40/40 PASS | 40/40 PASS |
| R4 | after_inflight_cancel (SDK) | FIXTURE | 40/40 PASS | 40/40 PASS |
| R4 | broken_name_keyed (control) | FIXTURE | 40/40 FAIL | 40/40 FAIL |
| R4 | **R4C after_completion_retained_token (C ABI)** | REAL C ABI + FIXTURE oracle | 40/40 PASS | 40/40 PASS |
| R4 | **R4C after_inflight_cancel_retained_token (C ABI)** | REAL C ABI + FIXTURE oracle | 40/40 PASS | 40/40 PASS |
| R4 | R4C broken_latest_token (control) | REAL C ABI | 40/40 FAIL | 40/40 FAIL |
| R5 | foreign_session_and_transport (#36) | FIXTURE | 40/40 PASS | 40/40 PASS |
| R5 | broken_session_keyed (control) | FIXTURE | 40/40 FAIL | 40/40 FAIL |
| R6 | shutdown_after_cancel | FIXTURE | **40/40 FAIL** | 40/40 PASS |
| R6 | end_session_after_cancel | FIXTURE | **40/40 FAIL** | 40/40 PASS |
| R6 | shutdown_no_cancel / end_session_no_cancel | FIXTURE | 40/40 + 40/40 PASS | 40/40 + 40/40 PASS |
| R6 | broken_ready_on_cancel (control, weak) | FIXTURE | 40/40 FAIL | 40/40 FAIL |
| R6 | broken_plain_closure_shutdown_after_cancel (P' control) | FIXTURE | – | 40/40 FAIL |
| R7 | ack_lost_guarded_retry (#105) | FIXTURE | **40/40 FAIL** (2 effects) | 40/40 PASS (1 effect) |
| R7 | control_ack | FIXTURE | 40/40 PASS | 40/40 PASS |
| R7 | broken_blind_retry / broken_plain_closure (P') | FIXTURE | 40/40 FAIL | 40/40 + 40/40 FAIL |
| R7 | delayed_after_native_exit (characterization) | FIXTURE | 40/40 FAIL | 40/40 FAIL |
| R8 | notification_in_flight (SDK core dispatcher) | FIXTURE | 40/40 IGNORED | 40/40 IGNORED |
| R8 | broken_honoring_transport (control) | FIXTURE | 40/40 HONORED | 40/40 HONORED |
| R8 | **notification_mid_native (stdio)** | **REAL** | **40/40 IGNORED** | **40/40 IGNORED** |
| R8 | control_no_cancel (stdio) | REAL | 10/10 PASS | 10/10 PASS |
| R3 | held-input cleanup exactly once | BLOCKED | BLOCKED | BLOCKED |

Pass splits are in `summary.json` (`matrix_by_pass`). Main and stress agree on every variant.

**Row status (pre-registered rules):**

| row | evidence | M | P' |
|---|---|---|---|
| R1 queued cancel never admitted | FIXTURE (SDK) + real C ABI | FAIL (R1D 40/40) | **PASS** |
| R2 capacity owned until native exit | FIXTURE | FAIL = gap reproduced | **PASS** |
| R3 held-input cleanup | BLOCKED (macOS oracle) | BLOCKED | BLOCKED |
| R4 late cancel never reaches a later issuance | FIXTURE + REAL C ABI | PASS | **PASS** |
| R5 foreign session/transport cannot cancel (#36) | FIXTURE | PASS | **PASS** (regression holds) |
| R6 no readiness before native exit | FIXTURE | FAIL = gap reproduced | **PASS** |
| R7 unchanged read is not authority (#105) | FIXTURE | FAIL = gap reproduced | **PASS** |
| R8 `notifications/cancelled` | REAL (stdio) + FIXTURE | IGNORED | OWNER_DECISION (IGNORED, not implemented) |
| Unit gate (core, sdk, cua-driver) | UNIT | – | green: 841 + 109 + 387 passed, 0 failed |

### Row notes

- **R1, and OWN-09's caveat restated.** OWN-09's M R1 PASS was a PASS by rule only: 0 FAIL in 40 counted
  iterations, but 3/200 exploratory. It was never evidence that main is free of the race.
  - This run had lower machine load. The SDK route did not hit the race on either arm: cancel_while_queued
    0/200 on both. cancel_race had 200/200 cancel winners on both arms, and none of OWN-09's "admission winner
    whose waiter saw cancelled" cases. So the SDK R1 rows here are **not discriminating**, and a 0/200 is a
    rate bound, not proof.
  - The discriminating evidence is R1D, which makes the window deterministic through the real C ABI. On M the
    flagged queued call was admitted, entered native work and landed its effect 40/40, and the callback
    reported a success. On P' it was refused with `cancelled_before_admission` 40/40, with no native entry and
    no effect, and the witness was admitted after the holder's exit.
  - Unit red/green for the same check: `raw/logs/support/c2-red-unit.txt` (check disabled: admitted, native
    entered, effect landed) and `c2-green-unit.txt`.
- **R2.** M: the probe was admitted before the cancelled owner's native exit, 40/40. P': the probe was admitted
  only after `native-exit:1`, 40/40. The P' plain-closure control fails 40/40, so the PASS comes from the
  production primitive and not from the harness.
- **R4.** The SDK rows are unchanged from OWN-09. R4C is new and REAL through the C ABI.
  - The host keeps the early operation's raw token (completed, or already cancelled in flight, but not yet
    released) and calls `cua_driver_operation_cancel_v1` on it while a later operation is in native work.
  - The later operation completed `Ok` exactly once, with its dispatch frame intact and one native entry and
    one effect. The early operation's callback fired exactly once, and the late cancel produced no second
    callback.
  - The broken host registry that resolves the cancel to the latest token cancelled the later operation 40/40.
- **R5.** Session substitution, foreign `end_session`, a foreign-transport MCP `notifications/cancelled`, and
  the foreign session ending itself left A's call untouched, with exactly A's single effect, 40/40 on both
  arms.
- **R6.** P': after a cancel, `shutdown()` returned only after the cancelled call's native exit. `end_session`
  answered "Session is ending after its in-flight action completes; retry end_session for final cleanup
  status." On M it answered "Session 'own09-end' ended.", 40/40. The session cleanup hook fired after native
  exit on P', 40/40 each. Unit red/green: `c3-red-unit.txt` (lifecycle hold removed: shutdown returned while native work
  ran) and `c3-green-unit.txt`.
- **R7.** P': after the lost ack and an unchanged first read, the guarded retry waited for the original's
  native exit. The original landed and the retry was refused, exactly 1 effect, 40/40. M landed 2 effects
  40/40. The characterization variant (the effect commits after native exit) still duplicates on both arms.
  Native-exit ownership cannot cover late effects; only reconciliation by operation identity can (#105).
- **R8 REAL stdio.** For each trial: a fresh fixture and Driver; `set_value` blocks inside the fixture's GTK
  handler; `notifications/cancelled {requestId}` is written to stdin after `effect-enter` is journaled; after a
  300 ms window the barrier opens.
  - No response arrived inside the window (0/40 each arm). The effect landed exactly once and a success
    response followed (40/40 each arm).
  - A later `tools/list` was answered, and no stray or error message was emitted for the notification (0/50
    each arm). Duplicates: 0.
  - This matches SOURCE: the strictly serial loop reads the notification only after the response and then
    drops it at `proxy.rs:94`.

## Controls

- **Discriminating (broken implementations), detected on both arms:** R4 name-keyed cancel registry, R4C
  latest-token registry, R5 session-keyed registry, R7 blind retry, and R8 honoring transport. On P' also the
  plain-closure controls for R2, R6 and R7. R1 detach-on-cancel and R6 ready-on-cancel are harness simulations
  and discriminate weakly. For those rows the discrimination rests on R1D and on the no-cancel variants.
- **Negative (no cancel), 0 failures on both arms:** R1D control 40, R2 control 40, R6 no-cancel 80, R7 ack 40,
  and R8 stdio control 10.
- **M reproduces the gaps:** R1D 40/40, R2 40/40, R6 80/80 and R7 40/40 FAIL.

## E1 / E4 accounting

- **E1.** Terminal dispositions for the #9 Linux rows at this source:
  - R1, R2, R4, R5, R6 and R7: measured on both arms, all PASS on P'.
  - R3: BLOCKED (macOS held-input oracle).
  - R8: OWNER_DECISION, with REAL stdio now measured (IGNORED on both arms).
  - The #36 cancellation cross-session row (R5) holds.
- **E4 (every arm, every counted iteration):**
  - Duplicate mutations: on P' 0 outside the characterization and broken variants. On M,
    ack_lost_guarded_retry duplicated 40/40, which is the reproduced gap.
  - Blind replay: only in the broken_blind_retry control.
  - Authority from an unchanged read: on P', 0/40 for the guarded retry. On M it authorized a landed second
    mutation 40/40.
  - Refusals stay refusals: P' `cancelled_before_admission` is a `status: refused` result with no effect. The
    R7 guarded retry records `effect: refused`.
  - Stale-ref dispatches: 0. Unverified successes: none claimed.
- **Work deleted vs wall-clock saved:** not applicable. This is a correctness lane with no timing claims and no
  component timings.

## Behaviour changes (deliberate, part of the fix)

- A cancelled call keeps the desktop permit, the session in-flight count and the SDK lifecycle read guard until
  its owned native work exits. A later physical action waits for that work, `end_session` reports cleanup
  pending, and `shutdown` waits.
- When a budget helper (`spawn_blocking_bounded`, `bounded_blocking`, the element-AX budgets) times out, the
  tool still returns its timeout error at once. The wedged closure keeps those guards until it exits, so the
  next physical action queues behind it instead of overlapping a possibly landed effect.
- A queued call whose cancellation was requested returns `cancelled_before_admission` instead of running.
  Callers already saw `Cancelled` in this case; only the never-observed work result changes.

## Deviations

1. **Harness labels.** The SDK harness was copied byte for byte, so its raw lines say `"lane": "OWN-09"`, and the
   P' raw directory is named `P`.
2. **C ABI rows** use a plain `spawn_blocking` barrier on both arms. They test operation identity and the
   admission point, not ownership after abort (R2, R6 and R7 test that).
3. **Arm M test files are not committed.** They are recorded as `raw/m-tree.patch`. The C ABI file blob equals
   the branch blob.
4. **Unit suites ran on the revision code tree `965762041`** before the harness commit and before PREREG. The
   Driver and SDK source is identical to the tested tree (`raw/unit/`). They are not trials. A confirmation
   run at the branch head is under Supporting runs.
5. **rustfmt reflow** of the touched lines, and of the revision's earlier files, is folded into commit (4).
6. **First launch of the counted runs** failed at argument parsing before anything ran: zsh did not
   word-split the loop variable. It wrote no receipt and no data and was relaunched under bash.
7. **Receipts' `utc_start`** includes the wait for the shared quiet-lane lock. Acquisition times are in
   `raw/quiet-lane-receipts.jsonl`.
8. **Shakedowns (uncounted, disclosed in PREREG, mirrored outside the packet):** a 2-iteration C ABI run on P',
   2 R8 stdio trials on M (notification), and 2 R8 stdio trials on P' (control).
9. **Logs sanitized.** `raw/logs/*.txt` and `raw/unit/*.txt` had local paths replaced (`<lanes>`,
   `<cargo-targets>`, `<tmp>`). The unsanitized originals are mirrored outside the packet.
10. **Near misses:** none. Every code-executing command, including Python text edits, rustfmt and the
    builds, ran under hostless. Nothing reached the host desktop.

## Next

- **Owner:** answer the R8 question above. If yes, implement concurrent stdin reading plus the chosen response
  contract in `proxy.rs` on top of the `with_caller_cancellation` path, then re-run R8 REAL as a gating row.
- `type_text`'s per-pid text-input admission (`tool.rs` `TextInputAdmission`) is the same class of capacity
  guard. It is still released with an aborted frame by design ("RAII releases it on task cancellation"). Decide
  whether to make it a hold too.
- macOS and Windows tools still use plain `spawn_blocking` (95 sites on Windows, plus macOS). They were not
  converted or measured here because they are outside the claim boundary.
- R7 late-commit effects remain the domain of reconciliation by operation identity (#105 / R2-05).
- R3 needs a macOS held-input oracle.

## Limits and claim boundary

Linux, at the exact SHAs above. The routes are the embedded SDK (barrier tool on the production dispatch
route), the exported C ABI, and the stdio Driver binary for R8, on base `989cc76ce`.

- Production tools were converted mechanically. Under cancellation they were exercised only through the shared
  primitive: the barrier tool calls the same `spawn_blocking_owned`, and R8 runs `set_value` without a cancel
  reaching it. No production Linux tool was aborted mid native work against a desktop oracle.
- The SDK R1 rows did not discriminate in this run; R1 rests on R1D.
- No macOS or Windows claims, and no timing claims.
- This is a candidate revision on a fork branch. It does not modify #84.

## Supporting runs

- Red/green unit evidence per commit: `raw/logs/support/c1-*`, `c2-*`, `c3-*` and `c4-red-convert-check.txt`.
- Head confirmation of the unit suites at the PREREG commit `b623d0470`, run after the counted runs
  (`raw/unit/head/`):
  - cua-driver-core: 841 passed, 0 failed.
  - cua-driver-sdk: 133 passed, 0 failed. That is the 109 lib/doc tests plus the 24 `own09_arm_p` harness row
    tests, which fail only on harness errors.
  - cua-driver: 387 passed, 0 failed.

## Files

- `PREREG.json`: rows, n, gating, controls, disposition rule and predictions. Committed before the first
  counted run.
- `run_rows.sh`: the counted invocations (hostless + quiet-timed, receipts).
- `raw/sdk/{main,stress}/{M,P}/*.jsonl`, `raw/cabi/{M,P}/*.jsonl`, `raw/r8_stdio/{M,P}/*.jsonl`: one line per
  iteration (events, counters, journal, callbacks or fixture journal, checks, verdict).
- `raw/receipts.jsonl`, `raw/quiet-lane-receipts.jsonl`, `raw/logs/` (counted output and support logs),
  `raw/unit/` (unit logs and summary), `raw/m-tree.patch`.
- `r8/r8_stdio.py`, `r8/fixture_barrier.py`: the REAL stdio harness and the barrier fixture (test-fixture code
  only).
- `tools/convert_spawn_blocking.py`, `converted_callers.json`: the conversion rule and the list of every
  converted production caller.
- `summary.json`: the matrix, row status, controls and disposition, written by
  `verify_artifacts.py --write-summary`.
- `provenance.json`: SHAs, trees, binaries, environment and commands.
- `verify_artifacts.py` (stdlib):
  - recomputes every verdict from raw data and audits vacuous PASSes and R8 phase;
  - rebuilds the matrix, row status and disposition from PREREG and compares them with `summary.json`;
  - checks PREREG order, the harness blobs against `bf07c8fe3`, the cited commits, and the committed tree;
  - scans the packet, and with `--git-range` every commit, for absolute paths, the host name and secrets.
