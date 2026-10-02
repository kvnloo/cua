# OWN-105: runner reconciliation for possibly landed completions, 2026-10-02

## Result in one paragraph

The three runner gaps R2-05 found in the kvnloo/cua#105 jev-use runners are closed in **both** Python and TypeScript with caller-side runner code and no new service, and the result holds on the **real MCP stdio transport**. The setup was a real Driver (0.31.0, sha256 `e57bb9ae…`), real Chrome 151, a private Xvfb session and an owned fixture whose target journal is the oracle. Across 148 fixed-runner trials (Python 12 and TypeScript 8 per main row R0–R6, plus 4 + 4 in an added pre-write negative control), the results were:
- **fixed duplicates 0 in 148 fixed trials**;
- **fixed receipts ok 148/148**;
- **landed effects classified as failure 0**;
- **R5 second dispatches 0 in 20** (the re-planned completion was blocked 20/20);
- **R6 exactly one reconsideration 20/20**, with R6n reconsiderations 0 in 8;
- every fixed trial matched its pre-registered row prediction (148/148) and fault placement held 148/148.

The unfixed base runner reproduced its gap in **20/20** control trials. G1: no reconciliation in R1 and R3, 10/10. G3: an uncaught `DriverToolError` with no receipt in R4, 5/5. G2: a second Submit dispatch in R5, 5/5, each of which became a duplicate mutation (unfixed duplicates 5). TypeScript on a real transport, NOT_RUN in R2-05, is now REAL. The unit suites go red at the tests commit and green at the fix commit (Python 259 run, 1 skipped, OK; TypeScript 165/165; typecheck and the 4 CLI verifiers rc 0). The CI E2E `verify_setup.py` steps also pass at the fix head (4/4).

Disposition by the pre-registered gates: **KEEP**. Uncertainty (exact 95% Clopper-Pearson): fixed duplicate-trial rate 95% CI 0.000–0.025; R5 second-dispatch trial rate 0.000–0.168. Three boundaries apply. The faults are injected in process. This is not exactly-once delivery. In TypeScript a realistic connection loss refuses the request *before* the write ledger sees it, so it is conservatively not reconsidered (R6n).

## Scope and owners

- Owner row kvnloo/cua#105 (recovery). It follows up R2-05 (kvnloo/cua#93; packet branch `exp/r2-05-ack-loss-real-20261001`, commit `236e37e01792d4e60ee5334f702b47e6f122921e`), whose Findings 4 and 5 named the three runner gaps closed here.
- kvnloo/cua#9: lifetime boundary only. The fix's unresolved-completion state (`pending`) lives inside one `run()` call and dies with it. It is never written to disk and never carried into a later run as authority. Cancellation (`CancelledError`, `KeyboardInterrupt`) is not caught and ends a run without a receipt; that and native lifetime stay with #9, **not tested**.
- kvnloo/cua#38 (upstream trycua/cua 4009): vocabulary. The receipt fields below (`resolution`, the `effect`/`verification`/`retryDisposition` values) are caller-side fields of the jev-use example runners. They are **not** proposed as public Driver fields.
- No Driver code change, no new service, no shadow state or registry, no retry policy. The provider is the mock provider (0 TypeSafe requests). No GitHub writes and no pushes from this lane.

## What changed (commit `27386f3e3`, tests in `feadb1965`)

Both runners (`libs/cua-driver/examples/jev-use/python/run.py`, `typescript/run.ts`) get the same minimal changes:

