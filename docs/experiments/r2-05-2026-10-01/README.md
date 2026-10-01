# R2-05: real acknowledgement loss and delayed effects, 2026-10-01

## Result in one paragraph

The test ran on the **real MCP stdio transport**, a real Driver (0.31.0, sha256 `e57bb9ae…`), real Chrome 151 and an owned fixture whose target journal is the oracle. A caller that follows the #105 `mutation_outcome` receipt made **0 duplicate target mutations**: typed duplicates 0 in 60 typed trials, and typed predicate held 60/60 across six rows of 10. The rows were a positive control, a proven pre-dispatch failure, a request lost after the write call, an applied effect whose acknowledgement was lost, a delayed effect that landed after an initially unchanged read, and a delayed effect that landed only after the reconciliation deadline. The naive restart-from-step-one counterexample produced RD naive duplicate in 10/10 (naive duplicates 10 in 50 naive trials). That shows the rows discriminate: one negative read while the original operation is still in flight is not authority to replay. The pre-registered gates give **KEEP** for the recovery invariant. Two boundaries matter. First, the recovery consumer is experiment code: the #105 runner itself stops at `unknown` and does not reconcile. Second, the #105 receipt cannot tell a proven pre-write failure from an ambiguous one (RA receipt attempted=true effect=unknown 20/20).

## Scope and owners

