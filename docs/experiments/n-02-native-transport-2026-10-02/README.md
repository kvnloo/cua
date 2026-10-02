# N-02: native MCP transport attribution, plus a causal A/B of caller-compiled validators and the settle-overshoot clamp, 2026-10-02

Owners: kvnloo/cua#93 (R2-04 / N-01R follow-up), kvnloo/cua#20 (focus/event input), kvnloo/cua#10 (accounting), kvnloo/cua#73 (canonical state). Advances E2 for the two native reference tasks.

## Result in one paragraph

On the canonical GTK3 task fixture, all 192 main trials were valid and verified against the app's own state file: 4 arms x 2 tasks x 24 Williams-balanced rounds, with one fresh Driver and one fresh fixture per trial. Every route check passed, and MCP span coverage was 1.0. Results:

- **Transport attribution (Phase 1).** The four-part split shows that the native "MCP transport" N-01R left untested is mostly the **Python client's output-schema validation** (`ClientSession._validate_tool_result`, which runs `jsonschema.validate` and re-checks the schema against its metaschema on every call). It accounts for 14.6 ms of the 20.1 ms observation transport and 6.8 ms of the 10.0 ms action transport on the checkbox (S0). On text (X) it accounts for 15.3 of 21.5 ms and 15.0 of 25.2 ms.
- **HC (caller-compiled validators): DELETED (KEEP, caller-side) on both tasks.** It saves **21.3 ms [19.9, 24.1]** of checkbox T and **25.9 ms [20.0, 53.6]** of text T. It accepts and rejects exactly what the library path does on 80/80 real and mutated results, and outcomes are identical (24/24 in every arm).
- **CL (settle-poll clamp): KILL under the pre-registered rule.** It saves 19.1 ms [14.0, 23.9] (checkbox) and 25.9 ms [18.0, 35.9] (text), and the settle drops from ~241 to ~220 ms. However, the rule "any steal miss in any arm: KILL" fired: 4 of 240 steal trials failed. None of those failures is attributable to the clamp:
  - two were decoy timing slips, where the steal landed 785-920 ms after the guard started, after the tool had returned; one of them was in a default arm;
  - one was an oracle artefact in a CL arm: the guard detected the steal and restored the state it had captured;
  - one was a genuine miss by the **default** guard (X+HC): an X call stalled for 2.3 s inside the settle loop, and the loop then ended on its deadline without a final diff.

  The default stays unchanged, and the clamp needs a cleaner control before any re-test (Next).

In the best eligible composed arms (S0+HC, X+HC), the untested share of T is **1.7%** (checkbox) and **3.2%** (text) under the standard reading, and **3.4%** and **5.0%** under the conservative reading. Without HC, the shares are 1.6% / 3.2% standard and 3.4% / 4.7% conservative.

Evidence classes are given per row. Runtime rows are REAL (real Driver, real GTK3 app, private AT-SPI bus, isolated X11 session) with BENCHMARK-style paired timing and no provider (scripted chooser; TypeSafe 0 attempts / 0 reached).

## Provenance (each SHA kept separate)

| Item | Value |
|---|---|
| Branch base | `3bb4a7fc70d1d58984b19a7a357892a7c9af31fa`, the accepted N-01R head. Its `libs/cua-driver` tree is identical to `b9b357bc72fe0627b841f66a2d0812fafca8711f` (`git diff --quiet` rc 0), i.e. `28b915ae9` (R2-04 marks on upstream main `229b65b28`, whose `libs/cua-driver` equals `352507b6c`) plus the N-01R knob commit |
| Measurement commit (tested source = base tree + this) | `194a6342e21b74f37f4e23af1d90bf32ad377397`: one commit, measurement-only, env-gated, default off (see below) |
| Pre-registration | `e8234b73dcf617692b207fe71c2dda7e5dd11353`, committed 17:38:00Z. The first measured block (`n02-d01`) started at 17:38:25Z. `verify_artifacts.py` checks the order and that `PREREG.json` and `plan.json` are unchanged since |
| Driver (N2) | `cua-driver-n02-194a6342e`, sha256 `893646ab95ebaa946283c5e05dd0e8555b64702bf41b0d63d90a17ff6098865e`, `cua-driver 0.32.0`, read inside `cua-x11-session.sh` (`raw/driver-build/driver-version.txt`). Built with `build-driver.sh` into `cua-release-n02` under the cargo-build lock; logged `head=194a6342e`, 0 Fresh workspace units, 216 s (`raw/driver-build/build-driver.txt`). Every block's meta row carries this sha256 |
| Provenance link | `cua-driver-n01r-b9b357bc7`, sha256 `c2a9978eb2b579d500a8fe4829e17fa9cfd2a19ec5d53e333e2b5582bdd3ff95` (`raw/driver-build/sha256.txt`). It was hashed only. Nothing here compares against it, except N-01R's committed per-trial metrics in the qualitative load section |
| Harness origin | N-01R harness at `3bb4a7fc7` (blobs in `provenance.json`). `xprobe.py` is copied verbatim; the rest is derived. The HC method is the B-01 H_C method (`exp/b-01r-browser-critpath-textfix-20261002` @ `0cd63f786`), re-implemented without monkeypatching |
| Live heads (gh read-only, 18:36:05Z) | Upstream main is `310cdfd58963`, 36 commits ahead of `352507b6c`. Of the API's file list (capped at 300), 25 files are under `libs/cua-driver`. None is `proxy.rs`, `focus_guard.rs`, `server.rs`, `mcp_wire.rs` or `atspi/*`, but `cua-driver-core/src/tool_schema.rs` is among them (see Limits). trycua/cua PR 4316 is `a0bca7440`, open, and is not this source |
| Publication SHA | set by the Publish agent (`provenance.json: publication_sha`) |