| Gap (R2-05) | Change |
|---|---|
| G1: on an ambiguous action error the runner stopped at `unknown` without reconciling | `finish()` → `reconcile()`: fresh reads of the task's own target oracle every 0.1 s up to a 3 s deadline (the R2-06 bounded re-read). The result is `verified`, `refuted` or `unresolved_unknown`. It never dispatches, so a negative read cannot authorize a replay |
| G2: after a completion whose effect was not visible in the 20 × 0.1 s window, the loop could re-plan and dispatch the completion again | The dispatched completion's receipt stays `pending`. If a completion candidate is chosen while it is pending, nothing is dispatched; the run ends with reconciliation and a receipt (`phase: completion_blocked`) |
| G3: a read failure after an unverified completion escaped as an uncaught `DriverToolError` | `run()` catches any `Exception` from an attempt while a receipt is pending and ends with reconciliation and the receipt (`phase: observe`, `error: <class>`) |
| Pre-write rule (R2-05 Finding 3) | A caller-side write ledger on the transport write (`WriteLedger` around the session write stream in Python; `recordToolCallWrites` around `StdioClientTransport.send` in TypeScript) records whether the `tools/call` request was handed over. Only when that write itself raised (`anyio.ClosedResourceError`/`BrokenResourceError`; a rejected stdio `send`) is the mutation reported `pre_write_failed` and reconsidered, once, from a fresh session. A call that never reached the ledger proves nothing, and an error after the write (for example the mcp 1.30.0 `list_tools` refresh) is reconciled instead |

Every dispatched completion now ends with a content-free `mutation_outcome` receipt, including the ordinary verified path. `verify_setup.py` accepts it on the verified outcome (a receipt with any other resolution is rejected; a log without one is still accepted). Diff (`git diff --numstat 98a45e6c5 27386f3e3`): `run.py` +194/−48, `run.ts` +171/−28, `verify_setup.py` +4/−1.

Receipt values (caller-side, `receiptKind: mutation-outcome/v0` plus `resolution`):

