# RECERT-BUG01: BUG-01 recertified on upstream main a9baa8d10, 2026-10-03

BUG-01 has two parts: A, the browser receipt delivery posture, and B, CDP session accumulation. Wave 1 measured both on the 0.32.0 line (`c4d0c6625`) and they had not been recertified since. This lane re-measures them on current upstream main `a9baa8d10` (cua-driver 0.33.1) and gives each part a terminal disposition against gates pre-registered in `PREREG.json`. The harness is the wave-1 one, copied blob-identically. The test ran in a private Xvfb session with Driver-launched Chrome 151.

- **A: RECERT_PASS.** The fix is still needed and it still works.
  - Plain main `M9` labels the forced foreground trusted `browser_click` as **background 20/20**. In those same 20 trials the page's own event log saw a trusted pointerdown and click on Submit, with focus and visibility.
  - The fix build `MF9` (`a9baa8d10` + `147f2adec` + `2533db6d5` + `49a3adf0f`) labels them **foreground 20/20**.
  - With a decoy window focused, true background `dom_event` clicks are labelled background 12/12 on both binaries, and the decoy stays active 12/12.
  - Across all 94 trials per binary (70 matrix, 24 decoy), only one receipt field changed: the T-click `delivery.mode`. Receipt key sets are identical.
  - Upstream has not touched the producer: the receipt producer files are byte-identical to the BUG-01 base. The candidate is not superseded.
- **B: RECERT_PASS.** Accumulation is still present.
  - An independent second CDP client read Chrome's own command counters. In each of 3 long sessions on `M9i` it saw **304 live Driver sessions at call 301**: Chrome received 304 `Target.attachToTarget` and 0 `Target.detachFromTarget` commands. Chrome kept the page `attached`.
  - The default-off Driver counters agree exactly at every checkpoint: maximum difference 0 over 12 checkpoints.
  - The uninstrumented `M9` binary shows the same 1/102/203/304 by the observer alone.
  - The post-navigation event burst scales with the session count: **1 / 101 / 201 / 301 events at 2 / 103 / 204 / 305 live sessions**.
  - In the counters, every one of the 918 M9i Driver calls after bind (900 measured, 15 navigations, 3 trailing snapshots) attached exactly one session and detached none.

Provider: none. TypeSafe attempts 0, reached 0.

## Heads (kept separate)

| What | SHA |
| --- | --- |
| BUG-01 base (wave 1, Driver 0.32.0) | `c4d0c6625b5c93849aa8bec610782410e9d45f69` (libs/cua-driver/rust tree == `229b65b28`) |
| BUG-01 packet | `097b4f0974d5c161360fc3683c17f298ff681c70` on `exp/bug-01-delivery-cdp-sessions-20261002` |
| **Tested source base** (upstream main at lane start) | `a9baa8d107fba8b0aef5a4ed6233e498e88d14d0` (cua-driver 0.33.1) |
| Upstream main live at packet time | `fe6d89d80`: 1 commit ahead of `a9baa8d10`, with 0 files under `libs/cua-driver` (read-only `gh api compare`) |
| Fix commits (originals) | test `147f2adec`, fix `2533db6d5`, fix `49a3adf0f`; guard tests `7431f03d1`; counters `a99ee937a` |
| M9 | `a9baa8d10` |
| M9 + test (UNIT red) | `1473e00d8` (= `147f2adec`, patch-id equal) |
| M9i | `46f9b05ff` (= `a9baa8d10` + `a99ee937a`, patch-id equal) |
| MF9 | `0b43df3ab` (= `1473e00d8` + `a4695856e` [`2533db6d5`] + `0b43df3ab` [`49a3adf0f`]; every patch-id equal, no conflict) |
| MF9 + guard tests (UNIT only) | `ee98acf91` (`7431f03d1` with a positional-only conflict; resolution in `raw/guard-resolution.txt`) |
| Harness copy / PREREG / anchor merge | `c45164d2b` / `5816bc2c3` (21:23:05Z, before the first measured block at 21:23:41Z) / `8e1beaa46` |
| Packet / publication SHA | the latest commit touching this README on local branch `exp/recert-bug01-main-a9baa8d10-20261003`. The Publish agent assigns the fork SHA. There is no PR head, and nothing was posted |

