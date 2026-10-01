# R2-06: trusted-input miss diagnosis, 2026-10-01

## Result in one paragraph

On upstream main `229b65b28` (Driver 0.32.0), the trusted `browser_click` route was accepted in **30/30** trials and independently verified in **30/30** within a 3000 ms bounded fresh re-read of the fixture's `/state`. Only **17/30** were verified by a single `/state` read taken as soon as the tool returned. The other **13/30** were late effects, not lost input. In each of them the page logged a trusted `pointerdown` → `click` on Submit → `submit`, and the fixture logged exactly one POST. That POST reached the fixture **2.3–10.1 ms after `browser_click` returned**, which is after the first read. Across all 70 verified T/D/plain trials, POST timing separates the two classes completely: every immediately verified trial had its POST land ≤ 1.8 ms after the tool returned, and every late one ≥ 2.3 ms. The dom_event control verified immediately in **30/30**. With one read at tool return, this gives the E1 shape (accepted 5/5, verified 2/5). The uninstrumented-page check came out **2/5** immediate and 5/5 bounded. No miss came from lost X input, focus, window activation, geometry or DPR. The smallest fix needs no Driver change: after an accepted trusted click, the caller re-reads the target-owned oracle until a bounded deadline. Applied to the same T receipts, that verifier gives 30/30, against 17/30 for a single read. Disposition for H: **KEEP** (pre-registered gate met). We cannot confirm that E1's own misses had this cause, because the E1 harness, its verification protocol and the 0.31.0 run were not kept.

## Scope

- Owner: kvnloo/cua#93 `R2-06` (original `E1`). #73 settles the queue; #10 sets the reporting rule.
- Forced path: ref-addressed `browser_click` on the jev-use fixture's Submit, with `delivery_mode:"foreground"` and the default `input_route` (trusted). This is CDP `Input.dispatchMouseEvent`. On Linux, trusted background delivery is refused by contract (control `N_bg`), so foreground is the only trusted `browser_click` path. Before every click, `browser_type` puts a per-trial token into the `verification value` textbox.
- Actual route/producer: the public envelope reports `route:"trusted_input"` for T and `route:"dom"` for D. The page journal confirms the producer: T clicks are `isTrusted:true` with `pointerdown`/`mousedown`/`mouseup`/`click` at the Driver's point; D clicks are a single `isTrusted:false` `click` (synthetic `el.click()`).
- Independent target-owned oracle: the fixture's `/state` (`submitted == token`), read by the probe over HTTP. The fixture's POST `/submit` receipt is the target journal. The Driver's result never counts as the oracle; its `effect` is `unverifiable` on both routes.
- No Driver code change and no new service. All instrumentation is caller-side or page-side, used only for measurement: a probe subclass of the jev-use fixture server appends a listener script to the page and journals POSTs. The fixture's `/state` and `/submit` semantics are unchanged.

## Provenance (kept separate)