| resolution | attempted | effect | verification | retryDisposition |
|---|---|---|---|---|
| `verified` | true | applied | verified | none |
| `refuted` | true | unknown | refuted | none |
| `unresolved_unknown` | true | unknown | unverified | observe |
| `pre_write_failed` | false | none | unverified | reconsider (first time) / none |

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Unfixed base (control arm) | `98a45e6c528da9e2715288c20c2a0feeeef8e73f` (kvnloo/cua#105 head; parent `ec83a3a8…`); unfixed `python/run.py` sha256 `e22fa246…` |
| Tests commit (red) | `feadb19659b5711589b08efaaa8e2fe0cea42420` |
| Fix commit (green, tested runner code) | `27386f3e34540e22218b704705e5238ef1316e85`; fixed `run.py` sha256 `dfc0352d…`, `run.ts` sha256 `f21ece75…` |
| Measured tree | PREREG commit `b91bf93990a7a1447aedddda170970a41771de49` (jev-use tree identical to `27386f3e3`; every block recorded `worktree_head` and a clean jev-use status) |
| Live PR heads (gh, read-only) | kvnloo/cua#105 `98a45e6c5…` OPEN draft, read at lane start and at 2026-10-02T03:07Z (unchanged); trycua/cua PR 4316 `a0bca744067d04f05904319d3d919be30c336556` OPEN |
| Driver source | `a0bca744067d04f05904319d3d919be30c336556`; `git diff --quiet a0bca7440 98a45e6c5 -- libs/cua-driver/rust` rc 0 (SOURCE) |
| Driver binary | `cua-driver 0.31.0`, sha256 `e57bb9aef66a3ef0aed8bb1c09ff8828e1b2b89b7f57f9a60de631dee3eaff95`, recomputed inside every block (`raw/measured/session-env-bNN.txt`); existing lane build used by R2-05, not rebuilt; plain binary, not the `-e2e` wrapper |
| Pre-registration | `PREREG.json` in commit `b91bf9399`, committed 2026-10-02T02:31:06Z; the measured run started 02:31:19Z. It freezes the sha256 of every harness file and of `verify_artifacts.py` (checked by `verify_artifacts.py`) |
| Publication SHA | set by the Publish agent after any push; not recorded here |

## Environment

Linux 7.2.2 x86_64 (i9-10900KF, 10 cores). Private rootless Xvfb 1920x1080x24 `-nolisten tcp`, openbox and picom, private dbus session, scrubbed environment (no `WAYLAND_DISPLAY`, `HYPRLAND_*` or host `XDG_RUNTIME_DIR`; every block recorded `wayland_set=no`, `hyprland_vars=0`), no AT-SPI bus. Google Chrome 151.0.7922.71 launched by the Driver with a Driver-owned `isolated_new` profile. Python 3.12.13, mcp 1.30.0, anyio 4.15.1; Node v22.23.2, `@modelcontextprotocol/sdk` 1.30.0. Each block of ≤10 trials held `flock -s quiet-lane.lock` (shared; correctness lane). Other agents shared the host; trial-start 1-minute loadavg ranged 1.68–13.91 and is recorded per trial.

## Method

**Forced path.** The unmodified runners at the measured tree, `--provider mock --guarded-completion --visual-observation off --max-steps 4`. Step 1: the mock provider types the token. Step 2: guarded completion re-proves Submit and dispatches `browser_click` (`dom_event`). Python runs `run()` in a child process with `run.stdio_client` pointed at the seam; TypeScript runs `run.ts` through its own CLI in a child process with the seam patched onto the SDK transport prototype.

**Fault seam.** In process, between the SDK client session and the real stdio streams of the real `cua-driver mcp`, reusing the R2-05 technique (`harness/fault_transport.py` is the R2-05 seam plus a `read_error` mode and journal probes; `harness/ts_trial.mts` is the TypeScript equivalent). Faults are placed by message sequence and target-journal barriers, never by sleeps. EOF is what the SDK sees when the Driver's stdout closes.

**Fixture.** The R2-05 owned fixture (`harness/ackloss_fixture.py`) with its target journal, serving the jev-use form with a **non-navigating Submit**: same form and accessible names, but a submit handler posts the same form body with `fetch` and stays on the page. Submit therefore stays observable after an unresolved completion, so G2 is really exercised (in R2-05 the pending POST navigation made the next snapshot fail instead). Placements of the first submit: `immediate`, `after_unchanged:1` (lands only after one unchanged `/state` read), `withheld` (lands only when the harness releases it after the runner exits). Later submits apply at once.

| Row | Fault | Fixture | What it tests |
|---|---|---|---|
| R0_control | none | immediate | positive control; verified receipt on the ordinary path |
| R1_ack_lost_applied | Driver answer held until the journal shows `applied`, dropped, EOF | immediate | G1: reconcile a landed effect |
| R2_delayed_within_deadline | as R1 but barrier `received` | after_unchanged:1 | G1: first read negative, effect lands within the deadline |
| R3_delayed_past_deadline | as R2 | withheld | G1: still unresolved at the deadline; no retry |
| R4_read_failure_after_unverified | Submit answer delivered; the next semantic snapshot answer replaced by a tool error result (`isError`, no structured content) | withheld | G3 |
| R5_replanned_completion | none | withheld | G2: the provider re-plans Submit at step 3 |
| R6_own_write_raised | after the step-2 snapshot answer, the caller-side write is closed; the Submit request's own write raises before anything is sent (Python `ClosedResourceError` from the session write stream; TypeScript `send()` raises the SDK's own `Not connected`), then EOF | immediate | pre-write rule: exactly one reconsideration |
| R6n_unproven_not_written (added control) | nothing is sent, but without proof that the request's own write raised. Python `request_lost`: the write returns, the seam drops the request, EOF. TypeScript `closed_before_request`: EOF right after the snapshot answer, so the SDK refuses the request before `send()` | immediate | the rule does not mint authority from absence or from "no effect seen" |

**Arms and n.** Fixed Python runner 12 per main row and 4 for R6n; fixed TypeScript runner 8 per main row and 4 for R6n; unfixed base Python runner 5 each for R1, R3, R4 and R5. 168 trials in a deterministic round-robin schedule (`raw/measured/schedule.json`), 17 blocks, every trial kept.

**Oracle.** The target journal: `received`/`applied` per `POST /submit` (op number, release reason, whether the value equals the trial token, Chrome user agent) and every `/state` read with whether the effect was visible. The harness snapshots it when the runner exits, releases held operations, waits for quiescence and records the final journal. The runner only reads `/state` through its own oracle function and never the journal. The runner's outcome and receipts are what is under test.

## Results (measured run, `raw/measured/`, 168 trials)

All counts are recomputed by `verify_artifacts.py` from `raw/measured/` (summary: `own-105-summary.json`). Times are the informational median child wall time per trial (Driver and Chrome launch included); they are not a measurement (see below).

