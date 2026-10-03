# N-04: native one-source composition and closure on R'n (BASE vs X vs X+V vs X+V+HCL), 2026-10-03

Owners: kvnloo/cua#93 (experiment), kvnloo/cua#10 (accounting), kvnloo/cua#20 (focus guard), kvnloo/cua#73 (canonical state).
Every arm ran one source and one binary, R'n: R' `45dff8f32` (R2-10R's tested source) plus the N-02 measurement-only marks. There is no provider (0 attempts, 0 reached). Nothing here is compared with R2-10R's binary R' (`922111c5`) or with N-03's binary N3.

## Result in one paragraph

All 528 measured tasks were valid and oracle-verified: 192 at k=1, 240 at k=5 (48 sessions) and 96 in the S0 supplement. Every cell is 100% valid (24/24 or 60/60), with 0 invalid rows and 0 E4 violations in any arm. **V is DELETED.** At k=1 it saves 2.94 ms [2.02 ms, 3.46 ms] of T on the checkbox task and 3.04 ms [2.01 ms, 3.91 ms] on text entry (paired X - X+V, 24 pairs each). The admission work it removes is 2.84 ms [2.64 ms, 3.00 ms] and 4.35 ms [4.15 ms, 4.68 ms] per task, and the V control passed 5/5. **HCL is OWNER_DECISION** (session-shape dependent). At k=1 it saves -0.04 ms [-0.96 ms, 1.02 ms] and 0.34 ms [-0.02 ms, 1.02 ms]. Across a 5-task session it saves 82.22 ms [71.50 ms, 86.86 ms] (checkbox) and 73.69 ms [69.62 ms, 85.14 ms] (text). The online lazy and library verdicts agreed on 746/746 calls, and offline 10/10 injected invalid outputs per tool were rejected by both paths, for 6/6 tools. **E3: the best composed arm is X+V+HCL on both tasks.** S = median T(BASE) / median T(X+V+HCL) is 1.196 [1.189, 1.198] for checkbox and 5.941 [5.938, 5.957] for text; both CIs lie above 1. **E2: native text entry's untested share falls from R2-10R's 6.9% to 1.65% on one source** (checkbox 1.19%). The conservative reading, which also splits the observation transport, gives 2.62% and 2.23%. Both readings are below the 5% target.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | The R2-04 native route on the canonical GTK3 fixture. `get_window_state` (tree + screenshot), the scripted jev-use lookup (`NativeObservation` + `eligible_controls`, unique exact label), then `click(element_token, delivery_mode: background)`, with `set_value` first for text. Every row's receipts and marks are checked (Method) | REAL (FIXTURE) |
| Actual route / producer | 1390 in-T calls on valid rows. Action routes seen: `click:accessibility:background` and `set_value:accessibility:background` only. V arms: `mcp.inner_validation_skipped` on 900/900 in-T calls. Non-V arms: 0 | REAL (FIXTURE) |
| Independent target-owned oracle | The fixture's own `CUA_GTK3_TASK_STATE` file (fresh per trial, atomic replace), read every 2 ms by a harness thread independent of the Driver | REAL (FIXTURE) |
| Negative / fallback controls | Default-off smoke R'n vs R'; the V control (re-list, unknown-tool refusal); HCL equivalence online and offline (injected invalid outputs); focus steal on X+V+HCL; a privacy-scanner control (Controls) | REAL (FIXTURE), UNIT |
| Tested source SHA | `11a03bf513a9b9ab107852ade67e13dbda5d30e7` = R' `45dff8f3227a21ff8bef1af4bf4c2bcbd9449b2a` + cherry-pick of `4c786178bb214e1a7b0f9e7af5e9dc9991524fc1` (N-02 settle clamp knob and MCP span marks; the patch N-03 used as `85a73c2c7`). No conflict. The range-diff (`raw/provenance/range-diff.txt`) shows only one added sentence in the commit message. libs/cua-driver tree `e047f85a42e1`, rust tree `3054612b8e99`. Upstream base `0f1955d2f`, whose libs/cua-driver tree `df2b49c32e73` equals live upstream main's at the start | SOURCE |
| Driver binary | R'n `cua-driver-n04-11a03bf51`, sha256 `78a1137d9fedef51e9dea651d8f4c09953ae2e4b38f102a4a890d548e9642dfc`, `cua-driver 0.32.0`, read inside every private session at chunk start and end (`raw/chunks/n04-c02-session-log.txt`). Built with build-driver.sh under hostless, the cargo lock and a SHARED quiet lock, family cua-release-r2-10. R' `cua-driver-r2-10r-a2-45dff8f32` (sha256 `922111c518d73b9675a9800d39a389c17070d40d16f25ada1426a90eccd06ec8`) was used for the default-off smoke only | SOURCE |
| Unit | Touched suites on `11a03bf51` under hostless: cua-driver `proxy::` 20/20, platform-linux `focus_guard` 14/14 (`raw/unit/unit-n04.txt`) | UNIT |
| Environment | One Linux host (kernel 7.2.2, 20 logical CPUs). Every code-executing command ran under bin/hostless, with bin/hostless-strict nested for session work. Private Xvfb (cua-x11-session.sh) with a private AT-SPI bus. Telemetry off (`CUA_DRIVER_RS_TELEMETRY_ENABLED=0`, `DO_NOT_TRACK=1`). jev-use venv: mcp 1.30.0, jsonschema 4.26.0. 1-minute loadavg on measured trials: 0.48-1.77 | SOURCE |
| PREREG commit | `aa1c2a346`, committed 2026-10-03T07:38:35Z. The first EXCLUSIVE receipt was 07:47:13Z (chunk n04-c01, no trial; Deviation 1), and the first measured trial ran at 08:41:44Z | SOURCE |
| Live heads, start | trycua/cua main `b4ffcd651a32` (07:37Z; 13 ahead of `0f1955d2f`, 0 libs/cua-driver files); trycua/cua PR 4316 `a0bca744067d` (open); kvnloo/cua#106 `c45845797b71` (open) | SOURCE |
| Live heads, end | trycua/cua main `410578a4a18e` (09:12Z; 18 ahead, 7 libs/cua-driver files, all in platform-macos and platform-windows: trycua/cua PR 4505, 4506, 4507, 4509; none touches platform-linux, cua-driver-core, the cua-driver proxy/server or jev-use, so no claim here depends on them); PR 4316 and kvnloo/cua#106 unchanged | SOURCE |
| Publication SHA | set by the Publish agent (`provenance.json` `publication_sha`); not assumed equal to the tested SHA | SOURCE |
| Provider | none (scripted chooser): 0 attempts, 0 reached; 0 non-loopback connects refused | NOT_RUN |

## Method

**Forced path.** Every task runs the R2-04 native route on the canonical GTK3 fixture: `get_window_state` (tree + screenshot), the scripted jev-use lookup (`NativeObservation` + `eligible_controls`, unique exact label), then `click(element_token, delivery_mode: background)` (checkbox) or `set_value` + `click` (text). No provider: the chooser is scripted.

**Arms** (`PREREG.json` `arms`):

- BASE: product defaults (R2-10's native BASE). Default cursor motion (`glide_duration_ms` 0.0 = the default reveal glide), the default 50 ms post-action sleep, the default focus-guard settle, and no `CUA_DRIVER_EXP_*` variable.
- X: R2-10R's native X knobs: `CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS=0` plus `set_agent_cursor_motion {glide_duration_ms: 1}`.
- X+V: X plus `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`.
- X+V+HCL: X+V plus N-03's caller-side lazy per-schema output validators. Each schema's validator is compiled at its first use, inside the call, with `jsonschema.validate`'s acceptance rule, and the library path re-checks each result after the trial, outside T.
- S0 (supplement only): the sleep knob alone, with the default cursor. Used only for S0 (KEEP-only).

**Harness.** `harness/n03/` holds the N-03 packet harness at `63d419034`, copied blob-identically. The git blob ids are in `PREREG.json`, and `verify_artifacts.py` re-checks them. `harness/n04_harness.py` imports that harness unchanged. It adds only two `ARMS` entries (BASE = N-03 arm B; X+V+HCL = N-03 arm X+HCL+V) and a round loop that applies the load rule and the soft cap. `harness/run_block_n04.sh` runs inside the private session. It waits a random 0-3 s and probes the private display with `xdpyinfo`; the session is not trusted unless the probe passes. It then checks the Driver's sha256 and reads the Driver version inside the session. `harness/run_chunks.sh` takes the locks and runs the chunks. `harness/make_plan_n04.py` writes `plan.json`.

**Design.** k=1 uses a 4x4 Williams square over BASE, X, X+V and X+V+HCL: 24 rounds per task (6 squares), both tasks per round, one fresh Driver and one fresh fixture per trial, so each contrast has 24 pairs per task. k=5 runs 12 sessions per arm per task for X+V and X+V+HCL, with 5 tasks per Driver session and fixture, AB/BA by session. The order comes from the round and the task's *fixed* index, so it alternates across rounds for each task (6/6). This avoids the order/element confound N-03 had in Part B, and the plan asserts the balance (`plan.json` `balance`). The S0 supplement is BASE vs S0 in 24 AB/BA rounds per task (12/12). Every measured block is one round.

**Locks and load.** Each measured chunk takes the cargo-build lock first, then `bin/quiet-timed <chunk>` (the EXCLUSIVE quiet-lane lock, with a receipt line in the shared ledger). Inside it, `timeout 600` caps the acquisition at 10 minutes, and no new round starts after a 420 s soft cap. A round starts only when the 1-minute loadavg is at most 4.0. Otherwise the harness re-reads it every second for up to 60 s and then ends the chunk, which resumes 90 s later outside the locks. Every check is logged in `raw/locks/load-gate.jsonl`: 60 of 60 rounds passed at the first check (loadavg 0.52-2.88), and no chunk ended on load. One chunk ended on the soft cap (n04-c02 after 27 rounds), and n04-c03 ran the remaining 33. The receipts are in `raw/locks/quiet-lane-receipts.jsonl`. The controls ran under the SHARED lock (`raw/locks/lock-ledger-shared.jsonl`).

**Route checks.** These run on every row. A failure makes the row invalid, and the row stays in the denominator.

- Every action receipt says `route: accessibility`, with the full R2-04 mark sequence in order.
- Every call has `dispatch_enter`/`dispatch_exit`, the N-02 MCP span marks (`request_read`, `parse_done`, `handler_start`, `handler_end`, `serialize_done`, `response_written`) in order, and the client stamps.
- V arms show `mcp.inner_validation_skipped` on every in-T tools/call. Non-V arms never do.
- HCL arms show a compile span inside the first call of each tool only. Non-HCL arms show none.
- The knob marks equal the arm's knobs.
- The cursor glide is 1.0 ms in the X arms and the 0.0 default in BASE and S0.

**Oracle.** The oracle is the fixture's `CUA_GTK3_TASK_STATE` file: a fresh path per trial, written by the app with atomic replace, and read every 2 ms by a harness thread that is independent of the Driver. A task is verified iff the first sample at or after the last action's return shows the expected state, and the final state has `seq == before.seq + 1`. T_oracle runs from the first observation's send to the read-end of that sample (R2-10's definition). T_land runs to the read-end of the first sample that shows the expected state, at any time.

**Statistics.** Paired within-round differences are reported as the median, with a seeded percentile bootstrap 95% CI over pairs (10000 resamples, seed 20261003). S = median T(BASE) / median T(arm) over paired rounds, with a paired bootstrap over rounds (R2-10's rule, same seed). The best composed arm is the composed arm (X, X+V, X+V+HCL) with the lowest median T_oracle among cells that are at least 95% valid. It is chosen on the same data, so S is also reported for every composed arm. E2 uses N-03's sub-spans. The primary reading splits the action transport. The conservative reading also splits the observation transport.

## Results (N of M, evidence class per row)

**k=1, median T_oracle per cell** (n = 24 per cell, 24/24 valid and verified in every cell):

| Task | BASE | X | X+V | X+V+HCL | Evidence class |
|---|---|---|---|---|---|
| checkbox | 334.95 ms | 282.95 ms | 280.59 ms | 279.98 ms | BENCHMARK+REAL (FIXTURE) |
| text | 1764.06 ms | 299.94 ms | 296.94 ms | 296.93 ms | BENCHMARK+REAL (FIXTURE) |

**Gates (pre-registered)**

| Gate | Rule | N of M | Result | Verdict | Evidence class |
|---|---|---|---|---|---|
| V, checkbox | paired X - X+V >= 0.5 ms with CI excluding 0 | 24 pairs | 2.94 ms [2.02 ms, 3.46 ms] | pass | BENCHMARK+REAL (FIXTURE) |
| V, text | same | 24 pairs | 3.04 ms [2.01 ms, 3.91 ms] | pass | BENCHMARK+REAL (FIXTURE) |
| **V** (both tasks) | both pass | 2/2 | V control 5/5 | **DELETED** | BENCHMARK+REAL (FIXTURE), REAL |
| HCL, checkbox | k=1 X+V - X+V+HCL >= 0.5 ms with CI excluding 0; otherwise OWNER_DECISION | 24 pairs | -0.04 ms [-0.96 ms, 1.02 ms]; k=5 per session 82.22 ms [71.50 ms, 86.86 ms] (12 pairs) | OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |
| HCL, text | same | 24 pairs | 0.34 ms [-0.02 ms, 1.02 ms]; k=5 per session 73.69 ms [69.62 ms, 85.14 ms] (12 pairs) | OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |
| **HCL** (overall) | DELETED iff both tasks DELETED | 0/2 | equivalence 746/746 online, offline pass | **OWNER_DECISION** | BENCHMARK+REAL (FIXTURE), UNIT |
| E3, checkbox | S_best CI above 1 | 24 pairs | best X+V+HCL: S 1.196 [1.189, 1.198] | met | BENCHMARK+REAL (FIXTURE) |
| E3, text | same | 24 pairs | best X+V+HCL: S 5.941 [5.938, 5.957] | met | BENCHMARK+REAL (FIXTURE) |
| E2, checkbox | untested share < 5% on the best arm | 24 rows | 1.19% (primary), 2.23% (conservative) | met | BENCHMARK+REAL (FIXTURE) |
| E2, text | same | 24 rows | 1.65% (primary), 2.62% (conservative) | met | BENCHMARK+REAL (FIXTURE) |
| Validity | >= 95% valid per cell | 16/16 cells | every cell 100% | pass | BENCHMARK+REAL (FIXTURE) |
| Secondary (no gate): X - X+V+HCL, V and HCL together at k=1 | reported | 24 pairs per task | checkbox 2.92 ms [2.00 ms, 3.09 ms]; text 3.39 ms [3.01 ms, 4.00 ms] | - | BENCHMARK+REAL (FIXTURE) |

**E3: speedup on one source** (S = median T(BASE) / median T(arm); paired rounds; 24 pairs):

| Task | Arm | S [CI] | T_land S [CI] | Evidence class |
|---|---|---|---|---|
| checkbox | X+V+HCL (best composed) | 1.196 [1.189, 1.198] | 1.095 [1.093, 1.161] | BENCHMARK+REAL (FIXTURE) |
| checkbox | X+V | 1.194 [1.189, 1.197] | 1.093 [1.061, 1.125] | BENCHMARK+REAL (FIXTURE) |
| checkbox | X | 1.184 [1.178, 1.184] | 1.001 [1.000, 1.044] | BENCHMARK+REAL (FIXTURE) |
| checkbox | S0 (KEEP-only; supplement, its own BASE) | 1.180 [1.177, 1.184] | 0.986 [0.972, 1.000] | BENCHMARK+REAL (FIXTURE) |
| text | X+V+HCL (best composed) | 5.941 [5.938, 5.957] | 29.938 [29.897, 31.154] | BENCHMARK+REAL (FIXTURE) |
| text | X+V | 5.941 [5.924, 5.950] | 30.532 [29.905, 30.585] | BENCHMARK+REAL (FIXTURE) |
| text | X | 5.881 [5.873, 5.899] | 28.746 [28.494, 28.795] | BENCHMARK+REAL (FIXTURE) |
| text | S0 (KEEP-only; supplement, its own BASE) | 1.030 [1.030, 1.031] | 1.001 [1.000, 1.002] | BENCHMARK+REAL (FIXTURE) |

X+V and X+V+HCL differ by 0.61 ms (checkbox) and 0.02 ms (text) in median T at k=1 (HCL compiles each schema once, inside T, which costs what the library's per-call compile costs). The choice of X+V+HCL as the best arm therefore moves S by at most 0.002. On checkbox, T_land S is above 1 only with V, because the admission work precedes the action. The sleep and glide deletions act after the effect lands (checkbox) or before it (text: the glide precedes `set_value`). S0 is the KEEP-only composition: only the post-action sleep, an N-01R KEEP. Its supplement block saves 51.59 ms [51.00, 52.00] (checkbox) and 51.94 ms [51.46, 53.64] (text) of T (`s0_supplement`).

**k=5 sessions** (12 sessions per arm per task, 60/60 tasks valid and verified per cell):

| Task / arm | Validation in task 1 / task 2 (median) | Sum of the 5 T's (median) | Evidence class |
|---|---|---|---|
| checkbox X+V | 19.71 / 19.90 ms | 1432.14 ms | BENCHMARK+REAL (FIXTURE) |
| checkbox X+V+HCL | 20.04 / 0.75 ms | 1347.16 ms | BENCHMARK+REAL (FIXTURE) |
| text X+V | 26.25 / 25.96 ms | 1498.59 ms | BENCHMARK+REAL (FIXTURE) |
| text X+V+HCL | 26.42 / 0.86 ms | 1427.01 ms | BENCHMARK+REAL (FIXTURE) |

Per-session HCL savings (X+V - X+V+HCL, sum of the 5 T's, one value per AB/BA session pair, in ms; `k5` `per_session_saving_ms`):

- checkbox: 88.5, 89.3, 70.0, 51.6, 83.4, 73.2, 81.0, 73.0, 86.3, 86.2, 68.5, 87.4
- text: 73.1, 74.4, 67.9, 87.0, 86.7, 73.2, 86.9, 53.1, 55.3, 83.6, 74.2, 71.4

The paired median per task position is:

- checkbox: task 1 -0.85 ms; tasks 2-5 6.02, 18.48, 23.35 and 29.02 ms.
- text: task 1 -0.63 ms; tasks 2-5 9.01, 28.83, 16.2 and 16.95 ms.

HCL also compiles the setup tools' validators at their first use, outside T: about 17.8 / 17.6 ms per session (median).

## E2: decomposition of the best arm (X+V+HCL, k=1)

**Primary reading.** R2-10's taxonomy, with the action transport split into N-03's sub-spans. Means are over 24 valid trials, and coverage of T_oracle is 1.00.

| Component | checkbox (ms) | text (ms) | Verdict (source) | Evidence class |
|---|---|---|---|---|
| focus-guard settle | 241.6 | 241.5 | IRREDUCIBLE (N-01R; CL settle clamp KILL per OWN-20G) | BENCHMARK+REAL (FIXTURE) |
| observation transport | 16.6 | 16.7 | IRREDUCIBLE (R2-10 label). Its split: client validation of `get_window_state` 13.5 / 13.6 ms is OWNER_DECISION via HCL; see the conservative reading | BENCHMARK+REAL (FIXTURE) |
| observation | 10.5 | 10.6 | IRREDUCIBLE (R2-10) | BENCHMARK+REAL (FIXTURE) |
| action transport: client output validation | 6.30 | 12.54 | OWNER_DECISION (HCL, this packet) | BENCHMARK+REAL (FIXTURE) |
| action transport: V-targeted admission residual | 0.13 | 0.25 | residual after DELETED V; counted UNTESTED | BENCHMARK+REAL (FIXTURE) |
| action transport: Driver serialize + write | 0.17 | 0.37 | IRREDUCIBLE (N-02) | BENCHMARK+REAL (FIXTURE) |
| action transport: Driver result conformance | 0.54 | 1.01 | UNTESTED | BENCHMARK+REAL (FIXTURE) |
| action transport: Driver parse, other admission, dispatch routing | 0.41 | 0.82 | UNTESTED | BENCHMARK+REAL (FIXTURE) |
| action transport: pipe + client read/parse/model | 0.38 | 0.58 | UNTESTED | BENCHMARK+REAL (FIXTURE) |
| action transport: client build + return | 0.07 | 0.13 | UNTESTED | BENCHMARK+REAL (FIXTURE) |
| reveal (fast glide residual) | 0.04 | 6.69 | OWNER_DECISION (R2-10) | BENCHMARK+REAL (FIXTURE) |
| dispatch | 0.97 | 2.50 | IRREDUCIBLE (R2-10) | BENCHMARK+REAL (FIXTURE) |
| resolution, result, runner | 1.81 | 2.12 | UNTESTED (R2-10) | BENCHMARK+REAL (FIXTURE) |
| post-action sleep | 0.07 | 0.07 | DELETED (N-01R) | BENCHMARK+REAL (FIXTURE) |
| verification read, effect lag | 0.61 | 0.67 | IRREDUCIBLE (R2-10) | BENCHMARK+REAL (FIXTURE) |
| **untested** | 3.33 ms of 280.30 ms = **1.19%** | 4.91 ms of 296.57 ms = **1.65%** | | BENCHMARK+REAL (FIXTURE) |
| T_irreducible / floor ratio | 270.6 ms / 1.036 | 272.4 ms / 1.089 | | BENCHMARK+REAL (FIXTURE) |

**Conservative reading.** This reading also splits the observation transport. Its client validation (13.5 ms checkbox, 13.6 ms text) becomes OWNER_DECISION, and its sub-millisecond Driver and pipe spans become UNTESTED. The untested share is 2.23% (checkbox) and 2.62% (text).

In both readings, the only components at or above the 5% / 50 ms line are the settle (IRREDUCIBLE) and, in the primary reading only, the observation transport as R2-10 labelled it. No UNTESTED component crosses the line (`e2` `above_threshold_untested` is empty).

The action transport that R2-10R left UNTESTED (18.5 ms on text) is now attributed on one source:

- client output validation: OWNER_DECISION;
- V admission: DELETED;
- Driver serialize/write: IRREDUCIBLE (N-02);
- what remains is about 2.5 ms (text) and 1.4 ms (checkbox) of sub-millisecond Driver-conformance, pipe and parse spans, which stay UNTESTED.

The figures in this section come from `n04-summary.json` → `e2`.

## Work deleted vs wall-clock saved

| Candidate | Work deleted (per task) | Wall-clock saved (paired median [CI]) | Evidence class |
|---|---|---|---|
| V (X -> X+V) | admission (`mcp.session_validated`→`admission_validated` + `inner_classified`→`inner_validated`): 2.84 ms [2.64 ms, 3.00 ms] checkbox, 4.35 ms [4.15 ms, 4.68 ms] text | 2.94 ms [2.02 ms, 3.46 ms] / 3.04 ms [2.01 ms, 3.91 ms] | BENCHMARK+REAL (FIXTURE) |
| HCL at k=1 | none: each tool is validated once, and the lazy compile costs what the library's per-call compile costs (compile inside T: 19.0 / 25.3 ms median) | -0.04 ms [-0.96 ms, 1.02 ms] / 0.34 ms [-0.02 ms, 1.02 ms] | BENCHMARK+REAL (FIXTURE) |
| HCL at k=5 | per-call compile for tasks 2-5: about 19 ms (checkbox) and 25 ms (text) of validation per task | 82.22 ms [71.50 ms, 86.86 ms] / 73.69 ms [69.62 ms, 85.14 ms] per 5-task session | BENCHMARK+REAL (FIXTURE) |
| BASE -> best (X+V+HCL) | component means: post-action sleep 51.1 / 51.1 ms; reveal glide 0 / 1410.6 ms; admission 3.1 / 4.7 ms (action + observation) | 54.27 ms [53.04, 55.21] / 1468.03 ms [1466.60, 1468.91] | BENCHMARK+REAL (FIXTURE) |
| S0 only (supplement) | post-action sleep about 51 ms | 51.59 ms [51.00, 52.00] / 51.94 ms [51.46, 53.64] | BENCHMARK+REAL (FIXTURE) |

The deleted provider decisions are 0 here: the chooser is scripted (Deviation 2).

## Controls

| Control | N of M | Result | Evidence class |
|---|---|---|---|
| Default-off smoke, R'n vs R' (arm D: no knobs, no trace file) | 10 + 10 | tools/list canonical sha256 `8119e796...` identical. Checkbox 5/5 and text 5/5 verified on both binaries. Identical receipt shapes (2) and routes (`click:accessibility`; `set_value:accessibility` + `click:accessibility`). 0 non-empty trace files, 0 rows with exp env | REAL (FIXTURE) |
| V control (X+V rows; X rows as the reference) | 5/5 pass (+5 X) | The mid-session re-list returns the identical inventory. The unknown tool is refused (-32602) before and after, as in X. Known tools are admitted in the modern and legacy eras. The task verifies | REAL (FIXTURE) |
| V invalidation scope | - | Unchanged from N-03's SOURCE reading: the inventory is loaded once in `SdkAdapter::load` and never mutated. `sdk_adapter.rs`, `proxy.rs` and `server.rs` are unchanged between N-03's source `85a73c2c7` and R'n (git diff: the 8 changed rust files are the upstream drift N-03 listed) | SOURCE |
| HCL equivalence, online (every lazily validated call re-checked by the library after the trial, outside T) | 746/746 | verdicts agree, messages identical, 0 rejects (92 HCL-arm trials) | BENCHMARK+REAL (FIXTURE) |
| HCL equivalence, offline (`hc_control.py`, `hc-control.json`): measured corpus from k=1 rounds 0 and 12 | 6/6 tools | For list_windows, set_agent_cursor_motion, get_agent_cursor_state, get_window_state, set_value and click: 10/10 injected invalid outputs rejected by both paths, every real output accepted by both, 82/82 identical verdicts | UNIT |
| HCL / V marks | 1390 in-T calls | V arms: 900/900 calls show `mcp.inner_validation_skipped`; non-V arms: 0. HCL compile spans only in task 0 calls; none in non-HCL arms (0 invalid rows) | REAL (FIXTURE) |
| Focus steal ~100 ms after the app's state change, X+V+HCL (reported, no gate) | 20 rows | 20/20 stolen, 20/20 verified, 0 missed. 19/20 restored by the strict rule. The one miss is `n04c-dec1/dec1-001` (checkbox, the block's first row). Its focus_pre snapshot shows the top-level window while the focus sampler's first sample and the final focus are its child. That is the same signature as N-03's `cd2-007` (N-02's startup focus_pre artifact). Exploratory: 20/20 are restored to the sampler's start, and the receipt says `focus_outcome=restored` in 20/20. The focus guard's deadline-exit gap is known (kvnloo/cua#20, OWN-20G), and R'n does not carry OWN-20G's guard final diff G | REAL (FIXTURE) |
| Privacy scanner (`privacy_scan_commits.py`, scratch repository) | 4/4 | It catches a hex-encoded home path and a base64-encoded host name (with or without the names file). It catches a plain user name only with `CUA_PRIVACY_NAMES_FILE`, and does not flag a public handle containing it (`raw/controls/privacy-scanner-control.txt`) | UNIT |
| Provider | - | 0 attempts, 0 reached; 0 non-loopback connects refused | NOT_RUN |

**E4, per arm:** 0 duplicate mutations, 0 success claims before the oracle, 0 stale dispatches, 0 blind replays and 0 authority from passive state, in BASE (96 rows), X (53), X+V (173), X+V+HCL (188) and S0 (48) (`e4`). Blind replay and passive authority are 0 by construction: the harness never re-dispatches, and element tokens come only from the same task's current observation.

## Deviations

1. **Chunk n04-c01 ran no trial (my invocation error).** The first measured launch passed the round list as one argument, because zsh does not word-split. The harness refused it with a KeyError before any trial, inside an EXCLUSIVE acquisition: 07:47:13-07:47:20Z, rc 1 (`raw/chunks/n04-c01-session-log.txt`, receipt kept). I stopped my own runner and relaunched from a bash launcher. No trial, round or file was lost, repeated or edited. The receipt is after the PREREG commit.
2. **Native T excludes provider decisions (scripted chooser).** This needs an owner ruling and is stated here, not hidden. The S values are for the native Driver path with a scripted chooser, not for live whole-task time with a model.
3. **The S0 supplement goes beyond the spec's four arms.** The spec asks for S0 (KEEP-only) to be reported, but none of its arms is S0. The supplement (BASE vs S0, 24 AB/BA rounds per task) was pre-registered in `PREREG.json` and plan blocks `s0-r00`..`s0-r23`. It has its own BASE rows and never enters the V or HCL gates.
4. **Best-arm selection on the same data.** X+V+HCL beats X+V by 0.61 ms (checkbox) and 0.02 ms (text) in median T. S is therefore also reported for every composed arm, and S(X+V) differs from S_best by at most 0.002.
5. **Waiting time.** The measured chunks queued about an hour in total for the cargo-build and quiet-lane locks behind other lanes. A long SHARED holder from another track starved the EXCLUSIVE waiters. The load rule never had to wait inside a window (60/60 at the first check).
6. **The build also took a SHARED quiet lock**, so it could not overlap another lane's EXCLUSIVE window. Unit tests ran the same way.
7. **Post-PREREG packet files.** `verify_artifacts.py`, `package_raw.py`, `make_headlines.py`, `privacy_scan_commits.py`, `provenance.json` and this README were written after registration. The registered files (`plan.json`, `harness/*`, `analyze_n04.py`, `hc_control.py`) are unchanged since `aa1c2a346`, and `verify_artifacts.py` checks the frozen ones.

Near misses: none known. Two `bash -n` syntax checks of the lane's own shell scripts ran in the plain host shell (parse only, no execution).

## Limits and claim boundary

- One host; private Xvfb + AT-SPI; the GTK3 canonical fixture (checkbox toggle, text entry); binary R'n only; no provider.
- No number here is ratioed against R' `922111c5`'s timings (R2-10R) or against N-03's N3 numbers. R' appears only in the default-off smoke identity check.
- V and HCL are env-gated, default-off measurement knobs. V is a Driver knob from B-02, and HCL lives in the caller. Shipping either is a reviewed change.
- No new service, and events are never the oracle.
- HCL's value depends on session shape (one task per Driver session saves nothing; multi-task sessions save about 6-29 ms per later task, median by position). That is a client and product policy choice, so the verdict is OWNER_DECISION.
- V's size depends on the 195 KB tools/list inventory.
- The settle (about 241 ms, 81-86% of T) is the floor here. It stays IRREDUCIBLE per OWN-20G's CL KILL.
- The observation transport keeps R2-10's IRREDUCIBLE label in the primary reading, even though most of it is client validation; the conservative reading counts that as OWNER_DECISION.
- Measured-trial loadavg was 0.48-1.77.

## Disposition

- **V (admission tools-list cache): DELETED (KEEP as measured) on R'n**, on both tasks.
- **HCL (lazy per-schema caller validators): OWNER_DECISION** (session-shape dependent). It saves 0 at k=1 and about 74-82 ms per 5-task session.
- **E3: met on one source.** S_best is 1.196 [1.189, 1.198] (checkbox) and 5.941 [5.938, 5.957] (text). S0 (KEEP-only) is 1.180 [1.177, 1.184] and 1.030 [1.030, 1.031].
- **E2: met for native on one source.** The untested share is 1.19% (checkbox) and 1.65% (text) in the primary reading, and 2.23% and 2.62% in the conservative reading.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed (`aa1c2a346`) before the first measured trial |
| `plan.json` | the measured plan (`harness/make_plan_n04.py measured`) with its asserted balance |
| `harness/n03/n03_harness.py`, `harness/n03/xprobe.py`, `harness/n03/fixture_axfg.py`, `harness/n03/make_plan.py`, `harness/n03/run_block.sh`, `harness/n03/run_all.sh` | the N-03 harness, blob-identical to `63d419034` |
| `harness/n04_harness.py`, `harness/run_block_n04.sh`, `harness/run_chunks.sh`, `harness/make_plan_n04.py` | the N-04 wrapper, in-session runner, chunk runner and plan generator |
| `analyze_n04.py` | recomputes `n04-summary.json` and `n04-trial-metrics.jsonl.gz` from `raw/` |
| `hc_control.py`, `hc-control.json` | offline HCL equivalence control |
| `make_headlines.py`, `headline-numbers.json` | every headline number with its summary path and README text |
| `package_raw.py` | builds `raw/` (redacted, deterministic gzip) |
| `privacy_scan_commits.py` | privacy scan of every commit (also run by the verifier) |
| `verify_artifacts.py`, `verify_helper.py` | the packet verifier and the template cited-file helper |
| `provenance.json` | every SHA, binary and environment detail |
| `raw/runs/n04-k1-r00/trials.jsonl.gz` (one directory per round or control block under `raw/runs/`) | raw trials, tools-list, output schemas, HC corpus, `done.json` |
| `raw/chunks/n04-c01-session-log.txt`, `raw/chunks/n04-c02-session-log.txt`, `raw/chunks/n04-c03-session-log.txt`, `raw/chunks/n04c-c01-session-log.txt`, `raw/chunks/n04c-c02-session-log.txt` | chunk session logs (Driver version, xdpyinfo probe, jitter) |
| `raw/locks/load-gate.jsonl`, `raw/locks/quiet-lane-receipts.jsonl`, `raw/locks/lock-ledger-shared.jsonl` | the load rule log and the lock receipts |
| `raw/pilots/n04p-pil/trials.jsonl.gz`, `raw/pilots-plan.json` | excluded SHARED pilots and their plan. Row `pil-014` failed by construction: a decoy row in a non-decoy block, so the harness had no decoy window. `pil2` re-ran the decoy pilot |
| `raw/provenance/range-diff.txt`, `raw/unit/unit-n04.txt`, `raw/controls/privacy-scanner-control.txt`, `raw/MANIFEST.json` | range-diff, unit log, scanner control, manifest |