`8e1beaa46` is a `merge -s ours` of `46f9b05ff` and `ee98acf91`. It leaves the branch tree as `a9baa8d10` plus this packet, and it keeps every build source reachable from the branch.

| Binary | sha256 | Version (in session) | Built from |
| --- | --- | --- | --- |
| M9 `cua-driver-recert-bug01-m9-a9baa8d10` | `4ac1ea5be1803bfa6f00551606f6c50d84d5198b84910b508fbae483209adcb0` | cua-driver 0.33.1 | `a9baa8d10` |
| M9i `cua-driver-recert-bug01-m9i-46f9b05ff` | `9261f8617229a89eb0e57ba4c25ea9351e90f87d75cae980fd95086da6e1c324` | cua-driver 0.33.1 | `46f9b05ff` |
| MF9 `cua-driver-recert-bug01-mf9-0b43df3ab` | `ea73294b9f4838fe2342631e279eea6385fb7820097e757a16c9015854c3fb32` | cua-driver 0.33.1 | `0b43df3ab` |

How the binaries were built:
- Each binary came from `flock cargo-build.lock build-driver.sh <wt> <label> cua-release-bug01` under `bin/hostless` and a SHARED quiet hold, with 0 Fresh workspace units (`raw/builds/`).
- The family target dir was seeded by a reflink copy of an existing third-party dependency cache. Its `Cargo.lock` differs from this one only in workspace crate versions, and every workspace crate was recompiled from its own worktree.
- Chrome is `Google Chrome 151.0.7922.71`, the same build as in BUG-01.
- The environment is `bin/hostless`, then `cua-x11-session.sh` (private rootless Xvfb 1920x1080x24, openbox, picom, private dbus, AT-SPI off), then `run_recert.sh`. The Driver launched an `isolated_new` profile with the Chromium sandbox on and default safety settings: no permission-mode override, no approval bypass, no `*-e2e` wrapper and no no-sandbox variable. Kernel: Linux 7.2.2.

## SOURCE map on a9baa8d10 (class SOURCE)

`git diff c4d0c6625 a9baa8d10` is **empty** for `cua-driver-core/src/action_record.rs`, `src/browser/` (every file) and `src/tool.rs`, and for `examples/jev-use`. Upstream changed none of the sites below after the BUG-01 base. The 74 files that drifted under `libs/cua-driver` are macOS, Windows, Linux overlay/Wayland, installer, e2e harness and contract/schema files. None of them is on these paths.

**Part A: receipt delivery producer.** Paths below are under `libs/cua-driver/rust/crates/cua-driver-core/src/`.

| Site (a9baa8d10) | What it does |
| --- | --- |
| `browser/tools.rs:68` `parse_delivery_mode` | parses the request's `delivery_mode` |
| `browser/tools.rs:1010`, `:1033-1050` (`BrowserClickTool`) | refusal gate: the trusted route with `foreground=false` on a standalone CDP window (`cdp_window_id`) on a platform with `standalone_trusted_input_background_limitation()` is refused before dispatch. On Linux Chromium this leaves only the foreground (activating) branch to execute trusted input |
| `browser/tools.rs:1325` | producer stamp `"delivery_mode": if foreground {"foreground"} else {"background"}`. It is derived from the request, not from the executed branch |
| `browser/pointer.rs:176`, `:375-393`, `:546-560` | the same gate for `browser_pointer`; its success payload states no `delivery_mode` |
| `action_record.rs:464-480` `from_legacy` -> `:945` `actual_delivery_from_legacy` | **`:956-961`: `browser_click`/`browser_pointer`/`browser_type` return `ActualDelivery::Background` unconditionally**, before the producer field is read (`structured_delivery_mode` at `:985` is never reached for browser tools) |
| `action_record.rs:337` `public_result` | the closed `ActionResult` published to MCP; the legacy payload, including the producer stamp, is not published |