| Row : arm | Class | N held / N | Outcome → receipt resolution | Journal received / applied | Duplicates | Median s (info) |
|---|---|---|---|---|---|---|
| R0_control : py_fixed | REAL | 12/12 | verified → verified | 1 / 1 ×12 | 0 | 4.6 |
| R0_control : ts_fixed | REAL | 8/8 | verified → verified | 1 / 1 ×8 | 0 | 4.6 |
| R1_ack_lost_applied : py_fixed | REAL | 12/12 | `McpError` → reconciled, verified (median 1 read) | 1 / 1 | 0 | 4.6 |
| R1_ack_lost_applied : ts_fixed | REAL | 8/8 | `McpError` → reconciled, verified | 1 / 1 | 0 | 4.5 |
| R2_delayed_within_deadline : py_fixed | REAL | 12/12 | `McpError` → first read negative, then verified (median 2 reads) | 1 / 1 | 0 | 4.9 |
| R2_delayed_within_deadline : ts_fixed | REAL | 8/8 | same | 1 / 1 | 0 | 4.5 |
| R3_delayed_past_deadline : py_fixed | REAL | 12/12 | `McpError` → unresolved_unknown (31 negative reads, no dispatch) | 1 / 1 (lands after release) | 0 | 7.9 |
| R3_delayed_past_deadline : ts_fixed | REAL | 8/8 | same | 1 / 1 (after release) | 0 | 7.1 |
| R4_read_failure_after_unverified : py_fixed | REAL | 12/12 | snapshot read raised (`ExceptionGroup` around `DriverToolError`) → unresolved_unknown, `phase: observe`, no crash | 1 / 1 (after release) | 0 | 10.0 |
| R4_read_failure_after_unverified : ts_fixed | REAL | 8/8 | `DriverToolError` → unresolved_unknown, `phase: observe`, no crash | 1 / 1 (after release) | 0 | 9.6 |
| R5_replanned_completion : py_fixed | REAL | 12/12 | provider re-planned Submit → not dispatched, `phase: completion_blocked`, unresolved_unknown | 1 / 1 (after release) | 0 | 9.7 |
| R5_replanned_completion : ts_fixed | REAL | 8/8 | same | 1 / 1 (after release) | 0 | 9.1 |
| R6_own_write_raised : py_fixed | REAL | 12/12 | own write raised `ClosedResourceError` → 1 `reconsider` (pre_write_failed) → fresh session → verified | 1 / 1 (0 before the fault) | 0 | 7.0 |
| R6_own_write_raised : ts_fixed | REAL | 8/8 | own `send()` raised `Error` (`Not connected`) → 1 `reconsider` → fresh session → verified | 1 / 1 (0 before the fault) | 0 | 7.1 |
| R6n_unproven_not_written : py_fixed | REAL | 4/4 | request written then lost, `McpError` → unresolved_unknown, 0 reconsiderations | 0 / 0 | 0 | 6.1 |
| R6n_unproven_not_written : ts_fixed | REAL | 4/4 | refused before `send()`, `Error` (`Not connected`) → unresolved_unknown, 0 reconsiderations | 0 / 0 | 0 | 6.0 |
| R1_ack_lost_applied : py_unfixed | REAL | gap 5/5 | `unknown`, receipt without resolution, 0 post-dispatch reads while the effect had already landed | 1 / 1 | 0 | 5.0 |
| R3_delayed_past_deadline : py_unfixed | REAL | gap 5/5 | `unknown`, 0 post-dispatch reads | 1 / 1 (after release) | 0 | 4.6 |
| R4_read_failure_after_unverified : py_unfixed | REAL | gap 5/5 | uncaught `ExceptionGroup`(`DriverToolError`), no outcome event, no receipt | 1 / 1 (after release) | 0 | 7.0 |
| **R5_replanned_completion : py_unfixed** | REAL | gap 5/5 | second Submit dispatched at step 3 → it applied, then the original landed | **2 / 2** | **5** | 7.0 |

Totals (from `verify_artifacts.py`):
- trials 168 (fixed 148, unfixed 20); schedule files match: True
- fixed duplicates 0 in 148 fixed trials; second dispatches 0
- fixed receipts ok 148/148; landed effects classified as failure 0; restart while unresolved 0; crashed 0
- fixed matched expected row outcome 148/148
- R5 second dispatches 0 in 20 (completion_blocked 20/20)
- R6 exactly one reconsideration 20/20; R6n reconsiderations 0 in 8
- placement ok 148/148. Fault-free fixed R0 trials (20) have no placement check. The R5 trials are checked for the first submit staying unapplied until the runner exits.
- unfixed gap reproduced 20/20 (R1 5, R3 5, R4 5, R5 5); unfixed duplicates 5
- journal quiescent after release in 168/168; one Driver sha256 across all trials.

