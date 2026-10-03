# N-03 (attempt 2): native one-source closure and the X11 ax_fg route

Owners: kvnloo/cua#93 (experiment), kvnloo/cua#10 (accounting), kvnloo/cua#20 (event fidelity / route), kvnloo/cua#73 (canonical state).
Source: R2-10's source plus the N-02 span marks (`85a73c2c7`). This branch makes no Driver change. One binary, N3, runs in every arm. No provider was used: 0 attempts, 0 reached.

## Results

- **HCL is OWNER_DECISION (session-shape dependent), on both tasks.** HCL compiles each output schema's validator lazily, at that schema's first use and inside T. With one task per Driver session (k=1), it saves nothing net, because each tool is validated exactly once and the first-use compile costs what the library's per-call compile costs. Checkbox: 0.00 ms [-2.99 ms, 1.90 ms]. Text: -1.83 ms [-12.49 ms, 3.97 ms]. With 5 tasks per session (k=5), every later task skips the compile: the per-task validation drops from 20.22 ms to 0.78 ms (checkbox, task 2) and from 26.99 ms to 0.91 ms (text). Summed over the 5 task T's of a session, the saving is 70.93 ms [66.33 ms, 87.68 ms] for checkbox and 101.42 ms [73.95 ms, 139.87 ms] for text. Lazy and library verdicts agreed on 1382 of 1382 calls online. Offline, all 10 injected invalid outputs per tool were rejected by both paths, for 6 of 6 tools. Every HCL-arm main and session trial was valid and verified (168 per task).
- **V is DELETED, on both tasks.** V is the admission tools-list cache, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`. At k=1 it saves 3.10 ms [0.40 ms, 4.97 ms] (checkbox) and 5.15 ms [3.51 ms, 8.04 ms] (text) of whole-task T. The work it removes is 3.63 ms [3.31 ms, 3.77 ms] and 5.77 ms [5.49 ms, 6.27 ms] of admission per task: per tools/call, two clones of the 195 KB inventory and a second `validate_tool_call`. The V control passed in 5 of 5 rows: re-listing mid-session returns the identical inventory, and an unknown tool is refused before and after the re-list. SOURCE: the inventory is a process-lifetime immutable `Value`, so the cache's invalidation scope equals the inventory's.
- **E2: the untested share is below 5% on both tasks.** On the best arm (X+HCL+V for both tasks) it is 1.47% for checkbox (4.20 ms of 286.51 ms) and 2.02% for text (6.14 ms of 304.98 ms) in the primary reading, which uses R2-10's taxonomy. The conservative reading, which also splits the observation's transport, gives 2.73% and 3.14%. R2-10's baselines were 4.1% and 7.5%. The action transport R2-10 left UNTESTED (9.9 ms checkbox, 20.6 ms text) splits on N3 into client output validation (7.1 / 13.9 ms, OWNER_DECISION via HCL), the V-targeted admission (DELETED; residual about 0.1-0.3 ms), Driver serialize and write (0.19 / 0.43 ms, IRREDUCIBLE per N-02), and sub-millisecond pipe, parse and conformance spans that stay UNTESTED.
- **R2-09 ax_fg route: S0 is DELETED. This is the terminal E1 verdict.** On the X11 `ax_fg` path (a foreground click on a scrolled-out, non-showing check box or button; receipt `route: accessibility`, `delivery: foreground`, `path=ax_fg`, with a `do_action_replied` mark), S0 was visible at return 20/20 per element type, with minimum margins of 819.75 ms (check box) and 820.20 ms (button) at the default configuration (family D, DELETED). The route is not unguarded at default: after the action body, the foreground wrapper's window-change observation (800 ms on X11) holds the return. With the documented host setting `CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS=0` (family U), the post-DoAction sleep is the only post-action wait. S0 is still visible 20/20 per element type, with minimum margins of 7.94 ms and 7.92 ms (DELETED). The app's handler changes the model before the DoAction reply goes back. The positive control shows that the oracle discriminates: with a 30 ms app-side delay, S0U was not visible at return in 10 of 10 rows. Deleting the sleep saves 50.01 ms [48.15 ms, 53.48 ms] (check box) and 51.20 ms [41.89 ms, 54.63 ms] (button) of T at default, and 51.48 ms [49.35 ms, 52.58 ms] and 51.99 ms [49.03 ms, 52.57 ms] in family U.
- **Validity and E4.** 192/192 k=1 tasks, 480/480 k=5 tasks (96 sessions), 160/160 ax_fg rows, 40/40 focus-steal rows and 10/10 vctl rows were valid and verified. No Part B row was refused for route (0 `global_input`). E4: 0 duplicate mutations, 0 success claims before the oracle, 0 stale dispatches, 0 blind replays, 0 authority from passive state.

## Provenance

| Item | Value |
| --- | --- |
| Branch | `exp/n-03-native-closure-axfg-a2-20261003` (worktree w4-a2-n03) |
| Base = tested source | `85a73c2c71e44ca512b8cc6023cf5c77c0f35bdc` = R2-10 source `8f3a646b4818b757648835cf89db8886626b1cf0` + cherry-pick of N-02 `194a6342e21b74f37f4e23af1d90bf32ad377397`. The range-diff (`raw/provenance/range-diff.txt`) shows only conflict context and the commit message changed. libs/cua-driver tree `186e373fb7d3`. No Driver change on this branch |
| PREREG | `PREREG.json`, commit `d929b49f25c83f237141641fab3eb03a3c231739`, 2026-10-03T02:53:34Z, before the first measured lock (a1 acquired 03:13:48Z) |
| Binary N3 (every arm) | `cua-driver-n03-a2-85a73c2c7`, sha256 `b1843871a7439486ebc719bf6e7817929b1c1d87e8b86183b99609f926bf7986`, `cua-driver 0.32.0` (read inside the private session). Built with build-driver.sh under hostless and the cargo lock, target family cua-release-r2-10 |
| Binary R (smoke comparator only) | `cua-driver-r2-10-8f3a646b4`, sha256 `12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9` |
| Attempt-1 binary | `262a8cfc...` from the same source. Not used. The rebuild is not bit-identical (+96 bytes; LLVM anonymous-symbol hashes differ) |
| Upstream main | Planning and start: `41c34cb0d704d816e612dd3f9d0c816cdfacf178` (0 ahead at 02:40Z). End: `a8d5788fddee3d851beaabd0d626bbc5e9fdf7cc` (2 ahead, 0 libs/cua-driver files, 05:45Z). Drift between the tested upstream base `989cc76ce` and main touches `tools/impl_.rs` (get_window_state's first-snapshot walk budget and description text) and `tool_schema.rs` (helper). It does not touch output schemas, `atspi/native.rs`, `input/foreground.rs`, `proxy.rs`, `server.rs` or `sdk_adapter.rs` |
| Live heads | trycua/cua PR 4316 `a0bca744067d` (open, unchanged start/end); kvnloo/cua#106 `c45845797b71` (open, unchanged) |
| Publication SHA | set by the Publish agent |
| Environment | One Linux host (10 CPUs). Every code-executing command ran under hostless; native blocks also ran under hostless-strict and cua-x11-session.sh (private Xvfb, private AT-SPI bus). Telemetry off (`CUA_DRIVER_RS_TELEMETRY_ENABLED=0`, `DO_NOT_TRACK=1`). jev-use venv: mcp 1.30.0, jsonschema 4.26.0 |
| Load | 1-minute loadavg per trial. k=1 tasks: median about 8 (5.3-31.1). Part B family D: 8.2-13.1. Family U: 1.5-2.2. Other tracks kept the host busy outside the quiet lock |

Full details: `provenance.json`.

## Method

**Forced path.** Part A forces the R2-04 native route on the canonical GTK3 fixture. The tasks are `get_window_state` (tree + screenshot), then a scripted jev-use lookup (`NativeObservation` + `eligible_controls`, unique exact label), then `click(element_token, delivery_mode: background)` and, for text, `set_value` first. Every arm runs R2-10's composed native arm X: `CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0` plus `set_agent_cursor_motion {glide_duration_ms: 1}`. The arms are:

- X: the library validates output with `jsonschema.validate` on every call.
- X+HCL: validators are compiled lazily per schema at first use, inside the call, with the library's exact acceptance rule.
- X+V: X with `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`.
- X+HCL+V: both.

Part B forces the X11 `ax_fg` route. It uses `click(element_token, delivery_mode: foreground)` on the check box "Hidden agree" and the button "Hidden save". Both sit in a 60 px `GtkScrolledWindow` below a 1200 px spacer, which makes them Visible but not Showing. The fixture variant is `harness/fixture_axfg.py`, gated by `CUA_N03_AXFG=1` and off by default. Its handlers stamp the app's CLOCK_MONOTONIC (`axfg_effect_mono_ns`) at the moment the model changes. Part B compares B (default 50 ms post-DoAction sleep) with S0 (`CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0`). Family D runs them at the default configuration; family U runs them with `CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS=0` in both arms.

**Actual route and producer.** In Part A, every action receipt must say `route: accessibility`, and the full R2-04 mark sequence must be present in order. Each call needs its dispatch marks, the N-02 MCP span marks in order, and the client stamps. V arms must show `mcp.inner_validation_skipped` on every in-T tools/call; non-V arms must never show it. HCL arms must show a compile span inside the first call of each tool, and no compile after that; non-HCL arms show none. The knob marks must equal `{post_action_sleep_ms=0}`, and the cursor glide must be 1 ms. In Part B, every row must show `route: accessibility`, `delivery.mode: foreground`, `path=ax_fg` in the receipt text, and an `atspi_action/do_action_replied` mark, and the knob marks must match the arm. Source path: `decide_foreground_element_placement` in platform-linux `tools/impl_.rs` returns `NoPoint` for a non-showing element. `foreground_element_click` then fires `perform_action_observed` inside `with_x11_foreground_opts`, which reaches `perform_action_ref` in `atspi/native.rs`, where the 50 ms sleep is. The wrapper then runs `wait_for_window_change` (`input/foreground.rs`). Its bound is `CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS`, 800 ms by default on X11; at 0 it reads the window set once and does not poll.

**Independent target-owned oracle.** The oracle is the fixture's `CUA_GTK3_TASK_STATE` file: a fresh path per trial, written by the app (atomic replace), and read every 2 ms by a harness thread that is independent of the Driver. A task is verified only when the first sample at or after the last action's return shows the expected state and the final state has `seq == before.seq + 1`. T_oracle is measured from the first observation's send to the read-end of that sample (the R2-10 definition). In Part B, a row is visible at return when the app's own handler stamp is not later than the click's caller-side return (same host CLOCK_MONOTONIC). The margin is the return time minus the effect time. The strict sampler reading (R2-09's metric) is also reported.

**Design.** Part A uses a 4x4 Williams square (first-order carry-over balanced). At k=1 there are 24 rounds per task, with one fresh Driver and one fresh fixture per trial (blocks a1 and a2, 96 trials each). This gives 24 pairs per contrast per task. At k=5 there are 12 sessions per arm per task, with 5 tasks per Driver session and fixture (blocks k1 and k2-r1, 48 sessions each). Part B runs 20 AB/BA rounds per element type in each family, with one fresh Driver and fixture per trial: D (b1) and U (bu1), 80 trials each. Measured blocks ran under the cargo-build lock followed by `bin/quiet-timed`, which takes the EXCLUSIVE quiet lock. Each held the lock for 2-4 minutes; the receipts are in `raw/locks/quiet-lane-receipts.jsonl`. Controls ran under the SHARED lock with their own receipt lines. Loadavg is recorded per trial, and every trial is kept.

**Statistics.** Paired within-round differences, reported as the median with a seeded percentile bootstrap 95% CI over pairs (10000 resamples, seed 20261003). Components use R2-10's native boundaries. Each call's transport is split with the N-02 span marks into the N-02 sub-spans. The V-targeted admission work (`mcp.session_validated` to `mcp.admission_validated`, plus `mcp.inner_classified` to `mcp.inner_validated`) is carved out of them.

## Part A results (k=1, one task per Driver session)

Median T_oracle (ms); n = 24 per cell; all valid and verified.

| Task | X | X+HCL | X+V | X+HCL+V | Class |
| --- | --- | --- | --- | --- | --- |
| checkbox | 285.31 ms | 285.00 ms | 282.94 ms | 281.40 ms | BENCHMARK+REAL (FIXTURE) |
| text | 305.06 ms | 305.46 ms | 298.91 ms | 298.90 ms | BENCHMARK+REAL (FIXTURE) |

| Contrast (paired, a - b) | checkbox T saved | text T saved | Work removed (paired) |
| --- | --- | --- | --- |
| X vs X+HCL (HCL, gating) | 0.00 ms [-2.99 ms, 1.90 ms] | -1.83 ms [-12.49 ms, 3.97 ms] | Validation span unchanged (each tool is compiled once, inside T). The compile inside T in X+HCL is a median of 19.6 ms (checkbox) and 27.2 ms (text) |
| X vs X+V (V, gating) | 3.10 ms [0.40 ms, 4.97 ms] | 5.15 ms [3.51 ms, 8.04 ms] | Admission 3.63 ms [3.31 ms, 3.77 ms] / 5.77 ms [5.49 ms, 6.27 ms] |
| X+HCL vs X+HCL+V (V, secondary) | 3.78 [2.06, 4.88] | 7.23 [3.72, 17.00] | Admission 3.66 / 5.76 |
| X+V vs X+HCL+V (HCL, secondary) | 0.78 [-0.47, 2.49] | -0.52 [-3.59, 1.95] | none |

## Part A results (k=5, five tasks per Driver session)

12 sessions per arm per task; 60/60 tasks valid and verified per cell.

| Task / arm | Validation in task 1 (median) | Validation in task 2 (median) | Session sum of the 5 T's (median) | Session wall incl. setup (median) |
| --- | --- | --- | --- | --- |
| checkbox X | 20.70 ms | 20.22 ms | 1469.9 | 2446.9 |
| checkbox X+HCL | 20.21 ms | 0.78 ms | 1397.5 | 2370.2 |
| checkbox X+V | 19.90 ms | 20.58 ms | 1458.6 | 2420.6 |
| checkbox X+HCL+V | 20.46 ms | 0.78 ms | 1346.6 | 2325.5 |
| text X | 27.32 ms | 26.99 ms | 1547.7 | 2519.2 |
| text X+HCL | 26.22 ms | 0.91 ms | 1468.1 | 2438.7 |
| text X+V | 27.36 ms | 26.81 ms | 1543.7 | 2509.2 |
| text X+HCL+V | 26.54 ms | 0.90 ms | 1426.6 | 2396.8 |

Net per-session saving (paired; the first-use compile is inside task 1's T; class BENCHMARK+REAL (FIXTURE)):

- X vs X+HCL, sum of the 5 T's: checkbox 70.93 ms [66.33 ms, 87.68 ms]; text 101.42 ms [73.95 ms, 139.87 ms]. Session wall including setup: 70.5 [51.0, 102.6] and 106.7 [74.8, 141.6]. Task 1 alone: -0.58 [-4.98, 1.27] and 0.00 [-1.93, 1.28]. The saving starts at task 2: 22.02 [21.02, 24.12] and 21.95 [20.07, 22.68] per task.
- HCL also compiles the setup tools' validators (list_windows, set_agent_cursor_motion, get_agent_cursor_state) at their first use, outside T. That costs about 18 ms per session (median), which the library also pays per call.
- X vs X+V: checkbox 16.31 ms [6.12 ms, 40.62 ms]; text 24.44 ms [-13.38 ms, 69.44 ms] (the CI includes 0 at n=12 sessions).

## Gates (pre-registered)

| Gate | Rule | Result | Verdict | Class |
| --- | --- | --- | --- | --- |
| HCL checkbox | DELETED iff k=1 net saving >= 5 ms with CI > 0, equivalence 100% and validity 100%. Otherwise OWNER_DECISION iff the k=5 saving is > 0 with CI > 0 | k=1 0.00 ms [-2.99 ms, 1.90 ms]; k=5 70.93 ms [66.33 ms, 87.68 ms]; equivalence 1382/1382 online and 60/60 offline; validity 168/168 | **OWNER_DECISION** | BENCHMARK+REAL (FIXTURE), UNIT |
| HCL text | same | k=1 -1.83 ms [-12.49 ms, 3.97 ms]; k=5 101.42 ms [73.95 ms, 139.87 ms]; validity 168/168 | **OWNER_DECISION** | same |
| V checkbox | DELETED iff saving >= 1 ms with CI > 0 and the control passes | 3.10 ms [0.40 ms, 4.97 ms]; control 5/5 | **DELETED** | BENCHMARK+REAL (FIXTURE), SOURCE |
| V text | same | 5.15 ms [3.51 ms, 8.04 ms]; control 5/5 | **DELETED** | same |
| ax_fg S0, family D (default; terminal for E1) | R2-09 rule: visible 20/20 per element type and minimum margin >= 1 ms | check box 20/20, 819.75 ms; button 20/20, 820.20 ms | **DELETED** | BENCHMARK+REAL (FIXTURE) |
| ax_fg S0, family U (`CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS=0`) | same, and the positive control must pass | check box 20/20, 7.94 ms; button 20/20, 7.92 ms; positive control 10/10 | **DELETED** (scoped) | BENCHMARK+REAL (FIXTURE) |
| E2 untested share (best arm, primary reading) | < 5% for both tasks | checkbox 1.47%, text 2.02% | **target met** | BENCHMARK+REAL (FIXTURE) |

## E2: decomposition on the best arm (X+HCL+V, k=1)

Primary reading (R2-10 taxonomy; the action transport is split). Mean ms over 24 valid trials; coverage of T_oracle is 1.00.

| Component | checkbox | text | Verdict (source) |
| --- | --- | --- | --- |
| focus-guard settle | 241.4 | 241.7 | IRREDUCIBLE (N-01R, carried by R2-10) |
| observation transport | 19.0 | 18.1 | IRREDUCIBLE in R2-10's reading. This packet's split shows that 15.1 / 14.5 ms of it is client validation of `get_window_state` (OWNER_DECISION via HCL; see the conservative reading) |
| observation | 12.6 | 14.7 | IRREDUCIBLE (R2-10) |
| action transport: client validation | 7.1 | 13.9 | **OWNER_DECISION** (HCL, this packet) |
| action transport: V-targeted admission | 0.15 | 0.28 | residual after **DELETED** V. Counted UNTESTED (R2-10 residual rule) |
| action transport: Driver serialize + write | 0.19 | 0.43 | IRREDUCIBLE (N-02) |
| action transport: Driver result conformance (`drv_inner_post`) | 0.63 | 1.19 | UNTESTED |
| action transport: pipe + client read/parse (`client_write_pipe`, `client_pipe_read_parse`, `client_result_model`) | 0.47 | 0.97 | UNTESTED (the kernel pipe is not isolated from the Python reader/writer) |
| action transport: Driver parse + other admission + dispatch routing | 0.51 | 0.95 | UNTESTED |
| action transport: client build + return | 0.12 | 0.26 | UNTESTED |
| reveal (fast glide residual) | 0.05 | 6.6 | OWNER_DECISION (R2-10) |
| dispatch | 1.3 | 2.8 | IRREDUCIBLE (R2-10) |
| resolution, result, runner | 2.3 | 2.5 | UNTESTED (R2-10) |
| post-action sleep | 0.08 | 0.07 | DELETED (N-01R) |
| verification read, effect lag | 0.7 | 0.5 | IRREDUCIBLE (R2-10) |
| **untested** | 4.20 ms of 286.51 ms = **1.47%** | 6.14 ms of 304.98 ms = **2.02%** | |
| T_irreducible / floor ratio | 275.1 / 1.04 | 278.3 / 1.10 | |

The conservative reading (N-02 taxonomy, with the observation transport split as well) gives an untested share of 2.73% (checkbox) and 3.14% (text). The only components above the 5% / 50 ms threshold are the focus-guard settle (IRREDUCIBLE) and the observation's client validation (OWNER_DECISION). On arm X, which is R2-10's composed arm on N3, this packet's verdicts give 1.92% and 3.43%. All of these numbers come from `n03-summary.json` → `e2`.

**Work deleted vs wall clock saved.** V deletes 3.63 / 5.77 ms of admission work per task, and T drops by 3.10 / 5.15 ms (k=1). HCL deletes no work at k=1; it moves the compile into a cache. At k=5 it deletes the per-call compile for tasks 2-5, about 20 ms (checkbox) and 26 ms (text) of validation work per task, and T drops by about 22 ms per later task. That is 70.93 / 101.42 ms of wall clock per 5-task session. On ax_fg, S0 deletes the 51 ms post-DoAction wait per click and saves 50.01 / 51.20 ms (D) and 51.48 / 51.99 ms (U) of T. The work deleted and the wall clock saved match there, because the sleep is serial.

## Controls

| Control | Result | Class |
| --- | --- | --- |
| HC equivalence, online: every lazily validated call re-checked with the library path after the trial, outside T | 1382/1382 verdicts agree; 1382/1382 identical messages; 0 rejects (164 HCL-arm trials) | BENCHMARK+REAL (FIXTURE) |
| HC equivalence, offline (`hc_control.py`, `hc-control.json`): real outputs from the measured a1/a2 corpus, plus 10 injected invalid outputs per tool | 6 tools (list_windows, set_agent_cursor_motion, get_agent_cursor_state, get_window_state, set_value, click): 10/10 invalid rejected by both paths per tool, every real output accepted by both, identical messages | UNIT |
| V cache: tools/list re-listed mid-session (5 X+V rows, 5 X rows) | 5/5 pass: inventory identical after the re-list; the unknown tool is refused (-32602) before and after, as in X; a known tool is admitted in the modern and legacy eras; the task verified | REAL (FIXTURE) |
| V invalidation scope | `SdkAdapter.tools_list` is loaded once in `SdkAdapter::load`, is never mutated (no interior mutability; `&self` accessors only), and serves both tools/list and `tools_list_ref`. The scope is the process lifetime, which is also the inventory's lifetime | SOURCE |
| Native focus steal about 100 ms after the state change, 5 per task per arm | 40/40 stolen and verified. Pre-registered "restored" rule: 39/40. The one miss (`n03a2-cd2/cd2-007`, checkbox X+HCL) is the known focus_pre snapshot artifact N-02 documented: the final focus equals the placement state and the focus sampler's first sample (exploratory: 40/40), and the receipt says `focus_outcome=restored` (40/40) | REAL (FIXTURE) |
| Default-off smoke, N3 vs R (no knobs, no trace file) | tools/list canonical sha256 `3a571977...` identical; checkbox 5/5 and text 5/5 verified on both; identical receipt shapes; 0 non-empty trace files | REAL (FIXTURE) |
| Part B route check | 190/190 rows: route accessibility, foreground, `path=ax_fg`, `do_action_replied`; 0 refused; 0 global_input | REAL (FIXTURE) |
| Part B fixture smoke (`CUA_N03_AXFG` unset) | 2/2: the same element labels and roles and the same state keys as the repository fixture; no hidden controls | REAL (FIXTURE) |
| Part B positive control (30 ms app-side delay) | S0U not visible at return 10/10 (margins -114.0 to -19.5 ms). BU visible 10/10. S0 at default visible 10/10 (the 800 ms observation covers the delay) | REAL (FIXTURE) |
| Provider | 0 attempts, 0 reached; 0 non-loopback connects refused | — |

## Part B detail

| Family / element | B (or BU) visible | S0 (or S0U) visible | S0 min margin | S0 strict sampler | Median DoAction reply to return, base / S0 | Median T, base / S0 | T saved (paired) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D check box | 20/20 | 20/20 | 819.75 ms | 20/20 | 872.5 / 821.2 | 922.9 / 871.9 | 50.01 ms [48.15 ms, 53.48 ms] |
| D button | 20/20 | 20/20 | 820.20 ms | 20/20 | 872.8 / 823.3 | 923.3 / 875.5 | 51.20 ms [41.89 ms, 54.63 ms] |
| U check box | 20/20 | 20/20 | 7.94 ms | 20/20 | 59.4 / 8.2 | 104.4 / 53.0 | 51.48 ms [49.35 ms, 52.58 ms] |
| U button | 20/20 | 20/20 | 7.92 ms | 20/20 | 59.4 / 8.0 | 103.7 / 52.5 | 51.99 ms [49.03 ms, 52.57 ms] |

There were no publication-lag rows: every S0 row was visible by both metrics. The post-DoAction wait was 51.1-51.4 ms in B and BU, and 0.07 ms in S0 and S0U.

## Deviations

1. **Background job over 2 h.** The first measured job started at 02:53Z. It spent most of its time queued behind other lanes' cargo and quiet locks, and passed 2 h at 05:04Z while block k2 was still waiting for the cargo lock. I stopped my own processes (run_all and its flock) before k2 opened a session. k2 had started no trial and had no lock receipt; it is recorded in `raw/locks/aborted-blocks.json`. k2 and bu1 were re-run under `timeout 7000` as `n03a2-k2-r1` and `n03a2-bu1`. No trial was lost or repeated. Each block held the EXCLUSIVE lock for less than 25 minutes.
2. **HC offline mutation strategies.** For list_windows, the pre-registered strategies yielded fewer than 10 mutants that the library rejects, as the pilot dry run showed. Two strategies were appended after the pre-registered ones: `array_item_drop_required` and `array_item_wrong_type` on the first window. Because they come last, they are reached only when the earlier ones run out. The selection rule (keep a mutant only if the library rejects it) is unchanged. Only list_windows uses them (`hc-control.json`).
3. **Exploratory decoy metrics.** `x_restored_to_sampler_start` and `receipt_focus_restored` were added to the analysis after the first control run (N-02 lineage). They never decide a gate. The pre-registered rule result (39/40) is the one reported.
4. **SHARED controls ran before the last measured blocks.** They ran in parallel with the queued measured job. Controls carry no timing claim.
5. **Default-off smoke.** As in R2-10, harness-side `CUA_DRIVER_PHASE_TRACE_FILE` stays unset in arm D (`trace_env_rows` 0), and no exp env is set.
6. **Block a1 started at loadavg 32** (other tracks; per-trial loadavg in raw). All 96 trials verified. Pairing within rounds controls for the drift.

## Attempt 1 (aborted, disclosed)

Attempt 1 (`exp/n-03-native-closure-axfg-20261003`) stopped before any PREREG or measured trial. Its SHARED pilots `n03p-ap1`, `n03p-ap2`, `n03p-bp1`..`bp5` and `n03p-bp1-r1` (`n03p-bp1` could not open the private DISPLAY) are excluded from every number here. Their lock receipts are listed in `raw/locks/quiet-lane-receipts.jsonl`. I reviewed its uncommitted harness and reused it with two added session timestamps; the plan is byte-identical. This attempt's own pilots (`n03a2p-*`, SHARED, excluded) are in `raw/pilots/`.

## Limits

- **Session shape decides HCL.** One task per Driver session (R2-10's shape) saves nothing. A caller that keeps a session, or a long-lived MCP client, saves about 20-26 ms per task after the first. That is a client and product policy choice, so the verdict is OWNER_DECISION and no default change is claimed. Removing client output validation altogether, rather than caching it, was not tested.
- **V's magnitude depends on inventory size** (195 KB tools/list here). V is a measurement knob from B-02, not a product change. Shipping it would be a reviewed change in the direct-stdio adapter.
- **The ax_fg verdict holds for an MCP stdio caller.** In family U, the effect reached the app's model before the DoAction reply (by the app's own handler stamp), and the return came at least 7.9 ms later. A caller with a much faster return path was not measured. The default configuration is guarded by the 800 ms window-change observation, which is itself a large foreground cost (`dar_to_return` about 821 ms) and is out of this lane's scope.
- **Other X11 foreground routes.** Hyprland foreground semantic clicks are BLOCKED (hardware). The on-screen GTK3 and Chromium X11 foreground clicks use XTest (R2-09), with no DoAction.
- **Carried-over verdicts.** `observation_transport` keeps R2-10's IRREDUCIBLE label in the primary reading. This packet's split shows that most of it is client validation, which is OWNER_DECISION under HCL; the conservative reading counts it that way.
- **Host load.** Other tracks kept the host loaded throughout (loadavg 1.5-32). The quiet lock serialized only lock-holding work. Every number is a paired within-round contrast.

## Claim boundary

GTK3 AT-SPI on X11 (private Xvfb), binary N3 only (`b1843871...`), scripted, no provider. Native live-provider arms stay BLOCKED (budget). Nothing is ratioed against R2-10's binary; R is used only for the default-off smoke identity. Every knob and fixture variant is env-gated and off by default. The source has no Driver change, there is no new service, and events are never the oracle.

## Evidence classes

- BENCHMARK+REAL (FIXTURE): all Part A and Part B measured blocks.
- REAL (FIXTURE): the controls.
- UNIT: the offline HC control.
- SOURCE: the V invalidation scope, the ax_fg route path, the window-change bound, and the drift reading.
- BLOCKED: native live-provider arms (budget); Hyprland foreground (hardware).
- NOT_RUN: Rust knob unit tests on N3. There is no Driver change; the knobs are byte-identical to R2-10's source, where B-02 and N-01R covered them.

## Disposition

- **E1, R2-09 X11 ax_fg route:** terminal, **S0 DELETED on ax_fg** at the default configuration. It is also DELETED in the scoped `CUA_DRIVER_WINDOW_CHANGE_TIMEOUT_MS=0` shape. The post-DoAction sleep's DELETED scope extends from GTK3 and Chromium background (N-01R, R2-09) to X11 `ax_fg`.
- **HCL: OWNER_DECISION** (session-shape dependent): 0 at k=1, and 70.93 ms / 101.42 ms per 5-task session.
- **V: DELETED (KEEP as measured)** on the native path: 3.10 / 5.15 ms of T.
- **E2:** the native untested share on the best arm is 1.47% (checkbox) and 2.02% (text), both below 5%. The R2-10 action transport is now attributed.

## Files

- `PREREG.json` (committed before the first measured trial), `plan.json` (make_plan.py measured).
- `harness/`: `harness/n03_harness.py`, `harness/fixture_axfg.py`, `harness/make_plan.py`, `harness/run_all.sh`, `harness/run_block.sh`, `harness/xprobe.py` (verbatim, blob f17d83691faa).
- `analyze_n03.py` regenerates `n03-summary.json` and `n03-trial-metrics.jsonl.gz` from `raw/`.
- `hc_control.py` writes `hc-control.json`. `make_headlines.py` writes `headline-numbers.json`. `package_raw.py` builds `raw/`.
- `verify_artifacts.py` checks everything. Run `python3 verify_artifacts.py` from a clean clone.
- `provenance.json`.
- `raw/`: `raw/runs/<label>/trials.jsonl.gz` per block, plus tools-list, output schemas, HC corpus and a session log (for example `raw/runs/n03a2-a1/session-log.txt`, the redacted session.log; the repository ignores `*.log`). Also `raw/pilots/` (excluded), `raw/locks/quiet-lane-receipts.jsonl`, `raw/locks/aborted-blocks.json`, `raw/provenance/range-diff.txt` and `raw/MANIFEST.json`.
