# B-05: browser MCP transport in/out, resolution and admission residual (attempt 2, 2026-10-03)

Lane B-05, wave 4 of the CUA RFC loop. Owners: kvnloo/cua#93 (experiment specs), kvnloo/cua#10
(whole-task accounting), kvnloo/cua#73 (E2). Upstream items are named as plain text (trycua/cua PR 4316).

**Disposition: REVISE.** The scripted COMP transport, admission and resolution components of R2-10
are split into 27 sub-spans and judged as 24 verdict rows (some floor keys group two sub-spans). Every row now has a verdict except four that no pre-registered menu
item addresses (request-side session prep, Driver post-dispatch work, response routing, and the toggle
inner admission). Both Phase B candidates delete real work but fail the 0.5 ms gate, so they are KILLed:
caller parse and caller validation are IRREDUCIBLE by the "every tested candidate failed" rule. Most of
R2-10's "MCP transport" and "admission residual" time was the phase-trace instrumentation itself.
**E2 (< 5% untested) is borderline and not established for any class.** The lane's primary view
(per-mark correction at c_m, both lane verdict rules on) gives 4.3% / 4.1% / 7.5%, but that view is
the most favourable one: scaling the correction to the measured instrumentation penalty, dropping
either lane rule, or both, puts every class at or above 5% (see "E2 sensitivity" below). Modal passes
only at low load (O1 rows, 3.9%).

## Headline

One binary B5 (R + marks + default-off knobs, sha256 `f4149bdd...`) in every arm. One host, private
Xvfb, scripted chooser, R2-10 COMP configuration. Timing ran only in EXCLUSIVE `quiet-timed` chunks
that also held the cargo lock (receipts: raw/locks/quiet-lane-ledger-b05a2.jsonl).

