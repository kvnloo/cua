# R2-02: real CDP event wake vs. the poll loop, 2026-10-01

Owners: kvnloo/cua#93 (R2-02), #10 (accounting), original E3.

## Result in one paragraph

On the jev-use browser fixture, a function-local wake on the Driver's existing CDP event demux (`CdpConnection::subscribe`) made the same DOM-route Submit click **slower**. The wake waited for a main-frame `Page.frameNavigated` with a new loader id, then did one fresh `/state` read. Both arms verified **24/24**. The median paired difference (event − poll) in click-to-verified time was **+42.1 ms**, with a 95% bootstrap CI of **[+31.9, +56.9] ms**. The poll arm was faster in **21 of 24** pairs.

The direction comes from ordering. The fixture's state commit (the oracle effect) lands about 1 ms after `Runtime.callFunctionOn` returns. The poll loop's first immediate read already sees it in 21/24 trials, so it needs no sleep, while the probe always adds setup, a wait for the commit event and cleanup. **The magnitude is not a property of the route.** The event arm slowed steadily with session age (see *Session-age drift*): the commit-event wait went from about 7 ms in the first two pairs to about 46-48 ms in the last two while load fell, and the median paired difference was +10.9 ms over the first 6 pairs vs +52.7 ms over the last 6. The run-wide medians (wait 33.8 ms, cleanup 10.6 ms, +42.1 ms) are averages over a drifting session, and the bootstrap CI treats the pairs as exchangeable, which they are not.

Correctness controls: 69/69 valid control trials met their pre-registered expectation. The run-1 C3 early-event control (6 trials) **could not fail by construction**, so it is reported as invalid and excluded. After a probe fix, C3 and its ablation C3u were rerun 6x each as a disclosed extension (deviation 6), where they differ only in whether the pre-dispatch drain runs. No event, and no missing event, ever produced a verified record without the oracle. Under the pre-registered gates the disposition is **KILL** for this wake source on this fixture and route.

## Scope and pinned sources

| Item | Value |
|---|---|
| Tested base | trycua/cua main `229b65b2849c3a595ddbc85200d7181b18bd2e47` |
| Live upstream main at execution (gh) | `effd9b298942d7e9808077adef4ef575d561141d`, 1 commit ahead, `release-please-config.json` only |
| Live PR head | none (R2-02 tests no open PR). For context only: trycua/cua#4316 `a0bca744067d04f05904319d3d919be30c336556` OPEN |
| Pre-registration | `PREREG.json`, commit `939d4c18c8b8bcb51fc0b8e0d312268554b1049f`, sha256 `74429ec74c6987b34e5d7a3bc3b158299f6472547671c163a944cffc7b17d8db`, committed before any trial ran and not edited afterwards |
| Tested source (worktree HEAD at the measured run, clean) | `3e41eb1b1cb6931fa75d95b30cc3245528905c5e` on local branch `exp/r2-02-cdp-wake-20261001` |
| Driver binary source | `4d092b16065f45ceb0b4266913f3aff225a880cf`. `3e41eb1b1` differs only in `#[cfg(test)]` code and `docs/` |
| Driver binary | sha256 `7034a43b382ee886a84e01138b46936e2a31852642dd6a6df8dff435f89a84c1`, `cua-driver 0.32.0`, `cargo build --locked --release -p cua-driver --features portal-input`, rustc 1.97.1, lane target dir, 0 Fresh workspace units |
| Extension (C3/C3u only) | tested source = binary source `55846dc660a05b6644b58fb915426421ec4e6e2b`; Driver sha256 `38f8c11db80e23480d8ea8d9a7bdad5169ddbf47e499fb67625e9e068463553b`, `cua-driver 0.32.0`, same build command, 0 Fresh workspace units. Live upstream main at the extension (gh, 22:50Z): `021b87ddf0faa0853ba7417303b05a283ca3b491`, 3 commits ahead of the tested base, none under `libs/cua-driver` |
| Publication SHA | set later by the orchestrator. It is not the tested source |

The `0.32.0` main Driver (`8b037961…`) and the #4316 Driver (`e57bb9ae…`) were **not** used. No number here is compared with them, with #106, or with the #93 E0/E1 probe.

## Environment