In MF9, three sites change:
- `action_record.rs:958-970` maps browser tools to `Foreground` only when the producer states `foreground`.
- `browser/tools.rs:86` `trusted_delivery_mode` states `foreground` only when the request is foreground AND the tab has a standalone CDP window AND the platform has the limitation. Otherwise it states `background`.
- `browser/tools.rs:1350` (click) and `browser/pointer.rs:555` (pointer) state that executed-branch posture.

**Part B: CDP session attach/detach.**

| Site (a9baa8d10) | What it does |
| --- | --- |
| `browser/engine.rs:1202-1229` `attach()` | `Target.attachToTarget {targetId, flatten: true}` on the browser-level connection (`conn.call(None, ...)`), returns a new `sessionId` |
| callers `engine.rs:1599` (`revalidate_for_mutation`), `:1955` (`capture_tab_screenshot`), `:2052` (`snapshot_tab`), `:2529` and `:2628` (`snapshot_tab_semantic`) | one fresh attach per tool call; the session id is not cached or reused |
| `engine.rs:2197`, `:2715` | the **only** `Target.detachFromTarget` calls. They detach OOPIF *child* sessions through the tab session. No code path detaches a tab session |
| `browser/cdp_ws.rs:68-69` | `Target.attachToTarget`/`detachFromTarget` in the existing-profile method allow-list (policy only) |

## Method

**Part A.**
- **A1 forced path (T):** `browser_type {ref: textbox, token, replace}`, then `browser_click {ref: Submit, delivery_mode: "foreground"}` on the default trusted route (CDP `Input.dispatchMouseEvent`). On Linux Chromium this is the branch that activates the browser window.
- **Plan:** the unchanged `harness/probe_delivery.py`. Per binary it runs 7 fresh Driver+browser blocks: 20 T, 20 D (`dom_event`), 20 Y (type only), 5 N_bg (trusted click with no `delivery_mode`, expected refused) and 5 N_domfg (`dom_event` with a stray foreground request).
- **Interleaving:** each block ran as one SHARED hold of an AB pair. Odd blocks ran M9 then MF9, even blocks MF9 then M9 (`raw/logs/recert-bug01-A1-b*.log`).
- **Actual route and producer:** the receipt `route=trusted_input` comes only from `BrowserClickTool`'s trusted branch. The page saw a trusted pointer chain, so that branch executed. The executed-branch stamp itself, the producer `delivery_mode` from `trusted_delivery_mode`, is read in UNIT, because the dispatch seam replaces the legacy payload with the closed `ActionResult`.
- **Independent, target-owned oracle:** the fixture page's own capture-phase log (sendBeacon). It records `isTrusted`, `document.hasFocus()` and `visibilityState` at the pointerdown and click on Submit. It is complemented by the fixture `/state` == token and the `POST /submit` journal. `page_trusted_foreground` means: the first pointerdown on Submit is trusted, focused and visible, and the first click on Submit is trusted.
- **A-decoy:** the unchanged `harness/probe_activation.py`. A Tk decoy window is made active (`xdotool windowactivate --sync`) before every click. Two invocations of 2 blocks per binary gave 12 D (true background `dom_event`) and 12 T. The pairs ran M9 then MF9, then MF9 then M9.
- **A-shape:** for every arm, the distributions of `effect`, `route`, `delivery_mode`, `delivered_count`, `evidence`, `escalation`, `error` and `summary_template` (the harness `analyze_a.receipt()`), and the receipt key sets, compared M9 against MF9. This covers click and type receipts in the matrix and in the decoy runs.