| Item | Value |
|---|---|
| Tested source | `229b65b2849c3a595ddbc85200d7181b18bd2e47` (upstream main at setup) |
| Live upstream main (gh, 22:10Z) | `effd9b298942d7e9808077adef4ef575d561141d`: 1 commit ahead, `release-please-config.json` only. **Not certified here.** |
| Live PR head | n/a (R2-06 tests main, not a PR) |
| Driver binary | `cua-driver-r2-main-229b65b28`, sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3`, `cua-driver 0.32.0` (MCP serverInfo 0.32.0 in all 8 blocks); built by the R2 setup worker, not rebuilt |
| Pre-registration | `PREREG.json` sha256 `4f88adc786ae0ddc4f79bbdabda09850b34502d000f001e61d10e6a13c93f840`, commit `138f091fb` at 22:03:53Z; the measured run took the quiet lock at 22:04:05Z |
| Publication SHA | recorded later by the orchestrator |

Full details are in `provenance.json` and `source-head.txt`.

## Environment

The run used `cua-x11-session.sh`: a private rootless Xvfb at 1920x1080x24 with openbox, picom and a private dbus, under a scrubbed environment with no Wayland or Hyprland variables. There was no AT-SPI bus. The browser was Google Chrome 151.0.7922.71, chosen by the Driver (this version comes from the setup smoke). Driver safety settings were left at their defaults: Chromium sandbox on, no permission override, no approval bypass. Telemetry was at its default, the same in every arm. The browser window was at (10,10), 945x1060, with a 937x969 viewport and DPR 1. The X pointer was parked at (1910,1070), outside the browser window, by the recorder positive control. The whole measured session ran under `quiet-lane.lock`. Other agents' correctness lanes were running, so the 1-minute loadavg ranged from 3.1 to 11.9; it is recorded for every trial.

## Method

- 8 blocks. Each block started a fresh Driver MCP process and a fresh `isolated_new` browser.
- Blocks 1–6: 10 trials each, alternating `ABBAABBAAB` / `BAABBAABBA` with A = T and B = D, giving 30 T + 30 D.
- Block 7: controls, each run 3 times and interleaved.
- Block 8: the plain (uninstrumented) page, T_plain/D_plain `ABBAABBAAB` (5 + 5).
- Every trial: `/reset`, then `browser_navigate`, then wait for the page `load` beacon, then `get_browser_state semantic_v2`, then `browser_type` the token, then the click, then fresh reads (one immediately, then every 50 ms up to 3000 ms).

Each trial was traced through these layers:

1. Acceptance: the MCP result. Acceptance means no `isError`, no refusal and no `effect:"refused"`.
2. X input delivery: `xinput test-xi2 --root` lines with timestamps during the tool span. A positive control at session start (two XTest motions on the bare root) produced `RawMotion`/`Motion`, so the recorder was live.
3. Page event: capture-phase listeners record type, `isTrusted`, client/screen coordinates, target, `elementFromPoint`, the Submit rect, DPR, viewport, window offset and `document.hasFocus()`.
4. Handler: the `submit` and `invalid` events.
5. Target journal: the fixture POST.
6. Fresh verification.
7. Focus/activation: `xdotool getactivewindow`/`getwindowfocus`, `_NET_ACTIVE_WINDOW` and window geometry, before and after the click.

All timestamps are wall-clock epoch ms from the same host kernel clock: page `performance.timeOrigin+now()`, server receive time, and probe `time.time()`. Durations use `perf_counter`.

## Results

`verify_artifacts.py` recomputes every row from `raw/main/`.

| Row | N of M | Evidence class |
|---|---|---|
| T trusted: tool accepted | 30/30 | REAL |
| T: verified by a single read at tool return | **17/30** | REAL |
| T: verified within the 3000 ms bounded re-read | **30/30** (13 late; first verified 52.9 / 54.2 / 55.9 ms min/p50/max, which is the second read at 50 ms resolution) | REAL |
| T: trusted `pointerdown` on Submit / `click` on Submit / `submit` event / exactly one token POST | 30/30 each | REAL |
| T: late class = POST landed after tool return | 13/13 late POSTs landed +3.6 to +10.1 ms after return; immediate POSTs landed −49.7 to +1.0 ms | REAL |
| T + D + plain: POST timing separates immediate (n=54, max +1.83 ms) from late (n=16, min +2.32 ms) | separated, 70/70 verified trials | REAL |
| T: late trials spread across blocks | late T in all 6 blocks (2, 4, 1, 1, 3, 2); 2 of 6 block-first T trials were late | REAL |
| D dom_event: accepted / verified immediately / exactly one POST | 30/30 / 30/30 / 30/30 | REAL |
| X11 events of any kind in tool spans (T + D) | 0 (recorder live: positive control `RawMotion` 2) | REAL |
| T: browser window active (`getactivewindow`) before / after click | 30/30 / 30/30 | REAL |
| T: `document.hasFocus()` true at `pointerdown` | 30/30 | REAL |
| T: Driver point inside the Submit rect at load / at `pointerdown`; rect moved; resize events | 30/30 / 30/30; 0; 0 (DPR 1, viewport 937x969, window offset (10,10) in every trial) | REAL |
| T_plain (uninstrumented page): single read / bounded | 2/5 / 5/5 | REAL |
| D_plain: single read / bounded | 5/5 / 5/5 | REAL |
| Verifier arm on identical T receipts: single-read vs bounded fresh re-read | 17/30 vs 30/30, no extra dispatch, 1 POST per trial | REAL (same receipts, verifier-only arm) |
| Driver code change / lane binary / unit suites | none / not built / NOT_RUN (no source touched) | SOURCE |
| E1's own misses had this cause | not confirmable (E1 harness, protocol and run not retained) | NOT_RUN |
| Conditional X4316 arm | not triggered (H = KEEP, not REVISE) | NOT_RUN |

Descriptive timing only, not a speed claim. Median click tool time was 1613.0 ms for T and 1564.7 ms for D (nearest-rank p95 1675.4 / 1578.5 ms). In T, the trusted `pointerdown` arrives at a median of 1579.7 ms into the tool span, so about 1.55 s of the span comes before input dispatch. That is R2-01's question (cursor/feedback causality), not this lane's.

### Negative / fallback controls (block 7)

| Control | Expected | Observed |
|---|---|---|
| `N_bg` trusted, background | refusal, no page input | 3/3 `effect:refused` `browser_input_trust_unavailable`, 0 page pointer events, `/state` null |
| `N_stale` ref from before a re-navigation | refusal | 3/3 refused `browser_ref_stale`, `/state` null |
| `N_blank` trusted at (8,8) | accepted, no effect | 3/3 accepted, trusted `pointerdown` hit `body`, 0 submit, 0 POST, `/state` null (accepted ≠ effect) |
| `N_empty` trusted Submit, no typing | HTML validation blocks submit | 3/3 accepted, `pointerdown` on Submit, 1 `invalid` event, 0 POST, `/state` null |

The refusal envelopes leave `isError` unset. A probe that checked only `isError` would wrongly count `N_bg`/`N_stale` as accepted; E1 recorded this same pitfall.

## Diagnosis and proposed fix

Cause of the reproduced miss: **verification-timing race (late effect)**. A trusted `browser_click` returns once CDP acknowledges `Input.dispatchMouseEvent` and focus emulation has been unwound. The page's `click` → `submit` → form-POST navigation then finishes asynchronously, a few milliseconds later. A verifier that reads the target once at tool return can observe the old state. A synthetic `el.click()` (dom_event) starts the submission inside the `Runtime.callFunctionOn` round-trip, so its POST landed within +1.8 ms in every trial. The input was not lost: every trusted click reached the page as trusted events at the right point on the right element, with the page focused and the window active.

Smallest fix, proposed only and with nothing applied to default behaviour: after an accepted trusted click, re-read the target-owned oracle until a bounded deadline. The negative first read stays **unknown**. It must not authorise a retry or a replay while the effect may still land; here a replay would have double-submitted in 13/30 trials. This needs no Driver change, contract delta or new service. The jev-use runner's own completion loop already polls (20 × 100 ms), so it is not affected; only single-read probes like E1 are. A possible doc-only follow-up: the `browser_click` description already says to "refresh page state and verify", and it could add that the trusted route's effect can land after the tool returns. Measurement-only arm: the verifier arm on identical receipts, 17/30 → 30/30.

## Work deleted vs wall-clock saved

- Work deleted: none. The fix adds a bounded wait to verification and deletes no stage. The structural conclusion is that a caller must not delete the bounded re-read after a trusted click.
- Wall-clock saved: none claimed. The bounded re-read costs one extra 50 ms poll in 13/30 T trials (first verified at about 53 ms). Read cadence, not effect latency, sets that number: the effect itself landed at most 10.1 ms after return.

## Deviations

1. `PREREG.json` `written_utc` says `22:10Z`. The actual commit time is `22:03:53Z`, which is authoritative; the field was an estimate. The file was not edited after the run.
2. The prereg named the immediate read "at tool return". Its exact latency after return was not stored per trial; reads start within a few ms of the probe receiving the MCP response. The late/immediate split therefore depends on caller read latency, and the 13/30 rate is specific to this caller, host load and machine.
3. Harness-development pilots ran before the prereg: 2 sessions × 2 trials, disclosed in the prereg, kept under `raw/pilot/`, and excluded from every denominator. In pilot-1 the harness acceptance flag was miscomputed (it checked `status` on the public envelope); this was fixed before the prereg.
5. After the measured run, `probe_trusted_input.py`'s sanitiser table was edited to remove literal local paths from the packet. It now derives the lanes and temp roots at runtime and changes nothing else. The run itself used the version committed with the prereg (`138f091fb`). `git diff 138f091fb -- probe_trusted_input.py` shows the edit.
4. Before the prereg, `xinput --help` was mistakenly run once outside the isolated session. It was a read-only invalid-argument call (`unable to find device --help`) against the host X server, with no input or window change. Every experiment run used the isolated session.

## Limits and claim boundary

- Covered: Linux, a private Xvfb/openbox X11 session, Chrome 151 chosen by the Driver, the jev-use fixture form only, main Driver 0.32.0 built from `229b65b28`, this caller and this host under the recorded load.
- Not covered: Hyprland/Wayland (#94), macOS, Windows, other pages or handlers, other Chromium builds, the 0.31.0/#4316 binary that E1 used, or `effd9b29`. 30/30 bounded verification is not universal certification of the trusted route.
- The late-effect rate (13/30) depends on caller read latency and load. It is not a property of the Driver.
- The X layer is not on the trusted browser path: CDP input never reached the X server, and zero XI2 events were recorded during either route. This says nothing about the Driver's native (non-browser) pointer routes.
- Timing alignment uses one host's wall clock across processes (page, server, probe). The mid-ms ordering between POST arrival and the first read is accurate to about 1 ms.

## Disposition

**KEEP H.** Every part of the pre-registered gate was met:
- 13/30 T trials failed a single read at tool return.
- 30/30 accepted T trials showed the full trusted page chain with exactly one POST, and verified within the bound.
- All controls behaved as expected.

The trusted route stays unpromoted on speed: R2-01 owns the ~1.55 s pre-dispatch span, and there is no reliability or speed win over dom_event. On reliability, accepted-then-verified-later is the expected trusted-route behaviour on this fixture, and its verification must be bounded. The RFC/contract delta is **none**.

## Files

- `PREREG.json`: pre-registration (sha above).
- `probe_trusted_input.py`, `make_plan.py`, `run_in_session.sh`: the harness (in-session only).
- `raw/main/`: one JSONL per trial (`NNN-ARM-xxxxxx.jsonl`), `block-NN.json`, `session-env.json`, `plan.json`, `probe-stdout.log`. `raw/pilot/`: excluded pilots.
- `analyze.py`: recomputation. `r2-06-summary.json`: its output. `verify_artifacts.py`: checks the headline numbers, the prereg hash and the privacy scan.
- `provenance.json`, `source-head.txt`.

Reproduce from this directory: `python3 verify_artifacts.py`. A re-run needs the commands in `provenance.json`, inside the isolated session only.
