# BUG-01: browser receipt delivery attribution (A) and CDP session accumulation (B), 2026-10-02

Two Driver bugs suspected in wave 0. Both were measured on upstream main `c4d0c6625` (Driver 0.32.0; its `libs/cua-driver/rust` tree is identical to `229b65b28`), with Chrome 151 in a private Xvfb session on the jev-use fixture.

- **A: CONFIRMED_BUG, with a reviewed fix candidate (`2533db6d5` + `49a3adf0f`).** On the baseline, all 20 of 20 foreground trusted `browser_click` receipts said `delivery.mode=background`. In the same 20 trials, the page saw a trusted pointer chain on Submit with focus and visibility, and the click verified 20/20. A decoy-window control (an extension added after round-1 verification, not pre-registered) shows the posture directly. With another window active before each click, the trusted foreground click made the browser the active X11 window 6/6, while the DOM click left the decoy active 6/6, on both binaries. The failing test fails at main and passes with the fix. Round-1 verification found that the first fix commit `2533db6d5` copied the *request* into the producer's `delivery_mode`. On a platform without the Linux limitation, or on an embedded route, a foreground request runs exactly the same background dispatch, yet it would have been reported as foreground. `49a3adf0f` states foreground only when the executed branch activates the window. Two new guard tests are red at `7431f03d1` and green at `49a3adf0f`. With the final fix binary, the matrix reports `foreground` 20/20 for T. D, Y and both controls keep their baseline labels, and no other receipt field changed. Contract and receipt-golden suites pass at main+test and at the fix.
- **B: ACCUMULATION_ONLY**, a pre-registered intermediate outcome. Every measured browser call sent exactly 1 `Target.attachToTarget` and 0 detaches: 1800 of 1800 calls. One long Driver session therefore ends with **304 live CDP sessions** after 300 calls (slope 100.9 per 100 calls, CI [100.86, 101.05]). Per-call event volume on the no-op workload stays flat (slope +0.23 events per 100 calls, CI [−0.49, +1.42]), and so does latency (−0.05 ms per 100 calls, CI [−0.16, +0.18]; long minus fresh-session control +0.004, CI [−0.16, +0.34]). An exploratory, not pre-registered, reading shows where the leak bites. After each page navigation, the next call received one event per accumulated session: 1, 101 and 201 events at 2, 103 and 204 live sessions, in each of the 3 long sessions.

Provider: none. Attempts 0, reached 0.

## Heads (kept separate)