**What the data shows, and what holds by construction.** Once the runner classifies an outcome as `unresolved_unknown` it has no dispatch path; that zero is code, not measurement. The empirical content is:
1. on the real path, the fixed runners turned 40 ack-loss trials (R1, R2) whose effect had landed into `verified` with exactly one dispatch. In R2 the first post-dispatch read was negative in 20/20 (forced by placement) and the runner still did not act on it;
2. the R4 read failure and the R5 re-plan actually happened in 40/40 fixed trials. The seam injected the error in every R4 trial, and every R5 trial reached `completion_blocked`, which only a re-planned Submit can produce. Neither escaped or dispatched;
3. the pre-write rule separated the cases by write state, not by error class. TypeScript R6 and R6n raise the **same class and message** (`Error: Not connected`); only R6, where the ledger saw the request's own write raise, was reconsidered (8/8 vs 0/4). The journal confirms nothing reached the target before either fault;
4. the unfixed runner reproduced every gap on the same fixture, Driver and transport, and in R5 it produced 5 real duplicate mutations.

**Producer attribution.** In every fault row the Submit dispatch came from the guarded-completion route (step 2, `browser_click` with `input_route=dom_event`; seam request records), except the R5 re-plan, which came from the provider route at step 3. Every forwarded Submit request carried `input_route=dom_event` (165/165), and every `received` POST carried a Chrome user agent (165/165, journal `user_agent_chrome`; 165 = 160 fixed and unfixed first submits + 5 unfixed R5 replays). Journal probes taken when a fault fired show `applied 0` wherever the effect must not yet have landed.

## Unit evidence (UNIT)

All suites ran inside `cua-x11-session.sh` with local paths replaced in `raw/unit/`.
- **Red at the tests commit** (`raw/unit/red-commit1-full`, jev-use tree `feadb1965`): Python 259 run, 8 failures and 3 errors, 1 skipped. The 11 are the 9 new `test_runner_reconcile.py` cases, the updated #105 ack-loss case and the new `verify_setup` receipt case. TypeScript 165 tests, 12 failing: the 9 new `run_reconcile.test.ts` cases, 2 accepted-outcome cases and the #105 ack-loss case. Typecheck and the 4 CLI verifiers rc 0. `raw/unit/red-commit1-focused` shows the same focused red (9/9 Python reconcile cases, 9/9 TypeScript), recorded on `c5610cea2`, whose tree differs from `feadb1965` only by the added `test_verify_setup.py` case.
- **Green at the fix commit** (`raw/unit/fix-head-full`, head `27386f3e3`, the exact CI `run-unit.sh` steps): Python 259 run, OK (1 skipped); TypeScript 165/165; typecheck rc 0; `verify_choice_cli`, `verify_decision_cli --model mock`, `verify_choice_cli --request-version v2`, `verify_decision_cli --model mock --fixture native` all rc 0; both guarded-focused steps rc 0.
- **Harness self-tests** (`raw/unit/harness-selftest.txt`): 10/10. They cover the fixture placements, the non-navigating page, the control server, the Python seam surfaces through a real `ClientSession` with the fixed runner's `WriteLedger` (`pre_dispatch` gives `ClosedResourceError` and `not_written`; `request_lost` and `ack_lost` give `McpError` and `written`; `read_error` gives an `isError` snapshot), and the schedule.
- **CI E2E verify_setup at the fix head** (REAL, `raw/e2e-verify-setup/`, under the shared lock): `--typescript`, `--typescript --guarded-completion`, `... --guarded-completion-decline`, and `--typescript --visual-fixture --expect-visual-status not_installed`, all rc 0. The verified runs end with the `verified` receipt; the visual fallback ends `budget_exhausted` with no receipt, because no completion was dispatched.

## Work deleted vs wall-clock saved

