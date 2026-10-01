# R2-02: real CDP event wake vs. the poll loop, 2026-10-01

Owners: kvnloo/cua#93 (R2-02), #10 (accounting), original E3.

## Result in one paragraph

On the jev-use browser fixture, a function-local wake on the Driver's existing CDP event demux (`CdpConnection::subscribe`) made the same DOM-route Submit click **slower**. The wake waited for a main-frame `Page.frameNavigated` with a new loader id, then did one fresh `/state` read. Both arms verified **24/24**. The median paired difference (event − poll) in click-to-verified time was **+42.1 ms**, with a 95% bootstrap CI of **[+31.9, +56.9] ms**. The poll arm was faster in **21 of 24** pairs.

The cause is ordering. The fixture's state commit (the oracle effect) lands about 1 ms after `Runtime.callFunctionOn` returns. The poll loop's first immediate read already sees it in 21/24 trials, so it needs no sleep. The commit event arrives a median **33.8 ms** after dispatch, and cleanup (`Page.disable`) adds a median **10.6 ms**.

Every correctness control met its pre-registered expectation, 63/63 in total. No event, and no missing event, ever produced a verified record without the oracle. Under the pre-registered gates the disposition is **KILL** for this wake source on this fixture and route.

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
| Publication SHA | set later by the orchestrator. It is not the tested source |

The `0.32.0` main Driver (`8b037961…`) and the #4316 Driver (`e57bb9ae…`) were **not** used. No number here is compared with them, with #106, or with the #93 E0/E1 probe.

## Environment

- Private rootless Xvfb 1920x1080x24 with `-nolisten tcp`, openbox and picom, a private dbus, and a scrubbed env (`cua-x11-session.sh` sha256 `de01a439…`). No AT-SPI bus. The host Wayland/Hyprland session was never reachable.
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
4. Drains and discards everything queued before dispatch.
5. After dispatch, waits for the first `Page.frameNavigated` on that session for the main frame with a different loaderId, or for a 1000 ms deadline.
6. Drops the subscriber and calls `Page.disable`.

The record says `wake_hint_only; application effect not verified`.

The public `ActionResult` projection drops unknown structured keys, so the record goes to an env-named JSONL log (`CUA_DRIVER_EXP_R2_02_CDP_WAKE_LOG`). The click's public result keeps its original shape: 0 of 113 trials leaked the probe key. Unit tests passed: `cargo test -p cua-driver-core --lib browser::` ran **184 passed, 0 failed**, including 5 probe tests (`unit-cargo-test-browser.txt`). The jev-use suites on the worktree matched the main baseline: Python 229 run, 228 passed, 1 skipped; TypeScript 105/105; typecheck and 4 CLI verifiers rc 0. The two `*-guarded-focused` steps fail by construction because those files exist only on #4316.

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
| Paired diff (event − poll), median | **+42.126 ms**, 95% bootstrap CI **[+31.877, +56.871]** (10000 resamples, seed 2026100102) | | BENCHMARK |
| Pairs favouring event / poll | 3 / 21 | | BENCHMARK |
| Diffs in the 3 pairs where poll slept | −191.099, −24.627, −26.176 ms | | BENCHMARK |
| Median diff in the 21 pairs where poll did not sleep | +44.691 ms | | BENCHMARK |

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

All 24 probes ended in `wake` and 0 in `deadline`. The 24 wakes saw 120 non-matching `Page.*` events (other methods) and 0 pre-dispatch events.

### Controls (all meet expectation; failures would be listed in `r2-02-summary.json`)

| Group | N met / N | Observed | Class |
|---|---|---|---|
| C1 lost (matching event suppressed) | 6/6 | Deadline every time (6 suppressed); first post-call read verified; median 2545.110 ms, so the full 1000 ms deadline is the cost of a lost wake | REAL |
| C2 spurious (interstitial commit, no effect yet) | 6/6 | Woke on a real commit; first post-wake read `unknown` 6/6; verified later by the fallback poll (5 reads); median 1960.282 ms | REAL |
| C3 early (synthetic matching event before dispatch) | 6/6 | Discarded by the pre-dispatch drain (`early_rejected` 6); real commit woke; verified | FIXTURE (synthetic event in a real run) |
| C3u early, guard ablated | 6/6 | Woke at once on the injected event; the oracle decided (verified, because the effect had already landed) | FIXTURE |
| C4 unrelated (child-frame churn, 150 ms target-side commit delay) | 6/6 | 36 real child-frame `frameNavigated` and 506 other-session events, none woke; main commit woke; verified | REAL |
| C5 stale (synthetic event with the pre-dispatch loaderId after dispatch) | 6/6 | `stale_rejected` 6; real commit woke; verified | FIXTURE |
| C5u stale, guard ablated | 6/6 | Woke at once on the stale event; the oracle decided | FIXTURE |
| C6 timeout, event (inert Submit) | 6/6 | Deadline; every read `unknown`; outcome timeout; 0 POSTs; median 4558.459 ms | REAL |
| C6p timeout, poll (inert Submit) | 6/6 | Outcome timeout; 0 POSTs; median 3554.064 ms. The event deadline adds about 1 s to the worst case | REAL |
| C7 refuted (value rewritten before POST) | 6/6 | Woke on a real commit; first post-wake read `refuted` 6/6; outcome refuted, never verified | REAL |
| C0 default-off (no env gate, argument present) | 3/3 | No probe record written (no log file); verified via the poll loop | REAL |

Across all 113 trials:

- False successes (verified without a final verified read and a journaled POST): **0**.
- Guarded controls woken by an injected event: **0**.
- Harness, tool or oracle errors: **0**.
- Probe log records: 79, matching the 79 armed calls by nonce.