| What | SHA |
| --- | --- |
| Upstream main tested | `c4d0c6625b5c93849aa8bec610782410e9d45f69`. Rust tree equals `229b65b28` (`git diff --quiet 229b65b28 c4d0c6625 -- libs/cua-driver/rust` exits 0) |
| Upstream main live at packet time | `8d4e7a086`. It is 1 commit ahead and touches no file under `libs/cua-driver` (read-only `gh api compare`) |
| PREREG | `d0d63f296` (committed before any measured trial) |
| Failing test (main + test) | `147f2adec` |
| Part B instrumentation (default-off) | `a99ee937a` |
| Part A fix, first commit | `2533db6d5` (its own commit, after the failing test; cherry-picks cleanly onto `147f2adec` without the instrumentation, checked with `git merge-tree`). Alone it is superseded: it derived the producer field from the request |
| Part B repro (ignored test) | `ec88394cd` |
| rustfmt-only | `8f52c55a7` |
| Executed-branch guard tests | `7431f03d1` (red at this commit, i.e. with `2533db6d5`'s producer logic) |
| Part A fix, second commit | `49a3adf0f` (its own commit, after the guard tests). It applies cleanly onto `147f2adec` + `2533db6d5` without the instrumentation (`git merge-tree`). The guard-test commit conflicts there only by its position in `v2_tests.rs` (it sits before the part B repro section) |
| **Part A fix candidate** | **`2533db6d5` + `49a3adf0f`** |
| Packet / publication SHA | the latest commit that touches this README, on local branch `exp/bug-01-delivery-cdp-sessions-20261002`. The Publish agent assigns the fork SHA. There is no PR head: nothing is opened or posted by this lane |

| Binary | sha256 | Version (in session) | Built from |
| --- | --- | --- | --- |
| baseline `cua-driver-r2-main-229b65b28` | `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3` | cua-driver 0.32.0 | `229b65b28` (wave-0 SETUP) |
| instrumented `cua-driver-bug01-instr-a99ee937a` | `75bd2d40b63813ae53d620b0e593a6824ec99f326b11b32642e649cfa9dac77e` | cua-driver 0.32.0 | `a99ee937a` |
| fix, superseded `cua-driver-bug01-fix-2533db6d5` | `ab75b36f29a103b16094df9e45e1a50fc66069ef494df4b44a556e10c64bc599` | cua-driver 0.32.0 | `2533db6d5` (contains the default-off instrumentation, with the variable unset in every part A run) |
| **fix, final** `cua-driver-bug01-fix-49a3adf0f` | `c61e8fc6a2814fe944ec491ff84f84299d6e0435e86b49ab3d8c47ba000c1ac5` | cua-driver 0.32.0 | `49a3adf0f` (same instrumentation note) |

Builds used `flock -s quiet-lane.lock flock cargo-build.lock build-driver.sh <wt> <label> cua-release-r2-02` with 0 Fresh workspace units (`raw/build-*.out`). `build-driver.sh` runs `<bin> --version` outside the isolated session, which only prints the version. All versions above were re-recorded inside the session.

**Environment.** Private rootless Xvfb 1920x1080x24 (`-nolisten tcp`) with openbox, picom and a private dbus (`cua-x11-session.sh` sha256 `de01a439…`), and a scrubbed env. The AT-SPI bus is not started, so the Driver logs its AT-SPI listener warning in every run. Chrome 151.0.7922.71 runs with an `isolated_new` profile launched by the Driver, with the Chromium sandbox on. Driver safety settings are the defaults. Kernel: Linux 7.2.2. Part A REAL blocks (including the round-2 fix matrix and the decoy control) and every cargo build/test held `quiet-lane.lock` SHARED; the part B measured run held it EXCLUSIVE (`raw/*.lockinfo`; `verify_artifacts.py` checks that every trial falls inside its window).

---

## Part A: delivery attribution in browser receipts

### Contract text (SOURCE)

- `docs/action-result-contract.md`: "`ActionResult` says what route the driver used and how strongly it can account for the action itself." The allowed values are `delivery.mode` = `background`, `foreground`, `not_applicable`, `unknown`.
- `docs/macos-background-input-v1-plan.md`: "`delivery.mode` reports what actually occurred;"
- `action_record.rs` `ActualDelivery`: "The delivery mode actually used by the actuator. `Unknown` means an attempt was made but the actuator could not determine whether it delivered in the requested mode." From `structured_delivery_mode`: "Prefer an explicit producer-emitted mode when one exists."
- Browser `delivery_mode` schema: "background (default) refuses trusted input where it would activate the browser window (Linux Chromium). foreground accepts that activation".

On Linux Chromium the trusted route has only one branch that can execute: the foreground one. Background is refused before dispatch (control `N_bg`, below). The producer, `BrowserClickTool`, already states `delivery_mode: "foreground"` for that branch. The baseline `actual_delivery_from_legacy` returned `Background` for every `browser_click`, `browser_pointer` and `browser_type` before it read that field. `foreground` is attributable here, so `unknown` is not needed. The same is not true on every path. The request flag only selects the refusal gate, and that gate exists only for a standalone window (`cdp_window_id`) on a platform whose `standalone_trusted_input_background_limitation()` is `Some`. Elsewhere a foreground request runs the background dispatch, so the producer must say `background` there.

### Method

- **Forced path (T):** `browser_type {ref: textbox, token, replace}`, then `browser_click {ref: Submit, delivery_mode: "foreground"}` on the default trusted route, i.e. CDP `Input.dispatchMouseEvent`. This is R2-06 arm T.
- **Other arms:**
  - D: the same, with `input_route: "dom_event"`.
  - Y: `browser_type` only.
  - N_bg (control): the trusted click without `delivery_mode`.
  - N_domfg (control): a `dom_event` click with a stray `delivery_mode: "foreground"`.
- **Design:** 7 blocks of 10 trials per binary, each block with a fresh Driver and browser. Each binary ran 20 T, 20 D and 20 Y in rotating patterns, plus 5 N_bg and 5 N_domfg. Agent-cursor feedback was at the Driver default, as in R2-06.
- **Actual producer/route:** taken from the public receipt (`route`) and cross-checked against what the page saw.
- **Independent, target-owned oracles:**
  - page-side capture listener (sendBeacon journal): `isTrusted`, `document.hasFocus()` and `visibilityState` at `pointerdown`/`click` on Submit;
  - X11 active window before and after the click;
  - fixture `/state` (immediate read, then re-reads up to 3000 ms) and the fixture `POST /submit` journal;
  - for `browser_type`, page `input` events whose value length equals the token length;
  - decoy-window control (extension, `probe_activation.py`, designed by the round-1 verifier): a Tk decoy window is made active (`xdotool windowactivate --sync`) before every click. The X11 active window is then sampled every 100 ms for 1.5 s after the click. 2 fresh Driver/browser blocks per binary, 6 T and 6 D alternating.
- **Unit:** the failing test drives `BrowserClickTool` and `BrowserPointerTool` (`double_click`) over mock CDP, on a platform that has the Linux trusted-background limitation. It builds the receipt the way the dispatch seam does (`from_legacy` → `public_result`). A guard test pins the background cases. Two more guard tests (`7431f03d1`) cover the paths where a foreground request activates nothing: a platform without the limitation, and an embedded route without a CDP window id. Each compares the CDP method list of a background and a foreground request (identical), then requires `background` in both the producer payload and the public receipt, for `browser_click` and `browser_pointer`.

### Results

| Row | Baseline `8b037961…` | Final fix `c61e8fc6…` | Class |
| --- | --- | --- | --- |
| T receipt `delivery.mode` | background 20/20 | **foreground 20/20** | REAL |
| T page trusted-foreground (trusted pointerdown + click on Submit, hasFocus, visible, X11 active = browser pre and post) | 20/20 | 20/20 | REAL |
| T receipt route / effect | trusted_input 20/20 / unverifiable 20/20 | same | REAL |
| T verified (`/state` == token), POSTs | 20/20, 20 | 20/20, 20 | REAL |
| D receipt delivery / route | background 20/20 / dom 20/20 | same | REAL |
| D page click on Submit `isTrusted` | false 20/20 (no pointerdown) | same | REAL |
| D verified | 20/20 | 20/20 | REAL |
| Y `browser_type` receipt delivery / route | background 20/20 / trusted_input 20/20 | same | REAL |
| Y page input value == token / `/state` stays null | 20/20 / 20/20 | same | REAL |
| `browser_type` receipt delivery in all 70 trials | background 70/70 | background 70/70 | REAL |
| N_bg: refused, no `delivery`, 0 page pointer events, `/state` null | 5/5 | 5/5 | REAL |
| N_domfg: route dom, delivery background, verified | 5/5 | 5/5 | REAL |
| Receipt fields compared (effect, route, delivery mode/count, evidence, escalation, error, summary template) | | only T `delivery.mode` changed | REAL |
| Superseded fix `ab75b36f…` (`2533db6d5`, 70 trials, `raw/part-a/fix-*`) vs final fix | | every receipt field distribution identical (Linux standalone labels unchanged) | REAL |
| Decoy control: decoy active before the click, T / D | 6/6 / 6/6 | 6/6 / 6/6 | REAL (extension) |
| Decoy control: browser active after the T click, first sample / end of 1.5 s | 6/6 / 6/6 | 6/6 / 6/6 | REAL (extension) |
| Decoy control: decoy still active after the D click | 6/6 | 6/6 | REAL (extension) |
| Decoy control: receipt `delivery.mode`, T / D | background 6/6 / background 6/6 | **foreground 6/6** / background 6/6 | REAL (extension) |
| Decoy control: page click on Submit trusted, T / D; page `hasFocus` at click, T / D | 6/6 / 0/6; 6/6 / 1/6 | same | REAL (extension) |
| Decoy control: verified (`/state` == token) | 12/12 | 12/12 | REAL (extension) |
| Failing test at `147f2adec` / at `49a3adf0f` | FAILED | ok | UNIT |
| Background guard test at both commits | ok | ok | UNIT |
| Executed-branch guard tests (no limitation; embedded route) at `7431f03d1` / at `49a3adf0f` | FAILED, FAILED (producer said foreground for an identical CDP sequence) | ok, ok | UNIT |
| `cargo test -p cua-driver-contract` (61 tests) | rc 0 | rc 0; outcomes identical to `2533db6d5` | UNIT |
| `cua-driver` receipt goldens (`compatibility_contract_test`, `protocol_tools_call_test`, `schema_consistency_test`; 8 tests) | rc 0 | rc 0; outcomes identical to `2533db6d5` | UNIT |
| `cargo test -p cua-driver-core` (lib + integration) | 1 failure besides the red test (history flake) | 1 failure (a different history flake) | UNIT |

The history failures were `offline_purge_is_exclusive…` at main+test, `modified_ciphertext_and_wrong_key_fail_closed` at `2533db6d5` and `retention_is_enforced_for_disabled_and_long_lived_query_checkpoints` at `49a3adf0f`. All three failed with `WriterStopped` under full-suite concurrency. The `history::` tests passed 5/5 alone at both fix commits. The branch does not touch `history.rs`. They are counted as pre-existing flakes, not as receipt changes. Besides them, the only core outcome changes from main+test to the final fix are the red test (FAILED → ok) and tests that are new on the branch (6 counter tests and 2 guard tests, all ok).

The page-level `hasFocus` was true at 1 of 6 D clicks while X11 still reported the decoy as active. The X11 active window, not the page flag, is the discriminating oracle here.

**Fix (`2533db6d5` + `49a3adf0f`, 3 files).**
- `actual_delivery_from_legacy` gives browser tools `Foreground` only when the producer states `delivery_mode: "foreground"`; everything else stays `Background` (`2533db6d5`).
- Both producers state the executed posture through one helper, `trusted_delivery_mode` (`49a3adf0f`). It says `foreground` only when the request accepted activation AND the tab has a standalone CDP window AND the platform reports the trusted-background limitation (Linux and macOS do; the trait default, which Windows uses, does not). Otherwise it says `background`.
- `browser_pointer`'s success payload now states `delivery_mode` on its trusted route, as `browser_click` already did.
- A request alone is not proof. A `dom_event` click with a stray foreground request stays background (unit guard, plus N_domfg 5/5 REAL), and so does a foreground request on a path that cannot activate the window (the two new guards).
- The legacy payload is replaced by the closed `ActionResult` at the dispatch seam, so the extra producer field is not published.

**Disposition A: CONFIRMED_BUG.** All four pre-registered conditions hold, and `verify_artifacts.py` recomputes them: the baseline mislabels ≥1 trusted-foreground trial (20); the test is red at main and green at the fix (`49a3adf0f`); the fix labels every arm as expected; no other field or contract test changed. The decoy control and the executed-branch guards support the attribution but are not part of the pre-registered gate. **Routing:** outcome vocabulary owner kvnloo/cua#38, upstream trycua/cua 4009 (plain text). Nothing was posted.

### Deviations (A)

1. A 1-block plumbing pilot (10 trials, baseline binary, `raw/pilot/part-a-pilot/`) ran before the baseline matrix. The PREREG did not declare it. It is excluded from every number, and it showed the same labels.
2. Both fix binaries contain the default-off part B instrumentation. `probe_delivery.py` and `probe_activation.py` refuse to run if `CUA_DRIVER_EXP_CDP_COUNTER_FILE` is set. Both fix commits apply cleanly without the instrumentation (`git merge-tree`), but no binary was built from main+test+fix alone.
3. The `browser_pointer` half of the fix is covered by UNIT only. The REAL matrix exercises `browser_click` and `browser_type`, as the PREREG specified.
4. In the pre-registered matrix, the X11 active window equals the browser window in every arm, D included, because that session has a single window. It confirms the foreground posture in T but cannot by itself tell T apart from D. The decoy control (deviation 6) closes this gap.
5. Round-1 verification found a BLOCKING defect in `2533db6d5`: the producers derived `delivery_mode` from the request. The guard tests (`7431f03d1`) and the second fix commit (`49a3adf0f`) were added after the measured matrices. The fix matrix was re-run in full (70 trials, same plan) with the final binary, 03:17:13Z–03:20:20Z under the SHARED lock. This is an extension of the PREREG, which was not edited. The superseded fix data are kept in `raw/part-a/fix-*`, `raw/unit/fix/`.
6. The decoy control is a disclosed extension that the PREREG does not declare. It was designed by the round-1 verifier and adopted with the logic unchanged (`probe_activation.py`). It ran 2 blocks × 6 trials per binary: baseline 03:20:42Z–03:21:45Z, final fix 03:21:45Z–03:22:48Z, both under the SHARED lock.
7. The part A pilot (02:08:10Z) ran after the PREREG commit but has no lockinfo, only `lock_note=caller-held` in its log.
8. PREREG `written_utc` says 02:05Z, but its commit `d0d63f296` is 02:01:59Z. The field was hand-written about 3 minutes late. This is cosmetic, and the PREREG was not edited.
9. The PREREG suites gate says the pass/fail sets "differ only by the new failing test". Taken literally, this is not met: a different `history::` `WriterStopped` flake failed at each commit (see above).
10. `147f2adec` and `a99ee937a` are not rustfmt-clean; `8f52c55a7` fixes them. Any publication or cherry-pick of test + fix alone must carry that formatting. `7431f03d1` and `49a3adf0f` are rustfmt-clean.
11. The Windows and embedded-route halves of `49a3adf0f` are covered by UNIT only (mock CDP). The REAL matrix is Linux standalone, where both fix commits give identical labels.

---

## Part B: CDP session accumulation

### SOURCE

- `engine.rs` `attach()` sends `Target.attachToTarget {flatten: true}` on every `revalidate_for_mutation`, `snapshot_tab`, `snapshot_tab_semantic`, capture and ref-resolution path. The only `Target.detachFromTarget` calls detach OOPIF child sessions.
- Design intent in `docs/browser-tool-implementation-plan.md`: "Session cleanup detaches its CDP sessions without closing a socket still used by another Cua session". Its risk table lists "Flat mode and one CDP session ID per Cua session/tab".

### Method

- **Instrumentation (`a99ee937a`):** measurement-only, env-gated, default-off. It is a new `browser/cdp_counters.rs`, hooked in `cdp_ws.rs` (command sent/acked, every parsed frame) and at the end of the tool dispatch seam. With `CUA_DRIVER_EXP_CDP_COUNTER_FILE` set, it writes one JSONL line per completed tool call: attach/detach commands sent and acked, `attachedToTarget`/`detachedFromTarget` events, the live session set, sessions seen, cumulative and per-call replies/events, and frames/events per session id. The module has 6 unit tests.
- **Default-off smoke:** the stock `browser-smoke.sh` with the instrumented binary and the variable unset gave rc 0/0 and verified `jev-guide-mock`. The retained session dir and the smoke outdir contain 0 counter files and 0 files with the counter schema (`raw/default-off-check.txt`).
- **Forced path:** `set_agent_cursor_enabled false` (both arms), then `browser_prepare isolated_new` → bind → navigate. After that, call k alternates: even k is `get_browser_state {snapshot_format: semantic_v2}`, odd k is `browser_click {No-op ref, input_route: dom_event}`. The page is jev-use PAGE plus one injected `<button type="button">No-op</button>`.
  - Long session L: 300 calls on one Driver and browser.
  - Control C: 30 fresh Driver+browser blocks of 10 calls each.
  - Order L1 C1 C2 L2 L3 C3, under the EXCLUSIVE quiet lock from 02:19:54Z to 02:22:44Z. 1-minute loadavg 2.27–3.43 (median 2.74).
- **Navigation probes:** in L, a reload before k=0, 100 and 200 and after k=299. In C, each block's setup navigate serves as the probe.
- **Chrome memory:** VmRSS and Pss over the process tree rooted at this lane's browser pid, read-only from /proc. Sampled every 25 calls in L, and at the start and end of each C block.
- **Producer attribution:** the counters are Driver self-report. Independent corroboration comes from client-side latency, Chrome's own memory, and the mock-CDP repro.
- **Statistics:** OLS slope per session (latency with a call-type intercept); the pooled slope is the mean over the 3 sessions; 95% CI from a seeded moving-block bootstrap (block 25, 10000 resamples, seed 20261002).

### Results (1800/1800 measured calls accepted; every call joined to one counter line)

| Metric | Long sessions L (3 × 300) | Fresh control C (3 × 30 × 10) | Class |
| --- | --- | --- | --- |
| Attach / detach commands per measured call | 1 / 0 in all 900 calls | 1 / 0 in all 900 calls | REAL |
| M1 live CDP sessions: slope per 100 calls | **100.89, CI [100.86, 101.04]** (each L ends at 304) | +0.11 over the series index, CI [−0.13, +0.14] (max 11 in any block) | REAL |
| M1 attach − detach: slope per 100 calls | 100.89, CI [100.86, 101.05] | n/a | REAL |
| M2 events per call: slope per 100 calls | +0.23, CI [−0.49, +1.42]: **flat** | 0.0, CI [0, 0] | REAL |
| M2 events per call (k<50 / k≥250 mean) | 1.0 / 1.0 (overall mean 2.0, from the two post-navigation bursts) | 1.0 | REAL |
| M3 latency slope (ms per 100 calls) | −0.05, CI [−0.16, +0.18] | −0.05, CI [−0.24, +0.11] over the series index | BENCHMARK |
| M3 L − C slope (ms per 100 calls) | +0.004, CI [−0.16, +0.34] | | BENCHMARK |
| Median latency, snapshot / click | 5.61 / 20.57 ms (k<50: 5.62 / 20.21; k≥250: 5.68 / 20.71) | 5.69 / 20.17 ms | BENCHMARK |
| M4 Chrome tree Pss slope (renderer Pss) per 100 calls | +10.3–10.4 MiB (renderer +7.5–7.7 MiB) per session, i.e. 10591–10631 KiB (7690–7864 KiB); consistent across L1–L3 | not comparable (a fresh browser grows about 5.3 MiB, 5465 KiB, per 10-call block during warm-up) | REAL (descriptive) |
| M5 events during the navigate call itself | 1 at every probe (live 2 → 305) | 1 (90/90) | REAL |
| Exploratory: events in the first call after a navigation | **1 / 101 / 201 at 2 / 103 / 204 live sessions**, all 3 L sessions; slope 0.99 events per live session | 1 (90/90, live 1) | REAL (exploratory, not pre-registered) |
| Exploratory: latency of that call | 10.1 / 8.0 / 8.2 ms (median by probe) | 9.9 ms | BENCHMARK (exploratory) |
| Repro: 10 semantic snapshots over mock CDP leave 10 live tab sessions (`--ignored`) | FAILED (as intended) | | UNIT |

**Disposition B: ACCUMULATION_ONLY.** This was pre-registered for the case M1 > 0 with M2 flat. The leak itself is confirmed: one undetached flattened session per browser call, linear in the call count, against a design intent of one session per Cua session/tab. **Effect size:** no measurable latency drift on this Driver path, with a latency slope of −0.05 ms per 100 calls, CI [−0.16, +0.18]. Event amplification appears only when the page changes. The browser then fans its post-navigation events out to every accumulated session, so the burst grows by about 1 event per prior call. M5 as pre-registered missed this, because the burst lands in the call after the navigate; it is therefore reported as exploratory. Renderer memory grows by about 7.5–7.7 MiB per 100 calls in the long sessions. That is consistent with leaked sessions holding DevTools agents, but it was not shown causally. The fix is out of scope. **Routing:** upstream trycua/cua 4052, the browser-timing owner (plain text), and the R2-02 side finding on kvnloo/cua#93. The repro test is `repeated_browser_calls_do_not_accumulate_cdp_tab_sessions`.

**Drift term for single-session runs.**
- R2-01-style runs start a fresh Driver per trial, so they carry no accumulation term.
- R2-02-style runs (one Driver session, a navigation per trial) do carry one: live sessions grow by the number of calls per trial, and here every navigation delivered one extra event to the next call per accumulated session. A mechanism hypothesis, not measured here: an arm that subscribes to and processes the CDP event stream could pay for that fan-out and drift with session age. This lane did not measure event-subscribing code paths (see the claim boundary) and does not compare with wave-0 numbers.
- On the plain tool-call path, this lane found no latency drift (CI upper bound +0.18 ms per 100 calls), so the R2-02 event-arm slowdown is not explained by tool-call latency alone. R2-10's fresh session per trial avoids the term.

### Deviations (B)

1. Two plumbing pilots ran, as the PREREG allowed (`raw/pilot/part-b-pilot*`). Pilot 1 showed renderer memory as 0 because Chrome rewrites child argv. The probe's `/proc` cmdline parsing was fixed before pilot 2 and the measured run.
2. The post-navigation burst metric was added after the run and is labelled exploratory. The pre-registered M5 (events during the navigate call) is reported unchanged.
3. The C memory delta is not a valid control for M4, because of browser warm-up after launch. M4 is descriptive only.
4. The counters do not record CDP event method names, so the burst events are counted but not named.
5. `rustfmt` differences in the test and instrumentation commits are fixed in the separate formatting-only commit `8f52c55a7`, made after both binaries were built.

---

## Invariants (#73/#93)

- No new service.
- The instrumentation is env-gated, default-off and measurement-only, with a unit test and a REAL smoke.
- The part A fix changes only delivery attribution: the published `delivery.mode` for browser tools, and the producer `delivery_mode` field that feeds it. That field now says `background` for a foreground request on a path that cannot activate the window. No dispatch changes.
- Events were never used as the success oracle: the fixture `/state` and the page journal are.
- No effect was replayed.
- All 1800 part B calls and 210 + 24 part A trials are in the denominators, with 0 harness errors.

## Work deleted vs wall-clock saved

None claimed. A is a truthfulness fix (0 ms; it changes no dispatched work). B is a diagnosis. Deleting the per-call attach (reusing one session per Cua session/tab) would remove 1 `Target.attachToTarget` round trip per browser call and N−1 duplicate event deliveries per navigation. The wall-clock saving is not measured; on this path it is below the resolution of M3.

## Claim boundary

Driver 0.32.0 tree at `229b65b28` == `c4d0c6625`, Chrome 151, X11 Xvfb, the jev-use fixture, the `isolated_new` (Unrestricted CDP policy) path.
- Part A's fix is a candidate for review, not a published or upstream change.
- Not claimed: macOS, Windows or Wayland delivery semantics (the fix's behaviour there is UNIT-only, on mock CDP); the existing-profile CDP policy path; `browser_pointer` REAL behaviour; renderer memory causality; latency effects of accumulation on event-subscribing code paths, which were not measured here.

## Files

- `PREREG.json`
- `README.md`
- `bug01-summary.json` (all numbers)
- `provenance.json`
- `verify_artifacts.py`: recomputes the summary from `raw/`, checks the lock windows, binary hashes, unit receipts and commit existence, and runs a privacy scan.
- `make_summary.py`, `analyze_a.py`, `analyze_b.py`
- `probe_delivery.py`, `probe_sessions.py`, `probe_activation.py` (decoy control), `bug01_common.py`, `run_in_session.sh`
- `raw/part-a/` (per-trial JSONL, block metadata, session env; labels `baseline`, `fix` = superseded `2533db6d5`, `fix2` = final `49a3adf0f`)
- `raw/part-a-activation/` (decoy control, `baseline` and `fix2`)
- `raw/part-b/` (`calls.jsonl`, per-block Driver counter JSONL, session env)
- `raw/unit/`, `raw/pilot/`, `raw/default-off-smoke/`, `raw/default-off-check.txt`, `raw/build-*.out`, `raw/*.lockinfo`, `raw/*.txt` (session logs)

Raw outputs are mirrored under the lanes artifacts dir `artifacts/r2/BUG-01/`.

Reproduce inside the isolated session (placeholders `<lanes>`, `<tmp>`):

```
flock -s <tmp>/locks/quiet-lane.lock <lanes>/cua-x11-session.sh <wt>/docs/experiments/bug-01-delivery-cdp-2026-10-02/run_in_session.sh <wt> <bin> probe_delivery.py --out <dir> --driver-label baseline
flock -s <tmp>/locks/quiet-lane.lock <lanes>/cua-x11-session.sh <wt>/docs/experiments/bug-01-delivery-cdp-2026-10-02/run_in_session.sh <wt> <bin> probe_activation.py --out <dir> --blocks 2
flock    <tmp>/locks/quiet-lane.lock <lanes>/cua-x11-session.sh <wt>/docs/experiments/bug-01-delivery-cdp-2026-10-02/run_in_session.sh <wt> <instr-bin> probe_sessions.py --out <dir>
python3 verify_artifacts.py
```
