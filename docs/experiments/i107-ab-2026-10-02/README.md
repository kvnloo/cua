# i107 lane AB: arm A and B_proj (B BLOCKED), 2026-10-02

kvnloo/cua#107, execution-sequence step "Establish A and B". Inherits the frozen map pre-registration (`../i107-map-2026-10-02/PREREG.json`, sha256 `8eeb837f…2c53`). The lane's own `PREREG.json` was committed in `ffefa30c2` at 2026-10-02T05:10:40Z, before any REAL trial. Paths are written as `<lanes>` / `<tmp>`; upstream items are plain text.

status: RAN
trials attempted: 289
trials measured: 285 (4 shakedown trials are kept in raw/ and flagged `excluded`; 20 of the 289 are the fix-round `controls3` block, a disclosed extension, see "Dependency controls")

**Load caveat for every absolute number.** Every measured timing trial ran at 1-minute loadavg 16-22 on 10 cores (see Limits). Absolute times (for example A's median T_oracle of 246 ms, ~245 ms of whole-page composition per 500-node snapshot, 7.1 ms of client parse) are inflated by an unknown amount. The claims are the paired, interleaved deltas and the structural results (CDP call sets, node counts, candidate equivalence, control outcomes), which do not depend on load.

Driver: `cua-driver-i107-092b065d5` (sha256 `f3a5c01a…7aed`) for every A and B_proj trial; `cua-driver-r2-main-229b65b28` only for CMP-distortion. Browser: Google Chrome 151.0.7922.71, `isolated_new`. Chooser: `choose_mock_for_task` (scripted, 0 provider HTTP). Feedback OFF (`set_agent_cursor_enabled false` before `browser_prepare`) and no guard in every arm. Focus settle at its default.

Machine-checked headlines (`verify_artifacts.py` check 2; deltas are B_proj − A paired medians per task):

```
W-quiet: 30 pairs, acquisition equal = True
W-quiet: semantic equivalence 30/30
W-quiet: response bytes B_proj - A median -2735.0
W-quiet: T_oracle B_proj - A median -0.658 ms
W-churn: 30 pairs, acquisition equal = True
W-churn: semantic equivalence 30/30
W-churn: response bytes B_proj - A median -94324.5
W-churn: T_oracle B_proj - A median -23.506 ms
W-static: 30 pairs, acquisition equal = True
W-static: semantic equivalence 30/30
W-static: response bytes B_proj - A median -94237.0
W-static: T_oracle B_proj - A median -9.05 ms
```

## Verdict

| Question | Result | Evidence |
|---|---|---|
| Can B (producer-side scoped fresh read) be expressed through the existing contract? | **No: B stays BLOCKED.** A `query` read acquires exactly what a full read acquires (REAL). A `scope_ref` read does the same in SOURCE and on the UNIT mock; `scope_ref` was not exercised REAL. | `query`: SOURCE (map §4) + UNIT (mock CDP: identical 16 CDP calls with identical params) + REAL (below). `scope_ref`: SOURCE + UNIT only (identical 15 calls on the mock, where no node is selected) |
| Acquisition equality A vs B_proj, REAL | Identical CDP method multiset on every one of 90 pairs (W-quiet, W-churn, W-static); identical DOM/layout/AX node counts on all 30 W-quiet pairs; W-churn and W-static nodes and reply bytes equal within noise | REAL |
| A↔B read-cost comparison | **BLOCKED** | — |
| B_proj semantic equivalence (same candidate ids and same logical controls per step) | 30/30 in each condition | REAL |
| B_proj projection/encoding/transport savings | Real but small: −2.7 kB and −0.2 ms client parse per task on W-quiet; −94 kB, −7.1 ms client parse and about −2.4 ms Driver build/serialize per task on W-churn. T_oracle: no meaningful benefit (W-quiet, W-static), inconclusive (W-churn) | REAL/BENCHMARK (scripted chooser) |
| A's #10 decomposition, feedback OFF, no guard | Named coverage 1.0 on every valid A trial (gate > 0.9 met); table below | REAL/BENCHMARK |
| Required-zero counts | stale-ref dispatch with effect 0, duplicate 0, unverified success 0, unauthorized 0. **Wrong-target 10 in A and 10 in B_proj, all from DC03** (the pre-registered competing-Submit control), so neither arm is promotable as-is | REAL |
| Live provider | **BLOCKED** (no TypeSafe request in this lane) | — |

Decision-table row (map PREREG): "B BLOCKED (producer-side scoping not expressible) and B_proj shows equal acquisition" → **BLOCKED for the read-cost question**. B_proj's projection savings are reported separately. Any producer-side scoping is a #73/#74 contract question. B_proj is never a read-cost claim.

## CMP-AB (DIAGNOSTIC, 30 ABBA pairs per condition, no continuation)

Paired delta = B_proj − A, median [95% bootstrap CI, seed 20261002, 10000 resamples]. Per task (2 decision snapshots).

| Metric | W-quiet A → B_proj | Δ | W-churn A → B_proj | Δ | W-static A → B_proj | Δ |
|---|---|---|---|---|---|---|
| T_oracle (ms) | 246.4 → 245.1 | −0.66 [−6.63, 5.32] | 859.3 → 843.2 | −23.5 [−60.7, 19.6] | 883.6 → 905.1 | −9.05 [−37.5, 38.1] |
| verdict (threshold) | no meaningful benefit (12.3 ms) | | inconclusive (43.0 ms) | | no meaningful benefit (44.2 ms) | |
| MCP response bytes | 5805 → 3070 | −2735 | 97394.5 → 3070 | −94324.5 | 97307 → 3070 | −94237 |
| selected nodes / refs | 23 → 6 / 7 → 4 | | 600 → 6 / 4 → 4 | | 600 → 6 / 4 → 4 | |
| client JSON parse (ms) | 0.73 → 0.52 | −0.20 [−0.32, −0.15] | 7.50 → 0.42 | −7.13 [−8.08, −6.32] | 8.92 → 0.40 | −8.53 [−10.29, −6.82] |
| Driver snapshot build + store + tool serialize (ms) | 0.55 → 0.46 | −0.09 [−0.16, −0.03] | 4.35 → 2.37 | −1.94 [−2.16, −1.40] | 5.62 → 2.45 | −2.45 [−3.48, −1.87] |
| Driver MCP serialize (ms) | 0.38 → 0.36 | −0.03 [−0.07, 0.02] | 0.56 → 0.31 | −0.25 [−0.30, −0.19] | 0.61 → 0.32 | −0.25 [−0.29, −0.20] |
| Driver page projection (ms) | 0.18 → 0.18 | 0.00 | 0.97 → 0.88 | −0.06 [−0.17, −0.01] | 1.12 → 0.90 | −0.16 [−0.35, −0.07] |
| caller candidate build (ms) | 0.15 → 0.16 | 0.00 | 0.36 → 0.14 | −0.22 [−0.26, −0.17] | 0.35 → 0.14 | −0.20 [−0.25, −0.18] |
| client output-schema validation (ms) | 0.008 → 0.010 | +0.001 | 0.007 → 0.008 | +0.001 | 0.007 → 0.008 | +0.001 |
| Driver CPU (ms) | 410 → 420 | +15 [−5, 20] | 960 → 960 | −10 [−40, 30] | 935 → 970 | −5 [−40, 30] |
| Driver VmHWM (kB) | 45404 → 45462 | −60 [−212, 114] | 62754 → 62510 | −326 [−444, −54] | 61900 → 61684 | −246 [−646, −38] |
| browser-tree CPU (ms) | 1220 → 1250 | +35 [−5, 65] | 1330 → 1395 | +45 [10, 100] | 1290 → 1395 | +35 [−25, 105] |

Work deleted vs wall-clock saved: B_proj deletes **no producer work** (same CDP calls, same nodes acquired, same whole-page composition). It deletes payload: 2.7 kB per task on the quiet page and 94 kB on the churn page. The only consistently measured wall-clock savings are client parse plus Driver build/serialize, about 9-11 ms per task on the 500-node pages and about 0.3 ms on the quiet page. Wall-clock T_oracle savings are within noise everywhere. `get_browser_state` declares no output schema, so client validation (≈ 0.01 ms) cannot be saved. The ~9-13 ms validations belong to `browser_type`, `browser_click` and `list_windows`. The browser-tree CPU increase in W-churn (+45 ms [10, 100]) is unexplained and is reported as observed.

Acquisition detail (REAL, per matched snapshot step): methods per snapshot are `Target.attachToTarget`, `DOM.getDocument`, `Page.getFrameTree`, `DOMSnapshot.captureSnapshot`, `Page.getLayoutMetrics`, `Accessibility.getFullAXTree`, plus `Target.setAutoAttach` ×2, identical in both arms on all 90 pairs. W-quiet: DOM/layout/AX = 21/15/20-22 nodes per snapshot, reply bytes paired delta 0. W-churn: node and reply-byte deltas are within noise (medians 0 nodes, +105.5 bytes with CI containing 0). **20 of the 30 W-churn pairs** (`pairs_with_diffs` in the summary) differ by ±2 layout or AX nodes, all on snapshot 1. The cause is the churn script, not the arm: after its first insert the script keeps one extra span standing, so a snapshot taken before or after that first insert sees one element (two layout/AX nodes) more or fewer. The lane PREREG's description "net node count unchanged after each tick" is slightly off: the implementation is net +1 element after the first insert and constant from then on.

Investigated difference (W-static, trial `static000-W-static-A-none`, snapshot 1): DOM 299 vs layout 916 nodes **inside one snapshot**. `browser_navigate` had returned 1.5 ms earlier while the parser was still inserting the region: `DOM.getDocument` replied with a partial tree, and `DOM.childNodeInserted`/`childNodeCountUpdated` events streamed before `captureSnapshot` (79 ms later) saw the full layout. The semantic result was nearly normal (712 vs 713 total nodes), so this is not an arm difference. It is a mixed-generation fresh read in the baseline itself, the "no atomic boundary" case of #107 rule 1, and is relevant to C's bootstrap. It is listed under `mixed_generation_snapshots` in the summary.

## Arm A decomposition (#10 spans, feedback OFF, no guard), mean ms per task over [snapshot1 send, first independent oracle observation]

| #10 span | W-quiet (n=30) | W-churn (n=30) | W-static (n=30) |
|---|---|---|---|
| observation acquisition (CDP) | 45.3 | 152.7 | 175.8 |
| projection/encoding/transport (pre-registered mapping) | 29.5 | 532.2 | 558.8 |
|   of which whole-page composition (all `observation_processing` intervals inside the snapshot window, equal across arms; see note) | 1.7 | 489.9 | 512.1 |
|   of which projection proper (page, build/store, MCP serialize/write, transport, client parse, client validation) | 27.8 | 42.3 | 46.7 |
| provider inference (scripted chooser) | 0.015 | 0.014 | 0.016 |
| resolution/validation (incl. endpoint re-proof ≈ 39.7 ms on W-quiet, MCP admission, caller candidate build) | 81.0 | 67.8 | 80.1 |
| dispatch | 7.4 | 7.5 | 8.3 |
| wait (focus settle 101.1 ms, visualization, polls, effect lag) | 108.6 | 106.5 | 106.5 |
| fresh verification (oracle reads + oracle detection lag) | 4.0 | 4.4 | 4.5 |
| residual/unattributed | 0.11 | 0.08 | 0.10 |
| W-quiet: A T_oracle median 246.407 ms, coverage min 1.0 | | | |
| W-churn: A T_oracle median 859.312 ms, coverage min 1.0 | | | |
| W-static: A T_oracle median 883.608 ms, coverage min 1.0 | | | |
| cleanup (outcome → stdio client exit and browser tree gone), outside T | 500.1 | 495.0 | 536.4 |
| cold startup (Driver spawn → navigate returned), outside T | 850.8 | 758.8 | 884.0 |

Note on "whole-page composition": the row sums every `observation_processing` interval inside a snapshot window. That is every Driver interval between `dispatch.enter` and the projection step whose left mark is not a CDP wait: document and layout indexing, AX composition and the end of the OOPIF walk (`b01_analysis.classify_mark`). The AX-composition interval alone (`snap.ax_cdp_done → snap.ax_composed`) has a per-snapshot median of 0.27 ms (A) and 0.26 ms (B_proj) on W-quiet, 240.6 / 241.3 ms on W-churn and 246.9 / 242.0 ms on W-static. The full `observation_processing` sum per snapshot is 0.82 / 0.75, 247.7 / 248.2 and 256.1 / 252.3 ms. So on the 500-node pages AX composition is almost all of it; on the quiet page it is a third. Both were recomputed from the raw traces in this fix round.

Reading: on the quiet page, observation acquisition is ~45 ms of ~276 ms (mean), and the 101 ms focus settle, the endpoint re-proof and MCP admission dominate. None of those is observation work. On the 500-node pages, **whole-page semantic composition inside the Driver (~245 ms per snapshot)** is the largest single cost. It runs before any `query`/`scope_ref` projection, so neither B_proj nor any post-acquisition scoping can remove it; only a result-equal internal optimization (a Driver change, not authorized here) could. The pre-registered mapping files this composition under projection/encoding/transport. The split above is a post-hoc reading, disclosed as such.

## Dependency controls (W-quiet, correctness, REAL, scripted chooser)

Machine-checked control lines (`verify_artifacts.py` check 2):

```
control DC01|A: n 5, verified 5, budget_exhausted 0, other outcomes 0, submits 5, wrong-target 0
control DC01|B_proj: n 5, verified 5, budget_exhausted 0, other outcomes 0, submits 5, wrong-target 0
control DC03|A: n 10, verified 10, budget_exhausted 0, other outcomes 0, submits 10, wrong-target 10
control DC03|B_proj: n 10, verified 10, budget_exhausted 0, other outcomes 0, submits 10, wrong-target 10
control DC04|A: n 10, verified 0, budget_exhausted 10, other outcomes 0, submits 0, wrong-target 0
control DC04|B_proj: n 10, verified 0, budget_exhausted 10, other outcomes 0, submits 0, wrong-target 0
control DC05a|A: n 5, verified 5, budget_exhausted 0, other outcomes 0, submits 5, wrong-target 0
control DC05a|B_proj: n 5, verified 5, budget_exhausted 0, other outcomes 0, submits 5, wrong-target 0
control stale_ref|A: n 10, verified 0, budget_exhausted 0, other outcomes 10, submits 0, wrong-target 0
control stale_ref|B_proj: n 10, verified 0, budget_exhausted 0, other outcomes 10, submits 0, wrong-target 0
```

| Control | A | B_proj | Block |
|---|---|---|---|
| DC01 field value changed by page script (value property, no attribute) after the type step | op applied and self-checked 5/5; the step-2 snapshot showed the field no longer holding the token 5/5; **re-typed** 5/5 (3 steps), verified 5/5, oracle exact | the same, 5/5 | `controls3` (fix round) |
| DC02 unrelated churn throughout | = CMP-AB W-churn: 30/30 verified, no outcome change | 30/30 verified; candidates and controls equal A's in 30/30 pairs | `main2` |
| DC03 competing Submit inserted before the original (after the type step) | 10/10 verified via the **competitor** (wrong-target 10) | 10/10 verified via the **competitor** (wrong-target 10) | `main2` + `controls2` |
| DC04 Submit removed | 10/10 budget_exhausted, 0 submits | 10/10 budget_exhausted, 0 submits | `main2` + `controls2` |
| DC05a benign same-looking re-render (a clone replaces Submit in the same form) before the step-2 snapshot | op applied and self-checked 5/5 (old node disconnected, clone connected); fresh ref used, verified 5/5, oracle exact | the same, 5/5 | `controls3` (fix round) |
| stale ref (navigate, then send the step-2 ref) | 10/10 `effect: refused` (outcome `unknown`), 0 dispatch marks, 0 submits; code `browser_ref_stale` on the 5 controls2 trials | same | `main2` + `controls2` |

DC03 shows the pre-registered first-match behaviour: the candidate builder (`BrowserSemanticSource.find`) takes the first `button "Submit"` ref, in both arms (B_proj's query ranks both buttons equally, then by document order). This is a baseline caller defect (no uniqueness fact), not an arm effect, and it blocks promotion of both arms. The known Driver gap (no `isConnected` check) was not exercised by this lane's controls (DC05b, which exercises it, is lane D's).

DC05a reading: the step-2 Submit ref differed from the step-1 ref in 5/5 DC05a trials, but it also differed in 5/5 DC01 trials, where Submit was not replaced. The Driver mints a new ref string on every snapshot, so "fresh ref != prior ref" does not by itself show the replacement. The replacement is shown by the op's own check (the original node is disconnected and the clone connected, or the op throws and the ack reports failure), which passed in 20/20 `controls3` trials.

### DC01-DC20 coverage for arms A and B_proj

The map PREREG (`be68363bc`, which wins over the lane PREREG under the lane PREREG's own precedence clause) names B_proj for DC01, DC02 and DC05a. **Deviation, disclosed:** the lane PREREG registered only DC03, DC04 and stale_ref, and the first packet (`d02657d04`) neither ran DC01/DC05a for B_proj nor marked them. No other lane runs B_proj (lane CSHADOW's PREREG: "B_proj and D (lane AB/D)" are not its arms; lane D runs A and D). Fix: DC01 and DC05a were run on both arms in block `i107-ab-controls3` (5 ABBA pairs each, harness `5f9e1c1ab`) as a **post-hoc extension, run after the first packet's results were known**. DC02 is the CMP-AB W-churn condition and is now labelled as such. The lane PREREG is unchanged.

| Control | A | B_proj |
|---|---|---|
| DC01 | RAN here (5, verified 5); lane D also ran A | RAN here (5, verified 5) |
| DC02 | RAN here = CMP-AB W-churn (30) | RAN here = CMP-AB W-churn (30) |
| DC03, DC04 | RAN here (10 each) | RAN here (10 each) |
| DC05a | RAN here (5, verified 5); lane D also ran A | RAN here (5, verified 5) |
| DC05b, DC06, DC07, DC10, DC12-DC17, DC20 | lane D, arm A on the same binary `cua-driver-i107-092b065d5` (branch exp/i107-d-20261002, packet `6d1c60926`; cited, not re-verified here) | not assigned by the map PREREG |
| DC08, DC09 | NOT_RUN (map PREREG: no admitted iframe fixture / no authorised tab-creation path) | NOT_RUN (map) |
| DC11 | **no REAL result in any lane.** Not run here: this lane did not register it, and the descent-proven renderer kill is lane CSHADOW's registered procedure (CSHADOW runs A and C_shadow_audit on its own binary). CSHADOW is BLOCKED with 0 REAL trials. Lane D's PREREG points DC11 to "lane CSHADOW/AB". | not assigned |
| DC18 | not assigned (C_shadow_audit only) | not assigned |
| DC19 | per the map PREREG, the check-to-dispatch part is covered by DC01 (here and lane D) plus DC05b and DC07 (lane D); the bootstrap and reconciliation parts are mirror-only (lane CSHADOW, BLOCKED) | not assigned |

The same table, with trial counts and outcome denominators recomputed from raw/, is `dependency_control_coverage` in `i107ab-summary.json`.

## Other checks

- Default-off (i107 binary, trace unset, W-quiet): 5/5 verified, trace variable absent from the Driver environment, no trace file created.
- CMP-distortion (A on the i107 binary with trace on − A on the uninstrumented reference, 10 ABBA pairs, W-quiet, DIAGNOSTIC): +2.06 ms [−35.9, 25.8].
- Denominators: every CMP-AB, W-static, distortion and default-off trial verified (30/30 per arm and condition, 10/10, 5/5); no refuted, abstained, timeout or error outcome anywhere; control outcomes as tabled. The full table is in `i107ab-summary.json` `denominators`.
- 0 non-loopback connects in every trial and manifest; 0 TypeSafe requests. Claim boundary: the non-loopback guard sits inside the runner process only. The Driver's product telemetry is on by default, every session log shows its first-run notice (fresh HOME per session), and its worker may have sent content-free events to the vendor's analytics endpoint. This is the same project-wide condition r2 SETUP records, identical across arms, and not a provider request (provenance.json `driver_telemetry`).
- Browser isolation guard passed on every REAL trial: the Driver's environment (inherited unchanged by Chrome) showed the private session DISPLAY (`:100`), no Wayland or Hyprland variables and no host runtime dir. Chrome's window was found through the Driver's private-display connection.

## Evidence labels per row

SOURCE: B feasibility (map §4). UNIT: Rust acquisition-equality test on the mock CDP endpoint (`unit/`, run on a temporary copy; `libs/` untouched) and the harness tests (`test_i107ab.py`, 39/39). REAL: acquisition equality, semantic equivalence, controls, isolation. BENCHMARK (scripted chooser `choose_mock_for_task`): every timing row. BLOCKED: A↔B read cost, live provider. NOT_RUN: K2-K4 cohorts for this lane, W-idle conditions (lane CSHADOW), arm E, TypeScript runner, OOPIF pages, native. The BLOCKED and NOT_RUN cells are also in the summary (`blocked_and_not_run_cells`) and in `ledger.jsonl` as `row_type: cell` rows with their reasons. Dependency-control coverage: see the DC01-DC20 table above.

## Deviations and disclosures

1. **Isolation wrapper.** The lane started with REAL work blocked: hostless v1 (bwrap user namespace) made Chrome appear owned by uid 65534. At 05:06:31Z `<lanes>/bin/hostless` was replaced by a v2 (env scrub + private runtime dir + Landlock scope for abstract unix sockets and signals); v1 is kept as `hostless-strict`. I found no separate approval record. I treated v2 as the orchestrator-provided wrapper because it is the wrapper the hard rules name and its header states it replaces v1 to unblock the Driver's isolated launch. The Driver's executable check was never bypassed. v2 does no mount masking, so host pathname sockets rely on the env scrub (provenance.json `isolation.residual_exposure`).
2. **Failed attempts (no trial, kept under raw/attempts/).** `i107-ab-shakedown` exited 126: `run_block.sh` lacked the executable bit, and no Driver ran. `i107-ab-main` launched Chrome, then the first trial was aborted by my isolation guard, which wrongly read Chrome's own environ (Chrome rewrites it for its process title). The runner then crashed joining a never-started poller, so no trial record was written. Both were fixed in `9405bc6fc` before `i107-ab-main2`. A queued preflight block was stopped by the harness's background time limit before it acquired the lock, and never ran.
3. **Stale-ref code.** The `i107-ab-main2` controls recorded `effect: refused` (caller events) but not `error.code`: the envelope read the wrong keys. The `controls2` block (`a23e7c6bb`) repeated the controls with the full envelope. All 60 control trials are kept.
4. **#10 mapping.** Whole-page composition is reported both under the pre-registered mapping and as a disclosed post-hoc split (above).
5. **Churn vocabulary** excludes 'value' as well as the map's 'submit'/'verification', so B_proj's query never matches churn (stricter than the map; declared in the lane PREREG).
6. **Harness tests.** The ledger/fixture/equivalence/proc/preflight/statistics pieces were written test-first (red log in raw/unit). The runner/plan, loopback-server, isolation and analysis tests were added after the corresponding code. The fix-round pieces (DC01/DC05a ops, ack self-check, `controls3` plan, Submit-ref identity flag, harness hashes, coverage table and BLOCKED/NOT_RUN cells) were written test-first: `raw/unit/harness-unit-red-r2.txt` (2 failures, 5 errors), then `harness-unit-green.txt` (46/46).
7. **DC01/DC02/DC05a for B_proj** (verifier round 1, blocking). See "DC01-DC20 coverage". DC01 and DC05a were run after results, as a disclosed extension; DC02 = W-churn.
8. **Control page change in `controls3`.** The control script now reports in its ack whether the op ran without throwing, and each new op checks its own effect. Control pages in `controls3` therefore differ from the `main2`/`controls2` control pages in the ack script only; the form and the W-quiet page are unchanged. The DC03/DC04 trials have no recorded op result (`op_ok_unrecorded` in the summary); their effect is shown by the snapshots and the journal instead.
9. **Harness commit per block.** The run manifests of `main2` and `controls2` do not record the harness. Each block runs one Python process, so the code is whatever was on disk at block start: `main2` ran `9405bc6fc` (`a23e7c6bb` changed `run_critpath.py` at 06:42Z, after `main2` had started at 06:41:02Z, and main2's stale_ref records have the older envelope shape), and `controls2` ran `a23e7c6bb`. `controls3` records the harness itself: `harness_commit` in its session-env file and `harness_sha256` per harness file in its manifest, checked against the commit's blobs by `verify_artifacts.py` check 13. Its session env shows 2 dirty files, `verify_artifacts.py` and `provenance.json`; the runner loads neither (provenance.json `harness_by_block`).
10. **Lock receipts.** `raw/lock-receipts.jsonl` holds this lane's blocks only. The round-1 verifier's own quiet-lock receipt (label `i107-ab-verifier-r1`) is left out by `collect_raw.py`.

## Limits

- **Host load.** Every measured CMP trial ran at 1-min loadavg 16-22 on 10 cores (`load1_range` in the summary); the fix-round `controls3` correctness block ran at 15.8-17.0. Load came from processes outside the quiet-lane lock, while this lane held the EXCLUSIVE lock. The pre-registered sensitivity re-analysis (pairs with load1 ≤ 8) therefore has n = 0 in every condition. Paired, interleaved ABBA order protects the deltas, not the absolute values.
- Fresh Driver + browser per trial, K1 cohort only (warm identical-task replay, unique token per trial). 30 pairs is an initial probe, not tail certification. p95 values in the summary are estimates.
- The fixture server runs in the runner process (B-01 deviation 5, identical in both arms).
- Browser results do not qualify native desktops or other platforms.

## Reproduce

```
# unit (under the lanes' hostless wrapper)
<lanes>/bin/hostless env PYTHONPATH=<jev-use>:<jev-use>/python JEV_USE_DIR=<jev-use> \
    <jev-use>/.venv/bin/python -m unittest test_i107ab -v
<lanes>/bin/hostless flock <tmp>/locks/cargo-build.lock unit/run_unit_acquisition.sh <worktree> <scratch> <cargo-target>
# REAL block (quiet lock taken before the session and the MCP session)
<lanes>/bin/hostless <lanes>/bin/quiet-timed <label> <lanes>/cua-x11-session.sh \
    <worktree>/docs/experiments/i107-ab-2026-10-02/run_block.sh <worktree> <lanes>/bin <out> \
    "shakedown default_off distortion ab controls static" <label>
# (fix round: the same command with plan "controls3" and label i107-ab-controls3)
<lanes>/bin/hostless python3 collect_raw.py <runs> <tmp>/locks/quiet-lane-ledger.jsonl main controls2 controls3
<lanes>/bin/hostless python3 analyze.py && <lanes>/bin/hostless python3 verify_artifacts.py
```

## Files

`PREREG.json` (lane), `provenance.json`, `run_critpath.py` + `b01_analysis.py` (adapted from kvnloo/cua 6689610d5; verbatim copies in `22e2ec829`), `i107ab_ledger.py`, `i107ab_fixtures.py`, `analyze.py`, `verify_artifacts.py`, `collect_raw.py`, `run_block.sh`, `test_i107ab.py`, `unit/`, `i107ab-summary.json`, `ledger.jsonl` (296 rows: 289 #10 task × arm × trial rows plus 7 BLOCKED/NOT_RUN cell rows), `raw/` (trial bundles, run manifests, lock receipts, sanitized session logs, unit logs, failed attempts).
