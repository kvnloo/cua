# i107 lane CSHADOW: shadow-mode mirror qualification and active-C admissibility (2026-10-02)

kvnloo/cua#107, execution-sequence steps "Qualify C in shadow mode" and "Run active C only where admissible". Map and frozen design: `../i107-map-2026-10-02/` (PREREG sha256 `8eeb837f…2c53`). Lane pre-registration: `PREREG.json` (commit `9dbd2f966`, 05:33Z). Amendment 1 (isolation approval, smoke-found harness fixes, block schedule, analysis refinements): `PREREG_AMENDMENT_1.json` (commit `1d36233a8`, 08:12:28Z). Schedule commit `9014f640b` (08:13:44Z). The first measured block took the quiet-lane lock at 08:13:56Z, after both commits. Post-data corrections after verification are in `ERRATUM_1.json` (E1-1 to E1-12). No new trial was run and neither PREREG file was changed. One departure from the frozen continuation rule is disclosed there (E1-2).

Placeholders: `<lanes>` is the lanes root and `<tmp>` / `<lane-tmp>` the lane temp root. Upstream items are plain text. Every row carries one evidence label: SOURCE / UNIT / FIXTURE / REAL / BENCHMARK / LIVE_PROVIDER / BLOCKED / NOT_RUN. The chooser in every task cell is `choose_mock_for_task` (FIXTURE/BENCHMARK). There were 0 provider requests and 0 non-loopback connects.

## Disposition

**Park the persistent mirror. Active C is NOT_ADMISSIBLE, and E stays NOT_RUN.** This is the map PREREG decision-table row "C shadow fidelity holds (false-current 0) and C_active NOT_ADMISSIBLE", applied mechanically by `analyze_cshadow.py`.