## Work deleted vs. wall-clock saved (reported separately)

- **Work deleted (structural):** over 24 trials the event arm removed the 4 fixed 100 ms sleeps and 4 oracle reads that the poll arm needed in 3 trials. It **added**, per click, one subscriber and three CDP round trips: `Page.enable`, `Page.getFrameTree` and `Page.disable`.
- **Wall-clock saved:** none. The paired median is +42.1 ms (event slower), with a CI entirely above 0. The only wins were the 3 pairs where the effect landed after the tool returned under load. Those pairs show that a late effect is where a wake could pay off, but they are 3 of 24.
- No CPU measurement was taken. No CPU claim.

## Why the wake loses here

On this route, `Runtime.callFunctionOn` returns after `click()` has queued the form submission. The browser sends the POST at once, and the loopback fixture commits state about 1 ms later (click-to-effect median 1542.58 ms against a poll tool span of 1542.30 ms). The poll arm's immediate first read usually lands after that commit.

The navigation commit that the probe waits for comes after the server response and renderer commit, so it lags the oracle effect by tens of milliseconds. For this oracle, waking on commit means waiting for something that happens **after** the predicate is already true. Cleanup then runs while the renderer is loading the new document, which makes `Page.disable` slow.

## Negative / fallback controls

These are covered above. Lost and timeout cases end at a bounded deadline followed by a fresh read and the unchanged poll fallback, so event absence never authorizes anything. Spurious and refuted wakes are never treated as success. Early, stale and unrelated events never wake when the guards are on. With the guards ablated (C3u/C5u) a wrong wake happens, and the oracle still decides the outcome.

## Deviations from PREREG.json

1. **Probe record channel.** PREREG expected the probe record in the `browser_click` structured result, and C0 was worded "no probe output in the result". The first shakedown, with binary `4ca5c0ff…` from `906377ca0` (no measured trials), showed that the Driver's public `ActionResult` projection drops unknown keys. The record moved to the env-named JSONL log at `4d092b160`, and C0 became "no record written". The arms, controls, n, gates and timing span are unchanged.
2. **Unrelated-event control.** To give child-frame events a guaranteed post-dispatch window, the `unrelated` variant posts to `/submit?delay_ms=150`, which the harness handler delays 150 ms before the unchanged commit. This was set before the measured run; its timings are not compared with the pairs.
3. **Shakedowns.** Two correctness shakedowns (15 trials each, no quiet lock) ran before the measured run, to validate the harness. They are not in `raw/` or in any statistic; they are kept only in the lane artifacts mirror.
4. **Test-only commit.** `3e41eb1b1` fixed a `#[cfg(test)]` initializer after the binary was built at `4d092b160`. The unit results above are from `3e41eb1b1`.
5. **Summary counting fix.** A cosmetic `probe_end` tally for no-probe groups was fixed in `verify_artifacts.py` before the summary was committed. No raw data changed.

## Limits

- One fixture, one route (`dom_event`), one browser build and one host. The effect is a loopback POST that commits about 1 ms after dispatch. Any effect that lands later (a slow server, an async handler, client-side rendering) changes the trade-off; the 3 late-effect pairs hint at that but are not a test of it.
- The browser action span is about 1.54 s in both arms, mostly the R2-01 subject. It is equal across arms but dwarfs the delta.
- Loadavg reached 7.5 while the lock was held, because others' non-timed work was running. Interleaving spreads that across arms, but tails are noisy.
- Intra-Driver probe phases and harness timings come from different processes. They are never subtracted from each other. Harness timings and the fixture journal share one process and `CLOCK_MONOTONIC`.
- n=24 pairs: the p95 values are estimates, not tail guarantees.
- The wake source was `Page.frameNavigated` only. Earlier signals (`Network.requestWillBeSent`, `Page.frameStartedNavigating`) precede the effect, so they would be spurious-by-construction wakes for this oracle. They were not tested.

## Claim boundary

**Supported:** on main `229b65b28` plus a default-off probe, with Chrome 151 in a private Xvfb session, the jev-use form fixture and a DOM-route Submit, waking on the existing CDP demux for the main-frame commit and then re-reading `/state` is **slower** than the existing 100 ms poll loop. The median paired cost is +42 ms with a CI above 0. Its event/oracle separation is correct: across 63 control trials, no early, stale, unrelated, spurious, lost or refuted event changed what the oracle decided.

**Not claimed:** trusted-input routes, AT-SPI/native events (R2-09), `wait_for_window`'s 0.25 s list_windows poll (no CDP event exists for native window creation, so it was NOT_RUN), other pages, other browsers, delayed effects, CPU, a public Driver contract, or composition with other treatments (R2-10). No RFC delta.

## Disposition

**KILL**, by the pre-registered gate (event arm slower, CI lower bound > 0), for *commit-event wake on this fixture/route*. The correctness design is sound, and that includes the generation guard, the pre-dispatch drain, deadline fallback and the oracle-only success rule. It should be reused if a later lane has an effect that demonstrably lands after the tool returns. Before revisiting, that lane would need two things: a measured share of late-effect trials large enough to matter, and a wake event that does not lag the oracle effect.

## Files

- `PREREG.json`: pre-registration (sha256 above).
- `run_r2_02.py`: the harness (reuses the jev-use Driver client, fixture server, candidate builder and oracle).
- `raw/NNN-<group>-<arm>.jsonl`: one receipt per trial (113).
- `raw/driver-probe.jsonl`: the Driver's env-gated probe records (79).
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
python verify_artifacts.py
```
