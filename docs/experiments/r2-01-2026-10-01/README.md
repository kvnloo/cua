# R2-01: causal browser feedback/cursor A/B, 2026-10-01

## Result in one paragraph

On upstream main `229b65b2` (Driver 0.32.0) plus default-off phase-trace marks, in a private rootless Xvfb session, the jev-use DOM click (`browser_click`, `input_route=dom_event`) took a median **1541.6 ms** with agent-cursor feedback ON and **23.5 ms** with it OFF. Every one of 24 AB/BA-interleaved pairs was slower with feedback ON. The median paired difference was **1517.9 ms** (bootstrap 95% CI **1516.7 to 1519.3 ms**). The Driver trace places the delay inside visualization: the median ON visualization interval was **1517.8 ms**, almost all of it the Linux overlay's wait for the cursor glide to arrive (median 1517.2 ms). That wait sits between `DOM.getBoxModel` and `Runtime.callFunctionOn`. Both arms verified **24/24** through the fixture's own `/state` oracle and fixture journal. Route, authorization and outcome were unchanged. Pre-registered disposition: **KEEP_H1**. The ~1.5 s action span on this route is the awaited cursor glide. This is a measurement result, not a recommendation to turn feedback off by default.

## Scope and owners

- Owners: kvnloo/cua#93 (`R2-01`), #10 (accounting), original `E1`. Canonical queue: #73.
- Pre-registration: `PREREG.json`, committed first as `ea317065b`, sha256 `3710ed7b8e79c02809b611d88ee336bf718fa21639b0ed4c2e3420ec15e19cda`. It was not edited after the runs. Deviations are listed below.
- No new service, shadow state, second verifier, router, lifecycle registry, batch API or event service. No GitHub writes, no pushes, no upstream posts.

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Tested source base | upstream main `229b65b2849c3a595ddbc85200d7181b18bd2e47` (pinned in SETUP) |
| Tested source with instrumentation | `7d3a28b663a041b072b4be8aadb187a1eab5fd28` on local branch `exp/r2-01-feedback-ab-20261001` |
| Live upstream main (gh read 2026-10-01T22:11:52Z) | `effd9b298942d7e9808077adef4ef575d561141d`: one commit ahead of the base, touching only `release-please-config.json` (no Driver code) |
| Live PR head | none. R2-01 has no PR; upstream main is the source under test |
| Publication SHA | set later by the orchestrator. This worker did not publish |
| Driver binary | `cua-driver-r2-01-trace-7d3a28b66`, sha256 `41338733a0b39d5b96bd98965f3b8adc3a18e4e28be00cb23077a4c9e964c346`, `cua-driver 0.32.0`; `build-driver.sh` into lane target dir `cua-release-r2-01` under the cargo lock. 0 Fresh workspace units, 196 s, rustc 1.97.1. Same binary in both arms |
| Browser | Driver-selected Google Chrome 151.0.7922.71, `isolated_new` profile, default sandbox, no permission-mode override, no approval bypass, no `*-e2e` wrapper |

Details: `provenance.json`, `source-head.txt`.

## Environment

Linux 7.2.2 x86_64, 10 CPUs, 23 GiB. Private rootless Xvfb 1920x1080x24, openbox, picom (xrender) and private dbus via `cua-x11-session.sh`. No AT-SPI bus (the Driver's harmless AT-SPI listener WARN is filtered from `raw/session-*.log`). Host Wayland/Hyprland variables were scrubbed. Telemetry was at Driver defaults in a fresh session HOME, identical across arms. All 56 locked trials ran in one session inside `flock quiet-lane.lock`, 22:18:41Z to 22:21:30Z. The 1-minute loadavg before each measured trial ranged from 1.91 to 3.4 (every trial's value is in `raw/trials/*.jsonl`).

## Method

