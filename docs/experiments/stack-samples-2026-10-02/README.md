# stack-samples-2026-10-02: Hermes sample collection and shadow backend evaluation

Lane: stack SAMPLES (kvnloo/hermes-agent#319, 2026-10-01 directive). Scope: collect joined decision
receipts from an ordinary Hermes workload without changing Hermes behaviour, freeze them, and compare
base-rate and deterministic baselines with every locally runnable z0int backend on exactly the same
examples. No new architecture, protocol or question family, and no active control. `promotion_ready`
is false for every row.

> **Corrected by SAMPLESFIX (2026-10-02, erratum E2).** An earlier version of this README blamed the
> default `-q` approval gate for the CUA input-task failures and listed those tasks as BLOCKED. The
> receipts contradict that. No CUA run made a single successful tool call. All 27 tool calls in the 12
> CUA runs were refused by Hermes's `tool_call` bridge before any tool was dispatched. No run reached
> computer_use, cua-driver or the approval gate. The CUA failures are REAL failures: the 3B model
> misused the bridge. The lane's request for an owner decision on an approval bypass
> (`approvals.single_query_mode`) is **withdrawn**. Labels, dataset and metrics are unchanged. Every
> change is listed under "Deviations and disclosures", and the repair lane's packet is
> `docs/experiments/stack2-samplesfix-2026-10-02/`.

`PREREG.json` was committed (726d6bf30) before any measured run. `python3 verify_artifacts.py` re-checks
everything below from committed data and prints `RESULT PASS`. Every table in this README sits between
`GENERATED` markers. `harness/make_tables.py` regenerates each one byte-for-byte from committed raw files,
and `verify_artifacts.py` fails if any table differs. Tamper copies print `RESULT FAIL` for each of these
edits: a flipped oracle verdict or turn label, an edited table cell, a CUA log error line rewritten as a
completed call, and a changed MANIFEST count.

## Results

**Workload (REAL).** 112 preregistered tasks; 105 ran and 7 were cut by the 08:35Z stop rule (NOT_RUN,
listed in `dataset/runs.jsonl`). Each ran as one isolated one-shot Hermes turn (hermes `exp/stack-samples-20261002`
5d01f60897373e67) with the metadata-only observer (#385), executor qwen2.5:3b on the system Ollama (0.16.1, CPU,
digest 357c53fb). The independent fixture oracle passed 48 and failed 57; 0 were unknown.

<!-- BEGIN GENERATED workload -->
| kind | run | oracle pass | oracle fail |
|---|---|---|---|
| file tools (10 families) | 93 | 46 | 47 |
| CUA, GTK3 TaskWindow in a private Xvfb session | 12 | 2 | 10 |
| total | 105 | 48 | 57 |
<!-- END GENERATED workload -->

- 97 runs exited 0 and 8 exited 1, with no timeouts. Of the 8, 7 hit Hermes's own
  `max_iterations_reached(4/4)`, and t096-sum_numbers-10 ended with `pending_tool_result`: it used its
  4/4 budget on a tool call.

<!-- BEGIN GENERATED exits -->
| exit code | turn_exit_reason (observer on_session_end) | runs | tasks |
|---|---|---|---|
| 0 | `text_response(finish_reason=stop)` | 97 | (file and CUA tasks) |
| 1 | `max_iterations_reached(4/4)` | 7 | t013-cua_agree-01, t015-sum_numbers-01, t025-cua_read_counter-02, t038-json_field-06, t040-cua_increment-01, t058-sum_numbers-07, t074-cua_agree-02 |
| 1 | `pending_tool_result` | 1 | t096-sum_numbers-10 |
<!-- END GENERATED exits -->

- Workload descriptor, not a latency result: the median wall time per task was 92 s, taken from
  `started_at`/`ended_at` during unlocked, contended collection outside `quiet-timed`.
- 0 observer rows were dropped, and 0 of 235 API attempts reached the 4096-token served context
  (`usage.prompt_tokens`).
- Per family: `find_file` 0/10 and `uppercase_copy` 0/10 passed; `json_field` 9/10 and `read_code` 8/9 passed.

**CUA runs: every failure is a tool_call bridge failure (REAL).** CUA tasks ran with `-t computer_use`,
so the only tool was computer_use. Hermes's default tool search deferred it behind the `tool_search` /
`tool_call` bridge ("0 core/visible tools kept, 1 deferred" in all 12 agent.logs). The 3B model never
called `tool_search` and never produced a valid `tool_call`:

- Tool calls: 27 in total, 0 completed. All 27 went to `tool_call`, and the bridge refused every one:
  - 23 `tool_call requires 'calls' (an array of {name, arguments})`.
  - 3 `'<name>' is not a known tool name` (`CuaTestHarness GTK3 Tasks`, `increment_button`,
    `clickCountButton`).
  - 1 `tool_call cannot invoke 'tool_search' (it is itself a bridge tool)`.
- Source check: all three errors are returned by `tools/tool_search_validation.py` before dispatch (SOURCE).
- What never happened:
  - computer_use was dispatched 0 times, and no Driver or computer_use logger line appears.
  - 0 approval or fail-close lines appear in agent.log, errors.log or the reply.
  - The fixture's GUI state is unchanged before and after in 12/12 runs.
- Cross-checks agree: the observer has 27 `pre_tool_call` and 27 `post_tool_call` rows in these 12
  sessions, matching the agent.log count run by run. API calls are 35 in both agent.log and observer.
- Positive control: the SMOKE lane's logs from the same Hermes logger contain 481
  `tool computer_use completed` lines, so a dispatch would have been logged.
- On the earlier figure of 23: the verifier's "23 tool errors" counts only the largest class
  (`requires 'calls'`). The logs hold 27.
- Consequence for the input tasks: `cua_increment` (0/2) and `cua_agree` (0/2) fail for the same reason
  as `cua_read_counter` (0/3). The approval gate (`tools/approval.py`, fail-closed with no human in `-q`
  mode) was never reached, so the preregistered approval expectation is a SOURCE-only statement that
  this run did not exercise.
- The 2 `cua_button_present` passes are not evidence of perception. The model answered "No" in all 5
  runs without any successful tool call, and the 2 passes are exactly the 2 tasks whose expected answer
  is "no" (t024, t083).
- Receipts:
  - `raw/runs/<cua run>/agent.log` and `errors.log`: the private-home logs, sanitized.
  - `raw/analysis/cua-bridge-tally.json`: written by `harness/cua_bridge_tally.py`.

<!-- BEGIN GENERATED cua -->
| task | oracle expects | verdict | exit / turn_exit_reason | API calls | tool calls completed | tool errors (class) | approval lines | GUI state changed | reply (first 40 chars) |
|---|---|---|---|---|---|---|---|---|---|
| t006-cua_read_counter-01 | `counter=0` | fail | 0 `text_response(finish_reason=stop)` | 2 | 0 | 1 (1 unknown_tool_name) | 0 | no | `It seems that 'CuaTestHarness GTK3 Tasks` |
| t013-cua_agree-01 | `{"agreed": true}` | fail | 1 `max_iterations_reached(4/4)` | 4 | 0 | 4 (4 missing_calls_array) | 0 | no | `Given that I've attempted to invoke tool` |
| t021-cua_button_present-01 | `yes` | fail | 0 `text_response(finish_reason=stop)` | 2 | 0 | 1 (1 missing_calls_array) | 0 | no | `No` |
| t024-cua_button_present-02 | `no` | pass | 0 `text_response(finish_reason=stop)` | 2 | 0 | 1 (1 missing_calls_array) | 0 | no | `No` |
| t025-cua_read_counter-02 | `counter=0` | fail | 1 `max_iterations_reached(4/4)` | 4 | 0 | 4 (4 missing_calls_array) | 0 | no | `Given that repeated calls to 'tool_call'` |
| t029-cua_button_present-03 | `yes` | fail | 0 `text_response(finish_reason=stop)` | 2 | 0 | 1 (1 missing_calls_array) | 0 | no | `No` |
| t040-cua_increment-01 | `{"counter": 3}` | fail | 1 `max_iterations_reached(4/4)` | 4 | 0 | 4 (1 bridge_self_invoke, 1 missing_calls_array, 2 unknown_tool_name) | 0 | no | `Following up on my previous commands, I ` |
| t041-cua_button_present-04 | `yes` | fail | 0 `text_response(finish_reason=stop)` | 2 | 0 | 1 (1 missing_calls_array) | 0 | no | `No` |
| t074-cua_agree-02 | `{"agreed": true}` | fail | 1 `max_iterations_reached(4/4)` | 4 | 0 | 4 (4 missing_calls_array) | 0 | no | `Given repeated failures with consistent ` |
| t080-cua_increment-02 | `{"counter": 3}` | fail | 0 `text_response(finish_reason=stop)` | 4 | 0 | 3 (3 missing_calls_array) | 0 | no | `Let's try incrementing the button manual` |
| t083-cua_button_present-05 | `no` | pass | 0 `text_response(finish_reason=stop)` | 2 | 0 | 1 (1 missing_calls_array) | 0 | no | `No` |
| t090-cua_read_counter-03 | `counter=0` | fail | 0 `text_response(finish_reason=stop)` | 3 | 0 | 2 (2 missing_calls_array) | 0 | no | `It seems that capturing the window with ` |
| total (12 runs) |  | 2 pass |  | 35 | 0 | 27 (1 bridge_self_invoke, 23 missing_calls_array, 3 unknown_tool_name) | 0 | 0 changed |  |
<!-- END GENERATED cua -->

**api.attempt_will_fail: DEGENERATE (H1 confirmed).** There were 235 joined attempts with 0 positives. The exact
one-sided 95% upper bound on the failure rate is 1.27%. The join audit counts 235 pre-request rows, 235 joined,
0 orphans, 0 terminals without a pre and 0 dropped rows. No backend ranking is claimed on this lane. The table
only shows miscalibration against an all-negative label.

<!-- BEGIN GENERATED api -->
| row | Brier | log-loss | mean p(fail) | scored | p exactly 0 or 1 |
|---|---|---|---|---|---|
| deterministic LOO-run prior | 0.0000 | 0.002 | 0.002 | 235 | 0 |
| decider_2b | 0.0389 | 0.219 | 0.197 | 235 | 0 |
| nanojev | 0.0864 | 0.348 | 0.293 | 235 | 0 |
| deterministic 0.5 | 0.2500 | 0.693 | 0.500 | 235 | 0 |
| laya_421m | 0.3051 | 0.804 | 0.552 | 235 | 0 |
| julia_1 | 0.6285 | 2.111 | 0.744 | 235 | 0 |
| qwen_3b_baseline | 0.9706 | 4.584 | 0.985 | 235 | 0 |
<!-- END GENERATED api -->

- What each row's probabilities look like:
  - The deterministic LOO-run prior is a smoothed prior from the other runs, which are all 0.
  - decider_2b: every p is below 0.4.
  - nanojev: p is about 0.3.
  - laya_421m: every attempt falls in the 0.4-0.6 bin (mean 0.552).
  - qwen_3b_baseline: every attempt falls in the 0.8-1.0 bin (mean 0.985).

**verification_needed: carries signal (H2 confirmed); no backend beats the preregistered baseline (H3 not supported).**
There are 105 turn examples, all labelled: 57 positive ("the unverified outcome failed the oracle") and 48
negative. Every model row had coverage 1.0 (0 backend errors, 0 missing probabilities, no p exactly 0 or 1).

How to read the table:
- G3 compares each row with the deterministic leave-one-family-out prior. It uses a paired bootstrap
  over tasks (2000 resamples) and reports the Brier difference with its 95% CI.
- Latency columns come from the scorer's per-call wall clock (`scorer_timing.wall_ms`): the first call
  (cold, includes weight load), then warm p50 / p95 / max over the remaining 104 calls.
- All latency comes from quiet-lane timed scoring processes (BENCHMARK, canary-to-small-cohort grade).

<!-- BEGIN GENERATED turn -->
| row | Brier | log-loss | ECE | acc@0.5 | G3 vs LOO prior: Brier diff [95% CI] | first call wall ms | warm wall p50 / p95 / max ms |
|---|---|---|---|---|---|---|---|
| base rate in-sample (oracle-optimistic ref) | 0.2482 |  |  |  |  |  |  |
| deterministic constant 0.5 | 0.2500 | 0.693 | 0.043 | 0.543 | beats -0.021 [-0.032, -0.011] |  |  |
| deterministic LOO-family prior | 0.2709 | 0.735 | 0.000 | 0.352 | (reference) |  |  |
| julia_1 (CPU) | 0.2466 | 0.852 | 0.113 | 0.667 | no difference -0.024 [-0.074, +0.031] | 10,815 | 68.5 / 87.8 / 106.7 |
| laya_421m (CPU, current default candidate) | 0.2513 | 0.696 | 0.096 | 0.505 | no difference -0.020 [-0.042, +0.001] | 16,963 | 433.8 / 465.4 / 598.4 |
| nanojev (GPU, comparison only) | 0.2906 | 0.779 | 0.212 | 0.457 | no difference +0.020 [-0.022, +0.063] | 17,169 | 28.4 / 34.5 / 35.6 |
| decider_2b (GPU) | 0.4348 | 1.280 | 0.439 | 0.457 | worse +0.164 [+0.081, +0.250] | 197,540 | 24.3 / 24.6 / 180,127.3 |
| qwen_3b_baseline (Ollama logprobs, CPU) | 0.5426 | 4.630 | 0.543 | 0.457 | worse +0.272 [+0.170, +0.378] | 9,356 | 2,057.8 / 2,290.6 / 2,359.7 |
| JEV reference | NOT_RUN (TypeSafe, paid) |  |  |  |  |  |  |
| fail-open control (dead-port adapter) | coverage 0.0, 105/105 rows `backend_error` |  |  |  |  |  |  |
<!-- END GENERATED turn -->

**Reading the table.**
- The preregistered LOO-family prior is a weak reference: family prevalence varies from 0/10 to 10/10, so
  leave-one-family-out estimates move away from each held-out family's rate.
- Descriptively (not preregistered for G3), every model row is within ±0.004 Brier of the constant 0.5 except
  NanoJev, Decider and Qwen, which are worse.
- Julia has the best accuracy (0.667) and is the only row that separates classes.
- Decider, NanoJev and Qwen never cross 0.5 (pairwise disagreement 0.000), so they always say "safe to
  respond". Laya agrees with them on 98 of 105 examples. Julia disagrees with each of them on 54 of 105.
- 19 of 105 examples are wrong for every model row; 32 are right for every model row.
- **decider_2b latency (E3).** The warm p50/p95 hide a stall. The full turn-lane series is:
  - First call: 197.5 s.
  - Warm call 3: one call of 180.1 s. Its cause is not recorded; the scoring log shows torch inductor
    activity, so a second compile is likely.
  - All 104 warm calls give p50 24.3 ms and p95 24.6 ms. Apart from the stall, the slowest warm call
    took 48.8 ms.
  - Warm mean: 1,755.8 ms. The first 4 calls hold 377.7 s of the process's 380.2 s scoring wall time.
  - The api-lane first call (28.9 s) ran after the turn lane and reused its compile cache, so it is not
    a cold start.
- `backend_create_ms` is under 0.1 s for every backend because weights load lazily on the first call.

<!-- BEGIN GENERATED by_kind -->
| row | Brier cua | n cua | Brier file | n file |
|---|---|---|---|---|
| julia_1 | 0.214 | 12 | 0.251 | 93 |
| laya_421m | 0.232 | 12 | 0.254 | 93 |
| nanojev | 0.372 | 12 | 0.280 | 93 |
| decider_2b | 0.588 | 12 | 0.415 | 93 |
| qwen_3b_baseline | 0.833 | 12 | 0.505 | 93 |
<!-- END GENERATED by_kind -->

<!-- BEGIN GENERATED disagreement -->
| pair | disagreement at 0.5 | examples |
|---|---|---|
| decider_2b vs julia_1 | 0.514 | 54/105 |
| decider_2b vs laya_421m | 0.067 | 7/105 |
| decider_2b vs nanojev | 0.000 | 0/105 |
| decider_2b vs qwen_3b_baseline | 0.000 | 0/105 |
| julia_1 vs laya_421m | 0.448 | 47/105 |
| julia_1 vs nanojev | 0.514 | 54/105 |
| julia_1 vs qwen_3b_baseline | 0.514 | 54/105 |
| laya_421m vs nanojev | 0.067 | 7/105 |
| laya_421m vs qwen_3b_baseline | 0.067 | 7/105 |
| nanojev vs qwen_3b_baseline | 0.000 | 0/105 |
| all model rows right / all model rows wrong |  | 32 / 19 of 105 |
<!-- END GENERATED disagreement -->

## Evidence classes

- **REAL:**
  - The 105 Hermes runs, the observer rows and the oracle verdicts.
  - The CUA tool-bridge failures (12 runs, 27 refused tool calls), with the private-home agent.log and
    errors.log committed.
  - Every backend distribution: laya_421m, julia_1, decider_2b, nanojev (z0int 6764ae7) and the Qwen logprob baseline.
  - The fail-open control.
- **BENCHMARK:** each latency number above comes from a scoring process wrapped in `quiet-timed`.
  - Ledger lines are in `raw/quiet-lane-ledger.samples.jsonl`. All have rc 0, and all were acquired after
    collection ended at 08:36:45Z.
  - Load averages and GPU use before and after each process are in `raw/scoring-logs/`. The machine and GPU
    are shared with other lanes (load average ranged from about 2 to 12).
  - The 92 s median task wall time is not a BENCHMARK number (see above).
- **FIXTURE:**
  - The deterministic rows are arithmetic over the REAL labels.
  - The oracle self-test passes on 112 of 112 tasks.
- **UNIT:** the hermes lab suite at 5d01f60897373e67 gives 25 passed and 2 skipped. The 2 Ollama-adapter
  tests skip because z0int is not on the path; with z0int 6764ae78 on PYTHONPATH the 3 shadow test files
  give 13/13. The original lane did not save a log. SAMPLESFIX re-ran the suite under `hostless` with a
  private HOME and saved it to `raw/unit/unit-lab-5d01f608.log` (direct `python -m pytest`, not the
  `run_tests.sh` wrapper).
- **SOURCE:**
  - Shadow output cannot reach Hermes: scoring is offline and starts after collection, and no Hermes runtime
    module reads examples or scored files.
  - The only Hermes code change touches the offline lab scripts. The observer plugin is unchanged from #385.
  - The approval gate fail-closes computer_use input in `-q` mode (tools/approval.py). This run did not
    exercise it (erratum E2).
  - The three tool_call refusals come from tools/tool_search_validation.py before dispatch.
- **NOT_RUN:**
  - The JEV reference observer (TypeSafe, paid).
  - openjev_06b and openjev_4b (not registered; outside the requested set).
  - Plugin on/off behavioural equivalence (not in this lane's scope).
  - The approval-gate path for CUA input actions (never reached; see E2).
- **BLOCKED:**
  - The orchestrator-allowed 64K-context Ollama on 127.0.0.1:11500. It is shared with other lanes, and this
    lane's model pull there was denied by the permission system, so the executor is qwen2.5:3b at a 4096-token
    served context on CPU. The observed 0/235 truncation means the 4K limit did not bind for this workload.

## Isolation

- Every run executed under `hostless` inside a bwrap that mounted an empty tmpfs over the live Hermes home,
  the real home, the host runtime dir and the host X11 socket dir.
- GUI runs kept only their private Xvfb socket bound. `mask.inside` shows 0 entries for every run, and
  `raw/env_checks.json` shows no live paths or provider-secret variables.
- HERMES_HOME was a fresh private dir per run. HTTP(S) egress went to a dead proxy except loopback.
- CUA tasks each ran in a fresh `cua-x11-session.sh` under `hostless` with private AT-SPI. The X11 kit was
  chosen because the Driver's AT-SPI path is verified there; the sway kit (canary-verified) was not needed.
- Live-home stat receipts (metadata only):
  - The live home directory's own mtime moved during every run, and `auth.json`'s mtime moved during 4 runs,
    with its size unchanged.
  - The `auth.json` mtimes step at about 45-minute intervals, and the first one observed (05:36Z) predates
    the first measured run (05:38Z). It is the concurrently running live Hermes; this lane's processes saw
    that directory as an empty tmpfs.
  - state.db, its WAL, config.yaml, .env and logs were unchanged in every run.

## Deviations and disclosures

1. **Isolation receipt redefined after the first freeze (no outcome impact).** The first freeze defined
   "live home unchanged" as all stat lines equal, which the live Hermes's own writes made false for every run.
   The receipt now compares file entries and lists the changed ones. The dataset was re-frozen twice for this
   receipt field only. `events.jsonl`, api examples, and turn requests and labels are byte-identical across
   all three freezes (content hashes 54f5aa49…, 3831e02e…, final 648e418e…).
2. **Harness changes after PREREG, before scoring.**
   - GPU headroom thresholds for decider/nanojev were set to 4800 / 3000 MiB.
   - `verify_artifacts.py` compares the re-run of `evaluate_shadow` with a 1e-9 float tolerance. The scorer
     venv is Python 3.11, and newer Python sums floats with compensation, so results differ in the last bits.
   - `harness/analyze.py`, `build_turn_examples.py`, `score_lane.py` and `run_scoring.sh` are not in the
     PREREG commit. They were written at 05:39-05:48Z, during the first 1-3 runs and before any scoring.
     PREREG fully specifies the metrics they compute.
3. **Sanitizing.** Committed copies replace local path prefixes with `$VARS`. This includes 3 model-written
   `upper.txt` files that contained mangled local path fragments; their verdict (fail) is unchanged and
   re-derived by `verify_artifacts.py`.
4. **Pilots** (`pilot-01`, `pilot-cua-01`, `P-p000*`, `P-p001*`) used separate prompts and are excluded. Their
   receipts are in the local mirror only.
5. **The executor model is also the Qwen baseline scorer** (qwen2.5:3b), as declared in PREREG.
6. **Erratum E1 (hermes commit in PREREG).** `PREREG.json` gives the hermes commit as
   `5d01f608975ab1d32d6a07c6c19213d2d4c5d98f`. That hash is wrong: only its first 10 hex digits match the
   real commit, `5d01f60897373e67f7a3af5a9150439760be93f9`, and the other 30 were made up when the PREREG
   was written. Results are unaffected. All 105 runs recorded the real head with a clean worktree,
   `verify_artifacts.py` checks it, and Hermes's own agent.log says "code changed to 5d01f6089737". PREREG
   is left unmodified; MANIFEST and provenance carry the correct hash.
7. **NanoJev identity quirk:** its `decision.revision` reports the Qwen3-0.6B backbone (`c1899de2…`). The bundle
   pin `4a19595e…` and `best.safetensors` sha256 `fff62d14…` are in `dataset/MANIFEST.json` identities.
8. **Erratum E2 (CUA attribution, SAMPLESFIX).** The earlier text said `cua_increment` and `cua_agree`
   failed "as preregistered: default approvals fail-close input actions in `-q` mode". It listed "CUA input
   tasks under default `-q` approvals" as BLOCKED, and the claim boundary said CUA rows reflect default
   approvals. All three statements were wrong:
   - The input runs never reached the approval gate. They are REAL tool-bridge failures (see "CUA runs").
   - The approval expectation is SOURCE-only and was not exercised.
   - 0 of 12 CUA runs reached the Driver.
   - The lane result's owner-decision request for an approval bypass is withdrawn.
   - No label, verdict, example, score or metric changes.
9. **Erratum E3 (decider latency).** The earlier text gave decider_2b's turn-lane warm p50/p95 only and
   called the 197.5 s first call "the true cold start". It did not disclose the 180.1 s warm call at index 3.
   The table now has a warm max column for every row, and the decider bullet gives the full series.
10. **Erratum E4 (timing label).** "Median wall time was 92 s per task" was printed next to latency
    results. It is a descriptive workload figure from unlocked collection, not a `quiet-timed`
    measurement. It is now labelled that way.
11. **Erratum E5 (exit reasons).** "Every exit 1 is `max_iterations_reached(4/4)`" holds for 7 of 8. t096
    ended with `pending_tool_result`. Both reasons come from the observer's `on_session_end` rows.
12. **Erratum E6 (latency column label).** The earlier table header said "warm per-call p50 / p95". Those
    values are the scorer wall-clock series (`warm_wall_ms_*`), not the backend-reported `latency_ms` series.
    The header now says so. No value changes.
13. **Ollama-adapter edge case (not triggered).** The docstring of `harness/vendor/ollama_logprob_backend.py`
    says it never returns a one-hot distribution. If only one of `true`/`false` appeared in the top-20
    logprobs, it would return exactly p=0 or p=1. No row hit this case:
    - turn-lane p(true) ranges from 3.4e-5 to 9.1e-4.
    - api-lane p(true) ranges from 0.83 to 0.998.
    - `n_probability_exactly_0_or_1` is 0 for every row.

    The vendored copy is left byte-identical to the one that produced the scores. A later adapter
    change should refuse or flag that case.
14. **Cosmetic:** `raw/controls/failopen.log` has 3 `rc=0` lines because the control was re-appended on
    each re-freeze run.

## Layout

- `PREREG.json`: hypotheses, rows, oracle, controls, metrics, gates and claim boundary.
- `workload/`: frozen tasks (`tasks.jsonl`, sha256 0e05d3c3…) and fixtures.
- `dataset/`: `MANIFEST.json` (content sha256 648e418e…), `events.jsonl` (1154 observer rows,
  z0int.hermes_observer_event.v1) and `runs.jsonl` (per task: status, session, verdict, isolation receipt).
- `raw/collect/`: the driver's index and the oracle verdicts.
- `raw/runs/<run>/`: oracle inputs (final reply, produced files, GUI state) plus exit code, argv and mask
  receipt. CUA runs also hold the private-home `agent.log` and `errors.log` (E2).
- `raw/examples/`: api and turn examples and join audits.
- `raw/scored/`, `raw/eval/`, `raw/analysis/`: scored rows, evaluations, analyses and `cua-bridge-tally.json`.
- `raw/scoring-logs/`, `raw/controls/`, `raw/quiet-lane-ledger.samples.jsonl`: scoring receipts.
- `raw/unit/`: the lab unit-test log.
- `harness/`:
  - `workload.py`: generator and oracle.
  - `oracle_selftest.py`.
  - `collect.sh`: driver.
  - `freeze.py`.
  - `build_turn_examples.py`: z0int adapter join glue.
  - `score_lane.py`.
  - `run_scoring.sh`.
  - `analyze.py`.
  - `make_summary.py`.
  - `build_packet.py`.
  - `copy_cua_logs.py`, `cua_bridge_tally.py` and `make_tables.py` (SAMPLESFIX).
  - Sanitized launcher copies.
  - `vendor/`: the exact hermes lab scripts used.
- `summary.json`, `provenance.json`.

## Claim boundary

- One executor model (qwen2.5:3b Q4_K_M, CPU, 4096-token served context) on one shared machine, with synthetic
  fixture tasks and N = 105 turns / 235 attempts.
- verification_needed labels are the proxy "the unverified outcome failed the oracle", not the normative
  decision-capability-v1 gold.
- CUA rows reflect a 3B model that could not use Hermes's default tool-search bridge. They say nothing
  about the approval gate (never reached) or about Driver capability (never reached).
- Nothing here authorises active control or promotes a backend.
