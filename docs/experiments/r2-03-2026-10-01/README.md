# R2-03: guarded completion with a real provider, 2026-10-01

## Result

**Disposition: KEEP**, within the claim boundary below. The run used the real #4316 Driver, a real Chromium browser, a live provider (TypeSafe Jev, model `jev-1.13.0`) and an independent fixture oracle. All arms ran on one source tree and one binary. The two arms differ only in the `--guarded-completion` flag.

- **Outcomes: 40/40 verified in each arm.** Baseline 40/40, guarded 40/40 (LIVE_PROVIDER + REAL). No failures, timeouts or duplicate submits.
- **Work deleted:** the guarded arm made one provider request and one decision per task instead of two, in 40 of 40 pairs. This is confirmed by responder receipts, not just configured intent. Each pair also saved 710 input tokens and 45 output tokens. The median provider decision time saved was 205.965 ms per pair (95% CI [-236.39, -176.525]).
- **Wall-clock saved:** the paired median `task_verified_ms` difference (guarded minus baseline) is **-211.849 ms**, 95% bootstrap CI **[-251.777, -192.138]**. Guarded was faster in 35 of 40 pairs. Medians: baseline 3698.287 ms, guarded 3519.708 ms, a reduction of about 5.7%.
- **Fresh refs:** guarded completion was accepted 40/40 times. Every guarded `browser_click` sent the fresh post-mutation Submit ref, and the pre-mutation ref differed in 40/40. In both arms, 80/80 clicks used the latest snapshot's Submit ref, and none reused the pre-mutation ref.

## Scope and pre-registration

- Owners: kvnloo/cua#10, #78, trycua/cua#4316 and #4394. The spec is the R2-03 row of kvnloo/cua#93.
- `PREREG.json` was committed before any measured run: commit `70e9d6b79a8726dcc34bbb5174363200ce47dd10`, sha256 `a900540933efb68fc0f273543e862f6b38ce9ad2f8337d34e59913a91c89f82e`. It has not been edited since. Departures from it are listed under Deviations.
- The unchanged simulated matrix from #106 was not re-run.

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Tested source | `a0bca744067d04f05904319d3d919be30c336556` (parent `345ff6d9`) |
| Live trycua/cua#4316 head (gh read, 22:00:36Z) | `a0bca744067d04f05904319d3d919be30c336556`, OPEN, not draft. Equals the tested source. |
| trycua/cua#4394 live head (not tested) | `039257811e0bbb2348c616c52562409923d2856f` |
| Upstream main at execution (not tested) | `effd9b298942d7e9808077adef4ef575d561141d` |
| Driver | `cua-driver-4316-a0bca7440`, sha256 `e57bb9aef66a3ef0aed8bb1c09ff8828e1b2b89b7f57f9a60de631dee3eaff95`, `cua-driver 0.31.0`. Plain binary, not rebuilt. |
| Runner source | `libs/cua-driver/examples/jev-use` is byte-identical to the tested source in every phase (`validity` files under raw/). `run.py` sha256 `b0880568…` |
| Harness / launcher used for controls and main | commit `3062ebcf7`. Harness sha256 `b4e38c35…`, launcher sha256 `67ea2d0f…` |
| Publication SHA | assigned later by the orchestrator |

`provenance.json` lists the full values, environment and commands. `source-head.txt` pins the tested commit.

## Environment

- Linux x86-64: 10 logical CPUs (i9-10900KF), 23 GiB RAM, kernel 7.2.2.
- Display: private rootless Xvfb with a private dbus session, openbox and picom. The host Wayland/Hyprland environment was scrubbed. No AT-SPI bus.
- Browser: Google Chrome 151.0.7922.71, chosen by the Driver, with a fresh isolated profile for each trial.
- Driver safety settings: defaults. Chromium sandbox on, no permission-mode override, no approval bypass, no `*-e2e` wrapper.
- Provider: typesafe-sdk 0.6.0 (`uv.lock`), responder host `api.typesafe.ai`. The key was forwarded into the session by name only.
- The main phase ran under the quiet-lane lock from 22:09:01Z to 22:18:41Z. Other agents' correctness work kept running during that window: 1-minute loadavg at trial spawn had a median of 10.19 (range 3.12 to 17.21). Every trial's loadavg is recorded.

## Method

- **Forced path:** the built-in jev-use fill→submit form, Python runner, `--provider live`, `max_steps 4`, visual observation on its default `auto`. The visual parse was skipped on every step because the page structure already offered executable candidates.
- **Actual route and producer:** taken from Driver receipts.
  - Step 1 was `browser_type` with result `route=trusted_input, effect=unverifiable`.
  - Step 2 was `browser_click` with `input_route=dom_event` and result `route=dom, effect=unverifiable`.
  - Step 2 was chosen by the provider in the baseline arm and by guarded completion in the guarded arm.