## The measurement commit

`194a6342e` (+146/-2, two files):

- **CL knob.** `CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP=1` makes each poll of the focus guard's settle watch sleep `min(SETTLE_POLL, watch_until - now)`. The last poll therefore ends at `watch_until`, and the 220 ms window is unchanged. Any other value, or unset, keeps the whole 30 ms poll. The knob is read once per process and writes an `exp_knob` mark `focus_guard_clamp=1` when on. A `focus_guard settle_poll` mark after each poll diff, written only under the trace gate and in every arm, shows the poll times.
- **MCP span marks.** These are written in `proxy::run_direct` behind the existing `CUA_DRIVER_PHASE_TRACE_FILE` gate:
  - `request_read`, scope `mcp`;
  - `parse_done`, `handler_start`, `handler_end`, `serialize_done` and `response_written`, scope `mcp:<tool|method>`.
- **Unit tests** (class UNIT; run inside the session under the cargo-build and shared quiet locks; `raw/unit/unit-in-session-1.txt`):
  - 3 new clamp tests: the knob parses on only for `1`; an unclamped poll sleeps a whole poll past the deadline (8 x 30 = 240 ms against 220 ms); a clamped poll ends exactly at the deadline;
  - `platform-linux` `input::focus_guard atspi:: tools::`: **184 passed** (N-01R's 181 plus the 3 new);
  - `cua-driver` `proxy::`: **19 passed**, including the new `mcp_trace_scope` test;
  - `cua-driver-core` `phase_trace`: 3 passed.

## Method

- **Fixture, tasks, oracle.** As N-01R.
  - Fixture: `libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py`, task window.
  - Checkbox: `get_window_state` (tree + screenshot), then the jev-use `eligible_controls` lookup, then `click(element_token, background)`.
  - Text: the same observation, then `set_value(Note)`, then `click(Save note, background)`.
  - Oracle: the app's own state file, read every 2 ms by an independent thread. T ends at the first matching sample taken at or after the last action's return.
- **Forced path and producer.** AT-SPI DoAction (cached-ref route) with background delivery and the focus guard, and AT-SPI `set_value`. Each trial checks:
  - `route == accessibility`;
  - the full N-01R click and set_value mark chains;
  - all six MCP span marks plus the client stamps on every call, in order;
  - `exp_knob` marks exactly matching the arm, and the HC flag with the compiled-validator count matching the arm.

  All 436 latest-attempt trials passed.
- **Arms.**

  | Task | Arm | Change |
  |---|---|---|
  | checkbox | S0 | post-DoAction sleep knob 0 (N-01R best checkbox arm) |
  | checkbox | S0+HC | + caller-compiled output validators |
  | checkbox | S0+CL | + `CUA_DRIVER_EXP_FOCUS_GUARD_CLAMP=1` |
  | checkbox | S0+HC+CL | both |
  | text | X | S0 + `set_agent_cursor_motion {glide_duration_ms: 1}` (N-01R best text arm) |
  | text | X+HC, X+CL, X+HC+CL | as above |

- **HC without monkeypatching.**
  - `StampedClientSession` is a `ClientSession` subclass. Its `_validate_tool_result` override stamps the validation span.
  - In HC arms it validates with one validator per distinct output schema, compiled right after `tools/list`, before T and outside it (median 107.5 ms per session). Compilation uses `validator_for` + `check_schema` + `cls(schema, registry=Registry())`, and each result is checked with `best_match(iter_errors(...))`, the acceptance rule of `jsonschema.validate`.
  - Every arm calls `tools/list` before T.
  - The session's read and write streams are wrapped by delegating objects. They stamp the hand-off of each outgoing message to mcp's stdio writer task, and the arrival of each parsed incoming message.
- **The four transport parts.** Per call, they sum to N-01R's transport: (m0 → `dispatch_enter`) + (`dispatch_exit` → m1).

  | Part | Sub-spans |
  |---|---|
  | client send | `client_build` (m0 → hand-off), `client_write_pipe` (hand-off → Driver `request_read`: JSON dump, pipe, Driver wake) |
  | Driver read→handler | `drv_parse`; `drv_admission` (`parse_done` → `handler_start`: protocol validate + `validate_tool_call(tools_list())` + session identity); `drv_inner_pre` (`handler_start` → `dispatch_enter`, includes the second `validate_tool_call` in `handle_request_inner`) |
  | Driver serialize/write | `drv_inner_post` (`dispatch_exit` → `handler_end`: SDK return, Driver-side result conformance, `finish_response`); `drv_bookkeep_serialize` (→ `serialize_done`); `drv_write` (→ `response_written`) |
  | client read/parse/validation | `client_pipe_read_parse` (→ parsed message on the read stream); `client_result_model`; `client_validate` (the `_validate_tool_result` span); `client_return` |

  Driver marks (wall ns) are mapped to the caller's monotonic clock with each trial's median wall-mono offset, as in N-01R.
- **Design.**
  - A 4x4 Williams square with 24 rounds per task. Both tasks run each round, the first task alternating. n = 24 per arm per task, paired within the round.
  - Two EXCLUSIVE `quiet-timed` acquisitions of 96 trials each (3 min 17 s and 3 min 20 s held).
  - Phase 1 uses the S0 / X cells of the same rounds (pre-registered).
- **Statistics.** Medians, nearest-rank p95, within-round paired differences base − arm (positive means faster), and a percentile bootstrap over rounds (10000 resamples, seed 9101).
- **Commands.**
  - `make_plan.py measured plan.json`.
  - `TMPDIR=<tmp> hostless hostless-strict env N02_LANES=<lanes> run_all.sh <wt> <driver> <sha256> plan.json <runs> <tmp> n02 [blocks]`. It runs `run_block.sh` and `n02_harness.py` inside `cua-x11-session.sh`.
  - `package.py`, which copies raw outputs and scrubs paths.
  - `hc_equivalence.py` (jev-use venv Python under hostless), then `analyze.py`, then `verify_artifacts.py`.

## Results

### Denominators

| Block / cell | Attempted | Valid route | Verified (oracle) | Class |
|---|---|---|---|---|
| Main, 4 arms x 2 tasks (e01, e02) | 192 (24 per cell) | 192 | 192 | REAL / BENCHMARK |
| Default-off smoke d01 (arm D, no knobs) | 4 | 4 | 4 | REAL |
| CL decoy 100 ms, 4 arms x 2 tasks | 80 | 80 | 80 (task verified; steal outcome below) | REAL |
| CL edge steal 205-215 ms, 4 arms x 2 tasks | 80 | 80 | 80 (task verified; 76/80 steal passes) | REAL |
| No-steal control, 4 arms x 2 tasks | 80 | 80 | 80 | REAL |
| HC equivalence (40 real + 40 mutated results) | 80 | | 80/80 agree | UNIT (offline, real recorded results) |
| Failed block attempts `n02-c01`, `-r1`, `-r2` (private Xvfb could not take its display, "cannot open the private DISPLAY") | 3 x 20 planned, 0 run | | | kept; re-run as `n02-c01-r3` |
| Pilot p01-p03 (14 trials, before PREREG) | excluded | | | |

There were no task failures, timeouts or unknown outcomes in any cell: all 436 latest-attempt cells verified.

### Main: whole-task T per arm (medians, ms; n = 24 each; REAL)

| Arm | T | p95 | T_land | loadavg (median) |
|---|---|---|---|---|
| checkbox S0 | 286.9 | 340.5 | 38.9 | 12.53 |
| checkbox S0+HC | 265.3 | 290.9 | 24.4 | 12.00 |
| checkbox S0+CL | 270.3 | 300.9 | 41.9 | 12.48 |
| checkbox S0+HC+CL | 245.1 | 273.0 | 25.0 | 12.66 |
| text X | 318.5 | 395.6 | 63.0 | 12.26 |
| text X+HC | 285.2 | 313.6 | 44.0 | 12.21 |
| text X+CL | 291.9 | 332.7 | 64.9 | 12.55 |
| text X+HC+CL | 262.5 | 343.3 | 41.9 | 12.51 |

In every trial the effect landed before the tool returned (`effect_visible_at_return` 24/24 per cell). HC also moves T_land earlier, because the observation's validation (about 14 ms) runs before the action is sent.

### Paired savings vs the base arm (median of within-round base − arm, 95% bootstrap CI, ms; BENCHMARK)

| Arm | Checkbox (vs S0) | Text (vs X) |
|---|---|---|
| +HC | **21.3 [19.9, 24.1]**, S = 1.08 [1.06, 1.09] | **25.9 [20.0, 53.6]**, S = 1.12 [1.06, 1.18] |
| +CL | **19.1 [14.0, 23.9]**, S = 1.06 [1.03, 1.09] | **25.9 [18.0, 35.9]**, S = 1.09 [1.03, 1.14] |
| +HC+CL | 41.0 [36.1, 44.8], S = 1.17 [1.14, 1.18] | 45.3 [39.9, 71.8], S = 1.21 [1.14, 1.28] |

### Phase 1: transport split in the base arms (median ms per trial, share of T; n = 24; BENCHMARK)

| Part | Checkbox S0: observation | Checkbox S0: action (click) | Text X: observation | Text X: actions (set_value + click) |
|---|---|---|---|---|
| Transport total (N-01R definition) | 20.1 (7.0%) | 10.0 (3.5%) | 21.5 (6.8%) | 25.2 (7.8%) |
| client send | 0.21 | 0.28 | 0.28 | 0.67 |
| Driver read→handler | 2.23 (admission 1.26, inner pre 0.97) | 2.19 (1.17, 0.98) | 2.81 (1.42, 1.37) | 5.84 (3.32, 2.47) |
| Driver serialize/write | 1.82 (inner post 1.72; serialize 0.06; write 0.05) | 0.34 (0.26; 0.02; 0.04) | 1.88 (1.78; 0.05; 0.05) | 0.70 (0.57; 0.04; 0.08) |
| client read/parse/validation | 15.35, of which **validate 14.61** | 7.00, of which **validate 6.76** | 15.89, of which **validate 15.28** | 14.98, of which **validate 14.95** |

- Kernel pipe plus Python read/parse (`client_write_pipe` + `client_pipe_read_parse`) is 0.2-0.8 ms per call.
- The observation payload is about 3.9 KB of structured JSON; the screenshot travels as MCP image content.
- The Driver-side MCP work is 4-7 ms per trial, mostly the two `validate_tool_call(tools_list())` passes (admission and `handle_request_inner`) and the Driver-side result conformance.
- With HC, `client_validate` drops to 0.79 ms (observation) and 0.17 ms (click) on the checkbox, and to 0.85 / 0.41 ms on text.

### Work deleted vs wall-clock saved (medians of within-round paired differences, ms)

| Arm | Work deleted | Wall-clock saved (T) |
|---|---|---|
| checkbox S0+HC | client validation: action 6.57 [6.23, 6.71] + observation 13.88 [13.38, 14.29] | 21.3 [19.9, 24.1] |
| text X+HC | client validation: actions 14.60 [13.24, 19.62] + observation 14.43 [13.18, 16.07] | 25.9 [20.0, 53.6] |
| checkbox S0+CL | settle 20.84 [20.74, 20.96] | 19.1 [14.0, 23.9] |
| text X+CL | settle 21.15 [20.96, 21.44] | 25.9 [18.0, 35.9] |
| HC cost moved outside T | validator compilation once per session at tools/list: median 107.5 ms (checkbox S0+HC), pre-T | not in T |

The settle loop ends at its last poll:
- with CL: median 220.09 ms after the guard starts (range 220.03-220.23);
- without CL: 240.96 ms on the checkbox, range 224.1-246.2. The unclamped loop ends after 7 or 8 polls, depending on how far the poll drifts under load.

### Controls

**HC equivalence (UNIT on REAL recorded results; `hc-equivalence.json`).**
- Inputs: 40 real `structuredContent` results from the e01 corpus: get_window_state 8, click 12, set_value 6, list_windows 6, set_agent_cursor_motion 4, get_agent_cursor_state 4.
- Mutants: 40 mutated results (add_unknown_property, drop_required, wrong_type, required_to_null).
- Agreement: the library path (`ClientSession._validate_tool_result` → `jsonschema.validate`) and the harness's compiled path give **identical accept/reject on 80/80**, with identical error messages on 80/80.
- Discrimination: 40/40 real results accepted and 40/40 mutants rejected.

**CL safety (REAL; shared lock, 20 trials per block).** The decoy is a pre-mapped harness X window (EWMH activate + raise + `XSetInputFocus`). It steals the focus a set delay after the app's state change. The oracle is an independent 2 ms X focus sampler. A trial passes only when the decoy stole the focus, the sampler's final (focus, active) equals the pre-trial snapshot, and the click receipt reports `focus_outcome=restored`.

| Kind | S0 | S0+HC | S0+CL | S0+HC+CL | X | X+HC | X+CL | X+HC+CL |
|---|---|---|---|---|---|---|---|---|
| decoy 100 ms: detected and restored | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| edge 205-215 ms: detected and restored | **9/10** | 10/10 | **9/10** | 10/10 | 10/10 | **9/10** | **9/10** | 10/10 |
| no steal: false restores | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |

The four edge failures, every one kept in the denominator:

| Trial | Arm | Steal after guard start | What happened |
|---|---|---|---|
| `c06-003` | S0 (default) | 920.9 ms, after the tool returned | The decoy thread saw the state change about 700 ms late (CPU-starved under load). The steal landed outside every arm's window, so no guard could catch it. Decoy timing failure |
| `c06-016` | S0+CL | 214.9 ms (inside) | The guard detected it at the clamped poll at 220.05 ms, restored, and reported `focus_outcome=restored`. The final state equals the sampler's first sample. The pre-trial one-shot snapshot was taken before GTK moved the focus to its child window, so the pre-registered oracle comparison fails. Oracle artefact |
| `c08-016` | X+CL | 785.4 ms, after return | Decoy timing failure, as `c06-003` |
| `c08-017` | X+HC (default Driver config; HC is caller-side only) | 217.5 ms (inside) | The settle loop polled at 30, 60 and 90 ms; then an X call inside the loop stalled until 2404 ms. The loop then ended on its deadline **without a final diff**, so the steal was never seen (`none_reported`, focus left on the decoy). A real miss by the default guard |

- **Exploratory reading** (added after the results; not pre-registered; never used by a verdict): among steals measured inside the 220 ms watch, with the sampler's first sample as the reference, the CL arms detected and restored 39/39 and the default arms 38/39. The detecting poll came at a median 218-220 ms after the guard start in the CL arms (the 7th poll, or the clamped last poll at 220 ms). In the default arms it came at a median 218-241 ms (the 7th poll, or the 8th at about 241 ms).
- **Main trials:** the focus was unchanged in 192/192, and receipts reported 0 false restores.

**Default-off smoke (arm D, no `CUA_DRIVER_EXP_*`).** 4/4 verified, with no `exp_knob` marks. The post-action sleep was 50.6-51.1 ms, and the settle 221.5-253.6 ms (≥ 220, unclamped).

### Load sensitivity of the observation transport (qualitative; different binaries, never combined)

- **This run** (N2, main trials, 1-minute loadavg 7.9-21.5, median about 12.5). OLS of observation transport on loadavg:
  - checkbox: slope −0.004 ms per unit, r −0.00;
  - text: slope 0.42 ms per unit, r 0.11.

  Action transport: checkbox r 0.04, text r 0.20.
- **N-01R** (c2a9978e, its committed trial metrics):
  - checkbox S0: median observation transport 28.4 ms at median loadavg 16.9;
  - text X: 27.3 ms at 17.4.

The mechanism found here explains why N-01R's span was about 2x R2-04's quiet value. It is CPU-bound Python work in the client (metaschema check + validator construction per call), so it scales with CPU contention. Within this run's load range the per-trial slope is small, and this packet does not claim a load model.

### Receipt-vs-oracle and invariants (E4), every arm

- 0 duplicate mutations: final seq = before + 1 in all 436 cells.
- 0 unverified successes: T always ends on the independent oracle, and click receipts are `unverifiable`.
- 0 refused or failed actions in the main trials.
- 0 stale dispatches: every action uses a token from the same trial's fresh observation. This packet runs no stale-token control. N-01R's control (c) covers stale-token refusal, and the measurement commit does not touch token resolution.
- Events are not used. Phase marks and stamps are measurement only, and no authority comes from passive state.
- The controls discriminate: 40/40 mutants were rejected; decoy steals were restored 80/80; no-steal trials show 0 false restores.

## Pre-registered verdicts

| Item | Result | Verdict |
|---|---|---|
| Validity gate | 24/24 valid and verified in every arm (≥ 95%) | holds |
| HC checkbox | saving 21.3 [19.9, 24.1] ms, CI excludes 0; outcomes identical; equivalence 80/80 | **DELETED** (KEEP, caller-side) |
| HC text | saving 25.9 [20.0, 53.6] ms, CI excludes 0; outcomes identical; equivalence 80/80 | **DELETED** (KEEP, caller-side) |
| CL checkbox | saving 19.1 [14.0, 23.9] ms (≥ 10, CI excludes 0); steal controls not 10/10 in every arm (S0 9/10, S0+CL 9/10) | **KILL** (rule: any steal miss); the misses are not attributable to the clamp (see Controls) |
| CL text | saving 25.9 [18.0, 35.9] ms; steal controls not 10/10 (X+HC 9/10, X+CL 9/10) | **KILL** (same) |
| Transport parts not removed by HC | Driver `drv_bookkeep_serialize` + `drv_write`: 0.06-0.13 ms per trial | IRREDUCIBLE (Driver serialize/write) |
| | `client_write_pipe`, `client_pipe_read_parse` (kernel pipe not isolated from the Python reader/writer) | UNTESTED, 0.2-0.8 ms |
| | `drv_admission` + `drv_inner_pre` (two `validate_tool_call(tools_list())` passes + identity/bookkeeping): 2.1-2.2 ms per call on the checkbox, 5.4-5.8 ms per text trial | UNTESTED (the B-02 admission tools-list cache mechanism; not on this source) |
| | `drv_inner_post` (Driver result conformance): 0.26-1.8 ms; `client_build`, `drv_parse`, `client_result_model`, `client_return`: < 0.3 ms each | UNTESTED |

## E2: critical path of the best eligible composed arm (HC DELETED; CL KILL, so +HC)

Median per-trial share of T. Verdicts are from this packet or from N-01R as noted.

| Component | Checkbox S0+HC (T 265.3 ms) | Text X+HC (T 285.2 ms) | Verdict |
|---|---|---|---|
| Focus-guard settle (220 ms window + ~21 ms poll overshoot) | 241.1 ms, 90.9% | 241.0 ms, 84.6% | IRREDUCIBLE (N-01R H_F). Overshoot: CL KILL under the pre-registered rule, so it stays inside the IRREDUCIBLE settle until a valid re-test |
| Observation body | 12.8 ms, 4.7% | 13.3 ms, 4.5% | IRREDUCIBLE by invariant (N-01R) |
| Reveal | 0.01 ms | 11.5 ms, 4.0% | OWNER_DECISION (N-01R H_C) |
| MCP transport, observation | 5.4 ms, 2.1% | 6.1 ms, 2.1% | client validation DELETED (HC); serialize/write IRREDUCIBLE; remainder UNTESTED (counted in the conservative reading) |
| MCP transport, actions | 3.2 ms, 1.2% | 7.9 ms, 2.8% | client validation DELETED (HC); serialize/write IRREDUCIBLE; remainder UNTESTED |
| Dispatch | 0.9 ms, 0.4% | 3.1 ms, 1.1% | IRREDUCIBLE (N-01R) |
| Resolution, runner | 1.5 ms, 0.6% | 1.9 ms, 0.6% | UNTESTED |
| Verification read; effect lag | 0.4 ms; 0 | 0.3 ms; 0 | IRREDUCIBLE; ZERO |

No component of at least 5% of T, or at least 50 ms, is left without a verdict.

**Untested share** (pre-registered; median over the cell):

| Arm | Standard | Conservative |
|---|---|---|
| checkbox S0 | 1.6% | 3.4% |
| checkbox S0+HC | 1.7% | 3.4% |
| checkbox S0+CL | 2.0% | 4.2% |
| checkbox S0+HC+CL | 1.9% | 3.9% |
| text X | 3.2% | 4.7% |
| text X+HC | 3.2% | 5.0% |
| text X+CL | 3.2% | 4.9% |
| text X+HC+CL | 3.2% | 5.1% |

- **Standard reading:** UNTESTED action-transport sub-spans + resolution + runner + unattributed time. The observation transport counts as IRREDUCIBLE by invariant, as in N-01R.
- **Conservative reading:** additionally the observation call's UNTESTED sub-spans and its T0 → send residual.

For comparison only (different binary and load), N-01R reported 5.8% / 10.3% standard and about 15% / 18% conservative. Checkbox is now below 5% under both readings in every arm. Text is below 5% under the standard reading in every arm. Under the conservative reading it is 4.7-4.9% without HC and 5.0-5.1% with HC, because HC shrinks T while the remaining Driver admission spans stay. The largest remaining untested span is the Driver's MCP admission + inner pre-dispatch, about 8 ms per text trial across observation and actions. It is a named mechanism: the tools-list rebuild that B-02's V knob deleted on the browser source.

## Evidence classes by row

| Row | Class |
|---|---|
| Main trials: T, transport split, paired savings, HC/CL verdicts, untested shares | REAL + BENCHMARK (paired timing; no provider) |
| CL decoy / edge / no-steal controls; default-off smoke | REAL |
| HC equivalence | UNIT (offline, over REAL recorded results) |
| Clamp and trace-scope unit tests; touched suites | UNIT |
| File:line mechanism notes (settle loop, `validate_tool_call` passes, `_validate_tool_result`) | SOURCE |
| Load comparison with N-01R | BENCHMARK, qualitative only, non-comparable across binaries |
| Provider decisions | NOT_RUN (TypeSafe cap 0: 0 attempts, 0 reached; harness refused 0 non-loopback connects) |
| Driver admission tools-list cache on the native path; kernel pipe isolation | NOT_RUN (named UNTESTED) |
| CL with a valid edge-steal control (decoy timing guaranteed inside the window) | NOT_RUN (Next) |
| Wayland, macOS, Windows; WebKit/Chromium AT-SPI targets; foreground delivery | NOT_RUN |

## Deviations

1. **Host-shell python3 at lane start (near miss, no effect).** Before switching to hostless, one stdlib `python3 -c` read the key list of the loop's STATE.json in the plain host shell. There was no GUI, display or bus import and no Driver; it was pure file I/O. Every later code-executing command ran under `hostless hostless-strict`.
2. **Isolation nesting.** As in N-01R, `hostless` (v2) does not mask the host socket directories, so every command ran as `hostless hostless-strict <cmd>`. The harness refuses to run when host sockets are visible.
3. **Unit-test lock order (first attempt).** The first unit-test job took the shared quiet lock and then queued for the cargo-build lock (17:35:10Z). While it waited it could have delayed EXCLUSIVE acquirers, including this lane's e01. It was stopped (this lane's own process) before any test ran (`raw/unit/unit-attempt0-stopped.txt`). It was re-run after the controls, taking the cargo lock first (`raw/unit/unit-in-session-1.txt`).
4. **HC mutation strategy.** The pre-registered `root_not_object` mutant cannot be built: mcp's `CallToolResult` requires `structuredContent` to be an object, so such a result never reaches either validation path. It was replaced by `required_to_null` before the equivalence run produced any result. The selection rule (the first mutant the library path rejects) is unchanged.
5. **Failed session starts.** `n02-c01` and two re-runs failed at session start with "cannot open the private DISPLAY". Other lanes' private Xvfbs had started at the same second on `:99` / `:100`. The private Xvfb shares the abstract socket namespace, and the hostless Landlock scope refused the connection to the foreign display. The 60 planned cells are kept as not run (`failed_block_attempts`); `n02-c01-r3` completed.
6. **Not a quiet host.** The spec asked for a quiet-host run. The EXCLUSIVE lock was held for e01/e02, but other tracks kept the 1-minute loadavg at 7.9-21.5 (median about 12.5) from outside the lock. Every comparison is paired within a round on one source, binary and environment.
7. **Marks beyond the spec list.** `focus_guard settle_poll` was added to show the clamp mechanism and the detecting poll. `handler_end` sits directly after the handler, so the Driver's result conformance (`drv_inner_post`) is classified UNTESTED rather than serialize.
8. **Analysis edits after PREREG.** Only an exploratory diagnostic (fields prefixed `x_`, and the failing-trial list) was added to `analyze.py` after the PREREG commit. Verdict code is unchanged: `git diff e8234b73d -- analyze.py` shows only those lines.
9. **Stale-dispatch gate by construction.** No stale-token control was run; see Invariants.
10. **Focus oracle snapshot.** The pre-registered steal oracle compares against a one-shot snapshot taken right after focus placement, before GTK settles its focus child. This caused the S0+CL edge failure, and in one no-steal trial (X+HC) the sampler's final state differed from that snapshot without any focus change. That trial is not a false restore: the receipt reported nothing and the sampler saw no change.