- Private rootless Xvfb 1920x1080x24 with `-nolisten tcp`, openbox and picom, a private dbus, and a scrubbed env (`cua-x11-session.sh` sha256 `de01a439…`). The session script started no AT-SPI bus (`CUA_SESSION_ATSPI` unset). The private dbus did activate `org.a11y.Bus` on demand when the Driver asked for it, but `org.a11y.atspi.Registry` failed to activate, so the Driver's AT-SPI listener never connected (logged as a warning, same in both arms and the extension). The host Wayland/Hyprland session was never reachable.
- The browser was Google Chrome 151.0.7922.71, chosen by the Driver's root-owned candidate list. The profile was a Driver-owned `isolated_new` profile. Default safety settings applied: no permission-mode override, no approval bypass, Chromium sandbox on.
- Host: Linux 7.2 x86_64, 10 logical CPUs, 23 GiB RAM. Python 3.12.13 from the jev-use `uv sync --frozen` venv.
- The whole measured session ran under `flock quiet-lane.lock`: acquired 22:22:39Z, released 22:28:09Z. The 1-minute loadavg before each trial ranged from 1.18 to 7.51 because other agents' non-timed work was running. Medians were 4.90 for poll and 4.95 for event, and every value is stored per trial.

## What was built (measurement-only, default-off)

`libs/cua-driver/rust/crates/cua-driver-core/src/browser/exp_cdp_wake.rs` plus a 20-line hook in the `dom_event` branch of `browser_click` (`tools.rs`). The probe arms only when **both** conditions hold:

- The Driver process has `CUA_DRIVER_EXP_R2_02_CDP_WAKE=1`.
- The call carries `exp_r2_02_cdp_wake`.

Otherwise the main code path runs unchanged. C0 confirms this at runtime: a Driver without the env var wrote no record and behaved like the poll arm.

When armed, the probe does the following, immediately before `Runtime.callFunctionOn`:

1. Subscribes on the existing pooled connection. No new socket and no new service.
2. Calls `Page.enable` on the call's tab session.
3. Calls `Page.getFrameTree` to read the main frame id and loaderId. This is the same frame-id plus loader-id document identity the store already re-proves before mutations.
4. Drains and discards everything queued before dispatch. (For the C3/C3u controls, the extension binary first sends one synthetic matching commit into this same queue.)
5. After dispatch, waits for the first `Page.frameNavigated` on that session for the main frame with a different loaderId, or for a 1000 ms deadline.
6. Drops the subscriber and calls `Page.disable`.

The record says `wake_hint_only; application effect not verified`.

The public `ActionResult` projection drops unknown structured keys, so the record goes to an env-named JSONL log (`CUA_DRIVER_EXP_R2_02_CDP_WAKE_LOG`). The click's public result keeps its original shape: 0 of 113 run-1 trials and 0 of 14 extension trials leaked the probe key. Unit tests passed: `cargo test -p cua-driver-core --lib browser::` ran **184 passed, 0 failed** at both `3e41eb1b1` and `55846dc66`, including 5 probe tests (`unit-cargo-test-browser.txt`). At `3e41eb1b1` the early-injection assertion was true by construction (deviation 6); at `55846dc66` it fails when the drain is disabled. The jev-use suites on the worktree matched the main baseline: Python 229 run, 228 passed, 1 skipped; TypeScript 105/105; typecheck and 4 CLI verifiers rc 0. The two `*-guarded-focused` steps fail by construction because those files exist only on #4316.

## Method