- Experiment `R2-05` from kvnloo/cua#93 and #73; recovery owner kvnloo/cua#105; measurement owner #10. kvnloo/cua#9 keeps cancellation and native lifetime, which were **not tested** here.
- Spec rows: (a) proven pre-dispatch failure, (b) applied-but-ack-lost, (c) delayed mutation after an initially unchanged read, at least 10 trials each, duplicate count, naive-retry counterexample. All are present (RA, RB, RC). RA2, RD and RE are added controls and probes.
- No Driver code change, no new service, no GitHub writes or pushes. Correctness lane: timing is informational only.

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Tested source (caller) | `98a45e6c528da9e2715288c20c2a0feeeef8e73f` (kvnloo/cua#105 head; parent `ec83a3a8…`) |
| Live PR head, gh read 2026-10-01T22:14Z | kvnloo/cua#105 `98a45e6c528da9e2715288c20c2a0feeeef8e73f` (OPEN, draft); trycua/cua#4316 `a0bca744067d04f05904319d3d919be30c336556` (OPEN) |
| Driver source | `a0bca744067d04f05904319d3d919be30c336556`. `git diff a0bca7440..98a45e6c5` outside `libs/cua-driver/examples` is empty (SOURCE) |
| Driver binary | `cua-driver 0.31.0`, sha256 `e57bb9aef66a3ef0aed8bb1c09ff8828e1b2b89b7f57f9a60de631dee3eaff95`, recomputed inside the session (`raw/measured/session-env.txt`). Existing lane build, not rebuilt; that build's `head=` stdout line was not saved (see `provenance.json`). Plain binary, not the `-e2e` wrapper |
| Upstream main at capture | `229b65b2849c3a595ddbc85200d7181b18bd2e47` (context only; not tested) |
| Pre-registration | `PREREG.json`, commit `6915dd75d` at 2026-10-01T22:15:33Z, sha256 `0ccae6dc66fe40b5929fd99f1b10b3e132ed80810b7d7d02fe18d8738445b750`. The measured run started at 22:15:46Z |
| Publication SHA | Set by the orchestrator after any push; not recorded in this packet |

## Environment

Linux 7.2.2 x86_64 (i9-10900KF, 10 cores, 23 GiB). Private rootless Xvfb 1920x1080x24 with `-nolisten tcp`, openbox and picom, a private dbus session, a scrubbed environment (no `WAYLAND_DISPLAY`, `HYPRLAND_*` or host `XDG_RUNTIME_DIR`), and no AT-SPI bus. The Driver launched Google Chrome 151.0.7922.71 with a Driver-owned `isolated_new` profile, sandbox on, and default Driver safety settings. Python 3.12.13, mcp 1.30.0, anyio 4.15.1. Other agents shared the host: the trial-start 1-minute loadavg ranged 0.44–10.82 and is recorded per trial. No leftover processes after the session exited.

## Method

**Forced path.** The caller is the **unmodified** jev-use `python/run.py` `run()` with `--provider mock --guarded-completion --visual-observation off`. In step 1 the mock provider picks `browser_type`. In step 2, guarded completion re-proves Submit and dispatches `browser_click` with `input_route=dom_event`. In R0, the step routes are `provider` then `guarded-completion` in 10/10. In every fault row the first outcome event has `decision_route=guarded-completion`. The runner runs in process, and its `run.stdio_client` name points at `harness/fault_transport.fault_stdio_client`. That function wraps the SDK's **real** `mcp.client.stdio.stdio_client`, which spawns the real `cua-driver mcp`.

**Fault seam.** The seam sits between `ClientSession` and the SDK stdio streams. Every byte otherwise crosses the real stdio pipes. Each fault closes the transport by sending EOF on the caller-facing read stream, which is what the SDK sees when the Driver's stdout closes. Its receive loop then fails pending requests with `McpError(CONNECTION_CLOSED)` and closes the session write stream.

| Row | Fault | Target placement (first submit only) | Arms |
|---|---|---|---|
| R0_control | none | immediate | typed |
| RA_pre_dispatch | When the Driver answers the step-2 snapshot, the seam closes the session write stream, delivers the answer, then sends EOF. The Submit request then fails **inside the SDK write call** (`ClosedResourceError`) | immediate | typed, naive |
| RA2_request_lost | The SDK write call returns, the seam does not forward the request, then sends EOF (`McpError`) | immediate | typed, naive |
| RB_ack_lost_applied | The request reaches the Driver and Chrome clicks. The seam holds the Driver's response until the journal records `applied`, drops it, then sends EOF | immediate | typed, naive |
| RC_delayed_after_unchanged | As RB, but the seam waits only for `received` | Applied only after the target has served **one** `/state` read that returned unchanged | typed, naive |
| RD_delayed_withheld | As RC | Held until the harness releases it after the caller finished (beyond the 3 s reconciliation deadline) | typed, naive |
| RE_runner_loop_withheld | none: the acknowledgement is delivered | Held, with its HTTP response, until the caller finished | runner |

**Arms.**
- `typed`: an experiment-side consumer of the runner outcome and #105 receipt.
  - `ClosedResourceError`/`BrokenResourceError` means the SDK raised from its write call before handing the message to the transport. The consumer classifies `not_dispatched_proven` and reconsiders once with a fresh run.
  - Any other ambiguous error is classified `unknown_effect`. The consumer reads the oracle every 0.1 s up to 3 s and never dispatches.
- `naive`: on `unknown`, restart the runner from step one at once; its only check is the runner's own step-start oracle read.
- `runner`: no recovery.

No arm resets the target before a retry.

**Oracle.** The target owns the fixture journal (`harness/ackloss_fixture.py`): `received` and `applied` per `POST /submit`, the release reason, whether the value equals the trial token, the Chrome user agent, and every `/state` read with whether the effect was visible. The caller reads only `/state`, through the runner's own `fixture_state`, and never the journal. The harness reads the journal after the caller finishes, once every held operation has been released and the journal is quiescent.

**Design.** n = 10 per cell, 12 cells, 120 trials. Blocks were interleaved: each block contains every cell once, rotated per block, with odd blocks reversed (AB/BA). One session ran trials sequentially, and every trial is kept.

## Results (measured run, `raw/measured/`, 120 trials, placement ok 120/120)

| Row : arm | Class | N held / N | First error | Classification → resolution | Journal applied | Duplicates |
|---|---|---|---|---|---|---|
| R0_control : typed | REAL | 10/10 | none | none | 1 ×10 | 0 |
| RA_pre_dispatch : typed | REAL | 10/10 | ClosedResourceError ×10 | not_dispatched_proven → fresh run, verified ×10 | 1 ×10 (0 received before reconsideration) | 0 |
| RA2_request_lost : typed | REAL | 10/10 | McpError ×10 | unknown_effect → unresolved_unknown ×10 (31 negative reads, no dispatch) | 0 ×10 | 0 |
| RB_ack_lost_applied : typed | REAL | 10/10 | McpError ×10 | unknown_effect → reconciled_applied ×10 (first read visible) | 1 ×10 | 0 |
| RC_delayed_after_unchanged : typed | REAL | 10/10 | McpError ×10 | unknown_effect → reconciled_applied ×10 (**first read unchanged ×10**, median 2 reads) | 1 ×10 | 0 |
| RD_delayed_withheld : typed | REAL | 10/10 | McpError ×10 | unknown_effect → unresolved_unknown ×10 (31 negative reads, no dispatch); the held op landed after release | 1 ×10 | 0 |
| RA_pre_dispatch : naive | REAL | n/a (counterexample) | ClosedResourceError ×10 | restart → verified ×10 | 1 ×10 | 0 |
| RA2_request_lost : naive | REAL | n/a | McpError ×10 | restart → verified ×10 (lucky: nothing had landed) | 1 ×10 | 0 |
| RB_ack_lost_applied : naive | REAL | n/a | McpError ×10 | restart → verified ×10 (its step-1 read saw the landed effect) | 1 ×10 | 0 |
| RC_delayed_after_unchanged : naive | REAL | n/a | McpError ×10 | restart → verified ×10 (its step-1 read released the held op; its step-2 read saw it) | 1 ×10 | 0 |
| **RD_delayed_withheld : naive** | REAL | n/a | McpError ×10 | restart → verified ×10 | **2 ×10** (replay applied, then the original) | **10** |
| RE_runner_loop_withheld : runner | REAL | n/a (probe) | none | none; uncaught `DriverToolError` ×10 | 1 ×10 | 0 |

Totals, all recomputed by `verify_artifacts.py`:
- typed duplicates 0 in 60 typed trials
- typed predicate held 60/60
- RD naive duplicate in 10/10
- naive duplicates 10 in 50 naive trials
- RA receipt attempted=true effect=unknown 20/20
- placement ok 120/120
- RE runner-loop duplicates 0/10
- No typed kill events.

**Producer attribution.** For RB, RC and RD, the Driver's (dropped) click result reported `route=dom` in every trial; R0 did the same. Every `received` POST carried a Chrome user agent. In RA the seam journal shows the session write stream closed before the next request and **no `browser_click` forwarded** in 20/20 attempts. In RA2 the request was taken by the seam and never forwarded, and the journal received 0 (10/10 typed).

**RE probe.** The acknowledgement was delivered and the effect held. The runner made its 20 post-click verification reads, then 1 step-3 read, all unchanged. Its step-3 semantic snapshot was refused after about 100 s (`browser_route_unavailable`: CDP `DOM.getDocument` timed out while the POST navigation was pending). The `DriverToolError` escaped `run()` uncaught. There was no second Submit, no outcome event and no `mutation_outcome` receipt. Median informational resolution was 106.1 s.

## Findings

1. **The recovery invariant holds on a real transport (REAL, KEEP).** Under every pre-registered fault, a caller that treats an ambiguous transport failure as `effect=unknown` and reconciles through fresh target reads never duplicated the mutation. The decisive rows are RC and RD: the first reconciliation read was negative in 20/20 trials while the original operation was still in flight, and the typed consumer did not treat it as authority.
2. **The counterexample discriminates (REAL).** A restart-from-step-one policy is safe in RB and RC only because of where its own reads happen to fall. In RC its step-1 read is the read that releases the held op. When the original stays in flight longer (RD), it duplicates in 10/10.
3. **A typed pre-dispatch proof exists at the SDK boundary, but the #105 receipt does not carry it (REAL + SOURCE).** In mcp 1.30.0 the error class tells the two cases apart:
   - After EOF, the session write stream is closed. A later request fails inside `_write_stream.send` with `ClosedResourceError`, which is a pre-write failure.
   - A request already handed to the transport fails with `McpError(CONNECTION_CLOSED)`, which is ambiguous.

   The #105 receipt reports `attempted=true, effect=unknown, retryDisposition=observe` for both (RA 20/20). That is safe but loses legal reconsideration. Any receipt or contract change is for #38 / upstream #4009 to decide; this packet does not propose a public field.
4. **Reconciliation is not in the tested runner (SOURCE).** On an action error, `run.py` writes `unknown` and returns. The bounded reconciliation and reconsideration measured here live in `harness/run_trials.py`, not in #105.
5. **The runner's own loop is unguarded by design but was not observed to replay (REAL probe + SOURCE).** After a completion click whose effect is not visible within its 20×0.1 s window, `run.py` continues to the next step. A fresh snapshot that still offered Submit would let the provider pick it again; nothing in the loop marks the earlier completion as unresolved. RE shows no duplicate only because Chrome's pending navigation made the next snapshot fail. That result depends on the fixture's held-response model and is not a safety proof. The uncaught read error also leaves no receipt for a dispatched-but-unverified completion.

## Work deleted vs wall-clock saved

- **Work deleted:** none was targeted. Relative to the naive policy, the typed consumer avoided 10 duplicate target mutations in RD, and the journal confirms each one. In RA it spent one extra full run (reconsideration) where the receipt alone would have stopped at `unknown`.
- **Wall-clock saved:** not measured and not claimed. Resolution times are informational only: they were not taken under `quiet-lane.lock`, the host was shared (loadavg up to 10.8), and the arms do different work. The typed RD median of 7.1 s includes the 3 s reconciliation deadline.

## Negative and fallback controls

- R0, a plain relay through the seam: 10/10 verified with 1 applied. The seam alone does not change outcomes.
- RA2, a request lost after the write call: the typed consumer did **not** infer pre-dispatch (10/10 `unknown_effect`) and stayed unresolved with 0 dispatches, even though nothing had landed. The conservative result is the correct one.
- RD naive: the validity gate for the counterexample (≥1 duplicate) was met in 10/10.
- Placement validity: the fault fired and its barrier was reached in 120/120 trials.
- Harness self-tests (UNIT, `raw/unit/harness-selftest.txt`): 8/8. They cover fixture placements over HTTP, the seam's error surfaces through a real `ClientSession` against an in-memory FastMCP server, and the schedule.
- jev-use suites at the tested source (UNIT, `raw/unit/`): Python 249 run, 1 skipped, OK; TypeScript 156/156; typecheck rc 0; all four CLI verifiers and both guarded-focused steps rc 0.

## Evidence classes beyond the table

| Item | Class |
|---|---|
| Driver-source identity a0bca7440 = 98a45e6c5 outside the examples | SOURCE |
| Findings 3–5, code-path statements | SOURCE |
| Harness self-tests, jev-use unit suites | UNIT |
| TypeScript runner on a real transport (`run.ts`; its SDK has a different pre-write surface) | NOT_RUN |
| Latency or benchmark of recovery | NOT_RUN |
| Live provider | NOT_RUN (mock provider; not needed for this correctness question) |
| Cancellation / native lifetime / held-input cleanup (#9) | NOT_RUN |
| Idempotency/deduplication rows from the #105 comment | NOT_RUN (the fixture claims no idempotency guarantee) |
| Driver-process crash or OS-pipe cut as the fault mechanism | NOT_RUN |

## Deviations

- `PREREG.json` says `registered_utc 2026-10-01T22:16Z`; the commit time is 22:15:33Z. The measured run started at 22:15:46Z, after the commit.
- The measured run set `CUA_SESSION_EXTRA_ENV="R205_DEBUG=1"`, which the registered command did not mention. It only prints exception tracebacks to the session log and changes no trial logic. The harness file hashes in `PREREG.json` still match (checked by `verify_artifacts.py`).
- Pilots: three plumbing pilots ran before registration. pilot1 (2 trials) and pilot2 (1 trial) hit a harness keyword bug in the `ack_lost` path, which is now fixed. pilot3 ran one trial per cell, 12 trials. They are kept in `raw/pilot/`, excluded from the denominators, and agree with the measured run.
- The session console log is mirrored only to the lane artifacts directory, not this packet, because it contains local paths.

## Limits and claim boundary

This packet establishes, for **Linux, a private Xvfb session, Driver 0.31.0 (`e57bb9ae…`), Chrome 151, MCP Python SDK 1.30.0 / anyio 4.15.1, the jev-use Python runner at `98a45e6c5`, the mock provider, and one guarded `dom_event` Submit mutation on an owned loopback fixture**, the following: a caller that follows the #105 receipt (observe and reconcile on unknown; reconsider only on SDK-proven pre-write failure) makes zero duplicate target mutations under the six injected fault placements, and a naive restart duplicates when the original stays in flight.

It does **not** establish any of the following:
- exactly-once delivery or an idempotency guarantee;
- behaviour under a Driver crash, an OS-level pipe cut, a socket transport, or the TypeScript runner;
- that the #105 runner itself reconciles;
- that the runner's own loop cannot replay;
- any timing or speed result;
- cancellation or native-lifetime behaviour (#9);
- any other workflow, platform or provider.

The typed and naive policies are experiment consumers, not product code. Events and transport errors were never used as the success oracle; the target journal was.

## Disposition

**KEEP** (`disposition_by_gates` in `r2-05-summary.json`): no kill event, every typed cell 10/10, RD naive duplicates 10/10, RE runner-loop duplicates 0/10. Follow-ups go to their existing owners; none adds a new service.
- **#105:** move bounded reconciliation into the runner, or document that callers must do it. Catch read failures after an unverified completion so they emit a receipt instead of escaping.
- **#38 / #4009:** decide whether a pre-write `not_written` distinction belongs in the outcome vocabulary.
- **Runner loop:** an explicit guard that blocks a second completion while the first is unresolved is worth a targeted test with a fixture that keeps Submit observable.

## Reproduction

```sh
# worktree at 98a45e6c528da9e2715288c20c2a0feeeef8e73f, deps: <lanes>/lane-deps.sh <worktree>
cd <worktree>
<lanes>/cua-x11-session.sh docs/experiments/r2-05-2026-10-01/harness/session_entry.sh \
  <worktree> <lanes>/bin/cua-driver-4316-a0bca7440 <artifacts>/r2-05/measured <tmp>/r2-05/measured --blocks 10
cd docs/experiments/r2-05-2026-10-01
(cd harness && <jev-use>/.venv/bin/python -m unittest test_harness)
python3 verify_artifacts.py
```