## Limits

- **Shared host.** Absolute spans are host-state specific (see Deviation 6).
- **Fresh processes.** One fresh Driver per trial. HC's one-time compilation (about 107 ms per session) is outside T; for a long-lived agent it is paid once.
- **Freshness.** Upstream main has since changed `cua-driver-core/src/tool_schema.rs`. Output-schema size drives the client validation cost, so HC's magnitude should be re-measured on R2-10's source. The mechanism transfers.
- **Synthetic decoy.** The decoy is an in-process Python thread that keys on the state file. Under load it slipped twice, by about 0.6 s.
- **Scope.** One fixture window; X11 (Xvfb, openbox, picom) only; the scripted chooser.

## Claim boundary

On the canonical GTK3 fixture, with AT-SPI background delivery, X11 Xvfb/openbox/picom and a private AT-SPI bus, Driver N2 (`194a6342e`, sha256 `893646ab…`), the scripted chooser and a fresh Driver per trial:

- the client-side output-schema validation is the dominant part of native MCP transport and is deletable caller-side, with identical acceptance (HC DELETED);
- the settle-poll clamp saves about 20 ms of settle, but it did not meet the pre-registered steal-control bar (CL KILL). The failures are attributed to decoy timing, the oracle snapshot and a default-guard stall, not to the clamp.