**Part B.**
- **Probe:** `probe_sessions_observed.py` imports the unchanged `harness/probe_sessions.py`. It runs `--series L --long-calls 300`: one Driver and browser, `set_agent_cursor_enabled false`, `browser_prepare isolated_new`, bind, then a setup navigate. Calls alternate: even k is `get_browser_state semantic_v2`, odd k is `browser_click {No-op, dom_event}`. Navigation probes run before k=0, 100 and 200 and after k=299.
- **Trailing call:** one trailing semantic snapshot after the last navigation lets B2 see the burst at call 301. The original probe ends the session with that navigation.
- **Sessions:** 3 long sessions on M9i (counters on) and 1 on plain M9 (observer only, descriptive), in the order M9i, M9i, M9, M9i. Each ran in its own SHARED hold.
- **Independent observer (`cdp_observer.py`):** a second CDP client on its own browser-level WebSocket, using the port from the profile's `DevToolsActivePort`. It never attaches to the page and sends only `Target.getTargets` and `Browser.getHistograms`.
  - Chrome counts every CDP command it receives in the sparse histograms `DevTools.CDPCommandFromRemoteDebugger` (browser-level) and `DevTools.CDPCommandFromDevTools` (session-routed).
  - Each bucket is a method-name hash: the low 32 bits of the first 8 MD5 bytes, big-endian (`cdp_hist.py`). This was identified in the plumbing pilot.
  - The hash is re-calibrated in every sample: the `Browser.getHistograms` bucket must equal the observer's own sample count, because the Driver never sends that command. It held in 20/20 samples.
  - The independent live count is `live_indep` = attach commands Chrome received − detach commands Chrome received, summed over both histograms.
- **Checkpoints:** calls 1, 101, 201 and 301 are the samples taken immediately before the navigation probe at k = 0, 100, 200 and 300.
- **Cross-check:** against the counter line written last before each sample.
- **B2:** the counters' `events_delta` for the first call after each navigation probe.

**UNIT.**
- `cargo test --locked -p cua-driver-core --lib` was run on the target tests, then on `browser::` + `action_record::`. Also run were `-p cua-driver-contract` and the `cua-driver` receipt goldens (`compatibility_contract_test`, `protocol_tools_call_test`, `schema_consistency_test`).
- Trees: `1473e00d8` (red) and `0b43df3ab` (MF9). As an extension, the two guard tests ran on `ee98acf91`.

## Results

### Part A (94 trials per binary: 70 matrix + 24 decoy; 0 harness errors)