- **Forced path (both arms):** `browser_prepare` (`isolated_new`) → bind → `browser_navigate` to the variant → `semantic_v2` snapshot → `browser_type` on the field ref → re-snapshot → pre-dispatch `/state` read → **timed** `browser_click` on the fresh Submit ref with `input_route=dom_event`. Candidates come from the unchanged jev-use `FixtureFormTask` + `fixture_sources`.
- **Actual route/producer:** the Driver reported `route=dom`, `effect=unverifiable` on every successful click. The mutation producer is a synthetic DOM `click()` through `Runtime.callFunctionOn`. The wake producer is Chromium's `Page.frameNavigated`, delivered through the existing `CdpConnection` demux.
- **A_poll:** the click without the probe argument, then the `python/run.py` completion loop: read `/state`, stop on verified/refuted, otherwise sleep 0.1 s, for at most 20 reads plus a final read.
- **B_event:** the click with `{deadline_ms: 1000, control: none}`, then one fresh `/state` read, then the identical A_poll loop as fallback.
- **Independent target-owned oracle:** `GET /state` on the loopback fixture, read by the harness process. Verified means `submitted == token`; refuted means any other value. The fixture handler also journals the `CLOCK_MONOTONIC` time immediately before each state commit, in the same process as the harness timers.
- **Interleaving:** 1+1 warm-up trials (kept and reported, excluded from the headline), then 24 pairs alternating AB/BA (12 each), then 10 control groups round-robin × 6, then 3 default-off trials in a second Driver process. All share one fixture server. Every trial has its own JSONL receipt in `raw/`.
- **Primary metric:** `click_to_verified_ms`, measured from immediately before the `browser_click` MCP call to the return of the `/state` read that first classifies verified. Probe subscription, setup, wait and cleanup all fall inside this span.

## Results

Evidence class: REAL (real Chromium and real CDP events) unless a row says otherwise. N of M counts every attempted trial.

### Paired comparison (24 pairs, AB 12 / BA 12)

| Row | A_poll | B_event | Class |
|---|---|---|---|
| Verified by oracle | 24/24 | 24/24 | REAL |
| click_to_verified median / p95 (nearest rank) | 1543.461 / 1670.660 ms | 1592.255 / 1646.033 ms | BENCHMARK |
| browser_click tool span median | 1542.302 ms | 1590.954 ms | BENCHMARK |
| tool return → verified median | 1.25 ms | 0.766 ms | BENCHMARK |
| state commit → verified median | 1.0 ms | 50.856 ms | BENCHMARK |
| First read after the call already verified | 21/24 | 24/24 | REAL |
| Oracle reads after the call, total | 28 | 24 | REAL |
| Fixed 100 ms sleeps, total | 4 (in 3 trials) | 0 | REAL |
| Paired diff (event − poll), median | **+42.125 ms** (median of unrounded diffs), 95% bootstrap CI **[+31.877, +56.871]** (10000 resamples, seed 2026100102; assumes exchangeable pairs, which session-age drift violates) | | BENCHMARK |
| Pairs favouring event / poll | 3 / 21 | | BENCHMARK |
| *Exploratory, not pre-registered:* diffs in the 3 pairs where poll slept | −191.099, −24.627, −26.176 ms | | BENCHMARK |
| *Exploratory, not pre-registered:* median diff in the 21 pairs where poll did not sleep | +44.691 ms | | BENCHMARK |

The probe's phase medians in B_event (n=24, intra-Driver `Instant` deltas, BENCHMARK):

| Phase | Median |
|---|---|
| Subscribe | 0.008 ms |
| `Page.enable` | 0.609 ms |
| Generation read | 0.298 ms |
| Setup total | 0.932 ms |
| Dispatch | 0.892 ms |
| Dispatch return → wake | 33.771 ms |
| Cleanup (`Page.disable`) | 10.55 ms |
| Setup + cleanup | 11.462 ms |
| Probe total | 45.505 ms |