A verdict transfers to R2-10's source by mechanism only. No Driver default changes: the knob and marks are measurement-only and default-off, and HC is caller-side.

## Disposition

**N-02: KEEP (HC) / KILL (CL, pre-registered rule).** This is terminal for the native transport and settle-overshoot follow-ups.
- **HC: DELETED (KEEP, caller-side)** on checkbox and text. It goes into R2-10's native composed arm (S0+HC, X+HC), and it is the same mechanism as B-01 H_C on the browser path.
- **CL: KILL** under the pre-registered rule. The ~21 ms overshoot remains inside the IRREDUCIBLE settle until a re-test with a valid control.
- **Transport remainder:**
  - Driver serialize/write: IRREDUCIBLE;
  - Driver admission + inner pre-dispatch: UNTESTED, 2-6 ms per trial (the B-02 V mechanism);
  - pipe/read/parse spans: UNTESTED, under 1 ms.
- **E2 native:**
  - standard reading: 1.7% (checkbox) and 3.2% (text) untested in the best eligible composed arm;
  - conservative reading: 3.4% and 5.0%.

## Next

1. **Guard fix candidate (#20, product, needs review).** When the settle loop exits on its deadline with no change seen, take one final diff before reporting. Trial `c08-017` shows that the default guard can silently miss a steal inside its window after an X stall. Smallest test: a red-before/green-after unit test with an injected stall.
2. **CL re-test (only after 1).**
   - Trigger the steal from the Driver-side `do_action_replied` timeline, or from a separate process, so that it lands inside the window.
   - Compare against the sampler's trial-start state.
   - Pre-register a window-validity rule before any trial.
3. **Native admission tools-list cache.** B-02's V knob on the native path would test the largest remaining untested span (about 8 ms per text trial).
4. **R2-10.** Put HC (caller-compiled validators) in the native composed arm and re-measure its magnitude on R2-10's source (upstream `tool_schema.rs` changed).

## Files

| File | Contents |
|---|---|
| `PREREG.json` | Pre-registration, committed before the first measured trial |
| `plan.json`, `make_plan.py` | The deterministic trial plan |
| `n02_harness.py`, `xprobe.py`, `run_block.sh`, `run_all.sh`, `unit_in_session.sh` | Harness (derived from N-01R), X focus sampler and decoy (verbatim), orchestration, unit runner |
| `hc_equivalence.py`, `hc-equivalence.json` | HC equivalence control and its result (80 rows) |
| `package.py` | Raw copy and scrub |
| `analyze.py` | Recomputes `n02-summary.json` and `n02-trial-metrics.jsonl.gz` from `raw/` |
| `verify_artifacts.py` | Recompute check, lock ledger, PREREG order, Driver/plan hashes, HC equivalence, controls, README numbers, privacy (packet files and every branch commit), tracked files |
| `provenance.json` | Every SHA, binary, build and environment fact |
| `raw/n02-<block>[-rN]/trials.jsonl.gz`, `session.txt` | One ledger per block attempt: meta, every trial (caller stamps, client stamps, oracle samples, Driver marks, receipts, focus samples), end |
| `raw/n02-e01/hc-corpus.jsonl.gz`, `raw/n02-<block>/output-schemas.json` | Full real results kept for the HC control; output schemas from tools/list |
| `raw/lock-ledger.jsonl` | quiet-timed (exclusive) and shared-lock receipts for every packaged label |
| `raw/driver-build/`, `raw/unit/`, `raw/run_all-*.txt` | Build output and hashes, Driver version, unit logs, orchestration logs |
