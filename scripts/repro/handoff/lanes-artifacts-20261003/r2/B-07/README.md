# B-07: browser MCP transport residual on R' (c_in.prep, c_out.route, d_out.post, adm.inner), 2026-10-03

Lane B-07, wave 5 of the CUA RFC loop. Owners: kvnloo/cua#93 (experiment specs), kvnloo/cua#10
(whole-task accounting), kvnloo/cua#73 (E2). Upstream items are named as plain text (trycua/cua PR 4316).
B-05 (exp/b-05-browser-mcp-transport-a3-20261003) left four browser MCP transport sub-spans UNTESTED; this
lane decomposes the transport on R' code and gives each of them a terminal verdict by causal A/B or by
the pre-registered selection rule.

## Result in one paragraph

Phase A 96 of 96, overhead control 120 of 120 and Phase B 360 of 360 trials (PREP_FAST 180, POST_FAST 180) were verified by the independent oracle with exactly one completion mutation, and all were valid on the forced path. N4a passed 45 of 45 in N2 (15 per arm). The default-off smoke passed 15 of 15 on B7 and 15 of 15 on R'. Every round started at 1-minute loadavg <= 4.0. Evidence class: REAL / BENCHMARK+REAL.

**Disposition: REVISE.** On R' code (binary B7), fill / toggle / modal, per task:

- corrected transport in/out is 3.35 / 2.45 / 2.48 ms (raw 6.71 / 5.81 / 5.84);
- the corrected admission residual is 0.11 / 0.11 / 0.11 ms (raw 1.53 / 1.54 / 1.53);
- corrected resolution is 1.98 / 0.94 / 0.81 ms.

Every residual sub-span that B-05 left UNTESTED now has a terminal verdict:

- **c_out.route: BELOW_GATE.** It is 0.34-0.39 ms, so ROUTE_FAST was not selected.
- **adm.inner: BELOW_GATE** at 0.09-0.11 ms. It was removed from the candidate menu, with the reason written in PREREG.json.
- **d_out.post: IRREDUCIBLE.** POST_FAST is KILL in every class.
- **c_in.prep: IRREDUCIBLE** for toggle and modal (PREP_FAST KILL).
- **c_in.prep on fill: DELETED by the pre-registered gate**, with a T_oracle saving of 3.94 ms [0.09, 10.07]. That pass is not robust:
  - one pair carries it: round 0's chunk-first trial, which in an AB round is always the control, ran about 82 ms slow;
  - without that pair the saving is 1.25 [-0.25, 2.90], which is a KILL;
  - the median paired difference is 0.04 ms;
  - PREP_FAST deletes only 0.48 ms of caller work per fill task.

  The lane reports this verdict as DELETED (fragile) and does not recommend carrying PREP_FAST.

E2 R'-source untested share, corrected at c_m with R2-10's carry-over mapping (fill / toggle / modal):

- 1.6% / 0.6% / 0.6% with BELOW_GATE counted as IRREDUCIBLE;
- 4.0% / 3.5% / 3.5% with BELOW_GATE counted as UNTESTED;
- 5.3% / 5.5% / 5.5% at the measured-overhead scale with BELOW_GATE counted as UNTESTED.

So the browser MCP transport no longer holds an UNTESTED component of 5% or more in any class at c_m. Two views stay above that line:

- Under B-04's mapping, where the observation cold excess counts as untested (outside this lane), fill and toggle are at 26.2% / 19.1%.
- The raw (marks-on) view with BELOW_GATE counted as UNTESTED is 8.4% / 10.0% / 10.0%.