- **Arms:** baseline runs `python/run.py --provider live`. Guarded adds `--guarded-completion`. Everything else is the same.
- **Design:** 40 pairs in strict AB/BA alternation (odd pairs ran baseline first, even pairs guarded first). Each trial started a fresh Driver MCP process, a fresh Chromium profile, a fresh harness-owned loopback fixture and a unique token. There was a 0.3 s gap between trials. Every trial is kept.
- **Independent oracle:** the harness polled the fixture's `/state` every 4 ms. It also recorded the server-side submit instant and a submit counter. A trial counts as verified when `/state == {submitted: token}` and exactly one submit was received. The runner's own outcome event is logged but is not the oracle.
- **Receipts:** `harness/receipt_launcher.py` imports the unmodified `run.py` and wraps calls in the runner process. It records:
  - every provider HTTP attempt: host, path, status, whether `x-typesafe-request-id` was present plus a sha256 prefix of it, and timing;
  - every SDK response: `model`, token usage and the selected id;
  - every Driver MCP call: the `ref` argument only, Submit refs per snapshot, and route/effect.
  It never records headers, bodies, typed text or the key. It changes no arguments, return values or exceptions. It is active only when the launcher is used, so default behaviour is unchanged.
- **Clock:** `CLOCK_MONOTONIC` is shared by the harness and runner processes on the same host, so no clock alignment is needed.
- **Metric definitions:**
  - `task_verified_ms`: from the start of the first `semantic_v2` observation to the first oracle observation.
  - `spawn_verified_ms`: from runner spawn to the oracle. This is the definition the #10 harness used.
  - `task_mutation_ms`: up to the server-side submit instant.
  - `cold_setup_ms`, `runner_lifetime_ms` and `cleanup_after_outcome_ms` are reported separately.
- **Statistics:** paired differences (guarded minus baseline), with seeded percentile bootstrap 95% CIs (10,000 resamples, seed 20261001) for the median and the mean.

## Results

| Row | Evidence class | Baseline | Guarded | Paired (guarded − baseline), median [95% CI] |
|---|---|---|---|---|
| Independently verified outcomes | LIVE_PROVIDER + REAL | 40/40 | 40/40 | gap 0 |
| Decision routes | REAL | `[provider, provider]` 40/40 | `[provider, guarded-completion]` 40/40 | — |
| Provider responses (receipts) per verified task | LIVE_PROVIDER | 2 (80 total) | 1 (40 total) | −1 in 40/40 pairs |
| Provider HTTP attempts | LIVE_PROVIDER | 80 | 40 | no retries |
| Receipts = runner decisions = HTTP 200 with request id | LIVE_PROVIDER | all trials | all trials | — |
| Input / output tokens per task | LIVE_PROVIDER | 1348 / 98 | 638 / 53 | −710 / −45 |
| Provider decision ms per task | LIVE_PROVIDER | median 462.32 | median 261.74 | −205.965 [−236.39, −176.525] |
| `task_verified_ms` (primary) | BENCHMARK | median 3698.287 | median 3519.708 | **−211.849 [−251.777, −192.138]**; mean −280.659 [−468.89, −171.482]; faster 35/40 |
| `task_mutation_ms` | BENCHMARK | 3696.065 | 3513.801 | −213.032 [−251.508, −192.351] |
| `spawn_verified_ms` | BENCHMARK | 5053.017 | 4858.184 | −260.996 [−447.325, −194.679]; mean CI crosses 0 |
| `cold_setup_ms` | BENCHMARK | 1363.436 | 1352.277 | −3.146 [−189.241, 50.177] (no effect expected) |
| `runner_lifetime_ms` | BENCHMARK | 5695.041 | 5444.748 | −300.219 [−399.655, −200.534] |
| Driver actions / semantic observations per task | REAL | 2 / 2 | 2 / 2 | 0 |
| Fresh-ref proof | REAL | 40/40 clicks used the latest snapshot ref; 0 reused the pre-mutation ref | 40/40 accepted; fresh == dispatched 40/40; prior ≠ fresh 40/40; step-2 `provider_decision_ms = 0` 40/40 | — |
| Named-span coverage of `task_verified_ms` | BENCHMARK | median 1.0 | median 1.0 | Phase-0 gate (>90%) met |
| Regression suites at the tested source | UNIT | Python 248 run, OK (1 skipped); guarded-focused Python OK; TypeScript 155/155; guarded TypeScript 30/30; typecheck OK; 4 CLI verifiers rc 0 | | — |

The wall-clock saving (−211.8 ms) is about the same size as the deleted provider decision time (−206.0 ms). The two action spans (about 1.5 s each) and the two semantic observations are unchanged. That fits the reading that the guard removes only the second provider round trip and adds no measurable cost of its own.

Pair 16 baseline had one provider decision of 3451.74 ms, but its HTTP attempt took only 266 ms. About 3.2 s went somewhere inside the runner's provider call outside the HTTP request: client construction, thread scheduling, or both, under loadavg around 10. This was not instrumented further. The trial stays in the data and is why the mean CIs are wider than the median CIs.

## Work deleted vs wall-clock saved

