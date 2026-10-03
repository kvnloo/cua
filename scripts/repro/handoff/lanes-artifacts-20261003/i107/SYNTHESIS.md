# kvnloo/cua#107 synthesis: live state mirror vs scoped reads and checked execution (2026-10-02)

Spec: kvnloo/cua#107 (read in full, with its claim comment). Map and frozen design: branch `exp/i107-map-20261002`, packet `docs/experiments/i107-map-2026-10-02/` (PREREG sha256 `8eeb837f…2c53`, committed `be68363bc` at 04:50:11Z, before any measured trial). Every lane branch descends from `be68363bc`.

## Identities

| Item | Value |
|---|---|
| Upstream main at pin | `352507b6c03162ab286b21d5ed509125cc3daece`; libs/cua-driver tree `892fdddb07de` |
| Upstream main at publication | `ab628e0d1cf1e993eef2f7f99d9ed8faf364506c` (17 commits later); libs/cua-driver tree still `892fdddb07de`, so no Driver drift |
| Guarded continuation | trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556`, re-read at publication: OPEN, not merged, not draft, updatedAt 2026-10-01T17:03:24Z (unchanged) |
| Tested source | `exp/i107-map-20261002`: `2251da142` (merge of a0bca7440), `fe424500d` (R2-01 trace), `a5e344291` (B-01 marks), `092b065d5` (i107 producer-RPC ledger, env-gated, default-off); libs/cua-driver tree `a87dc39dc3b2`; jev-use tree `72bf81561367` |
| Driver, arms A / B_proj / D | `cua-driver-i107-092b065d5`, sha256 `f3a5c01a…7aed`, 0.32.0 |
| Driver, lane CSHADOW (both sides of every C comparison) | `cua-driver-i107-cshadow-904b249c1`, sha256 `6b481e0e…1fd23` |
| Uninstrumented reference | `cua-driver-r2-main-229b65b28`, sha256 `8b037961…4cd3` (CMP-distortion only) |
| Browser | Google Chrome 151.0.7922.71, `isolated_new` |
| Chooser | `choose_mock_for_task` (scripted mock). 0 TypeSafe requests across the whole track |
| Isolation | hostless v2 (env scrub, private runtime dir, Landlock scope; sha256 `36738895…ed6b`) + `cua-x11-session.sh` (private Xvfb) + exclusive `quiet-timed` lock per block |

Publication heads (verified commits; lane-result `commit` fields for AB and CSHADOW are stale and are not cited):

| Lane | Branch | Verified head | Verdict |
|---|---|---|---|
| AB | `exp/i107-ab-20261002` | `2253734f3bbc738285ef512e0cfe620812eefed8` | ACCEPTED (non-blocking items only) |
| CSHADOW | `exp/i107-cshadow-20261002` | `39aea0c706c82c0015090f1924b0ee0aa476d60a` (ERRATUM_1) | ACCEPTED (non-blocking items only) |
| D | `exp/i107-d-20261002` | `6d1c609261289d73833395d390d1150ad2187285` | ACCEPTED (non-blocking items only) |

No lane was rejected. Each verifier re-derived the headline numbers from `raw/` with its own code and re-ran a small REAL subset (diagnostic only).

## Decision table (#107), row by row

| Comparison | Result | #107 / map row that applies | Disposition |
|---|---|---|---|
| **B vs A** | B is BLOCKED: no producer-side scoped fresh read is expressible through the existing contract. `semantic_v2` `query`/`scope_ref` are fetch-then-filter. REAL: a `query` read issued the identical CDP method multiset and identical request bytes on 90/90 A/B_proj pairs; node counts equal on 30/30 W-quiet pairs and within noise elsewhere (UNIT mock CDP agrees: identical 16/15 calls). B_proj (named fallback, diagnostic) picks the same candidates on 30/30 per condition and only trims the response. | "Evidence incomplete, baseline unavailable, or contract requires a new permission → BLOCKED/INCONCLUSIVE; do not weaken the gate" (map: "B BLOCKED and B_proj shows equal acquisition") | **BLOCKED** (read-cost question). B_proj projection savings reported separately, never as a read-cost saving |
| **C vs B** (run as C vs A, B BLOCKED) | Shadow fidelity holds within a narrow boundary: 0 false-current in 90,659 covered-field checks (155 un-faulted trials, 225 compared audits), 0 action-relevant. Every frozen resource budget met. Mirror deletes 0 work and adds +6 to +12 CDP sends and +9 to +136 events per task. Active C NOT_ADMISSIBLE: every Driver read on the fill fixture is a required (a) ref-minting or (b) binding read; the 95 reads outside strict (a)-(d) are decision reads in perturbed controls whose facts the mirror never establishes. | Neither "B improves A; C no benefit" nor "C improves B" applies cleanly because B is BLOCKED. Map row: "C shadow fidelity holds (false-current 0) and C_active NOT_ADMISSIBLE → park the mirror". Also #107 execution step: "If none can safely disappear, report that result rather than bypassing checks" | **Park the persistent mirror (KILL for promotion on this fixture)**. Active C not run |
| **D vs B** (run as D(A-reads) vs A) | D deletes one chooser decision per task (2 → 1); snapshots, CDP sends, acquired nodes and mutations unchanged. Wall clock: NO_MEANINGFUL_BENEFIT in W-quiet, W-churn and K2. DC06: PR 4316's guard accepted a Submit relocated into another form and submitted to the decoy 5/5 (wrong-target, required-zero breach). DC03: guard declined correctly, but the fallback (arm A's first-match chooser) hit the competing Submit 5/5. | "D improves B → prioritise checked continuation under R2-07" does **not** apply (no measured improvement). Map row: "D accepts a wrong target in DC06 … → REVISE D; no promotion" | **REVISE D**. Live-provider value BLOCKED |
| **E vs D** | Not run. Gate requires active C and D to each show independent value against A; neither did. | "E improves D after C and D qualified separately" not reachable | **NOT_RUN** |
| Warm-replay-only benefit | No benefit found in any cohort | "Benefit exists only for warm identical-task replay → publish that scope" | n/a (no benefit to scope) |
| Churn / startup / memory | Mirror cost grows with churn and session length (W-idle-churn Driver CPU +0.38 s per 20 s; resident +85 ms CPU and +10.5 MiB VmHWM per 10-task session), within budget but with nothing deleted | "Churn, startup, fallback, or memory costs erase benefit → narrow or kill" | consistent with parking the mirror |

## Cohort-specific claim boundary

- **K1 (same task, same app, warm identical-task replay; unique token per trial):** the only cohort for AB and CSHADOW and the primary cohort for D. All results above are K1 unless stated.
- **K2 (held-out parameter, 64-char uppercase token, same app):** lane D only. D vs A −0.64 ms [−6.13, +12.75] against 12.36 ms: NO_MEANINGFUL_BENEFIT. Not run for A/B_proj or C.
- **K3 (held-out composition) and K4 (unfamiliar app):** NOT_RUN (frozen in the map PREREG). Nothing here qualifies composition, unfamiliar apps, other browsers' fixtures, OOPIF pages, or any native desktop.
- **Workload conditions:** W-quiet and W-churn (500 nodes, 20 Hz) are primary for every lane. W-static: AB only. W-idle-quiet / W-idle-churn (20 s): CSHADOW only.
- **Mirror boundary:** false-current = 0 is a finite census of **young** mirrors (median age 191 ms, max 487 ms). Idle and resident mirrors were never audited. 8 of 13 action-relevant fields (visibility, geometry, occlusion, focus, typed value, AX role/name/states) are never established; the Submit match set was `unknown` in 60/60 audits. The form subtree emits no DOM events on this fixture, so action-relevant FC_AR = 0 is weak evidence. In DC18 drop/delay, false-current values (10 and 7 fields, churn region) were caught only by the fresh audit, confirming issue rules 3-4.
- **Load:** every timed comparison ran at 1-min loadavg ~11.6 to 22 from other tracks while the lane held the exclusive quiet lock. The pre-registered loadavg ≤ 8 sensitivity analysis has n = 0 in every lane. Paired ABBA interleaving protects the deltas; absolute times are inflated.
- **Provider:** every task cell is FIXTURE/BENCHMARK with `choose_mock_for_task`. No LIVE_PROVIDER row exists. Decision deletion is worth about 0 ms with a mock chooser; its live value is BLOCKED.
- B-01 traces (PENDING, rejected for text only, numbers reproduced by its verifier) are reused for the active-C classification and the A decomposition; label them PENDING when cited.

## #10 ledger rows (compare within a lane only; binaries, harnesses and blocks differ between lanes)

dec = chooser decisions, obs = full `semantic_v2` observations, act = mutating Driver actions. Every row: K1 unless noted, scripted chooser, REAL + BENCHMARK.

| Lane / arm | Binary | dec | obs | act | T_oracle p50 W-quiet (ms) | T_oracle p50 W-churn (ms) | Verified / failures | Paired Δ vs A [95% CI] |
|---|---|---|---|---|---|---|---|---|
| AB A | `f3a5c01a` | 2 | 2 | 2 | 246.4 | 859.3 | 30/30 per condition | — |
| AB B_proj (diagnostic) | `f3a5c01a` | 2 | 2 (same acquisition) | 2 | 245.1 | 843.2 | 30/30 per condition | W-quiet −0.66 [−6.63, 5.32]; W-churn −23.5 [−60.7, 19.6]; W-static −9.05 [−37.5, 38.1] |
| CSHADOW A | `6b481e0e` | 2 | 2 | 2 | 221.1 | 516.0 | 30/30 per condition | — |
| CSHADOW C_shadow_M | `6b481e0e` | 2 | 2 (+ mirror session) | 2 | 211.0 | 479.2 | 30/30 per condition | W-quiet −2.3 [−19.1, 4.4]; W-churn −5.3 [−41.1, 13.6] (budget check; improvement INCONCLUSIVE, continuation block not run, E1-2) |
| D A | `f3a5c01a` | 2 | 2 | 2 | 270.6 | 1221.1 | 30/30 per condition | — |
| D D(A-reads) | `f3a5c01a` | 1 (+1 plan, +1 resolve) | 2 | 2 | 271.6 | 1219.1 | 30/30 per condition | W-quiet +1.07 [−10.04, 10.79]; W-churn −4.44 [−40.95, 20.55]; K2 −0.64 [−6.13, 12.75] |

Accounting gate (>90% of T_oracle explained by named spans): met in every lane and arm (AB coverage 1.0; CSHADOW ≥ 0.995, sequential caller spans; D ≥ 0.9954). AB A decomposition W-quiet (mean ms): acquisition 45.3, projection/encoding/transport 29.5, provider 0.015, resolution/validation 81.0 (endpoint re-proof ≈ 39.7), dispatch 7.4, wait 108.6 (focus settle 101.1), fresh verification 4.0. On 500-node pages, whole-page composition inside the Driver is ≈ 245 ms per snapshot, before any scoping (post-hoc split, disclosed; the pre-registered mapping files it under projection/encoding/transport).

### Work deleted vs wall-clock saved

| Lane | Work deleted | Wall-clock saved |
|---|---|---|
| AB B_proj | No producer work (same CDP calls, same nodes, same whole-page composition). Payload only: −2.7 kB per task (W-quiet), −94 kB (W-churn) | Client parse + Driver build/serialize ≈ 9-11 ms per task on 500-node pages, ≈ 0.3 ms on the quiet page. T_oracle within noise everywhere |
| CSHADOW C_shadow_M | 0. Adds +1-2 attaches, +6-12 CDP sends, +9-136 events, +4.8-84 KiB replies per task | None claimed (INCONCLUSIVE at 30 pairs) |
| D D(A-reads) | 1 chooser decision per task (mock, ≈ 0.007 ms); adds 1 plan + 1 resolve call (medians < 0.06 ms; max resolve 1.07 ms) | NO_MEANINGFUL_BENEFIT in all three conditions. Live value BLOCKED. R2-03's live −212 ms is not borrowed or summed |

## Negative controls and required-zero counts

| Control | A | B_proj | C_shadow_audit | D | Note |
|---|---|---|---|---|---|
| DC01 value property changed after typing | re-typed, verified (AB 5, CSHADOW 5, D 5) | same (5) | verified 5; value stays unknown | guard declined `field_not_proven` 5/5, re-typed, verified | |
| DC02 unrelated churn | = W-churn, verified | = W-churn, verified | verified 5, FC 0 | = W-churn, verified | |
| DC03 competing Submit inserted first | **wrong target 10/10 (AB), 5/5 (D)**; CSHADOW variant (inserted after, in form) verified via main form 5/5 | **wrong target 10/10** | verified 5; fresh count 1→2, mirror match set `unknown` | guard declined `submit_not_unique` 5/5, **fallback wrong target 5/5** | caller first-match without uniqueness fact; blocks promotion of A, B_proj and D |
| DC04 Submit removed | budget_exhausted, 0 submits | same | same | declined, budget_exhausted | |
| DC05a benign same-looking re-render | verified | verified | verified | accepted with fresh ref, verified | |
| DC05b replacement in check-to-dispatch | Driver dispatched to detached node 5/5 (no effect), next step verified | — | — | same 5/5 | Driver stale acceptance (R2-07 gap, no `isConnected`), both arms, 0 duplicates |
| DC06 relocated look-alike in another form | **decoy submit 5/5** | — | — | **guard accepted 5/5, decoy submit 5/5** | missing form-scope fact in PR 4316; blocks D |
| DC07 document replacement before dispatch | Driver refused `browser_ref_stale` 5/5, no effect | — | same (mirror resynced on `frame_navigated`) | same | jev-use `Driver.call` treats `effect: refused` as success (caller defect, recovered) |
| stale ref after navigate | refused 10/10, 0 submits | refused 10/10 | — | — | |
| DC10 old binding under second session label | refused `protected_resource_scope_invalid` (D 5/5; CSHADOW 5/5 also `authorization_host_failed`) | — | same; not a session replacement | same | map expected `browser_binding_stale`/`browser_ref_stale`; refusal still before any effect |
| DC11 renderer SIGKILL | CSHADOW (own binary): fresh read refused `browser_route_unavailable` after 100.0 s, 5/5 | — | same; mirror `target_crashed` → unknown | **NOT_RUN** | Driver finding (100 s hang) |
| DC12 hidden / DC14a overlay / DC16a,b disabled / DC17b CSS name | budget_exhausted, 0 submits | — | same, FC 0 | declined 5/5 each | |
| DC13 offscreen / DC15 blur / DC17a value cleared | verified | — | verified | accepted or declined as predicted, verified | |
| DC14b overlay at dispatch | effect lands 5/5 | — | verified | accepted 5/5, effect lands | `dom_event` bypasses hit testing (route property) |
| DC18 drop / delay | — | — | **false-current 10 / 7 fields, caught only by the fresh audit** (fails map's frozen DC18 expectation; amendment re-scoped before data) | — | value-event loss is invisible to the mirror |
| DC18 dup / early / overflow / reconnect / foreign / stale / swap | — | — | self-detected or ignored, resynced | — | |
| DC19 400-op bursts during bootstrap / audit | verified | — | verified, FC 0, lag ≤ 116 ms | — | |
| DC20a ack lost after effect / DC20b delayed effect | `unknown` 5/5 with 1 submit, 0 redispatch / verified late 5/5 | — | — | same | no duplicate effects |

Required-zero totals: stale-ref effects 0, unauthorized 0, duplicate effects 0, unverified success 0 in every lane. **Wrong-target effects are non-zero in A (AB 10, D 10), B_proj (10) and D (10)**, all from DC03 and DC06; any of these stops promotion. Driver detached-node acceptance: 5 per arm (DC05b). On measured comparison pairs (no perturbation) every required-zero count is 0.

## Blocked / NOT_RUN cells

| Cell | Status | Reason |
|---|---|---|
| A↔B read-cost comparison | BLOCKED | no producer-side scoped read expressible; result-equal Driver optimisation or #73/#74 contract change required, neither authorised |
| B `scope_ref` at REAL level | NOT_RUN | SOURCE + UNIT only |
| Active C | NOT_ADMISSIBLE / not run | no removable work; gate 2 fails |
| E | NOT_RUN | active C and D both lack independent value |
| Live-provider cells (all arms) | BLOCKED | TypeSafe budget reserved for #93 R2-10; owner approval needed |
| Existing-profile (approved) routes for C | BLOCKED | persistent event observation on a user profile is a permission change (#73/#74); not an allowlist gap (CSHADOW E1-1) |
| K3, K4 cohorts | NOT_RUN | frozen in map PREREG |
| K2 for A/B_proj and C | NOT_RUN | lane scope |
| DC08 (iframe), DC09 (tab creation) | NOT_RUN | no admitted iframe fixture / no authorised tab-creation path |
| DC10 as true Driver session replacement | NOT_RUN (REAL) | ran as second label on same MCP connection; mirror drop at session end is UNIT only |
| DC11 for D | NOT_RUN | map assigned DC11 to A and C only; open qualification gap for D |
| CMP-C-overhead continuation block | NOT_RUN | frozen continuation rule partially skipped (E1-2, disclosed after data); budget verdict margins wide |
| Accessibility.enable mirror variant | NOT_RUN | not built |
| W-static for C, W-idle for AB/D | NOT_RUN | lane scope / time box |
| loadavg ≤ 8 sensitivity re-analysis | NO_DATA (n = 0) | shared host load 11.6-22 on every timed trial |
| TypeScript runner, OOPIF pages, native desktops | NOT_RUN | outside this fixture |

## Recommendations for #73 / #93

| Mechanism | Recommendation | Basis |
|---|---|---|
| Producer-side scoped fresh reads (B) | **BLOCKED** | Not expressible through the existing `semantic_v2` contract without weakening it (`page_occluded`, document-wide query matching, no `captureSnapshot` subtree form). Route to #73/#74 only if someone proposes a result-equal contract. |
| Whole-page composition cost (~245 ms per snapshot on 500-node pages) | **INCONCLUSIVE → candidate for a separate, result-equal internal Driver optimisation** (owner decision; not authorised here) | Dominant cost under churn (AB), inside every required fresh read, before any scoping. Measured under heavy shared load. |
| B_proj payload projection | **KILL as a read-cost claim**; projection savings (≈ 9-11 ms per task on large pages, client side) INCONCLUSIVE at task level | Equal acquisition; T_oracle within noise |
| Persistent incremental mirror (C) | **KILL for promotion (parked)**; shadow code stays fork-only, env-gated, default-off | 0 work deleted, adds CDP work and memory; establishes almost none of the action-relevant facts; active C not admissible. Re-open only with a pre-registered amendment naming an unperturbed-path read outside (a)-(d) whose facts lie entirely in covered fields, or a #73/#74-approved scoped-read/composition contract |
| Checked continuation D (PR 4316 guard on A reads) | **REVISE** | Deletes 1 decision per task, ≈ 0 ms with mock chooser; DC06 wrong target (missing form-scope fact) and DC03 fallback wrong target must be fixed caller-side, DC11 tested, and live value measured with owner budget before any R2-07 prioritisation |
| Conditional composition E | **NOT_RUN / BLOCKED** on C and D | Gate not met |
| Caller uniqueness (A baseline, first-match `BrowserSemanticSource.find`) | **REVISE** (baseline defect) | DC03 wrong target in A, B_proj and D fallback |
| jev-use `Driver.call` treating `effect: refused` as success | **REVISE** (caller defect) | DC07 |
| Driver detached-node acceptance (R2-07 gap) | **REVISE** (existing #93 R2-07 item) | DC05b 5 per arm |
| Driver renderer-crash handling | **INCONCLUSIVE → owner** | DC11: fresh read refused only after 100.0 s |

## Open items for the orchestrator / owner

1. Confirm hostless v2 (sha256 `36738895…ed6b`) as the approved isolation wrapper. CSHADOW's amendment records approval conditions; AB and D inferred approval from the canonical wrapper replacement. If not confirmed, REAL rows would be relabelled; this cannot flip any decision toward running C or E.
2. Driver product telemetry was left at its default in every lane (content-free events to the vendor's analytics endpoint; fresh HOME per session). Recommend `DO_NOT_TRACK=1` / `CUA_TELEMETRY_ENABLED=false` across lanes.
3. hostless does not unshare the network namespace and v2 does no mount masking; host pathname/abstract sockets are protected by the env scrub (and Landlock for abstract sockets).
4. Shared load: overlapping shared holders starve exclusive quiet-lock requests and unlocked work raised loadavg to 16-22 during every timed block.
5. Assign DC11 for D if D is revised.

## Hard-rule log (synthesis/publication step)

No hard_rule_breach, no near_miss. Only git, gh, grep, tar, gzip, file and file reads/writes ran in the plain host shell; no code was executed. GitHub writes are limited to kvnloo/cua (branch pushes with `--no-follow-tags`, no force; comments on kvnloo/cua#107 and kvnloo/cua#10). Nothing written to trycua. 0 TypeSafe requests.

## Publication record

- Pushed to kvnloo/cua with `--no-follow-tags`, no force, no prior remote ref (ls-remote empty before each push): `exp/i107-ab-20261002` = `2253734f3`, `exp/i107-cshadow-20261002` = `39aea0c70`, `exp/i107-d-20261002` = `6d1c60926`. A first push attempt failed locally (shell refspec expansion error, `src refspec … does not match any`), sent nothing, and was re-issued correctly.
- Leak scan before push: 28 unique commits since merge-base `352507b6c` across the three branches (messages, identities, added lines) plus every committed tar.gz (contents, member names, owners 0/0, gzip headers): 0 local paths, 0 host name, 0 secrets. Text hits were test canary constants (`proof-token-i107-unit`, PR 4316 fixture canaries), a privacy-scanner regex, and compressed bytes; only vendor browser install paths (`/opt/google/chrome/...`) appear as absolute paths.
- Comments: kvnloo/cua#107 issuecomment-5951449252; kvnloo/cua#10 issuecomment-5951449499.