Provider: 0 attempts, 0 reached.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | R2-10R COMP (harness/r2-10r/r2_10_browser.py `ARMS["COMP"]`, byte-identical to c183b95e3): cursor/feedback off, guarded completion, settle 0 on fill, 10 ms poll, admission tools-list cache, compiled client validators, compiled replay on fill; fresh Driver, isolated Chrome, fixture state and token per trial. Each row is checked by R2-10R's own `browser_row` plus the lane rules: marks on/off as the arm says, the exact `CUA_DRIVER_EXP_*` set per arm, and for PREP_FAST that the fast path was taken (per-trial counters) and never taken in a default arm | REAL |
| Actual route / producer | fill `browser_type:trusted_input` then `browser_click:dom`; toggle and modal two `browser_click:dom`; decision producer = scripted chooser, compiled replay on fill after one training invocation per (layer, arm) | REAL |
| Independent target-owned oracle | jev-use fixture-server state sampled every 2 ms by a harness thread; verified only with the expected final state and exactly one completion mutation in the fixture journal; T_oracle by the R2-10 rule | REAL |
| Negative / fallback controls | N4a stale-ref (node replaced between bind and dispatch) 15 per arm; malformed frames through the client stack (route default vs fast); request-byte edge cases and fallback types (prep default vs fast); UNIT schema-rejected payload with and without the prewarm knob | REAL, FIXTURE, UNIT |
| Tested source SHA | Driver source ac319cbe90d6cdf0cc8cd8984f99f5b04b68fdac = R' 45dff8f32 + picks a17530466 / c65b1d2f2 / 501158460 (of 4c786178b / 3116b6981 / b376f1ff3, range-diff all `=`, 0 conflicts) + the B-07 knob; rust tree `20c9f051248a`; libs/cua-driver tree of R' = df2b49c32e73 (= upstream main cb685fad7 and 0f1955d2f). The binary was built at packet commit 231f6e8bb, whose rust tree is the same | SOURCE |
| Driver binary | B7 `cua-driver-b07-231f6e8bb`, sha256 `6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa`, `cua-driver 0.32.0` (read inside the private session at every chunk start). R' reference for the default-off smoke only: `922111c518d73b9675a9800d39a389c17070d40d16f25ada1426a90eccd06ec8`, `cua-driver 0.32.0` | SOURCE |
| Environment | one Linux host shared with other tracks; bin/hostless for every code-executing command; private Xvfb (cua-x11-session.sh) with 0-3 s start jitter and an xdpyinfo probe; system Chrome (Google Chrome 151.0.7922.71 and Chromium 151.0.7922.173 both installed, read in session; raw/source/browser-versions.txt); telemetry off; provider key never forwarded; jev-use venv mcp 1.30.0. 1-minute loadavg means: Phase A 3.22, overhead 2.31, PREP_FAST 3.11, POST_FAST 2.32 (trial records) | SOURCE |
| PREREG commit | 231f6e8bb (2026-10-03T07:48:13Z), before the first measured chunk (A1, lock acquired 2026-10-03T09:16:20Z); PREREG-AMENDMENT-1 f9ab56947 (09:19:32Z), before the first Phase B chunk (P1, 11:02:14Z) | SOURCE |
| Live heads | start 09:19Z: trycua/cua main 410578a4a (18 ahead of 0f1955d2f; 7 libs/cua-driver files changed, all under platform-macos and platform-windows, none on the Linux path tested here); trycua/cua PR 4316 a0bca7440, open. End: 12:02Z: trycua/cua main 379085c5e (26 ahead of 0f1955d2f; 14 libs/cua-driver files: platform-macos and platform-windows sources plus Skills MACOS.md, the cua-driver-e2e AppKit test, a macOS AppKit fixture and tests/fixtures/shared/scenarios.json; none in cua-driver-core, cua-driver, cua-driver-sdk, cua-driver-contract or platform-linux, so no tested Linux path changed); trycua/cua PR 4316 a0bca7440, open, unchanged | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); never equal-by-assumption to the tested SHA | SOURCE |
| Provider | none (scripted chooser); TypeSafe attempts 0, reached 0 (lane cap 0) | NOT_RUN |

## Phase 0: the four sub-spans in code (SOURCE)

PREREG.json `phase0_source_map` has the full call chains. In short:

| sub-span | what runs there (R' + picks, jev-use mcp 1.30.0) | candidate | class |
|---|---|---|---|
| c_in.prep | RecDriver.call stamp → jev-use `run.Driver.call` → `ClientSession.call_tool` (three pydantic request models) → `BaseSession.send_request` (model_dump, JSONRPCRequest, SessionMessage) → capacity-0 memory-stream hand-off to the stdin-writer task | PREP_FAST: build the JSON-RPC line directly and write it from the calling task (plain-JSON arguments only; byte-identical) | SOURCE |
| c_out.route | stdout reader → capacity-0 hand-off to the session receive loop → `_handle_response` (id normalise, routers, pop waiter) → waiter wake → result model | ROUTE_FAST: hand a parsed response straight to its waiter (decoded-identical) | SOURCE |
| d_out.post | dispatch exit → runtime activity observer → SDK `normalize_result` → adapter JSON re-parse and session mirror → `conforming_tool_result` (per-tool-name, lazily compiled jsonschema output validator + typed ActionResult check) → completion/telemetry bookkeeping | POST_FAST: default-off knob `CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM=1` compiles the shared ActionResult validator once at transport start (byte-identical responses) | SOURCE, UNIT |
| adm.inner | `apply_direct_session_identity`, `begin_tool_call` session context, observation timer, inner classification (repeat validation already skipped by the B-02 cache) | none: removed from the menu (its work above the mark cost is session identity and session context, both invariant-bearing) | SOURCE |

Design input (B-05 raw, binary B5, not a B-07 result): almost every d_out.post interval is about one mark
cost; the exception is `mcp.invoke_end → mcp.conformed` on the first call of each action-result tool in a
fresh Driver process (246-307 us, against 48-51 us on the second call), which is the lazy validator compile.

## Method

- **Arms.** COMP (phase trace on), COMP_OFF (trace off), and the Phase B candidates named in
  PREREG-AMENDMENT-1.json (PREP_FAST, POST_FAST). One binary (B7) in every Part 1 arm.
- **Phase A** (chunk A1): 32 rounds, rotated class order, 96 COMP trials. Every in-T call is split at every
  Driver mark and caller stamp by B-05's harness/b05/b05_spans.py; corrected = raw − (marks starting
  intervals of that sub-span) × c_m, with c_m the median of the in-situ null-pair intervals.