- **Arms.** ON: `set_agent_cursor_enabled {enabled:true}`, the Driver default made explicit so both arms issue identical RPCs. OFF: `set_agent_cursor_enabled {enabled:false}`, the toggle reused from `exp/agent-cursor-off-runner-20260929-local` `e1706ee4d`. The call is made right after MCP initialize, before `browser_prepare`.
- **Forced path, per trial** (`run_feedback_ab.py`, reusing jev-use `python/run.py` functions, `FixtureFormTask`, `choose_mock_for_task` and `FixtureServer`):
  1. Start a fresh `cua-driver mcp` process.
  2. Set the arm toggle.
  3. `browser_prepare` with an isolated_new profile, then `wait_for_window`, bind, and navigate to the loopback fixture.
  4. Step 1: oracle read, `semantic_v2` snapshot, mock choice, then `browser_type` with replace=true.
  5. Step 2: oracle read, snapshot, mock choice, then `browser_click {ref, input_route: dom_event}` (candidate `submit-form`).
  6. The runner's completion loop: an oracle read, then a 0.1 s sleep, at most 20 times.
- **Pairs.** 24 pairs. Pair k runs ON then OFF when k is even and OFF then ON when k is odd. Each trial gets a fresh Driver and browser, and the fixture is reset before every trial.
- **Timestamps.** Every timestamp uses one clock, the host `CLOCK_MONOTONIC`:
  - caller: `time.monotonic_ns()` around each call and oracle read;
  - Driver: the default-off `CUA_DRIVER_PHASE_TRACE_FILE` marks;
  - fixture journal: a `FixtureState` subclass stamps the POST `/submit` mutation.

  Clock order (caller send ≤ `dispatch.enter` ≤ `dispatch.exit` ≤ caller return) held in 48/48 trials.
- **Instrumentation** (measurement-only, env-gated, default off). New file `cua-driver-core/src/phase_trace.rs`. Marks:
  - the registry dispatch boundary (`tool.rs`);
  - `browser_click` phases (lock, revalidate, ref resolve, `DOM.resolveNode`, scroll, box model, CDP send and response);
  - the `browser_type` visual boundary;
  - engine `visualize_browser_action` (visibility eval, layout metrics, platform call);
  - the Linux platform gate and animate, and the overlay arrival wait.

  With the variable unset, no file is opened and no detail is built.
- **Statistics.** Median and nearest-rank p95 per arm. The paired difference is D = ON − OFF within each pair. The median D has a percentile bootstrap CI (10000 resamples, seed 20261001). Every trial is kept.

## Results

| Row | ON | OFF | Evidence class |
|---|---|---|---|
| Verified by fixture `/state` + journal token match | 24/24 | 24/24 | REAL |
| Forced path (mock chose `browser_click` dom_event; trace `click.enter` route dom_event; public route `dom`; effect `unverifiable`) | 24/24 | 24/24 | REAL |
| Feedback path as assigned (ON: `cursor_enabled=true` plus arrival wait; OFF: `cursor_enabled=false`, no animate marks) | 24/24 | 24/24 | REAL |
| `browser_click` span, median (p95) | 1541.578 (1544.911) ms | 23.461 (28.864) ms | BENCHMARK |
| Visualization interval, median | 1517.843 ms | 0.452 ms | BENCHMARK |
| Overlay arrival wait, median (min to max) | 1517.242 (1507.929 to 1521.789) ms | not entered | BENCHMARK |
| Visualization CDP work (visibility `Runtime.evaluate` + `Page.getLayoutMetrics`), median | 0.180 + 0.177 ms | 0.184 + 0.165 ms | BENCHMARK |
| Revalidate (largest non-visual phase in both arms), median | 10.825 ms | 11.735 ms | BENCHMARK |
| `Runtime.callFunctionOn` send to response, median | 1.548 ms | 0.992 ms | BENCHMARK |
| Target mutation (journal POST) after CDP send, median | 9.331 ms | 8.502 ms | BENCHMARK |
| MCP transport in / out, median | 1.539 / 7.491 ms | 1.696 / 7.112 ms | BENCHMARK |
| Fresh verification: first verified read after tool return, median | 1.065 ms (first read) | 0.849 ms (first read) | BENCHMARK |
| `browser_type` span, median (its visualization) | 1607.957 (1477.045) ms | 128.517 (0.406) ms | BENCHMARK |