- **Work deleted:** none was targeted; this is a correctness fix. Relative to the unfixed runner, the fix removed 5 duplicate target mutations (R5) and 5 uncaught crashes (R4). It also replaces the caller-side reconciliation that R2-05's experiment consumer had to do (R2-07 and R2-10 can rely on the runner now).
- **Work added:** at most 31 oracle reads (3 s) per ambiguous outcome. It is added only where a mutation's effect is in doubt: an ambiguous action error, a blocked re-plan or a failure after an unverified completion. On the ordinary path the only addition is building a receipt. Ack-lost trials whose effect landed resolved in a median of 1 (R1) or 2 (R2) reads.
- **Wall-clock saved:** not measured and not claimed. The medians in the table include Driver and Chrome launch and were taken under the *shared* lock while other lanes ran (loadavg 1.68–13.91). The unresolved rows (R3, R4, R5) are slower than the unfixed runner by about the 3 s deadline plus, for R4/R5, the existing 2 s verification window, by construction.

## Negative and fallback controls

- R0 positive control through the seam: 20/20 verified, 1 applied each. The seam alone does not change outcomes.
- R6n pre-write negative control: nothing reached the target (received 0 in 8/8), yet the runners did **not** reconsider (0/8), because neither the write returning (Python) nor the SDK refusing before `send()` (TypeScript) is proof that the request's own write raised. Absence of an event never mints authority.
- UNIT scope control (`test_closed_stream_after_the_write_is_not_pre_write_proof` and the TypeScript twin): the same error class raised *after* the write (the mcp 1.30.0 post-response `list_tools` refresh shape) is reconciled, not reconsidered.
- Unfixed base runner (discriminating before-control): every gap reproduced, 20/20.
- Placement validity: 148/148 fault- or placement-checked trials. The ack barrier was reached and the journal probes matched in every fault trial. In R3/R4/R5 the first submit stayed unapplied until the runner exited, and in R2 a negative read preceded the landing 20/20.
- Harness: the TypeScript seam has no self-test of its own; its placement is checked per trial from raw/ instead (R2-05 had no TypeScript seam).

## Evidence classes