| Row | M9 `4ac1ea5b…` | MF9 `ea73294b…` | Class |
| --- | --- | --- | --- |
| **A1 T receipt `delivery.mode`** | **background 20/20** | **foreground 20/20** | REAL |
| A1 T page trusted-foreground (page log: trusted pointerdown+click on Submit, hasFocus, visible) | 20/20 | 20/20 | REAL |
| A1 T mislabel (background while page saw trusted foreground) / correct | 20/20 / 0/20 | 0/20 / 20/20 | REAL |
| A1 T receipt route / effect | trusted_input 20/20 / unverifiable 20/20 | same | REAL |
| A1 T X11 active = browser pre and post (reported, not gated) | 20/20 | 20/20 | REAL |
| A1 T verified (`/state` == token), submit POSTs | 20/20, 20 | 20/20, 20 | REAL |
| D receipt delivery / route / verified / page click trusted | background 20/20 / dom 20/20 / 20/20 / 0/20 | same | REAL |
| Y `browser_type` only: receipt delivery, `/state` stays null | background 20/20, 20/20 | same | REAL |
| `browser_type` receipt delivery in all 70 matrix trials | background 70/70 | background 70/70 | REAL |
| N_bg (negative control): click refused (not accepted), no `delivery`, `/state` null, 0 POSTs | 5/5 | 5/5 | REAL |
| N_domfg (stray foreground request on `dom_event`): route dom, delivery background, verified | 5/5 | 5/5 | REAL |
| **A-decoy D** (decoy active before; `dom_event`): receipt background, page click untrusted, decoy still active after, verified | **12/12** | **12/12** | REAL |
| A-decoy D page `hasFocus` at click | 2/12 | 2/12 | REAL |
| A-decoy T: decoy active before / browser active at first sample and after | 12/12 / 12/12, 12/12 | same | REAL |
| A-decoy T receipt `delivery.mode` | background 12/12 | foreground 12/12 | REAL |
| A-decoy T page click trusted, hasFocus; verified | 12/12, 12/12; 12/12 | same | REAL |
| **A-shape**: receipt field distributions changed M9 → MF9 | | only click T `delivery_mode` (matrix and decoy); key sets identical | REAL |
| Failing test `foreground_trusted_browser_input_receipt_does_not_claim_background_delivery` at `1473e00d8` / at `0b43df3ab` | FAILED | ok | UNIT |
| Background guard `background_browser_receipts_keep_background_delivery` | ok | ok | UNIT |
| `cua-driver-core` `browser::` + `action_record::` (208 tests) | 207 ok, 1 FAILED (the red test) | 208 ok | UNIT |
| `cua-driver-contract` (63) + receipt goldens (8) | 71 ok | 71 ok, identical outcomes | UNIT |
| Executed-branch guard tests (`7431f03d1`: no limitation; embedded route) at `ee98acf91` | | ok, ok | UNIT (extension) |

### Part B (M9i: 3 × 300 measured calls; M9: 1 × 300; 1200/1200 accepted, 0 transport errors)

| Row | M9i L1 | M9i L2 | M9i L3 | M9 (observer only) | Class |
| --- | --- | --- | --- | --- | --- |
| **live_indep at call 1 / 101 / 201 / 301** (Chrome-received attach − detach) | 1 / 102 / 203 / **304** | 1 / 102 / 203 / **304** | 1 / 102 / 203 / **304** | 1 / 102 / 203 / 304 | REAL |
| Chrome-received `Target.detachFromTarget` (any session) | 0 | 0 | 0 | 0 | REAL |
| Page target `attached` (Target.getTargets) at the 4 checkpoints | true 4/4 | true 4/4 | true 4/4 | true 4/4 | REAL |
| Driver counters `live_sessions` at the same checkpoints | 1 / 102 / 203 / 304 | same | same | n/a | REAL |
| Cross-check max abs difference; observer calibration | 0; 5/5 | 0; 5/5 | 0; 5/5 | n/a; 5/5 | REAL |
| Counters: attach/detach per call (all calls after bind) | 1/0 in 306/306 | 1/0 in 306/306 | 1/0 in 306/306 | n/a | REAL |
| **B2 post-navigation burst**: events in the next call at call 1 / 101 / 201 / 301 | **1 / 101 / 201 / 301** | same | same | n/a | REAL |
| live sessions before that call | 2 / 103 / 204 / 305 | same | same | n/a | REAL |
| events during the navigation call itself | 1 at each probe | same | same | n/a | REAL |

The observer reads Chrome's own per-command counters, so it is independent of Driver self-report. It counts commands *received*. A session Chrome dropped on its own would not show up there. The `attached` flag and 0 `detachedFromTarget` events in the counters rule that out here. The count discriminates: it reads 0 after prepare and 1 at call 1, and rises linearly to 304.

### Disposition

**A: RECERT_PASS**. All pre-registered gates pass, and `verify_artifacts.py` recomputes them from `raw/`:
- M9 mislabels 20/20 (gate ≥ 18);
- MF9 is correct 20/20;
- the decoy D is correct 12/12 on both binaries;
- A-shape shows no other change.