- **Phase A (attribution, BENCHMARK+REAL):** 96 of 96 COMP trials (32 per class) were verified and valid.
  Per-mark trace cost c_m = 34.5 us (median of 1536 in-situ null intervals).
  - Coverage of T_runner by the B-05 sub-spans was 1.000 on every trial (R2-10's own coverage: min 0.986).
  - The B-05 sub-spans add up exactly to R2-10's component values (max deviation 0.0 ms).
- **What the instrumentation costs (overhead control, 20 AB/BA pairs per class):** marks on make
  T_runner longer by:
  - fill: 6.11 ms [0.78, 10.39];
  - toggle: 6.57 ms [4.86, 8.42];
  - modal: 4.40 ms [2.42, 6.53].

  That is above the 0.5 ms threshold, so the overhead is reported and subtracted (corrected view).
- **Corrected transport in/out per task** (R2-10 measured 4.7-5.2 ms with marks on):
  - fill: 4.51 ms (raw 8.09);
  - toggle: 3.95 ms (raw 7.53);
  - modal: 6.75 ms (raw 10.33; one trial with an 86 ms caller stall).

  The admission residual drops from 1.73-1.87 ms raw to 0.21-0.36 ms corrected. Resolution drops from
  1.73-3.35 to 1.24-2.76 ms.
- **Phase B (causal A/B, 30 AB/BA pairs per class per candidate):** per-task caller-side saving
  (COMP_OFF − candidate), 95% CI:

  | candidate | fill | toggle | modal |
  |---|---|---|---|
  | PARSE_FAST | [0.11, 0.34] | [0.01, 0.25] | [0.08, 0.34] |
  | VALIDATE_FAST | [-0.04, 0.36] | [0.02, 0.24] | [0.04, 0.31] |

  - Equivalence was 100% (per Phase B chunk, 1980 of 1980 responses decoded identically, and 990 of 990 validations
    gave the identical verdict and error text).
  - N4a passed 15 of 15 per arm, and the negative controls rejected everything they should.
  - Both candidates deleted work, but every mean is below the 0.5 ms gate, so the verdict is KILL.
- **E2 recomputed on B5 with the R2-10 COMP component mapping** (untested share of mean corrected
  T_runner, BELOW_GATE counted as IRREDUCIBLE):

  | | fill | toggle | modal |
  |---|---|---|---|
  | BELOW_GATE counted as IRREDUCIBLE | 4.3% | 4.1% | 7.5% |
  | BELOW_GATE counted as UNTESTED | 6.0% | 6.1% | 9.7% |

  The raw (marks-on) view gives 5.9 / 7.2 / 9.0% and 10.9 / 12.4 / 15.6%. Target: < 5%. These
  numbers are not robust; the full sensitivity grid is in "E2 sensitivity" below, and E2 is reported
  as **borderline / not established** for all three classes.
- **Provider:** 0 attempts, 0 reached. TypeSafe was not used (lane cap 0).

## Forced path, route/producer, oracle

- **Forced path:** R2-10 COMP. Clicks take the `dom_event` route through the Driver CDP engine
  (receipt route `dom`, and with marks on, `click.cdp_send` inside every click call). Typing uses
  `browser_type` (receipt route `trusted_input`).
  - The arm configuration is checked per row by R2-10's own `browser_row`: feedback off, settle 0 on
    fill, 10 ms poll, admission tools-list cache on every admitted call, compiled validators, and
    decision routes (provider for scripted, compiled or guarded on fill).
  - Marks-off rows (COMP_OFF and the Phase B arms) cannot show trace marks. They are checked on the
    caller-visible part instead: receipt route and input_route, and the Driver environment
    (admission cache = 1, settle = 0 on fill, no trace file, no other `CUA_DRIVER_EXP_*`).
  - 0 rows were invalid in any phase.
- **Actual route/producer:**
  - fill: `browser_type:trusted_input` then `browser_click:dom`;
  - toggle and modal: two `browser_click:dom`.

  The decision producer is the scripted chooser, plus compiled replay on fill after one training
  invocation per (layer, arm). Each training invocation is counted in its class.
- **Independent oracle:** the jev-use fixture server state, with a CLOCK_MONOTONIC journal, re-read
  every 2 ms by a harness thread. Fill requires `submitted == token`, toggle requires `checked`, and
  modal requires `opened` and `modal`. Every measured trial in every phase was verified with exactly
  one completion mutation.

## Method

- **Phase A:** 32 rounds, rotated class order (raw/browser/A1.tar.gz). Every in-T call is split at
  every Driver mark and caller stamp by harness/b05_spans.py. Caller stamps are CLOCK_MONOTONIC, the
  same clock as the Driver.
  - Each interval is labelled by its left point. It keeps the R2-10 component of the latest mark
    R2-10 knows, so R2-10's own code computes the component view on the same trial with the B5-only
    marks removed.
  - **Correction:** each mark's write cost lands in the interval it starts, so corrected = raw −
    (marks starting intervals of that sub-span) × c_m.
- **Floor (FIXTURE):** harness/floor/floor_echo.rs is a std-only Rust server. It replays each Phase A
  trial's recorded response frames byte for byte, with one write(2) per response
  (raw/floor/floor-F1-A1.jsonl.gz, raw/floor/floor-F0-A1.jsonl.gz). 1248 of 1248 request lines were
  byte-matched in each replay.
  - **F1:** the same caller stack and pipes (mcp 1.30 stdio client + ClientSession + R2-10 compiled
    validators + jev-use Driver wrapper).
  - **F0:** a minimal synchronous client (os.write, os.read to newline, json.loads).
  - The irreducible floor is F0 (PREREG floors.interpretation). F1 is reported alongside.
- **Overhead control:** COMP_OFF vs COMP (raw/browser/O1.tar.gz).
- **Phase B:** PREREG-AMENDMENT-1.json was committed before any Phase B trial. Arms are COMP_OFF vs
  candidate, each with a fresh Driver, Chrome, fixture and token per trial (raw/browser/B1.tar.gz,
  raw/browser/B2.tar.gz). N4a ran 5 per class in each candidate arm.
  - The primary metric is the per-task caller-side transport time: the sum over in-T calls of
    (call_send → c.req_written) + (c.first_byte → call_return).
- **Statistics:** seeded bootstrap (seed 20261003, 10000 resamples). Paired rounds are used for A/B
  comparisons. Every trial is kept.

## Results: sub-spans (Phase A, corrected per-task ms; excess over F0 with 95% CI)

The sub-span names are defined in PREREG.json under `subspans`. "UNTESTED" here means that no menu
candidate exists.

| sub-span (floor key) | fill corr / F0 / F1 / excess [CI] | toggle | modal | verdict (fill / toggle / modal) |
|---|---|---|---|---|
| adm.inner | 0.21 / 0.00 / 0.00 / 0.21 [0.14, 0.34] | 0.30 / 0.00 / 0.00 / 0.30 [0.17, 0.50] | 0.19 / 0.00 / 0.00 / 0.19 [0.16, 0.23] | BELOW_GATE / UNTESTED / BELOW_GATE |
| adm.outer | 0.03 / 0.00 / 0.00 / 0.03 [0.01, 0.05] | 0.05 / 0.00 / 0.00 / 0.05 [0.03, 0.08] | 0.02 / 0.00 / 0.00 / 0.02 [0.00, 0.05] | BELOW_GATE |
| c_in.prep | 0.83 / 0.00 / 0.33 / 0.83 [0.79, 0.87] | 0.91 / 0.00 / 0.33 / 0.91 [0.84, 0.99] | 3.58 / 0.00 / 0.33 / 3.58 [0.87, 8.94] | UNTESTED |
| c_in.serialize | 0.09 / 0.02 / 0.04 / 0.07 [0.07, 0.08] | 0.09 / 0.02 / 0.04 / 0.07 [0.07, 0.08] | 0.09 / 0.02 / 0.04 / 0.07 [0.07, 0.08] | BELOW_GATE |
| c_out.parse | 0.78 / 0.07 / 0.40 / 0.71 [0.67, 0.76] | 0.56 / 0.05 / 0.26 / 0.51 [0.48, 0.55] | 0.57 / 0.05 / 0.25 / 0.52 [0.48, 0.56] | IRREDUCIBLE (candidate failed) |
| c_out.result_model | 0.18 / 0.00 / 0.06 / 0.18 [0.17, 0.19] | 0.16 / 0.00 / 0.06 / 0.16 [0.15, 0.18] | 0.17 / 0.00 / 0.06 / 0.17 [0.17, 0.18] | BELOW_GATE |
| c_out.return | 0.11 / 0.00 / 0.04 / 0.11 [0.11, 0.12] | 0.10 / 0.00 / 0.04 / 0.10 [0.10, 0.11] | 0.11 / 0.00 / 0.04 / 0.11 [0.10, 0.11] | BELOW_GATE |
| c_out.route | 0.56 / 0.00 / 0.18 / 0.56 [0.53, 0.59] | 0.50 / 0.00 / 0.17 / 0.50 [0.47, 0.53] | 0.54 / 0.00 / 0.17 / 0.54 [0.51, 0.57] | UNTESTED |
| c_out.validate | 0.51 / 0.00 / 0.26 / 0.51 [0.47, 0.55] | 0.46 / 0.00 / 0.28 / 0.46 [0.43, 0.49] | 0.48 / 0.00 / 0.28 / 0.48 [0.45, 0.51] | IRREDUCIBLE (candidate failed) |
| d_in.invoke | 0.12 / 0.00 / 0.00 / 0.12 [0.10, 0.15] | 0.17 / 0.00 / 0.00 / 0.17 [0.14, 0.21] | 0.16 / 0.00 / 0.00 / 0.16 [0.13, 0.19] | BELOW_GATE |
| d_in.parse | 0.04 / 0.00 / 0.00 / 0.04 [0.02, 0.06] | 0.05 / 0.00 / 0.00 / 0.05 [0.03, 0.08] | 0.03 / 0.00 / 0.00 / 0.03 [0.01, 0.05] | BELOW_GATE |
| d_out.post | 1.18 / 0.00 / 0.00 / 1.18 [1.07, 1.30] | 0.85 / 0.00 / 0.00 / 0.85 [0.73, 1.00] | 0.92 / 0.00 / 0.00 / 0.92 [0.82, 1.01] | UNTESTED |
| d_out.serialize | 0.03 / 0.00 / 0.00 / 0.03 [0.02, 0.03] | 0.02 / 0.00 / 0.00 / 0.02 [0.02, 0.03] | 0.03 / 0.00 / 0.00 / 0.03 [0.02, 0.03] | BELOW_GATE |
| d_out.write_flush | 0.21 / 0.00 / 0.01 / 0.21 [0.16, 0.26] | 0.18 / 0.00 / 0.01 / 0.18 [0.15, 0.21] | 0.18 / 0.00 / 0.01 / 0.18 [0.16, 0.20] | BELOW_GATE |
| pipe_out_frame | 0.16 / 0.01 / 0.09 / 0.15 [0.10, 0.19] | 0.07 / 0.02 / 0.09 / 0.05 [0.03, 0.08] | 0.12 / 0.03 / 0.09 / 0.08 [0.02, 0.15] | BELOW_GATE |
| write_pipe_in | 0.23 / 0.01 / 0.18 / 0.21 [0.19, 0.23] | 0.28 / 0.01 / 0.18 / 0.27 [0.21, 0.35] | 0.25 / 0.01 / 0.18 / 0.24 [0.22, 0.26] | BELOW_GATE |

| resolution sub-span | fill corr [CI] | toggle | modal | verdict |
|---|---|---|---|---|
| res.dispatch | 0.23 [0.21, 0.25] | 0.18 [0.17, 0.20] | 0.20 [0.17, 0.22] | BELOW_GATE |
| res.ref_parse | 0.00 [0.00, 0.01] | 0.00 [0.00, 0.01] | 0.01 [0.00, 0.01] | BELOW_GATE |
| res.store_lookup | 0.04 [0.03, 0.04] | 0.02 [0.02, 0.03] | 0.03 [0.02, 0.03] | BELOW_GATE |
| res.frame_proof | 0.45 [0.43, 0.48] | 0.48 [0.44, 0.55] | 0.58 [0.48, 0.72] | IRREDUCIBLE (invariant: one Page.getFrameTree re-proving frame identity) |
| res.type_focus | 0.55 [0.50, 0.62] | absent | absent | IRREDUCIBLE (invariant: one DOM.focus) |
| res.cdp_node_resolve | 1.03 [0.92, 1.17] | 0.56 [0.49, 0.67] | 0.43 [0.40, 0.48] | IRREDUCIBLE (invariant: one DOM.resolveNode per action, FIX-01 liveness) |
| res.editable_check | 0.45 [0.39, 0.52] | absent | absent | IRREDUCIBLE (invariant: one Runtime.callFunctionOn) |
| res.post_check | 0.01 [0.00, 0.01] | absent | absent | BELOW_GATE |

Per-call means by tool are in `phase_A.by_class.<cls>.per_call` in b05-summary.json. The hypothesis
had three parts:

- **(i) Stdio floor:** F0 per task is 0.01-0.07 ms per pipe/frame/parse key. It is negligible next to
  everything above it.
- **(ii) Payload-size Driver cost:** this part does not appear. Frames in T are 0.2-1.8 KB.
  d_out.serialize is 0.02-0.03 ms and d_out.write_flush is 0.18-0.21 ms per task, both BELOW_GATE.
- **(iii) Caller-side Python client cost:** this is the bulk of the corrected transport (prep, parse,
  route, result model, validate, return). The client-stack floor F1 already contains about one third
  of it.

The single-write knob, compact serialization, duplicated-text removal and the snapshot-store cache
were not run. Their target sub-spans are below the gate (PREREG-AMENDMENT-1.json `not_selected`).

## Work deleted vs wall-clock saved

| item | work deleted (per task, paired mean [CI]) | wall-clock saved (T_runner paired mean [CI]) | class |
|---|---|---|---|
| PARSE_FAST, c_out.parse | 0.26 [0.23, 0.29] fill, 0.16 [0.13, 0.19] toggle, 0.18 [0.15, 0.21] modal | 1.61 [-0.81, 5.26], 0.14 [-1.41, 1.69], 1.07 [-0.08, 2.28]: not distinguishable from 0 | BENCHMARK+REAL |
| VALIDATE_FAST, c_out.validate | 0.15 [0.13, 0.17], 0.12 [0.10, 0.14], 0.13 [0.12, 0.15] | -0.73 [-4.15, 3.44], 0.33 [-1.51, 2.36], -0.22 [-2.10, 1.62]: not distinguishable from 0 | BENCHMARK+REAL |
| phase-trace marks (measurement only, default off) | about 238-247 marks × 34.5 us per task when on | 4.40-6.57 ms (overhead control); not a product saving, because product default never writes marks | BENCHMARK+REAL |

## Controls

| control | n | result | class |
|---|---|---|---|
| Default-off smoke, tools/list | 3 reads each from B5, R and the attempt-1 binary | byte-identical (195113 bytes, sha256 `ca6594c5...`, same as R2-10) (raw/smoke/toolslist-B5.json, raw/smoke/toolslist-R.json, raw/smoke/toolslist-A1.json) | REAL |
| Default-off smoke, fill/toggle/modal (R2-10 smoke plan, BASE, no `CUA_DRIVER_EXP_*`, no trace) | 5 per class, per binary (B5 and R) | 15 of 15 and 15 of 15 verified; identical receipt shapes per class; no trace-like file (raw/browser/D-B5.tar.gz, raw/browser/D-R.tar.gz) | REAL |
| N4a, node replaced between bind and dispatch | 5 per class per candidate arm | 15 of 15 PARSE_FAST and 15 of 15 VALIDATE_FAST: refused `browser_ref_stale`, one rebind, verified | REAL |
| Equivalence, parser | 1980 tools/call responses per chunk (B1 and B2, both arms) | 0 mismatches against the library parser (raw/equivalence/equivalence-B1.json, raw/equivalence/equivalence-B2.json) | FIXTURE |
| Equivalence, validator | 990 structured results per chunk | 0 mismatches in accept/reject or error text | FIXTURE |
| Negative, malformed frames through the client stack | 10 frames × {default, fast} parser | 20 of 20 rejected (raw/negative/parser-neg-control.json) | FIXTURE |
| Negative, schema-invalid results | 80 mutations per chunk; 56 rejected by the library | the fast validator gives the library's verdict and text on 80 of 80 | FIXTURE |
| Unit, touched crates on the lane tree | core browser:: 193, phase_trace 6, cua-driver proxy:: 22 (incl. B-05 knob tests), platform-linux focus_guard 14 | all pass (raw/unit/steps.txt) | UNIT |
| E4 | every measured trial in every phase | 0 stale-ref dispatches, 0 duplicate mutations, 0 unverified successes, 0 refusals returned as success, 0 blind replays | REAL |

## E2: recomputed share and what remains untested

Components outside the lane keep R2-10's verdicts. Lane components use the sub-span verdicts above.
The untested items are listed in `e2.<cls>` of b05-summary.json. The corrected untested items for
toggle are:

- c_in.prep 0.91 ms;
- d_out.post 0.63 + 0.22 ms (the second part in R2-10's "unattributed");
- c_out.route 0.50 ms;
- adm.inner 0.30 ms;
- runner 0.31 ms.

Fill adds R2-10's input_prep, 1.36 ms. In modal, one trial (A1-058) carries an 86 ms caller stall in
c_in.prep. It is kept: modal's untested share is 7.5%, and the c_in.prep median is 0.86 ms.

No pre-registered menu item addresses any of these four:

- request-side session prep (pydantic request model + memory-stream hop);
- Driver SDK post-dispatch normalisation and conformance;
- response routing hops;
- admission inner bookkeeping.

They are named for a wave-5 follow-up. The caller parse and validate rows are IRREDUCIBLE only in the
spec's "every tested candidate failed" sense: Phase B shows 0.12-0.26 ms per task of deletable work
with 100% equivalence, and their F0 excess of 0.51-0.71 ms means even full deletion could barely clear
the 0.5 ms gate for toggle and modal. For wave 5 read them as **reducible, below gate**.

### E2 sensitivity (added after verification; documentation only)

`e2_sensitivity` in b05-summary.json recomputes the untested share with analyze_b05's own code under
three per-mark correction scales, the four combinations of the two lane verdict rules, and two load
levels. Verdicts and gates are unchanged; they still use the lane c_m.

- **Correction scale.** The predicted instrumentation cost (marks × c_m) is 8.51 / 8.20 / 8.20 ms,
  but the overhead control measured 6.11 / 6.57 / 4.40 ms, i.e. 0.718 / 0.801 / 0.536 of the
  prediction. "x_pooled" scales c_m by the pooled ratio 0.685 (c_m 23.6 us) and "x_min" by 0.536
  (c_m 18.5 us). At both scales adm.inner flips from BELOW_GATE to UNTESTED for fill and modal.
- **Lane rules.** "lane" = both lane rules on (BELOW_GATE and IRREDUCIBLE (invariant) count as not
  untested). "no BG" counts BELOW_GATE as untested; "no inv" counts the four single-CDP-request
  resolution rows as untested; "neither" drops both.
- **Load.** Phase A ran at mean loadavg 13.8. The overhead control's COMP rows (O1, same binary and
  arm, loadavg 4.3) have corrected T_runner 70.9 / 47.0 / 46.4 ms against Phase A's 98.9 / 71.1 /
  71.9 ms, so load inflated the whole task by 40-55%, not only reval_endpoint. A larger denominator
  lowers every share; it does not raise it.

Untested share, fill / toggle / modal (target < 5%):

| rows | rules | c_m x1 (lane) | x_pooled | x_min |
|---|---|---|---|---|
| Phase A (load 13.8) | lane | 4.3 / 4.1 / 7.5% | 5.4 / 5.2 / 8.6% | 5.7 / 5.6 / 9.1% |
| Phase A | no BG | 6.0 / 6.1 / 9.7% | 7.6 / 8.2 / 11.7% | 8.4 / 9.2 / 12.6% |
| Phase A | no inv | 6.8 / 5.6 / 8.9% | 7.9 / 6.6 / 10.1% | 8.2 / 7.1 / 10.5% |
| Phase A | neither | 8.6 / 7.5 / 11.1% | 10.2 / 9.7 / 13.1% | 10.9 / 10.7 / 14.0% |
| O1 COMP (load 4.3) | lane | 4.4 / 4.1 / 3.9% | 5.7 / 5.7 / 5.5% | 6.2 / 6.4 / 6.3% |
| O1 COMP | no BG | 5.9 / 5.7 / 5.5% | 8.1 / 8.9 / 8.7% | 9.2 / 10.3 / 10.1% |
| O1 COMP | no inv | 6.9 / 5.9 / 5.3% | 8.1 / 7.5 / 7.0% | 8.6 / 8.2 / 7.8% |
| O1 COMP | neither | 8.4 / 7.6 / 6.9% | 10.6 / 10.8 / 10.2% | 11.6 / 12.2 / 11.6% |

Only the lane view at the lane c_m is below 5%, for fill and toggle at both loads and for modal at low
load. Every other cell is at or above 5%. **E2 is therefore borderline and not established for any
class.** The two lane rules are pre-registered in PREREG.json but are not spec gates, and the per-mark
correction over-subtracts by 20-46%, so the lane view is the most favourable reading.

## Provenance

- **Driver source:** b376f1ff3867d92f9ec1b7fb1428d642eff05c67, the attempt-1 head, unchanged; rust
  tree d58bf362e461.
  - It is R2-10's R (8f3a646b4) plus 4c786178b (the N-02 cherry-pick) plus 3116b6981 (B-05 marks)
    plus b376f1ff3 (single-write knob, default off, not used).
  - Range-diff of 4c786178b against 194a6342e: focus_guard.rs identical; proxy.rs differs only in
    context (raw/source/range-diff-4c786178b-vs-194a6342e.txt).
  - Every spec mark already existed, so no mark commit was added.
  - Privacy scan of all 12 inherited commits: 0 hits.
- **Packet commits:** PREREG 03f52d7eb (2026-10-03T03:29:02Z); PREREG-AMENDMENT-1 59034f533
  (04:00:50Z); results dd8c11746; post-verification fixes = the commit that adds deviation 10. The
  first three were rewritten from 3cced771f / 92cab8900 / d1b42db63 with original dates kept
  (deviation 10). Publication SHA: set by the Publish agent.
- **Binary B5:** label b05-a2-b376f1ff3, sha256 f4149bddffab0a4b02d6c529be3dc01e7b4a1c364f2270db0b57caf283732ae1,
  `cua-driver 0.32.0` (read inside a private session).
  - The attempt-1 binary (e4c5f43d..., same source and build command) has the same crate metadata
    hashes and no embedded worktree paths, but different bytes (compiler-generated symbol names).
    Its tools/list output is identical, and it was never used for timing.
  - R: 12b9045a... (smoke reference only).
  - Floor server sha256: 86071c3c... (provenance.json).
- **Environment:**
  - One Linux host shared with other tracks, running hostless with a private Xvfb, telemetry off and
    the provider key never forwarded.
  - 1-minute loadavg means: Phase A 13.8, overhead 4.3, Phase B 3.5 / 3.1.
  - Chunks held the cargo lock and then the EXCLUSIVE quiet lock for 2.3, 2.2 and 6.8 minutes.
- **Live heads:**
  - Start, 02:40Z: trycua/cua main 41c34cb0d (the planning SHA, 0 ahead); trycua/cua PR 4316
    a0bca7440, open.
  - End, 05:27Z: main 67c2f39af (1 ahead, 0 files under libs/cua-driver); PR 4316 a0bca7440, open,
    unchanged.
  - After the post-verification fixes, 06:14Z: main 66e0b6652 (3 ahead of the planning SHA, 0 files
    under libs/cua-driver); PR 4316 a0bca7440, open, unchanged.
  - The tested source is not upstream main: R is 989cc76ce plus the R2-10 steps.

## Deviations and disclosures

1. **Attempt 1 aborted:** branch exp/b-05-browser-mcp-transport-20261003, not modified. It ran one
   SHARED shakedown (b05-shake1) and no counted trial. Its harness was copied after review, and its
   shakedown files were inspected while planning (PREREG `attempt_1_disclosure`).
2. **Attempt-2 shakedowns:** b05a2-shake1 to shake5 and the smoke ran under the SHARED lock and are
   not analysed. In b05a2-shake2 the private Xvfb died at session start: 12 trials with
   browser_prepare refused, kept as a failed session block and re-run as shake3. b05a2-neg1 (the
   parser negative control) completed 20 of 20, but the session exited rc 1 when xvfb-run cleaned up.
3. **Floor interpretation:** the PREREG uses F0, not F1, as the irreducible floor for caller-side
   sub-spans. This is the stricter reading, and F1 values are reported.
4. **Lane rules for verdicts not in the spec:** two pre-registered rules are added. IRREDUCIBLE
   (invariant) covers single required CDP requests. BELOW_GATE covers a CI upper bound under 0.5 ms,
   and E2 is reported both ways.
5. **Instrumentation correction over-subtracts (corrected after verification):** the measured
   marks-on penalty is 6.11 / 6.57 / 4.40 ms, while the predicted marks × c_m is 8.51 / 8.20 / 8.20 ms,
   so the measured penalty is only 54-80% of the prediction. In un-instrumented runs the caller side
   is 0.11-0.26 ms slower per task, which is consistent with idle-state or frequency effects.
   Corrected values therefore under-state marks-off time, and not slightly: with c_m scaled to the
   measured penalty, the E2 shares rise by 1.1-2.4 points and adm.inner flips to UNTESTED for fill
   and modal (E2 sensitivity). The raw view is reported beside every corrected share.
6. **Near misses (no effect):** three commands ran directly in the host shell instead of under
   hostless. They were an empty `python3` heredoc, `rustc --version`, and `python3 -c 1`. None
   touched a display, a session bus or the network. During the post-verification fixes a fourth
   one ran: a stray `python3 -c 1` no-op appended to a README text edit in the host shell.
7. **PREREG order_of_work not followed exactly:** shakedowns 1-4 (02:59-03:27Z) ran before the PREREG
   commit (03:29Z), and the PREREG text already reports their outcomes. The overhead control O1 was
   queued at 03:58Z but acquired the quiet lock only at 04:22:59Z, after the PREREG-AMENDMENT-1
   commit (04:00:50Z), although order_of_work puts it before the amendment. No measured trial
   preceded the PREREG, and the amendment used no O1 data, so the candidate selection is unaffected.
8. **PREREG-AMENDMENT-1 erratum (file not edited):** `not_selected.others` says every other lane
   sub-span is below 0.5 ms per task. That is false for resolution rows: res.cdp_node_resolve is
   1.03 ms [0.92, 1.17] for fill (at least 1.0 ms above its zero floor, so a mandated row with no
   menu item), and res.cdp_node_resolve toggle 0.56, res.type_focus 0.55 and res.frame_proof modal
   0.58 ms are above 0.5 ms. The outcome does not change, because the PREREG's IRREDUCIBLE
   (invariant) rule already covered these rows, but the amendment should have listed them.
9. **Verdict precedence:** rows whose CI touches their zero floor (adm.outer modal [0.00, 0.05],
   res.ref_parse [0.00, 0.01]) meet the spec's IRREDUCIBLE rule ("CI overlaps the floor") but are
   labelled BELOW_GATE. The magnitude is negligible (≤ 0.03 ms per task).
10. **Post-verification fixes (no new trial, no data change):**
    - verify_artifacts.py imported the cited harness and wrote `__pycache__` into harness/r2-10/,
      which then failed its own ignored-file check from a clean clone (29/30). It now disables
      bytecode writing before the import and skips `__pycache__` in that check.
    - The verifier stored the private-name list hex-encoded, which still committed the host name in
      all three lane commits. The names now come from an untracked file at verify time
      (CUA_PRIVACY_NAMES_FILE) plus the verifying host's name. The three unpublished lane commits were
      rewritten with only that file changed, keeping messages, identities and author/committer dates:
      PREREG 3cced771f → 03f52d7eb, amendment 92cab8900 → 59034f533, results d1b42db63 → dd8c11746.
      Nothing had been pushed.
    - raw/run-plans/run-plans.json adds the executed chunk plans (paths scrubbed) with the Driver
      sha256 per step: B5 f4149bdd... in every A1, O1 and B step.
    - The E2 sensitivity section and `e2_sensitivity` in the summary were added; disposition and
      wording now call E2 borderline / not established.

## Limits and claim boundary

- One host under heavy shared load, private Xvfb, scripted chooser only, and binary B5 (R + marks +
  default-off knobs) in every arm.
- Nothing is ratioed against R2-10's binary or numbers. The shares use a different denominator
  (Phase A T_runner was inflated 40-55% by host load; see E2 sensitivity).
- The caller-side candidates are harness-only variants of the jev-use Python client. They change no
  Driver default and no public output.
- These verdicts reach the wave-5 composition only by cherry-picking onto R'. Neither KILLed variant
  is worth carrying.
- No new service, and no product default changed.

## Files

- **Pre-registration:** PREREG.json, PREREG-AMENDMENT-1.json.
- **Results:** b05-summary.json (recomputed from raw/ by analyze_b05.py), headline-numbers.json,
  provenance.json.
- **Verifier:** verify_artifacts.py (`python3 verify_artifacts.py`, standard library, about 3 minutes;
  run it under the lane's hostless wrapper). It recomputes the summary, checks every headline against
  this README, fails on any cited file that is missing, untracked or git-ignored, and privacy-scans
  every commit of the branch. Private names are never stored in the repository: set
  CUA_PRIVACY_NAMES_FILE to an untracked file with one name per line; without it the name sub-check
  covers the verifying host's name and the generic home/mount path patterns only, and says so.
- **Harness:**
  - the R2-10 harness subset (harness/r2-10/: the 17 of the 40 harness files at 030f6bdbf that this
    packet uses, each byte-identical);
  - caller stamps: harness/b05_stdio.py;
  - plans: harness/b05_browser.py;
  - sub-spans: harness/b05_spans.py;
  - floor: harness/b05_floor.py and harness/floor/floor_echo.rs;
  - variants: harness/b05_variants.py;
  - equivalence: harness/b05_equivalence.py;
  - session and lock wrappers: harness/run_chunk.sh and harness/in_session.sh.
- **Raw:** raw/browser/ (A1, O1 without frames, B1, B2, D-B5, D-R), raw/floor/, raw/equivalence/,
  raw/negative/, raw/smoke/, raw/unit/, raw/locks/, raw/source/, and raw/run-plans/run-plans.json
  (executed chunk plans with the Driver sha256 per step).