| Item | Class |
|---|---|
| Fixed Python and TypeScript runners, rows R0–R6 and R6n, on real MCP stdio, Driver, Chrome and the fixture journal | REAL |
| Unfixed base Python runner, R1/R3/R4/R5 | REAL |
| CI E2E `verify_setup.py` steps at the fix head | REAL |
| Red/green jev-use suites, typecheck, CLI verifiers, harness self-tests | UNIT |
| Driver-source identity a0bca7440 = 98a45e6c5 under `libs/cua-driver/rust`; code-path statements about the SDKs | SOURCE |
| Unfixed TypeScript runner on a real transport | NOT_RUN (the before-control was specified for Python; the TypeScript red is UNIT) |
| Driver crash, OS pipe cut, socket transport as the fault mechanism | NOT_RUN |
| Cancellation / native lifetime / held-input cleanup (#9) | NOT_RUN |
| Native (AT-SPI) tasks, other browser task classes | NOT_RUN |
| Live provider | NOT_RUN (mock provider; 0 TypeSafe attempts, 0 reached) |
| Latency or benchmark of the fix | NOT_RUN (correctness lane) |

## Deviations

- **Fixture page.** Submit uses `fetch` instead of a navigating POST, so Submit stays observable (needed for G2, per the lane spec). Behaviour under the original navigating page is covered by R2-05, not re-run here.
- **Child processes.** R2-05 ran the Python runner in the harness process. Here each runner runs in a child process, so that the unfixed and fixed Python runners and the TypeScript runner can share one harness. Seam barriers therefore go through a harness-only control server; the runner never talks to it.
- **Added row R6n** (8 trials) as a negative control for the pre-write rule; it is outside the n = 20 per row the spec asked for.
- **R4 failure shape.** The read failure is an injected tool-error result (`isError`, no structured content), not the roughly 100 s CDP `DOM.getDocument` timeout R2-05 observed. Both surface as `DriverToolError` in the runner.
- **Pilots.** Two plumbing pilots ran before registration and are kept in `raw/pilot/`, excluded from all denominators. pilot1 had 10 trials; 2 TypeScript trials failed to start because the entry compiled as CommonJS, fixed by renaming it to `.mts`. pilot2 had 12 trials, all matching the later measured run. The gates come from the lane spec, which predates the pilots. The per-row predictions and the placement-validity condition were written after the pilots.
- **PREREG timing.** `registered_utc` in `PREREG.json` points to the commit time (02:31:06Z). The measured run started 13 s later.
- **Lock waits.** Block b11 waited about 14 minutes on the shared `quiet-lane.lock` while another lane held it exclusively. No trial ran unlocked.
- **Session console and child logs** are mirrored only to the lane artifacts directory, because they contain local paths.
- **Near-miss, disclosed.** While collecting provenance, a `google-chrome --version` command was issued on the host shell outside the isolated session. `google-chrome` is not on the host `PATH`, so nothing executed and no Chrome process or display was touched. The Chrome version above comes from the package database instead.

## Limits and claim boundary

This packet establishes the following for **Linux, a private Xvfb session, Driver 0.31.0 (`e57bb9ae…`), Chrome 151, MCP Python SDK 1.30.0 / anyio 4.15.1 and TypeScript SDK 1.30.0, the jev-use Python and TypeScript runners at `98a45e6c5` + this fix (`27386f3e3`), the mock provider, and one guarded `dom_event` Submit mutation on an owned loopback fixture with a non-navigating Submit**. Under the eight injected fault placements, the fixed runners made zero duplicate mutations and ended every trial with a content-free receipt. They classified no landed effect as failure, never dispatched a second completion while the first was unresolved, and reconsidered exactly once only when the mutation request's own write provably raised.

It does **not** establish any of the following:
- exactly-once delivery or an idempotency guarantee;
- behaviour under a Driver crash, an OS pipe cut or a socket transport: the faults were injected in process;
- behaviour on native/AT-SPI tasks, other browser task classes or other providers;
- cancellation or native-lifetime behaviour (#9);
- any public contract change. The receipt fields are caller-side example-runner fields and are not proposed for the Driver (#38 / upstream trycua/cua 4009);
- that a TypeScript connection loss before the write is reconsidered: it is not (R6n), by design;
- any timing result.

Events and transport errors were never the success oracle; the target journal was.

## Disposition

**KEEP** (`disposition_by_gates` in `own-105-summary.json`): no kill event (blind second effects 0, landed-as-failure 0, restart while unresolved 0) and every keep gate true: zero duplicates, all receipts, zero landed-as-failure, R5 zero second dispatch, R6 exactly one reconsideration, unfixed control reproduces, suites pass, placement valid. This gives owner row #105 a terminal disposition backed by REAL evidence in both runtimes, superseding the PARTIAL left by R2-05.

Follow-ups go to existing owners and none adds a service:
- **#105:** this branch (`exp/own-105-runner-reconcile-20261002`) is ready for the Publish agent to push as the #105 update.
- **#38 / upstream trycua/cua 4009:** if a pre-write distinction is ever wanted in a public vocabulary, the evidence here says it must be keyed to write state (a ledger at the write), not to an error class. This packet proposes no field.
- **R2-07 / R2-10:** can rely on runner-side reconciliation instead of experiment-side reconcilers.

## Reproduction

```sh
# worktree at the measured tree; deps: <lanes>/lane-deps.sh <worktree>
# unfixed runner copy: git archive 98a45e6c5 libs/cua-driver/examples/jev-use/python | tar -x -C <tmp>/base-src
cd <worktree>
flock -s <tmp>/locks/quiet-lane.lock <lanes>/cua-x11-session.sh \
  docs/experiments/own-105-runner-reconcile-2026-10-02/harness/session_entry.sh \
  <worktree> <tmp>/base-src/libs/cua-driver/examples/jev-use <lanes>/bin/cua-driver-4316-a0bca7440 \
  <out> <tmp>/trials bNN --start <10*NN> --count 10        # NN = 00..16
# unit: <lanes>/cua-x11-session.sh <lanes>/run-unit.sh <worktree> <out>
# harness self-tests (inside the session): cd harness && <jev-use>/.venv/bin/python -m unittest test_harness
python3 docs/experiments/own-105-runner-reconcile-2026-10-02/verify_artifacts.py
```