FIXED_UPSTREAM does not apply: M9 is correct 0/20, against a threshold of ≥ 19.

The fix candidate `2533db6d5` + `49a3adf0f` is not superseded. It replays onto `a9baa8d10` with equal patch-ids and no conflict, and it still turns the red test green without changing any other unit outcome. Routing is unchanged: kvnloo/cua#38, and upstream trycua/cua issue 4009 (plain text; open at read time).

**B: RECERT_PASS** (still accumulating). In each of the 3 M9i sessions, live_indep at call 301 is 304, against a gate of ≥ 290, and the cross-check holds with a maximum difference of 0. The BUG-01 reading is unchanged on 0.33.1: one undetached flattened tab session per browser call, and one extra post-navigation event per accumulated session. Routing: upstream trycua/cua issue 4052 (plain text). Its state at read time was **closed**, so the #74 queue entry for B needs a live owner before anything is posted.

**E4.**
- 0 unverified successes: success is counted only from `/state`, and accepted T/D/N_domfg clicks without verification were 0 on both binaries, in the matrix and the decoy runs.
- 0 duplicate dispatches: there were 0 trials with more than one submit POST and 0 T trials with more than one trusted pointerdown on Submit.
- Part B: 1200/1200 calls were accepted, with 0 transport errors.

## Five mechanism requirements

1. **Forced path.**
   - A: the trusted foreground click branch, forced by `delivery_mode: foreground` on the default trusted route. The decoy run forces true background `dom_event` with another window active.
   - B: 300 alternating snapshot and no-op calls on one Driver/browser, with navigation probes at fixed points.
2. **Actual route/producer.**
   - A: receipt `route=trusted_input` (A1 T) versus `dom` (D). The executed-branch stamp (`trusted_delivery_mode`) is pinned in UNIT.
   - B: the attach site `engine.rs:1202`, confirmed per call by the counters (1/0) and by Chrome's own attach count.
3. **Independent target-owned oracle.**
   - A: the page's own event log (`isTrusted`, `hasFocus`, `visibilityState`) and fixture `/state`, plus the X11 active window in the decoy run.
   - B: Chrome's command histograms, read by a second CDP client, and Chrome's `attached` flag.
4. **Negative/fallback controls.**
   - A: N_bg (refused before dispatch, 0 page events), N_domfg (a request alone does not make foreground), D in the matrix and with a decoy (true background stays background), Y (type receipts stay background).
   - B: the plain M9 run (uninstrumented, same counts), the observer's own calibration bucket, and the count reading 0/1 at the start of every session.
5. **Exact provenance.** See Heads, `provenance.json`, `harness/MANIFEST.json` and `raw/patch-ids.txt`.

## Work deleted vs wall-clock saved

None claimed.
- A is a receipt-truthfulness fix. It changes no dispatched work and adds 0 ms.
- B is a recertified diagnosis. Reusing one session per Cua session and tab would delete 1 `Target.attachToTarget` per browser call and N−1 duplicate event deliveries per navigation. The wall-clock effect was not measured: this is not a timing lane, and every wall time here is descriptive.

**Component timings.** Not applicable (no timing claim). For description only:
- one 300-call long session took about 15 s;
- the A1 pair holds took 65–97 s.

## Deviations