Paired, n = 24 complete pairs:
- `browser_click` median D = **1517.905 ms**, CI [1516.717, 1519.329]. Range 1509.891 to 1522.556 ms. 24/24 pairs were slower ON.
- The median difference in the visualization interval was 1517.411 ms. The median of (D minus the visualization difference) was 0.542 ms, so the visualization interval accounts for the whole click difference.
- Secondary, added after the runs and not used as gates:
  - `browser_type` D = 1480.187 ms, CI [1474.408, 1489.177].
  - Verified outcome (click send to first verified read) D = 1518.110 ms, CI [1516.980, 1519.355].
  - Trial wall D = 3011.956 ms, CI [3000.447, 3031.955].

Span coverage (#10 gate, >90%): the marks are contiguous from caller send to caller return, so the named phases telescope to the full span. Unattributed time is 0 by construction. Phase granularity is the limit, not coverage.

Gates as pre-registered:
- (a) verified ≥ 90% in each arm: yes.
- (b) median D ≥ 50% of the ON span: 98.46%.
- (c) the CI excludes 0: yes.
- (d) ON visualization ≥ 50% of the ON span: 98.46%.

The forced feedback path was exercised in 24/24 ON trials, and the ON span is ≥ 500 ms, so the earlier ~1.5 s span is reproduced on this source. Disposition: **KEEP_H1**.

Every number above is recomputed from `raw/` by `verify_artifacts.py` (`feedback-ab-summary.json` holds per-trial rows and all aggregates).

## Localization (what the delay is and is not)

- **Is.** `overlay::animate_cursor_to_for` on X11 sends `MoveTo` and then awaits the renderer's arrival signal, capped at 5.5 s. `browser_click` dom_event awaits that whole visualization before `Runtime.callFunctionOn`. `browser_type` does the same before text delivery.
- **Is not** target resolution (lock + revalidate + ref + DOM resolve + scroll + box model is about 12 ms in both arms), CDP dispatch (about 1 to 1.5 ms), a post-dispatch wait (`post_cdp` about 0.1 ms) or MCP transport (about 9 ms in total).
- With feedback OFF, the largest remaining phase is `revalidate` (median 11.735 ms). The page mutation lands about 8.5 ms after CDP send, near tool return. The first fresh oracle read already sees it.
- **Not profiled (NOT_RUN):** why a glide takes about 1.5 s (renderer pacing, speed-based glide distance, picom/Xvfb frame timing). The arrival wait was near-constant (1508 to 1522 ms) in this session.

## Work deleted vs wall-clock saved

- **Work deleted, structural.** With feedback OFF, each DOM click and each type skips one overlay `MoveTo` + `PinAbove` + `ClickPulse` and one awaited arrival. That is 2 awaited glides per fill-and-submit task. No CDP call, verification read, authorization check or oracle read is removed. The visibility `Runtime.evaluate` and `Page.getLayoutMetrics` calls still run in OFF (about 0.35 ms), because the engine runs them before the platform gate.
- **Wall-clock saved** (this fixture, binary and session only): median paired 1517.9 ms per DOM click, 1480.2 ms per type, and 3012.0 ms per two-action trial (ON median trial wall 4057.272 ms vs OFF 1046.436 ms).

## Negative and fallback controls

| Control | Result | Evidence class |
|---|---|---|
| No-submit (type only, oracle read after 1.0 s), 2 ON + 2 OFF | 4/4 `submitted=None`, 0 journal submits | REAL |
| Stale ref (snapshot, re-navigate, click the old Submit ref with dom_event), 2 ON + 2 OFF | 4/4 refused envelope (`effect=refused`, `isError=false`), 0 journal submits, oracle unchanged | REAL |
| Fallback route | none exists for dom_event. No measured trial refused or errored, so the failure denominator is 0/48 | REAL |
| Default-off check: stock `browser-smoke.sh` (jev-use `verify_mcp_tools.py` + `verify_setup.py`) with this lane binary and the trace unset | rc 0 / rc 0, verified `jev-guide-mock`, no trace file anywhere in the session dir. Observational: the stock runner's submit `action_ms` was 1541.46 (n=1, outside the lock, not a benchmark row) | REAL |
| Phase-trace unit tests (`cua-driver-core`, 4 new) and full `cua-driver-core` lib suite | 4/4 and 815/815 pass | UNIT |
| `platform-linux` lib suite (run inside the isolated session) | 599 passed, 0 failed, 10 ignored | UNIT |
| jev-use Python/TS suites | not touched by this change, not re-run | NOT_RUN |

Each control was checked on the structured envelope, not only `isError`. #93 recorded that `isError` alone is misleading for these refusals.

## Deviations from PREREG

1. The stale-ref refusal code was not captured. The harness looked for `code` / `refusal.code`; the envelope reported `effect=refused` with `isError=false` and no `code` at those keys. The pre-registered condition (refused envelope, no mutation) holds, but the exact code (expected `browser_ref_stale`) is unrecorded.
2. Paired secondary metrics (`browser_type`, verified outcome, trial wall) were added to the analysis after the runs. They are descriptive and are not gates.
3. The shakedown (1 ON + 1 OFF, `raw/shakedown/`) ran without the quiet lock, which the PREREG did not require. It is excluded from every number above. It showed the same pattern: ON click 1563.8 ms, OFF 47.0 ms.
4. `build-driver.sh` runs `<bin> --version` outside the isolated session (no display use), as recorded in SETUP.
5. Two earlier `platform-linux` unit-test attempts were aborted:
   - The first was started outside the session and stopped during compilation, before any test binary ran, because the host desktop variables were set in that shell.
   - The second ran in the session but failed to start cargo (the fresh HOME lacked a rustup config).

   The result reported above comes from a third run inside the session with `RUSTUP_HOME` passed in.
6. `rustfmt --check` flags formatting-only differences in the instrumentation. The tested source is kept exactly as built; nothing was reformatted after the build.

## Limits

- One fixture, one route, one browser build and one X11 session with picom/Xvfb. The glide length depends on the renderer and session and may differ on a GPU compositor, on Wayland (#94; there the wait has its own budget) or on macOS/Windows. Nothing here transfers to those platforms.
- The trace adds a file write per mark in both arms; with the trace unset, the stock runner showed the same ON span (one observation).
- n = 24 pairs. The p95 values are estimates, not tail guarantees.
- The mock provider was used, so no provider latency is included. This is not a LIVE_PROVIDER claim.

## Claim boundary

On upstream main `229b65b2` (instrumented build `7d3a28b66`, Driver 0.32.0, Chrome 151), in this private rootless Xvfb/openbox/picom session on Linux, the ~1.5 s inside the jev-use DOM-route `browser_click` and `browser_type` action spans is the awaited agent-cursor glide arrival in `visualize_browser_action`. Disabling feedback per session with the existing `set_agent_cursor_enabled false` removes it (median about 1.52 s per action) with identical route, authorization and independently verified outcome.

No claim is made about trusted input (R2-06), other fixtures, Wayland/Hyprland, macOS or Windows, live providers, or changing default behaviour. Per #93, feedback is not turned off globally on this evidence. Any product change, such as a non-blocking glide or an opt-in host knob, is a separate proposal through #73/#74.

## Disposition

**KEEP_H1** for the R2-01 cursor hypothesis (pre-registered gates a–d all met; 24/24 pairs; failures 0/48). Next owners can rank "an opt-in or non-blocking feedback mode for automation hosts" (the #93 E1 next-gate list, item 1) on this evidence, without assuming it transfers to other compositors.

## Files

- `PREREG.json`: the pre-registration.
- `run_feedback_ab.py`: the trial runner (thin; reuses jev-use).
- `verify_artifacts.py`: recomputes every headline number and checks the privacy rules.
- `feedback-ab-summary.json`, `provenance.json`, `source-head.txt`.
- `raw/trials/<trial>.jsonl` (caller events + summary with fixture journal and loadavg) and `raw/trials/<trial>.driver-trace.jsonl` (Driver marks).
- `raw/run-manifest.json`, `raw/shakedown/`, and `raw/session-*.log` (sanitized; paths shown as `<tmp>`, `<lanes>`, `<home>`).