- **Work deleted (structural, receipt-backed):** per verified task, 1 provider HTTP request, 1 provider decision, 710 input tokens and 45 output tokens. That is 40 requests, 28,400 input tokens and 1,800 output tokens across the 40 guarded trials. Driver actions, semantic observations and fresh-ref resolution are unchanged; the guard still takes a fresh snapshot.
- **Wall-clock saved (measured):** median 211.849 ms per task on this fixture, 95% CI [−251.777, −192.138]. This is about 5.7% of `task_verified_ms`.
- **Cost:** the receipts expose token usage only. No price or cost field is returned, so no monetary figure is claimed.

## Negative and fallback controls

| Control | Evidence class | Result |
|---|---|---|
| C0 mock smoke (two runs, untimed, excluded) | REAL | 4/4 verified. Receipts show `backend=mock` and 0 provider HTTP attempts, so mock decisions cannot be mistaken for live ones. |
| C1 guard decline: the existing `DUPLICATE_SUBMIT_ON_INPUT` fixture, guarded arm, live provider, n=3 | LIVE_PROVIDER + REAL | 3/3: guard declined with `submit_not_unique`, route `[provider, provider]`, 2 provider responses each, fixture verified with exactly 1 submit, 0 stale dispatch. |
| C2 provider unreachable: `TYPESAFE_BASE_URL` set to a closed loopback port, one cell per arm | REAL | 2/2: 0 successful provider responses, only `TypeSafeAPIConnectionError` (3 SDK attempts each, all to 127.0.0.1), 0 Driver mutations, fixture stayed `submitted: null`, outcome not verified (`runner_error`, rc 1). Configured intent was not counted as a decision. |

## Deviations

1. **smoke-1:** the launcher's first version tested `isinstance(arguments, dict)`, but candidate arguments are a read-only mapping, so smoke-1 did not record the click `ref`. This was fixed before smoke-2, and smoke-2 and every later phase use launcher `67ea2d0f…`. Both smoke runs are kept in `raw/smoke/` and excluded from analysis, as the pre-registration says.
2. **Request budget accounting:** the budget counts every HTTP attempt, including the 6 loopback-refused attempts from C2. Total 132 of the 300 cap; 126 actually reached the provider.
3. **Control phases and the lock:** C1 and C2 were untimed and ran outside the quiet-lane lock, as pre-registered for correctness phases. They may have added load to another lane's measurement window.
4. **Chrome version check:** I ran `/opt/google/chrome/chrome --version` once outside the isolated session to confirm the browser version. It only prints a version and touches no display or profile, but it breaks the "every Chromium run goes through the session" rule.
5. **Mean CIs:** the pre-registration asked for both median and mean CIs, and both are reported. The KEEP gate uses the median CI, as pre-registered.

## Limits and claim boundary

- One fixture: the jev-use built-in fill→submit form, with one forced DOM page-structure path.
- Python runner only. The TypeScript runner was not run live.
- One Driver binary: the #4316 build `e57bb9ae`, 0.31.0, based 28 commits behind the setup's main pin. No numbers are compared with the main Driver.
- Google Chrome 151 in a private rootless Xvfb session on one Linux host. The quiet-lane lock serialised timing phases but did not make the machine idle (loadavg about 10). Arms were interleaved within that same environment.
- One live provider: TypeSafe Jev, responder model `jev-1.13.0`, as reported in the receipts.
- The receipts here are an attributed responder receipt equivalent to #4394's `backend` field. They do not test #4394's code.
- Results do not transfer to other tasks, providers, platforms, upstream main, or another #4316 head.
- No Driver-internal profile is claimed.
- About 3.2 s in one baseline provider call is unattributed.
- 40 pairs gives an estimate, not a certified tail.
- No new service, verifier, router or API is proposed. The RFC delta is none.

## Disposition

**KEEP.** None of the KILL conditions occurred: no stale-ref dispatch, no unverified guarded completion, no duplicate submit, and the guard never accepted in C1. The structural deletion holds by receipts (2 → 1 provider requests in 40/40 pairs). The paired median `task_verified_ms` is −211.849 ms with a 95% CI that excludes 0. The scope is exactly the claim boundary above.

## Files

- `PREREG.json`: the pre-registration.
- `provenance.json`, `source-head.txt`: provenance.
- `r2-03-summary.json`: every derived number plus a per-trial table.
- `verify_artifacts.py`: recomputes the summary from raw/ and checks it, the README headline values and a privacy scan.
- `harness/`: `r2_03_harness.py`, `receipt_launcher.py`, `run_phase.sh`, `package_raw.py`.
- `raw/main/*.jsonl`: one file per trial with the cell record, runner events with arrival times, and receipts. `raw/controls-*`, `raw/smoke/`, `raw/validity/`, `raw/end/`, `raw/budget.json`, `raw/main-lock.txt` and `raw/unit/` hold the controls, smoke runs, per-phase validity, budget, lock times and unit results.

Reproduce from this directory with `python3 verify_artifacts.py`.