1. **Pilots before the PREREG.** Three part B plumbing pilots ran on M9i and M9, with 20-call sessions (`raw/pilot/`). They were used to build the observer and to identify the histogram hash. They are excluded from every number. No part A pilot ran.
2. **UNIT before the PREREG.** The UNIT red/green `target` steps (21:17–21:23Z) started before the PREREG commit (21:23:05Z). The `browser`, `contract` and `guard` suites ran after it. The red/green expectation was fixed by the lane spec before any run, and the red outcome matches BUG-01.
3. **A-decoy n.** n = 12 D per binary rather than 10, because the unchanged harness runs 3 D per block. The gate uses all 12.
4. **Trailing call.** `probe_sessions_observed.py` adds one trailing snapshot after the last navigation probe, for B2 at 301 (declared in the PREREG). It is not a measured call and is excluded from the 300.
5. **Lock holds.** Three SHARED holds exceeded 300 s while waiting for the shared cargo lock under other lanes' builds: build-mf9 336.6 s, unit-mf9-browser 328.0 s and unit-red-contract 325.3 s.
   - Two streams of this lane's SHARED holds overlapped: cargo tests and REAL blocks. The 30 s spacing held within each stream, not across them.
   - No hold saw a queued EXCLUSIVE waiter at acquire, and none had to yield (`raw/locks/ledger.jsonl`).
   - Load average was high, 6.6–46.6 (1-minute), because other lanes were running. The rows are non-timing.
6. **Guard tests.** `7431f03d1` replays with a positional conflict (`raw/guard-resolution.txt`). The added lines are byte-identical; only the patch-id differs.
7. **Formatting.** `147f2adec` and `a99ee937a` are still not rustfmt-clean (BUG-01 deviation 10). The BUG-01 rustfmt-only commit `8f52c55a7` was not replayed. This does not affect any binary or test outcome.
8. **Seeded target dirs.** The cargo target dirs were seeded from existing dependency caches by reflink copy (see Heads). Every workspace crate was rebuilt (0 Fresh workspace units).

## Limits and claim boundary

The claim covers Linux X11 in a private Xvfb, Chrome 151 launched by the Driver with an `isolated_new` profile (Unrestricted CDP policy), the jev-use fixture, and Driver 0.33.1 at `a9baa8d10`. It covers receipt honesty and session hygiene only, and makes **no timing claim**.

Not claimed:
- macOS, Windows or Wayland delivery semantics. The executed-branch logic for those is UNIT-only, on mock CDP.
- `browser_pointer` REAL behaviour (UNIT only).
- The existing-profile CDP policy path.
- Whether accumulation causes latency or memory effects. These were not measured here.

The fix candidate is a candidate for review: nothing was published or sent upstream.

## Files

- `PREREG.json`, `README.md`, `provenance.json`, `recert-bug01-summary.json`
- `analyze_recert.py`: recomputes every number from `raw/`.
- `verify_artifacts.py`: checks harness blob identity, recomputes the summary and gates, and checks binary hashes, lock windows, PREREG order, commits and patch-ids. It also runs a privacy scan.
- `harness/`: blob-identical BUG-01 probes, helpers, `run_in_session.sh` and `analyze_a.py`, with `MANIFEST.json`.
- `run_recert.sh`: a path-only wrapper. `cdp_observer.py`, `cdp_hist.py` and `probe_sessions_observed.py` make up the independent observer.
- `raw/`:
  - `part-a/` (per-trial JSONL, block metadata, session env), `part-a-decoy/`, `part-b/` (calls, counters, observer);
  - `unit/`, `builds/`, `logs/`, `pilot/` (excluded), `locks/ledger.jsonl`;
  - `versions-in-session.txt`, `patch-ids.txt`, `guard-resolution.txt`.

Raw outputs are mirrored under the lanes artifacts dir `artifacts/r2/RECERT-BUG01/`.

Reproduce, from inside `bin/hostless`, with each step under a SHARED quiet hold:

```
<lanes>/cua-x11-session.sh <packet>/run_recert.sh <wt> <M9|MF9 bin> harness/probe_delivery.py --out <dir> --driver-label <m9|mf9> --blocks <b>
<lanes>/cua-x11-session.sh <packet>/run_recert.sh <wt> <M9|MF9 bin> harness/probe_activation.py --out <dir> --blocks 2
<lanes>/cua-x11-session.sh <packet>/run_recert.sh <wt> <M9i bin> probe_sessions_observed.py --out <dir> --series L --long-calls 300 --label measured
python3 verify_artifacts.py
```