- **Overhead control** (chunk O1): 20 AB/BA rounds per class, COMP vs COMP_OFF.
- **Selection** (PREREG-AMENDMENT-1.json): a candidate runs iff its target sub-span has a corrected Phase A
  mean ≥ 0.5 ms in some class: c_in.prep and d_out.post were selected; c_out.route was not (BELOW_GATE).
- **Phase B** (chunks P1, Q1): 30 AB/BA rounds per class per candidate vs COMP_OFF; N4a (chunk N1) 5 per
  class in COMP_OFF, PREP_FAST and POST_FAST. Primary metric T_oracle (paired COMP_OFF − candidate);
  T_runner and the work metric (caller stamps, visible with marks off) are reported beside it.
- **Load and locks.** A round starts only at 1-minute loadavg ≤ 4.0 (waits up to 60 s, else the chunk
  ends and resumes; every gate attempt is in the run manifests). Every measured chunk held the cargo-build
  lock, then `bin/quiet-timed` (EXCLUSIVE), then the private session, ≤ 10 min (raw/locks/).
- **Statistics.** Seeded bootstrap of the mean (seed 20261003, 10000 resamples), paired by (class, round);
  every trial kept.

## Results: R'-source decomposition (Phase A, BENCHMARK+REAL)

96 of 96 COMP trials are valid and verified.