All 24 probes ended in `wake` and 0 in `deadline`. The 24 wakes saw 120 `other_method` events (any event on the call's session other than `Page.frameNavigated`, 5 per wake) and 0 pre-dispatch events.

These phase medians pool a drifting series; the wait and cleanup phases depend on session age (next section).

### Session-age drift (exploratory, not pre-registered)

The event arm got slower within the single measured Driver/browser session, and the slowdown does not track load. All numbers below are recomputed by `verify_artifacts.py` (`pairs.exploratory_not_preregistered.session_age_drift`).

| Series | Early | Late | Note |
|---|---|---|---|
| Pair event-arm dispatch-return → wake (`wait_ms`) | 6.80, 7.42 ms (pair00/01) | 47.90, 45.55 ms (pair22/23) | From pair10 on it rises almost every pair (r(index, wait) = 0.944) while 1-min load falls from 7.51 to 4.12 (r(load, wait) = −0.914) |
| Paired diff (event − poll), median | +10.89 ms (first 6 pairs) | +52.74 ms (last 6 pairs) | r(index, diff) = 0.41 over all 24, 0.66 from pair10 on |
| Control wake waits, round 1 → round 6 | C2 50.9, C3 52.7, C5 59.7, C7 59.3, C4 203.1 ms | C2 147.4, C3 140.3, C5 147.9, C7 158.5, C4 302.6 ms | Load 3.9 → 1.2-1.9 over the controls |
| Control cleanup (`Page.disable`), round 1 → round 6 | C2 14.2, C5 17.0, C7 16.2 ms | C2 36.8, C5 41.5, C7 40.7 ms | Same load trend |
| C1 `unrelated_session` events per 1000 ms deadline | 204 at seq 50 | 404 at seq 100 | Exactly 4 × (seq + 1) in all 6 trials |
| Extension C3 waits (fresh session, 55846dc66 binary) | 6.77 ms (1st) | 13.13 ms (6th) | Same upward trend over 14 trials; correctness-only run, not compared with the pairs |

Interpretation, with its limits:

- Something in the session that emits CDP events grows by one unit per trial, in both arms (C1's other-session event count grows by exactly 4 per trial). A likely source, from SOURCE reading only: the base Driver attaches a fresh flattened session (`Target.attachToTarget`, `engine.rs` `attach()`) on each tool call, and no matching `Target.detachFromTarget` was found on that path. This is **not verified** and is listed as a confound and follow-up, not a finding.
- AB/BA interleaving cannot cancel a drift that only affects the arm waiting on the navigation commit. The poll arm's first read lands about 1 ms after the commit regardless of session age.
- The KILL direction does not rest on the drift: the first two pairs were already +8.4 and +13.4 ms, the probe adds setup + a wait of at least about 7 ms + cleanup on every click, and the poll's first read already verifies in 21/24 pairs. An independent 3-pair rerun in a fresh session by the packet verifier (same binary `7034a43b`, quiet lock, isolated session; not part of `raw/`) gave +25.6 and +25.9 ms, and −120.3 ms in the one pair where poll slept.
- The **magnitude** (+42.1 ms, wait 33.8 ms, cleanup 10.6 ms) and the earlier explanation of it (server response plus renderer commit) depend on session age and should not be quoted as properties of the route.

### Controls (all meet expectation; failures would be listed in `r2-02-summary.json`)

| Group | N met / N | Observed | Class |
|---|---|---|---|
| C1 lost (matching event suppressed) | 6/6 | Deadline every time (6 suppressed); first post-call read verified; median 2545.110 ms, so the full 1000 ms deadline is the cost of a lost wake | REAL |
| C2 spurious (interstitial commit, no effect yet) | 6/6 | Woke on a real commit; first post-wake read `unknown` 6/6; verified later by the fallback poll (5 reads); median 1960.282 ms | REAL |
| C3 early, run 1 | **INVALID** (6 trials, excluded) | Cannot fail by construction: the run-1 binary only incremented `pre_dispatch` and `early_rejected` and dropped the synthetic event, which never entered the queue or the drain. No real event was drained either (`pre_dispatch` 0 apart from that hard-coded 1). Kept in `raw/`; superseded by the extension row | NOT_RUN as a test (SOURCE shows the defect) |
| C3u early, guard ablated, run 1 | 6/6 | Woke at once on the injected event; the oracle decided (verified, because the effect had already landed). This binary handed the event straight to the wait loop, not through the queue | FIXTURE |
| C3 early, **extension** (fixed binary `38f8c11d…`) | 6/6 | The synthetic matching commit is sent into the subscriber's own queue after subscription and before dispatch; the drain saw it every time (`pre_dispatch` 6, `early_injected_drained` 6, `early_rejected` 6); the real commit woke (`wake_injected` false 6/6); verified 6/6 | FIXTURE (synthetic event in a real run) |
| C3u early, guard ablated, **extension** | 6/6 | Same injection, drain skipped: `pre_dispatch` 0, woke on the injected event 6/6 (`wake_injected` true); the oracle decided (verified 6/6, 1 POST each) | FIXTURE |
| C4 unrelated (child-frame churn, 150 ms target-side commit delay) | 6/6 | 36 real child-frame `frameNavigated` and 506 other-session events, none woke; main commit woke; verified | REAL |
| C5 stale (synthetic event with the pre-dispatch loaderId after dispatch) | 6/6 | `stale_rejected` 6; real commit woke; verified | FIXTURE |
| C5u stale, guard ablated | 6/6 | Woke at once on the stale event; the oracle decided | FIXTURE |
| C6 timeout, event (inert Submit) | 6/6 | Deadline; every read `unknown`; outcome timeout; 0 POSTs; median 4558.459 ms | REAL |
| C6p timeout, poll (inert Submit) | 6/6 | Outcome timeout; 0 POSTs; median 3554.064 ms. The event deadline adds about 1 s to the worst case | REAL |
| C7 refuted (value rewritten before POST) | 6/6 | Woke on a real commit; first post-wake read `refuted` 6/6; outcome refuted, never verified | REAL |
| C0 default-off (no env gate, argument present) | 3/3 | No probe record written (no log file); verified via the poll loop | REAL |

Across all 113 run-1 trials and the 14 extension trials (127 in total):

- Valid control trials meeting expectation: **69/69** (run 1: 57/57, i.e. 9 groups × 6 + C0 × 3, excluding the 6 invalid C3 trials; extension: 12/12). The 6 invalid run-1 C3 trials are not failures and not passes; they are reported separately above.
- False successes (verified without a final verified read and a journaled POST): **0**.
- Guarded controls woken by an injected event: **0**.
- Harness, tool or oracle errors: **0**.
- Probe log records: 79 in run 1 and 13 in the extension, each matching the armed calls by nonce.

## Work deleted vs. wall-clock saved (reported separately)

- **Work deleted (structural):** over 24 trials the event arm removed the 4 fixed 100 ms sleeps and 4 oracle reads that the poll arm needed in 3 trials. It **added**, per click, one subscriber and three CDP round trips: `Page.enable`, `Page.getFrameTree` and `Page.disable`.
- **Wall-clock saved:** none. The paired median is +42.1 ms (event slower), with a CI entirely above 0. The only wins were the 3 pairs where the effect landed after the tool returned under load. Those pairs show that a late effect is where a wake could pay off, but they are 3 of 24.
- No CPU measurement was taken. No CPU claim.

## Why the wake loses here

On this route, `Runtime.callFunctionOn` returns after `click()` has queued the form submission. The browser sends the POST at once, and the loopback fixture commits state about 1 ms later (click-to-effect median 1542.58 ms against a poll tool span of 1542.30 ms). The poll arm's immediate first read usually lands after that commit.

The navigation commit that the probe waits for comes after the server response and renderer commit, so it necessarily lags the oracle effect. For this oracle, waking on commit means waiting for something that happens **after** the predicate is already true. How far it lags was not stable: about 7 ms at the start of the session and 45-48 ms at the end, with cleanup (`Page.disable`) growing alongside (see *Session-age drift*). The earlier reading that the tens-of-milliseconds lag is intrinsic to the route is withdrawn; the lag on a fresh session is single-digit to low tens of milliseconds, and the growth is a suspected Driver/session accumulation confound.

## Negative / fallback controls

These are covered above. Lost and timeout cases end at a bounded deadline followed by a fresh read and the unchanged poll fallback, so event absence never authorizes anything. Spurious and refuted wakes are never treated as success. Stale and unrelated events never woke when the guards were on (run 1). The early-event guard is supported only by the extension: an injected matching commit queued before dispatch was removed by the drain in 6/6 trials, and with the drain skipped it woke in 6/6. With the guards ablated (C3u/C5u) a wrong wake happens, and the oracle still decides the outcome.

## Deviations from PREREG.json

1. **Probe record channel.** PREREG expected the probe record in the `browser_click` structured result, and C0 was worded "no probe output in the result". The first shakedown, with binary `4ca5c0ff…` from `906377ca0` (no measured trials), showed that the Driver's public `ActionResult` projection drops unknown keys. The record moved to the env-named JSONL log at `4d092b160`, and C0 became "no record written". The arms, controls, n, gates and timing span are unchanged.
2. **Unrelated-event control.** To give child-frame events a guaranteed post-dispatch window, the `unrelated` variant posts to `/submit?delay_ms=150`, which the harness handler delays 150 ms before the unchanged commit. This was set before the measured run; its timings are not compared with the pairs.
3. **Shakedowns.** Two correctness shakedowns (no quiet lock) ran before the measured run, to validate the harness. They are not in `raw/` or in any statistic. Only the second (binary `7034a43b…` from `4d092b160`, 15 trials, about 22:17Z) is kept in the lane artifacts mirror. No receipts from the first (binary `4ca5c0ff…` from `906377ca0`) were retained; only its build log exists.
4. **Test-only commit.** `3e41eb1b1` fixed a `#[cfg(test)]` initializer after the binary was built at `4d092b160`. The unit results above are from `3e41eb1b1`.
5. **Verifier changes after the run (first packet commit).** Before the summary was first committed, `verify_artifacts.py` got a `probe_end` tally fix for no-probe groups **and** post-hoc additions: the probe-log and default-off checks, and three analyses that split results by whether poll slept (`pairs_where_poll_slept`, `diffs_where_poll_slept`, `median_diff_where_poll_did_not_sleep`). Those splits were not pre-registered; they are now under `exploratory_not_preregistered` and labelled exploratory in the tables. No raw data changed.
6. **C3 early control was invalid; fixed and rerun as an extension.** In the run-1 binary (`4d092b160`), `before_dispatch()` with `inject_early` only incremented `pre_dispatch` and `early_rejected`; the synthetic event was dropped and never reached the queue or the drain. The PREREG expectation (`early_rejected == 1`) and the old unit test were therefore true by construction, and the old README's claims about the pre-dispatch drain were unsupported. Fix (`55846dc66`): the early controls subscribe with a sender into the subscriber's own queue (`CdpConnection::subscribe_with_sender`, crate-internal, used only by these controls), send one synthetic matching commit before dispatch and drop the sender; the drain classifies every drained event and counts wake-class ones in `early_rejected`, and the injected one in `early_injected_drained`. C3 and C3u now differ only in whether the drain runs. A mutation that disables the drain makes the unit test fail (`unit-cargo-test-browser.txt`). The extension reran C3 and C3u 6x each, round-robin after a 1+1 warm-up, with the same harness procedure (`--groups`), in the isolated session under the quiet lock (22:48:17Z-22:48:58Z), Driver `38f8c11d…`. Receipts: `raw/ext-c3/`. It is correctness evidence only; no timing from this binary is compared with the run-1 pairs, and the pairs were **not** rerun with it. The fix touches only the early-control paths and adds one classification per drained pre-dispatch event (0 in every pair trial).
7. **PREREG timestamp.** PREREG `written_utc` says 22:05Z, but its commit `939d4c18c` is at 22:02:45Z (the field was written approximately). Ordering against the trials is unaffected: the shakedowns ran after 22:10Z and the first measured trial at 22:22:45Z.
8. **Rounding.** The median paired diff is now computed on unrounded per-pair diffs (42.125 ms). The first packet rounded each diff to 3 decimals first (42.126). The CI is unchanged.
9. **Second packet revision (post-review).** Besides deviations 6-8, `verify_artifacts.py` now also loads `raw/ext-c3/`, excludes run-1 C3 from all totals and gates, checks the extension's provenance block, and computes the exploratory session-age drift series.

## Limits

- One fixture, one route (`dom_event`), one browser build and one host. The effect is a loopback POST that commits about 1 ms after dispatch. Any effect that lands later (a slow server, an async handler, client-side rendering) changes the trade-off; the 3 late-effect pairs hint at that but are not a test of it.
- The browser action span is about 1.54 s in both arms, mostly the R2-01 subject. It is equal across arms but dwarfs the delta.
- Loadavg reached 7.5 while the lock was held, because others' non-timed work was running. Interleaving spreads that across arms, but tails are noisy.
- Intra-Driver probe phases and harness timings come from different processes. They are never subtracted from each other. Harness timings and the fixture journal share one process and `CLOCK_MONOTONIC`.
- n=24 pairs: the p95 values are estimates, not tail guarantees.
- **Session-age confound.** All 24 pairs ran in one Driver/browser session whose event-arm cost grew with trial index. The CI assumes exchangeable pairs. A design that resets the session per block, or a Driver that detaches its per-call sessions, would be needed to state a route-level magnitude.
- The wake source was `Page.frameNavigated` only. Earlier signals (`Network.requestWillBeSent`, `Page.frameStartedNavigating`) precede the effect, so they would be spurious-by-construction wakes for this oracle. They were not tested.

## Claim boundary

**Supported:** on main `229b65b28` plus a default-off probe, with Chrome 151 in a private Xvfb session, the jev-use form fixture and a DOM-route Submit, waking on the existing CDP demux for the main-frame commit and then re-reading `/state` is **slower** than the existing 100 ms poll loop. The median paired cost is +42 ms with a CI above 0. The size of that cost grew with session age (+10.9 ms median over the first 6 pairs, +52.7 ms over the last 6), so +42 ms is a session average, not a route constant. Its event/oracle separation is correct: across 69 valid control trials, no stale, unrelated, spurious, lost or refuted event changed what the oracle decided, and the early-event drain (extension, fixed binary) removed a queued pre-dispatch matching commit 6/6.

**Not claimed:** any early-event guarantee from run 1 (its C3 control was invalid), the mechanism of the session-age drift (suspected per-call session accumulation, not verified), the existing-profile CDP policy path, trusted-input routes, AT-SPI/native events (R2-09), `wait_for_window`'s 0.25 s list_windows poll (no CDP event exists for native window creation, so it was NOT_RUN), other pages, other browsers, delayed effects, CPU, a public Driver contract, or composition with other treatments (R2-10). No RFC delta.

## Disposition

**KILL**, by the pre-registered gate (event arm slower, CI lower bound > 0), for *commit-event wake on this fixture/route*. The correctness design held in every valid control: the generation guard, the pre-dispatch drain (shown only by the extension), deadline fallback and the oracle-only success rule. It could be reused if a later lane has an effect that demonstrably lands after the tool returns. Before revisiting, that lane would need: a measured share of late-effect trials large enough to matter; a wake event that does not lag the oracle effect; a measurement that controls session age (or a Driver that does not accumulate per-call sessions); and a cleanup that works under the existing-profile CDP policy. `Page.disable` is not in `EXISTING_PROFILE_METHODS`, so under that policy cleanup would be refused and Page left enabled. Only the `isolated_new` (Unrestricted) path and the `dom_event` route were exercised here.

## Files

- `PREREG.json`: pre-registration (sha256 above).
- `run_r2_02.py`: the harness (reuses the jev-use Driver client, fixture server, candidate builder and oracle).
- `raw/NNN-<group>-<arm>.jsonl`: one receipt per trial (113).
- `raw/driver-probe.jsonl`: the Driver's env-gated probe records (79).
- `raw/ext-c3/`: the disclosed C3/C3u extension (14 receipts, its own `driver-probe.jsonl` with 13 records and `run-meta.json`).
- `raw/run-meta.json`: run metadata.
- `r2-02-summary.json`: every headline number, recomputed by `verify_artifacts.py`.
- `provenance.json`, `source-head.txt`: SHAs, binary identity and environment.
- `unit-cargo-test-browser.txt`: the Rust unit result excerpt.

Reproduce, with `<lanes>`/`<tmp>` placeholders, inside the isolated session and the quiet lock:

```sh
flock <tmp>/locks/quiet-lane.lock <lanes>/cua-x11-session.sh \
  <worktree>/libs/cua-driver/examples/jev-use/.venv/bin/python \
  <worktree>/docs/experiments/r2-02-2026-10-01/run_r2_02.py \
  --driver <lanes>/bin/cua-driver-r2-02-cdp-wake-4d092b160 --out <out>
# extension (deviation 6), binary built at 55846dc66:
flock <tmp>/locks/quiet-lane.lock <lanes>/cua-x11-session.sh \
  <worktree>/libs/cua-driver/examples/jev-use/.venv/bin/python \
  <worktree>/docs/experiments/r2-02-2026-10-01/run_r2_02.py \
  --driver <lanes>/bin/cua-driver-r2-02-cdp-wake-55846dc66 --out <out-ext> \
  --pairs 0 --controls 6 --default-off 0 --groups C3_early,C3u_early_unguarded
python verify_artifacts.py
```