- Shadow fidelity held: 0 false-current values across 90,659 compared covered-field checks in 155 un-faulted audit trials. This only covers **young mirrors**: compared audits had a median age of 191 ms (max 487 ms) and at most 1,326 events applied since bootstrap. Long-lived idle and resident mirrors were never audited (E1-5).
- The mirror stayed inside every frozen resource budget. The CMP-C-overhead *improvement* verdict is **INCONCLUSIVE** at 30 pairs in both conditions. The frozen continuation block was not run, and that departure is disclosed (E1-2). No improvement is claimed.
- It deletes no work on this fixture. Every Driver read is still required, and the mirror adds work: +6 to +12 CDP sends and +9 to +136 CDP events per task.
- Existing approved (existing-profile) browser routes stay **BLOCKED** on the map PREREG's frozen ground: a persistent event session on a user's approved profile is broader observation than that contract grants, so it is a permission change (#73/#74). This is *not* an allowlist gap. `EXISTING_PROFILE_METHODS` includes `Page.enable`, `Page.getFrameTree`, `DOM.getDocument` and `Target.attachToTarget`/`detachFromTarget`. Only `Inspector.enable` and `DOM.requestChildNodes` are missing, and the mirror treats both as best effort. The mirror refuses `ExistingProfile` up front in `ensure_for_tab`, so it never ran on those routes (E1-1).

## Results

All measured rows are REAL: hostless v2, inside `cua-x11-session.sh`, one `quiet-timed` receipt per block, on the lane binary `cua-driver-i107-cshadow-904b249c1` (sha256 `6b481e0e…1fd23`). A always means the mirror variable is unset. There were 577 measured trials in 30 blocks, 0 harness errors, and every trial was kept.

| # | Item | Evidence | Result |
|---|---|---|---|
| 1 | Active-C admissibility | SOURCE + REAL (B-01 traces, PENDING) + REAL (this lane) | **NOT_ADMISSIBLE.** The verdict rests on the pre-registered classification of the B-01 fill traces: 600 `get_browser_state` calls, strictly 400 (a) ref-minting reads whose minted ref the next mutation resolves and 200 (b) bindings, 0 outside (a)-(d). This is reproduced by `verify_artifacts.py --b01-archive`. The lane's own REAL cross-check covers 165 A task trials: 165 (b) and 315 strict (a). The other **95 reads are decision reads not followed by a mutation, so they fall outside strict (a)-(d)**: 60 were followed by a re-observe decision and 35 found no admissible candidate, including the 5 refused fresh reads in DC11. All 95 come from perturbed controls (DC04, DC12, DC14a, DC16a, DC16b and DC17b with 15 each, DC11 with 5). Unperturbed trials have 0. No Driver read follows the last mutation of a verified trial (verification is the fixture oracle, (c)). The mirror cannot replace these 95 reads, because the facts they decide on (role, name, visibility, enabled state, typed value) are never established by it. So no active-C arm could be registered, no amendment was made and no active-C trial was run (E1-3). |
| 2 | Default-off | REAL | **Holds.** In 10 rounds, the lane binary with the mirror unset and the map binary (no mirror code) sent identical CDP method multisets: 10/10 rounds equal. Across all 231 lane-A trials there were 0 `i107.mirror.*` marks and 0 mirror-only methods (`Page.enable`, `Inspector.enable`, `DOM.requestChildNodes`, `Target.detachFromTarget`). With the mirror on, 10/10 trials created it. |
| 3 | CDP event methods vs the Driver-launched Chrome | REAL (endpoint read, smoke) + SOURCE | `/json/protocol` was read from each trial's own DevTools endpoint inside the session: Chrome/151.0.7922.71, protocol 1.3, sha256 `c61c953c…1458`. This is the same resource as the `resources.pak` extraction behind `raw/protocol_events.json`, so every event method the map lists is confirmed against the live endpoint (`raw/endpoint_protocol.json`). |
| 4 | CMP-C-overhead W-quiet (30 ABBA pairs, A vs C_shadow_M) | REAL | T_oracle: A median 221.1 ms (p95 335.3), C 211.0 ms (p95 350.2). Paired Δ **−2.3 ms**, 95% CI [−19.1, +4.4]. Threshold max(5 ms, 5%) = 11.1 ms. Resource budget: **within budget** and not straddled. Minimum useful improvement: **INCONCLUSIVE** (CI lower bound −19.1 < −11.1). The frozen continuation rule required one more 30-pair block, which was **not run**. This departure is disclosed in E1-2. Driver CPU Δ 0 ms (limit 38 ms). Driver VmHWM Δ +0.29 MiB, browser RSS Δ −0.71 MiB. Work added per task: +1 attach, +6 CDP sends, +9 events, +4.8 KiB of replies. Work deleted: 0. |
| 5 | CMP-C-overhead W-churn (30 pairs) | REAL | T_oracle: A 516.0 ms (p95 846.3), C 479.2 ms (p95 786.0). Δ **−5.3 ms**, CI [−41.1, +13.6]. Threshold 25.8 ms. Resource budget: **within budget** and not straddled. Minimum useful improvement: **INCONCLUSIVE** (CI lower bound −41.1 < −25.8). The continuation block was **not run** (departure, E1-2). Driver CPU Δ −10 ms (limit 64 ms). VmHWM Δ **+3.5 MiB** [2.9, 6.4], browser RSS Δ +1.4 MiB. Work added per task: +2 attaches, +12 sends, +136 events, +84 KiB of replies. Work deleted: 0. |
| 6 | CMP-C-idle W-idle-quiet (30 pairs, 20 s, no tool calls) | REAL | Driver CPU Δ 0.00 s (budget 0.2). Browser-tree CPU Δ +0.01 s [0.00, 0.035] (budget 1.0). Events/s 0 in both arms. VmHWM Δ +0.25 MiB, browser RSS Δ +1.2 MiB. |
| 7 | CMP-C-idle W-idle-churn (30 pairs) | REAL | Driver CPU **+0.38 s per 20 s** [0.37, 0.385] (A 0.30 s, C 0.68 s; budget 1.0). Browser CPU +0.15 s [0.135, 0.18] (budget 2.0). Driver events/s: A 267, C 534. The mirror's session doubles the stream that the Driver's existing, never-detached snapshot sessions already receive in A. VmHWM Δ +2.4 MiB, browser RSS Δ +1.7 MiB. All within budget. |
| 8 | CMP-C-fidelity W-quiet (30 C_shadow_audit trials) | REAL | 60 audits: 30 compared and 30 coincident with the mirror's own bootstrap (all `ambiguous_in_flight` by construction, never counted as agreement). **False-current 0** of 1,890 covered-field checks (all agree). Mirror age at the compared audit: median 194 ms (max 414), median 1 event applied since bootstrap. In effect this compares the bootstrap with a fresh read. The unknown share on action-relevant nodes is 61.5%. That share is **definitional, not measured**: 8 of 13 fields (visibility, geometry, occlusion, focus, value property, AX role/name/states) are never established by any event. Unknown checks on covered fields: 0 (E1-6). Match set: fresh count 1 in 60/60, mirror status `unknown` in 60/60. |
| 9 | CMP-C-fidelity W-churn (30 trials) | REAL | 30 compared audits: **false-current 0** of 51,265 checks (all agree). 17,887 checks were changed in flight and excluded (`ambiguous_in_flight`); 3,208 raw differences fell inside the bracketing window. Mirror age at the compared audit: median 414 ms (max 487), median 125 events applied (max 138). Unknown share on action-relevant nodes is 61.5% (definitional); unknown checks on covered fields: 0. Medians: audit compare 6.3 ms, cut 1.7 ms. |
| 10 | All un-faulted audit trials (fidelity + controls) | REAL | 155 trials, 385 audits, 225 compared, 90,659 checks, **false-current 0** (action-relevant 0). Claim boundary: every compared audit was of a young mirror, median age 191 ms (max 487 ms), median 3 events applied (max 1,326, from the DC19 bursts). Long-lived idle and resident mirrors were never audited, and every navigation re-bootstraps (E1-5). Event lag over 79 control ops: median 0.81 ms after the page's own mutation time, p95 115.7 ms (the DC19 400-op bursts). Measured against the server's ack receipt the median is −0.23 ms, because the ack arrives after the mirror has applied the event. |
| 11 | Dependency controls: 5 trials per arm (A + C_shadow_audit), DC18 5 per fault | REAL | Required-zero counts are all 0: duplicate effect, wrong-target effect, unverified success, unexpected submit, mirror false-current (action-relevant). Per-control results are in the table below. |
| 12 | CMP-C-resident (secondary): 6 ABBA session pairs × 10 tasks, W-churn | REAL | 120/120 tasks verified. Per-task runner-read latency: A 389.6 ms, C 390.7 ms (Δ +1.2 ms [−0.1, +1.7]). Per 10-task session: Driver CPU **+85 ms** [55, 120], VmHWM **+10.5 MiB** [7.5, 21.1], attaches 59 → 79, CDP sends +120, events +622. Median session age 5.0 s. The mirror is re-bootstrapped after every navigation, and the cost grows with session length. |
| 13 | Mirror implementation | SOURCE + UNIT (previous run) | `cua-driver-core` lib 860/860, `platform-linux` lib 602 passed / 10 ignored, TDD red log first. All under hostless. Clippy NOT_RUN. |

The accounting gate (named caller spans explain more than 90% of T_oracle) passes in both overhead conditions and both arms: minimum share 0.995. The spans are sequential caller-level spans, which cover about 100% almost by construction. The PREREG's 10-span decomposition is not reported for the C arms (E1-12). The load-sensitivity re-analysis (pairs with 1-min loadavg ≤ 8) has **0 pairs** for CMP-C-overhead, because the host's median loadavg during those blocks was 15.9 to 17.4 (other tracks). Idle and resident blocks ran at a median loadavg of 0.8 to 3.0, where the sensitivity subsets agree with the full sets. The overhead budget verdicts are therefore measured under heavy shared load. The CIs are wide (±20 to 40 ms), and the budget rule (median ≤ threshold and CI upper bound ≤ 2× threshold) passes anyway.

### Dependency controls (REAL, 5 per arm)

| Control | A outcome | C_shadow_audit outcome | Mirror behaviour |
|---|---|---|---|
| DC01 field value set by the page after typing | 5 verified (re-typed) | 5 verified | value is a property and stays unknown; 0 false-current |
| DC02 unrelated churn | 5 verified | 5 verified | 0 false-current |
| DC03 competing Submit inserted in the form | 5 verified (main form) | 5 verified | the fresh count goes from 1 to 2; the mirror match set stays `unknown` (its DOM estimate is also 2, a diagnostic only) |
| DC04 Submit removed | 5 budget_exhausted, 0 submits | same | 0 false-current |
| DC05a same-looking replacement | 5 verified | 5 verified | 0 false-current |
| DC07 `location.replace` between snapshot and click | 5 verified; the old-ref click was **refused** by the Driver, then a fresh read, re-type and submit | same | `frame_navigated` set it to unknown and it resynced |
| DC10 old binding and ref under a second session label on the **same** MCP connection | 5/5 refused (`authorization_host_failed`, `protected_resource_scope_invalid`) | same | **not dropped**: the second label is not a session replacement. The original session and its mirror carried on (coverage current, audited at step 2) until the `frame_navigated` after submit. This control tests session-scope refusal, not Driver session replacement, which the map's "new MCP session" asked for; that remains NOT_RUN at REAL level. Mirror drop at session end is UNIT evidence only (`session_end_drops_the_mirror_and_detaches_its_event_session`) (E1-4) |
| DC11 renderer SIGKILL (descent from this runner proven 5/5 per arm, 20 renderers per arm) | 5 unknown: the fresh read refused `browser_route_unavailable` after **100.0 s** | same | `target_crashed` set it to unknown; resyncs refused (`page_enable_failed`) |
| DC12 hidden ancestor / DC14a overlay / DC16a disabled fieldset / DC16b aria-disabled / DC17b CSS-only name change | 5 budget_exhausted each, 0 submits | same | 0 false-current (these facts are unestablished in the mirror) |
| DC13 offscreen / DC14b overlay at dispatch / DC15 blur / DC17a property-only value | 5 verified each | same | 0 false-current |
| DC19a/b 400-op burst during bootstrap / during the audit | 5 verified each | same | 0 false-current; lag up to 116 ms |
| DC18 drop:7 / delay:7:200 | n/a | 5 verified each | **false-current that only the audit detected**: 10 and 7 covered fields, all in the churn region, plus `missing_node` resyncs when a structural event went missing. 0 action-relevant, only because the form subtree emits no DOM events on this fixture. Against the map PREREG's frozen DC18 expectation ("each fault ends in unknown/resync, never false-current"), these two faults **fail**. Amendment 1 re-scoped DC18 before data, and the summary now records `expectation_met: false` (E1-7). |
| DC18 dup / early / overflow / reconnect | n/a | 5 verified each | self-detected (`duplicate_node`, `pre_bootstrap_event`, `overflow`, `reconnect`), set to unknown, resynced |
| DC18 foreign / stale / swap | n/a | 5 verified each | foreign and stale-generation events are ignored as unrelated; swapping independent events leaves no false-current |

Not run in this lane (E1-8):

| Row | Status | Reason |
|---|---|---|
| DC05b, DC06 | NOT_RUN here | owned by lane AB/D (arms A, D) |
| DC08, DC09 | NOT_RUN | frozen NOT_RUN in the map PREREG |
| DC20 (ack-lost / delayed effect) | NOT_RUN here | arms A and D only; owned by lane AB/D |
| DC10 as Driver session replacement (new MCP session) | NOT_RUN (REAL) | the lane PREREG ran a second label on the same connection instead; UNIT only |
| W-static (churn page, churn stopped) | NOT_RUN | secondary; lane time box |
| Accessibility.enable mirror variant | NOT_RUN | separately recorded variant from the lane spec; not built or measured |
| CMP-distortion (trace on vs uninstrumented reference) | NOT_RUN here | map/AB lane and owner |
| CMP-AB, CMP-D, CMP-D-K2 | NOT_RUN here | other lanes |
| Cohorts K3/K4 | NOT_RUN | frozen |
| Live-provider cells | BLOCKED | owner budget |
| Existing-profile routes | BLOCKED | permission change (E1-1) |

## What the mirror is (and is not)

The mirror lives in `libs/cua-driver/rust/crates/cua-driver-core/src/browser/i107_mirror.rs`. It is wired only at the fresh `semantic_v2` snapshot (`engine.rs` +24 lines) and stored on `TabRecord` (`store.rs` +6 lines). `remove_session` / the session-end hook, `invalidate_endpoint_generation` and navigation invalidation therefore drop it.

- It is enabled only by `CUA_DRIVER_EXP_I107_MIRROR=shadow|shadow_audit`. Unset, it creates nothing (row 2).
- It keeps one persistent event session per tab. It subscribes first, then calls `Target.attachToTarget`, `Page.enable`, `Inspector.enable`, `Page.getFrameTree` and its own `DOM.getDocument`, concurrently with the normal read.
- Covered fields: existence, node name, text value, attributes, ordered children.
- Always unknown: visibility, geometry, occlusion, focus, typed value, AX role/name/states.
- Bounds: 10,000 queued events and 20,000 nodes. An inconsistency, navigation, crash, overflow or reconnect sets coverage to `unknown` and triggers a resync.
- It never mints, revives or validates refs. It never touches the action path, revalidation or verification. Its output goes to the phase trace only. It adds no public tool or field.

The REAL data confirms the UNIT bound that limits every claim: **a lost value event is invisible to the mirror and only a fresh read catches it** (DC18 drop/delay). Structural faults self-detect. Value-only loss does not. That is why issue rule 4 forbids observation-skipping authority, and why active C has nothing it may delete here.

## Limits

- **Pathname-socket caveat (isolation).** hostless v2's Landlock scope blocks `connect()` to abstract unix sockets bound outside the scope, plus signals. It does not cover pathname sockets (`/tmp/.X11-unix/X*`, `/run/user/<uid>/*`), and the network namespace is shared. Those paths rely on the environment scrub plus this lane's pre-flight, which refuses unless:
  - DISPLAY is a session-private number greater than 2 (`:99` in every block);
  - the listening X socket inodes belong to the session's own Xvfb;
  - XDG_RUNTIME_DIR and the D-Bus daemon are the session's own, and XAUTHORITY is the session's xvfb-run cookie;
  - no Wayland, Hyprland or AT-SPI host variable is present;
  - NoNewPrivs=1.

  Every measured manifest records an all-pass pre-flight together with the hostless, landlock-scope and session-script sha256s. A process inside that set DISPLAY to a host display could still reach it. Nothing in this lane does that.
- Single fixture (jev-use fill form, cohort K1), mock chooser, Chrome 151 on Linux X11. Nothing here qualifies native desktops, other browsers, unfamiliar apps or a live provider.
- `false-current = 0` is a finite census, not a completeness guarantee (issue rule 4). On this fixture the form subtree emits no DOM events during a task, so the action-relevant fields the mirror *could* cover are rarely exercised by events. The action-relevant fields that matter (typed value, visibility, enabled state, AX name) are unestablished and always `unknown`.
- The first audit of every trial coincides with the mirror's own bootstrap and is all `ambiguous_in_flight` by construction. Fidelity is measured on the later audits (30 per condition).
- Memory: host memory PSI was non-zero. VmHWM read lower at idle end than at idle start on the same pid in the smoke, and VmSwap is recorded alongside. The frozen metrics (VmHWM, browser-tree RSS) are reported unchanged.
- The first `ctl-3` attempt was killed by the agent harness's 2 h background-task limit before its manifest and quiet-lane receipt were written. Its 15 complete trials and 1 partial trial are kept, excluded, in `raw/interrupted/`, and the block was re-run with the same round index.
- **In-process fixture and oracle.** The fixture server (`CshadowServer`, a ThreadingHTTPServer) and the 2 ms oracle poller run as threads inside the runner's Python process and share its GIL. This is identical in every arm (map PREREG `fixture_reset` disclosure, E1-9).
- **Queue cap.** The 10,000-event cap detects overflow and then drains. It is not a strict memory bound, because the demux `subscribe()` channel is unbounded and can grow during the bootstrap and `requestChildNodes` awaits. The overflow path was exercised only by simulation (DC18 overflow:50) and by UNIT tests. The REAL high-water marks were 98 queued events and 534 nodes (E1-11).
- **Caller tree.** The runner imports from the tested source's jev-use tree `72bf8156` (the PR 4316 merge), not from `635a4f588` at main. The imported functions are unchanged by that merge, and `--guarded-completion` is never used (E1-10).
- The resident cell is secondary. Its latency is the runner's verified read, because resident sessions run no independent poller. Its mirror cost summary covers each session's final mirror instance.

## Files

- `PREREG.json`, `PREREG_AMENDMENT_1.json`: frozen design and the amendment (unchanged).
- `ERRATUM_1.json`: post-data corrections and the disclosed continuation departure.
- `run_cshadow.py`: the runner, one block per invocation, with the pre-flight. `run_schedule.sh`: the measured schedule. `cshadow_fixture.py`: the fixture.
- `analyze_cshadow.py`: writes `raw/ledger.jsonl` (#10 task × arm × trial rows) and `cshadow-summary.json`. `classify_reads.py`: the active-C classifier.
- `verify_artifacts.py` reproduces the summary and ledger from `raw/`. It checks the manifests, the isolation pre-flight, the quiet-lane receipts, the identities and the hashes, and scans for local paths and secrets.
- `raw/`:
  - `trials-measured.tar.gz`: 577 trials (caller events + Driver phase trace).
  - `manifests/`, `quiet-lane-receipts.jsonl`, `block-logs/`.
  - `smoke/`: excluded smoke runs.
  - `interrupted/`.
  - `endpoint_protocol.json`, `protocol_events.json`, `admissibility.json`.
  - `build/`, `unit/`, `fixture-selftest.json`.

## Commands

- REAL schedule: `run_schedule.sh <lanes> <out>`. Each block runs as `hostless quiet-timed i107-cshadow-<block> cua-x11-session.sh <jev-use>/.venv/bin/python run_cshadow.py --driver <bin> --out <out> --block <block> --plan <plan> ...`.
- Analysis: `hostless python3 analyze_cshadow.py .`
- Verification: `hostless python3 verify_artifacts.py [--b01-archive <path>]`

## Hard-rule log

- hard_rule_breach: none.
  - Every browser and Driver process launched inside `cua-x11-session.sh` under hostless v2, on a private `:99` whose socket belonged to the session's own Xvfb.
  - No host DISPLAY, WAYLAND_DISPLAY or socket path was ever used.
  - No secret was handled and nothing was written upstream.
  - Every reported number comes from a `quiet-timed` block.
- near_miss: several `python3` one-liners ran in the plain host shell instead of under hostless. They parsed JSON trial files and printed counts; one applied a text replacement to `run_cshadow.py` as an editor. None imported a GUI, session or network library, so none could have had an effect. Every runner, fixture, analysis, verification and collection step ran under hostless. The schedule driver `run_schedule.sh` is a plain-shell loop whose only executing step per block is `hostless …`. The erratum pass added the same class: two host-shell `python3` JSON reads of the PREREG files and one heredoc used as a text editor on `analyze_cshadow.py`. None imported project, GUI, session or network code. The analysis and verification re-runs ran under hostless.
- No push, no GitHub write, no stash. 0 TypeSafe requests. The only processes killed were this lane's own: DC11 renderers with proven descent, plus the harness's kill of its own schedule at the time limit.