- **Coverage and consistency.** B-05 sub-span coverage of T_runner is 1.000 on every trial (gate 0.98). R2-10R's own coverage has a minimum of 0.985. The sub-spans add up to R2-10R's component values exactly (maximum deviation 0.0 ms).
- **Per-mark cost.** c_m = 32.33 us, the median of 1536 null intervals.
- **Task time** (fill / toggle / modal). Mean T_runner is 76.59 / 49.48 / 49.43 ms, 68.61 / 41.78 / 41.73 ms corrected. Median T_oracle is 63.90 / 49.40 / 49.44 ms.
- **Instrumentation share at c_m.** The marks make up 50.09 / 57.85 / 57.56% of raw transport in/out and 93.00 / 92.59 / 92.78% of the raw admission residual.
- **The correction over-subtracts.** The overhead control measured 0.57 of the predicted penalty (marks x c_m, pooled; fill's CI is wide). The E2 section therefore also reports the measured-scale view.

Groups, per task, raw / corrected [95% CI] in ms (fill | toggle | modal):

| group | fill | toggle | modal | class |
|---|---|---|---|---|
| transport_in_out | 6.71 / 3.35 [3.06, 3.85] | 5.81 / 2.45 [2.39, 2.51] | 5.84 / 2.48 [2.40, 2.56] | BENCHMARK+REAL |
| admission_residual | 1.53 / 0.11 [0.08, 0.14] | 1.54 / 0.11 [0.09, 0.14] | 1.53 / 0.11 [0.10, 0.12] | BENCHMARK+REAL |
| resolution | 2.53 / 1.98 [1.86, 2.15] | 1.40 / 0.94 [0.89, 1.00] | 1.26 / 0.81 [0.77, 0.86] | BENCHMARK+REAL |
| client_validation | 0.38 / 0.38 [0.36, 0.42] | 0.35 / 0.35 [0.34, 0.36] | 0.35 / 0.35 [0.34, 0.37] | BENCHMARK+REAL |

Overhead control (marks on − marks off, paired), ms:

| class | pairs | T_runner [CI] | T_oracle [CI] | predicted marks × c_m | measured / predicted | class |
|---|---|---|---|---|---|---|
| fill | 20 | 2.47 [-6.51, 7.85] | 1.80 [-7.41, 7.41] | 7.99 | 0.31 | BENCHMARK+REAL |
| toggle | 20 | 5.07 [3.05, 7.06] | 5.28 [3.54, 6.97] | 7.69 | 0.66 | BENCHMARK+REAL |
| modal | 20 | 5.68 [4.52, 6.80] | 5.13 [3.89, 6.32] | 7.69 | 0.74 | BENCHMARK+REAL |

Sub-spans (verdict units as in B-05), per task raw / corrected [95% CI] in ms, and the terminal verdict:

| unit | fill | toggle | modal | verdict | class |
|---|---|---|---|---|---|
| c_in.prep | 0.63 / 0.63 [0.58, 0.70] | 0.60 / 0.60 [0.58, 0.62] | 0.61 / 0.61 [0.59, 0.63] | DELETED (PREP_FAST) / IRREDUCIBLE (candidate failed: PREP_FAST KILL) / IRREDUCIBLE (candidate failed: PREP_FAST KILL) | BENCHMARK+REAL (A1) |
| c_out.route | 0.39 / 0.39 [0.36, 0.44] | 0.34 / 0.34 [0.33, 0.35] | 0.35 / 0.35 [0.33, 0.36] | BELOW_GATE | BENCHMARK+REAL (A1) |
| d_out.post | 2.59 / 0.91 [0.86, 0.99] | 2.25 / 0.57 [0.55, 0.60] | 2.27 / 0.59 [0.57, 0.62] | IRREDUCIBLE (candidate failed: POST_FAST KILL) | BENCHMARK+REAL (A1) |
| adm.inner | 1.00 / 0.09 [0.08, 0.12] | 1.01 / 0.11 [0.09, 0.12] | 1.01 / 0.10 [0.09, 0.12] | BELOW_GATE | BENCHMARK+REAL (A1) |
| adm.outer | 0.53 / 0.01 [0.01, 0.02] | 0.53 / 0.01 [0.00, 0.02] | 0.52 / 0.01 [0.00, 0.01] | BELOW_GATE | BENCHMARK+REAL (A1) |
| c_in.serialize | 0.07 / 0.07 [0.07, 0.08] | 0.07 / 0.07 [0.06, 0.07] | 0.07 / 0.07 [0.06, 0.07] | BELOW_GATE | BENCHMARK+REAL (A1) |
| write_pipe_in | 0.20 / 0.20 [0.14, 0.33] | 0.15 / 0.15 [0.14, 0.16] | 0.14 / 0.14 [0.13, 0.14] | BELOW_GATE | BENCHMARK+REAL (A1) |
| pipe_out_frame | 0.37 / 0.11 [0.07, 0.16] | 0.27 / 0.02 [-0.00, 0.03] | 0.27 / 0.01 [-0.01, 0.03] | BELOW_GATE | BENCHMARK+REAL (A1) |
| c_out.parse | 0.54 / 0.54 [0.49, 0.60] | 0.32 / 0.32 [0.30, 0.34] | 0.32 / 0.32 [0.30, 0.34] | IRREDUCIBLE (candidate failed, B-05 PARSE_FAST KILL) | BENCHMARK+REAL (A1) |
| c_out.result_model | 0.13 / 0.13 [0.12, 0.15] | 0.12 / 0.12 [0.11, 0.12] | 0.12 / 0.12 [0.11, 0.12] | BELOW_GATE | BENCHMARK+REAL (A1) |
| c_out.validate | 0.38 / 0.38 [0.36, 0.42] | 0.35 / 0.35 [0.34, 0.36] | 0.35 / 0.35 [0.34, 0.37] | IRREDUCIBLE (candidate failed, B-05 VALIDATE_FAST KILL) | BENCHMARK+REAL (A1) |
| c_out.return | 0.09 / 0.09 [0.08, 0.10] | 0.08 / 0.08 [0.07, 0.08] | 0.08 / 0.08 [0.08, 0.08] | BELOW_GATE | BENCHMARK+REAL (A1) |
| d_in.parse | 0.39 / 0.00 [-0.01, 0.02] | 0.37 / -0.01 [-0.02, -0.01] | 0.37 / -0.01 [-0.02, -0.01] | BELOW_GATE | BENCHMARK+REAL (A1) |
| d_in.invoke | 0.60 / 0.08 [0.06, 0.11] | 0.60 / 0.08 [0.07, 0.08] | 0.61 / 0.09 [0.08, 0.10] | BELOW_GATE | BENCHMARK+REAL (A1) |
| d_out.serialize | 0.16 / 0.03 [0.02, 0.05] | 0.14 / 0.02 [0.01, 0.02] | 0.14 / 0.01 [0.01, 0.02] | BELOW_GATE | BENCHMARK+REAL (A1) |
| d_out.write_flush | 0.54 / 0.16 [0.14, 0.18] | 0.50 / 0.11 [0.10, 0.12] | 0.50 / 0.12 [0.10, 0.13] | BELOW_GATE | BENCHMARK+REAL (A1) |

| resolution sub-span | fill corr [CI] | toggle | modal | verdict | class |
|---|---|---|---|---|---|
| res.dispatch | 0.16 [0.15, 0.18] | 0.13 [0.13, 0.14] | 0.13 [0.12, 0.14] | BELOW_GATE | BENCHMARK+REAL (A1) |
| res.ref_parse | 0.01 [0.00, 0.01] | 0.00 [0.00, 0.01] | 0.00 [0.00, 0.00] | BELOW_GATE | BENCHMARK+REAL (A1) |
| res.store_lookup | 0.03 [0.03, 0.04] | 0.02 [0.02, 0.02] | 0.01 [0.01, 0.02] | BELOW_GATE | BENCHMARK+REAL (A1) |
| res.frame_proof | 0.41 [0.37, 0.45] | 0.39 [0.36, 0.43] | 0.35 [0.33, 0.37] | IRREDUCIBLE (invariant: Page.getFrameTree re-proves the ref's frame identity at dispatch) | BENCHMARK+REAL (A1); invariant SOURCE |
| res.type_focus | 0.39 [0.37, 0.42] | absent | absent | IRREDUCIBLE (invariant: DOM.focus: trusted_input typing goes to the focused element) | BENCHMARK+REAL (A1); invariant SOURCE |
| res.cdp_node_resolve | 0.70 [0.66, 0.74] | 0.40 [0.38, 0.42] | 0.31 [0.29, 0.34] | IRREDUCIBLE (invariant: DOM.resolveNode: the live node (FIX-01 detached-node refusal) and its objectId) | BENCHMARK+REAL (A1); invariant SOURCE |
| res.editable_check | 0.29 [0.26, 0.33] | absent | absent | IRREDUCIBLE (invariant: Runtime.callFunctionOn: non-editable targets are refused before typing) | BENCHMARK+REAL (A1); invariant SOURCE |
| res.post_check | 0.00 [0.00, 0.00] | absent | absent | BELOW_GATE | BENCHMARK+REAL (A1) |

## Phase B: causal A/B (BENCHMARK+REAL)

Paired saving = COMP_OFF − candidate (positive = faster), ms, mean [95% CI]:

| candidate | class | pairs | T_oracle saving | T_runner saving | work deleted (work metric) | candidate | target verdict | class |
|---|---|---|---|---|---|---|---|---|
| POST_FAST | fill | 30 | 3.39 [-0.13, 9.44] | 3.65 [0.14, 9.77] | 3.66 [0.17, 9.74] | KILL | IRREDUCIBLE (candidate failed: POST_FAST KILL) | BENCHMARK+REAL |
| POST_FAST | toggle | 30 | 1.19 [-0.07, 2.48] | 1.69 [0.24, 3.18] | 1.34 [0.12, 2.66] | KILL | IRREDUCIBLE (candidate failed: POST_FAST KILL) | BENCHMARK+REAL |
| POST_FAST | modal | 30 | -0.28 [-1.38, 0.81] | -0.23 [-1.27, 0.81] | -0.14 [-1.12, 0.84] | KILL | IRREDUCIBLE (candidate failed: POST_FAST KILL) | BENCHMARK+REAL |
| PREP_FAST | fill | 30 | 3.94 [0.09, 10.07] | 4.07 [0.35, 10.10] | 0.48 [0.43, 0.52] | DELETED (KEEP) | DELETED (PREP_FAST) | BENCHMARK+REAL |
| PREP_FAST | toggle | 30 | 0.23 [-0.98, 1.42] | -0.24 [-1.56, 1.06] | 0.45 [0.42, 0.48] | KILL | IRREDUCIBLE (candidate failed: PREP_FAST KILL) | BENCHMARK+REAL |
| PREP_FAST | modal | 30 | 0.61 [-1.37, 2.90] | 1.10 [-0.96, 3.45] | 0.49 [0.44, 0.56] | KILL | IRREDUCIBLE (candidate failed: PREP_FAST KILL) | BENCHMARK+REAL |

Equivalence and controls:

- **PREP_FAST.**
  - 1800 of 1800 tools/call request lines are byte-identical to the library serialisation.
  - Responses are decoded-identical in 180 of 180 trials, and every in-T call validated ok in both arms.
  - The fast path was taken in every PREP_FAST trial and never in a COMP_OFF trial.
- **POST_FAST.**
  - Requests are identical in 1800 of 1800 lines, and responses are decoded-identical in 180 of 180 trials.
  - Response structure is identical in 89 of 90 pairs. The one differing pair is fill round 0, where the chunk-first COMP_OFF trial's get_browser_state reported `tabs[0].active: null`.
  - P1 shows the same pair difference, and PREP_FAST does not touch the Driver. The difference is an observation state, not an action result, but under the pre-registered criterion POST_FAST equivalence is not 100% (Deviation 3).
- **N4a.** 15 of 15 per arm in N2: refused `browser_ref_stale` with `effect: refused` in the response frame, then one rebind, verified.

Post-hoc sensitivity (documentation only) with round 0 dropped. T_oracle saving fill / toggle / modal:

- PREP_FAST 1.25 [-0.25, 2.90] / 0.04 [-1.20, 1.24] / 0.56 [-1.46, 2.97];
- POST_FAST 0.62 [-0.34, 1.59] / 1.02 [-0.23, 2.34] / -0.49 [-1.59, 0.51] ms.

Without round 0, no candidate passes the gate in any class.

## Work deleted vs wall-clock saved

| item | work deleted (per task) | wall-clock saved (paired T_oracle, mean [CI]; fill, toggle, modal) | class |
|---|---|---|---|
| PREP_FAST (c_in.prep) | caller call_send -> c.req_written, paired: 0.48 [0.43, 0.52] fill, 0.45 [0.42, 0.48] toggle, 0.49 [0.44, 0.56] modal; every mean is below the 0.5 ms gate | 3.94 [0.09, 10.07], 0.23 [-0.98, 1.42], 0.61 [-1.37, 2.90]; medians 0.04 / -0.03 / -0.03 | BENCHMARK+REAL |
| POST_FAST (d_out.post) | The knob moves the validator compile out of T. On B7 Phase A the first action-result call's conform interval is 211-229 us, against 41-42 us for a warm call: about 0.37 ms per fill task (two tool names, two compiles) and about 0.18 ms per toggle or modal task. Per process, the knob deletes one compile on fill (browser_type and browser_click share one validator) and only moves it on toggle and modal. The marks-off Driver-window paired difference is 3.66 [0.17, 9.74] / 1.34 [0.12, 2.66] / -0.14 [-1.12, 0.84] ms. It includes the whole tool execution and is too noisy to isolate the compile | 3.39 [-0.13, 9.44], 1.19 [-0.07, 2.48], -0.28 [-1.38, 0.81] | BENCHMARK+REAL |
| phase-trace marks (measurement only, default off) | about 247.00 / 238.00 / 238.00 marks x 32.3 us per task when on | see the overhead control; not a product saving | BENCHMARK+REAL |

## Controls

| control | n | result | class |
|---|---|---|---|
| Default-off smoke (R2-10 smoke plan, BASE, no `CUA_DRIVER_EXP_*`, no trace), B7 vs R' 922111c5 | 5 per class per binary | 15 of 15 and 15 of 15 verified; receipt shapes and routes identical per class; no EXP env; no trace-like file (raw/browser/D-B7.tar.gz, raw/browser/D-Rp.tar.gz) | REAL |
| N4a, node replaced between bind and dispatch | 5 per class in COMP_OFF, PREP_FAST and POST_FAST | N2: 45 of 45 (15 per arm). Each is refused `browser_ref_stale` with `effect: refused`, then one rebind, verified. N1: 30 of 45; its 15 fill trials stopped in the harness before any dispatch because no compiled routine was in the run directory (Deviation 2) | REAL |
| Request bytes (PREP_FAST), Phase B | every tools/call request in P1, both arms | 1800 of 1800 byte-identical to the library serialisation (raw/equivalence/equivalence-P1.json) | REAL (FIXTURE check) |
| Request-byte edge cases and fallback types (PREP_FAST) | 11 argument sets: non-ASCII, U+2028/2029, control characters, quotes, nested, float, None, int >= 2**53 | every request line identical between arms and to the library; 8 fast-path and 3 fallback cases, as designed (raw/controls/controls.json) | FIXTURE |
| Malformed frames through the client stack (ROUTE_FAST code path) | 12 frames x route default / fast | identical outcome per frame in both arms; every malformed frame rejected; the string-id frame is accepted in both arms (library id normalisation). ROUTE_FAST was not selected, so this only shows the variant is safe (raw/controls/controls.json) | FIXTURE |
| POST_FAST results with and without prewarm | valid and schema-rejected payloads, 3 tools | identical result bytes; one shared validator (raw/unit/core-mcp-result-tests.txt) | UNIT |
| Unit suites on the lane tree | core mcp_result:: (incl. 2 B-07 tests), browser::, phase_trace; cua-driver proxy::; platform-linux focus_guard | all pass (raw/unit/steps.txt) | UNIT |
| E4 | every measured trial of A1, O1, P1 and Q1 | 0 stale-ref dispatches, 0 duplicate mutations, 0 unverified successes, 0 refusals returned as success, 0 blind replays | REAL |

## Modal stall (pre-registered definition)

Pre-registered definition: a caller-side interval (c_in.* or c_out.* by B-05's left-point label) longer than 20 ms inside T.

- Phase A has 0 such stalls (fill: 0, toggle: 0, modal: 0 trials).
- So c_in.prep is the same with and without stall trials: 0.63 / 0.60 / 0.61 ms against 0.63 / 0.60 / 0.61 ms.
- There is nothing to classify as GC or scheduler.
- B-05's 86 ms modal stall (one trial, binary B5, loadavg 13.8) did not recur on R' with every round started at loadavg <= 4.0.

## E2: R'-source untested share

Untested share of mean T_runner per class, BELOW_GATE counted as IRREDUCIBLE and as UNTESTED, corrected
(c_m) and raw. Each cell is (a) R2-10's carry-over mapping (observation IRREDUCIBLE) / (b) B-04's mapping
(the cold excess E = span(snapshot1) − span(snapshot2) on B7 counts as UNTESTED for fill and toggle:
per-document IRREDUCIBLE but unsized, per-process pending B-06, u = 1). The two mappings are never
combined, and nothing here is combined with B-06 numbers or with another binary's (B5, R, R').

| class | corr, BG as IRREDUCIBLE (a / b) | corr, BG as UNTESTED | raw, BG as IRREDUCIBLE | raw, BG as UNTESTED | mean corrected T_runner (ms) | class |
|---|---|---|---|---|---|---|
| fill | 1.6% / 26.2% | 4.0% / 28.5% | 1.8% / 23.8% | 8.4% / 30.4% | 68.61 | BENCHMARK+REAL (A1) |
| toggle | 0.6% / 19.1% | 3.5% / 22.1% | 0.6% / 16.3% | 10.0% / 25.7% | 41.78 | BENCHMARK+REAL (A1) |
| modal | 0.6% / 0.6% | 3.5% / 3.5% | 0.6% / 0.6% | 10.0% / 10.0% | 41.73 | BENCHMARK+REAL (A1) |

- **What stays untested.** Corrected, with BELOW_GATE counted as IRREDUCIBLE, the remaining untested items are outside the transport: fill's R2-10 `input_prep` (0.88 ms) and the runner overhead (0.21-0.23 ms). With BELOW_GATE counted as UNTESTED, the largest items are c_out.route (0.34-0.39 ms) and the other transport units below 0.5 ms.
- **The measured-overhead scale** (c_m x 0.566 = 18.3 us). Here adm.inner rises above 0.5 ms and becomes IRREDUCIBLE (invariant) by the pre-registered admission rule. The shares are 1.7% / 0.6% / 0.6% with BELOW_GATE counted as IRREDUCIBLE, and 5.3% / 5.5% / 5.5% with BELOW_GATE counted as UNTESTED.
- **No cross-binary comparison.** B-05's 7.5% modal share was measured on binary B5 at loadavg 13.8 and is not compared with these numbers.
- **Cold excess.** On B7, E is 16.83 / 7.74 / 7.54 ms (BENCHMARK+REAL, B-04 estimator). It is used only in mapping (b).

## Deviations and disclosures

1. **Near misses (no effect).**
   - A `python3 --version` (output discarded) ran in the plain host shell during read-only inspection.
   - A `pgrep -f` was used inside a read-only `ps` listing while inspecting the lock queue. No signal was sent.

   Neither touched a display, a bus or another process.
2. **N4a chunk N1.** Every fill N4a trial stopped in the harness ("no admitted routine for A/<arm>") before any dispatch. Fill runs compiled replay, and N1's run directory had no trained routine. Toggle and modal passed 30 of 30. N2 reran all 45 with a routine store made of exact copies of the routines trained in P1 (COMP_OFF, PREP_FAST) and Q1 (POST_FAST). The N4a gate uses N2; N1 is packaged and reported.
3. **Equivalence structure check.** One pair per Phase B chunk differs: fill round 0, where get_browser_state reports `tabs[0].active` null in the chunk-first COMP_OFF trial. That is an observation-state difference in a call neither candidate changes. POST_FAST's pre-registered equivalence includes the structure check, so it is reported as 89 of 90, not 100%. POST_FAST fails the T gate in every class regardless.
4. **Chunk-first order artifact.** In AB round 0 the control arm always runs the chunk's first trial, which is cold (P1 fill COMP_OFF 137 ms against 55 ms). AB/BA interleaving does not balance this, because each candidate has one chunk. PREP_FAST's fill DELETED rests on this one pair. The post-hoc sensitivity without round 0 is reported for every cell, and no cell passes. The verdict column keeps the pre-registered computation.
5. **Analysis code timing and changes after the data.** analyze_b07.py was written before Phase A ran but was first committed with the results; the PREREG fixes the rules it applies. After Phase B it gained:
   - the per-candidate equivalence criterion exactly as PREREG words it (PREP_FAST: requests and responses; POST_FAST: plus structure);
   - the N4a `effect: refused` evidence from response frames, and N2 as the gate chunk;
   - the round-0 sensitivity and the x_pooled E2 view.

   No gate threshold, selection rule or verdict rule changed.
6. **FIXTURE controls ran once before the PREREG commit** (harness debugging; no Driver, no timing). The counted run is raw/controls/controls.json, made after the PREREG.
7. **Binary label.** B7 was built at packet commit 231f6e8bb (label b07-231f6e8bb). Its rust tree 20c9f051248a is identical to the knob commit ac319cbe9's. PREREG.json had named the label b07-ac319cbe9.
8. **PREREG wording on the libs tree.** df2b49c32e73 is the libs/cua-driver tree of R's base 0f1955d2f (= upstream main cb685fad7). R' itself (45dff8f32) has libs/cua-driver tree 11ee32235d5e. The B7 source has rust tree 20c9f051248a.
9. **Lock waits.** Overlapping shared holders from other tracks starved the exclusive quiet lock, and chunks queued for 20-60 minutes. Every measured trial still ran inside its own EXCLUSIVE window (raw/locks/quiet-lane-ledger-b07.jsonl). The smoke chunks D-B7 and D-Rp ran under the shared lock; they are not timing runs.
10. **Overhead control, fill.** The CI of the marks-on penalty is wide ([-6.51, 7.85]). The corrected view uses c_m as pre-registered, and the x_pooled view is reported as sensitivity.

## Limits and claim boundary

- One host shared with other tracks, private Xvfb, system Chrome (Google Chrome 151.0.7922.71 and Chromium 151.0.7922.173 both installed, read in session; raw/source/browser-versions.txt), binary B7 only for Part 1
  (R' 922111c5 only for the default-off smoke), scripted chooser, no provider.
- PREP_FAST and ROUTE_FAST are harness-only variants of the jev-use Python client stack (mcp 1.30.0); they
  change no Driver default and no public output. POST_FAST is an env-gated, default-off Driver knob.
- No new service; no product default changed; events are not used as an oracle.
- Shares use B7's own T_runner; nothing is added to or ratioed with B5, R or R' numbers.
- The candidate verdicts rest on 30 pairs per class with T_oracle on a 2 ms oracle grid. A 0.5 ms effect is near the resolution of this design, and the fill result shows how one cold pair can carry the gate.

## Files

- **Pre-registration:** PREREG.json, PREREG-AMENDMENT-1.json.
- **Results:** b07-summary.json (recomputed from raw/ by analyze_b07.py), headline-numbers.json,
  provenance.json, RESULT.json (lane record).
- **Verifier:** verify_artifacts.py (`python3 verify_artifacts.py`, standard library, under the lane's
  hostless wrapper; set CUA_PRIVACY_NAMES_FILE to an untracked names file). It recomputes the summary,
  checks every headline number and every rendered table row against this README, the selection rule, the
  smoke, N4a, equivalence, controls, E4, lock receipts and the PREREG/amendment order, fails on any cited
  file that is missing, untracked or git-ignored (plus the PKT-01 verify_helper.py), and privacy-scans every
  commit after R' (hex and base64 literals decoded).
- **Harness:** harness/b07_stdio.py, harness/b07_browser.py, harness/b07_equivalence.py,
  harness/b07_controls.py, harness/neg_server.py, harness/run_chunk.sh, harness/in_session.sh,
  harness/unit.sh, harness/package_raw.py; byte-identical copies under harness/r2-10r/ (c183b95e3),
  harness/b05/ (a91a86a4a) and harness/b04/ (8620ebfa2).
- **Raw:** raw/browser/ (D-B7, D-Rp, A1, O1, P1, Q1, N1), raw/equivalence/, raw/controls/controls.json,
  raw/unit/ (steps.txt and one log per suite), raw/locks/, raw/source/ (range-diff and lane commits),
  raw/run-plans/run-plans.json.
