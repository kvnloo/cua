# B-02: causal A/B of the three B-01 browser Driver sites, 2026-10-02

## Result in one paragraph

The browser A/B could not run. Every command must run under the `hostless` wrapper, a bwrap user namespace that maps only the lane uid. Inside it, every root-owned file appears owned by uid 65534. The Driver's isolated browser launch accepts only a root-owned, non-writable Chromium payload (`trusted_root_owned_installation`, `platform-linux/src/browser_platform.rs:147-164`, the `metadata.uid() != 0` test at :156), so `browser_prepare {allow_launch, isolated_new}` refuses with `browser_route_unavailable`. That happened in 18 of 18 attempts (REAL). The stack track recorded the same blocker on its own. bwrap is not setuid here, so no rule-compliant wrapper keeps root ownership. Every browser block is therefore **BLOCKED**: the 3-class × 4-arm measured A/B, N-E1/N-E2/N-E3, N-W1/N-W2, the browser default-off smoke and the STEP 0 browser probes. They are pre-registered unchanged and can run once the owner rules on the wrapper. The blocks that need no browser did run. The single measurement commit adds both knobs, default off (UNIT, 11 new tests, all suites green). On the same binary, the admission knob `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1` cuts the Driver's per-`tools/call` admission span from 1.573 ms to 0.32 ms. The paired saving is 1.257 ms [1.22, 1.28], positive in 20 of 20 rounds, which is 79.9% of the span (BENCHMARK). The invalid-call envelopes are byte-identical with and without the knob (REAL, 8 cases × 10 trials). STEP 0 SOURCE shows `tools_list()` is a deep clone of an inventory that is loaded once and never changes, and it was cloned twice per call. **Verdicts:** H_V per-call deletion confirmed, whole-task verdict BLOCKED. H_E BLOCKED (UNIT only). H_W BLOCKED (no knob built, not IRREDUCIBLE). **E2 is not advanced by a measured number.** The untested share stays at B-01's 51.2% / 70.2% / 69.3%. If the per-call saving carries over to the browser tasks, the PROJECTION is 5.9% (fill), 9.5% (toggle) and 9.2% (modal) of B-01's composed T. TypeSafe: 0 attempts, 0 reached.

## Scope and owners

- Lane B-02, wave 2 (experiment). Owners: kvnloo/cua#93 (R2-01/B-01 follow-up, R2-10 prep), kvnloo/cua#10 (accounting), kvnloo/cua#73 (security invariants).
- Advances: E2 browser (causal verdicts for B-01's localized sites). Only the V per-call part is delivered. E3 prep: which Driver-side deletions may join the R2-10 composed arm. E4: the controls. Only N-V ran; the browser controls are BLOCKED.
- Coordination: B-02 does not test observation reuse across steps or any event-maintained state (that is the kvnloo/cua#107 track). No new service, shadow state, router, registry, batch API or event service. Both knobs are env-gated and default off. No default changes.
- Pre-registration: `PREREG.json`, commit `1a902e453` at 2026-10-02T05:08:15Z. The measured block (vmicro) started at 05:10:57.389Z under the EXCLUSIVE receipt acquired at 05:10:51.908Z. The PREREG records the blocker. It was found in STEP 0, before any measured trial.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Base | `f5c991e5927513c8b94da4330c94276dc5f8ce22`, the B-01 tested source: upstream main `229b65b28` + R2-01 trace `7d3a28b66` + trycua/cua PR 4316 merge `0c6a53237` + B-01 marks/knob | SOURCE |
| Measurement commit (exactly one on base) | `560bd8247c36c9d249f481b509a073c131e93620`: endpoint- and admission-step marks, `CUA_DRIVER_EXP_ENDPOINT_REPROOF=bound`, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`. No `CUA_DRIVER_EXP_CDP_WARM` (not built) | SOURCE |
| PREREG commit | `1a902e45320a199f1852c4d71ab197a1ca4cbd87` (also adds the harness) | SOURCE |
| Packet commit | the commit that adds this README (branch `exp/b-02-browser-driver-sites-20261002`). Publication SHA: set by the Publish agent. This lane did not push | — |
| Driver binary | `cua-driver-b02-560bd8247`, sha256 `7e6c06090fa2f2b63152a9276fe3a4766f88d2d5cbe7b412236208ee537bd3a0`, `cua-driver 0.32.0` (read inside `cua-x11-session.sh` under `hostless`). Built by `build-driver.sh` (family `cua-release-r2-01`, 0 Fresh units, 89 s) under `flock -s quiet-lane.lock` + `flock cargo-build.lock`, receipted (`raw/lock-ledger.jsonl`, label `build-b02-560bd8247`) | SOURCE |
| Harness copied from B-01 | `6689610d5:docs/experiments/b-01-browser-critpath-2026-10-02/`. Blobs: `run_critpath.py` 673c7f5a, `b01_fixtures.py` 6b2e7ad8, `b01_tasks.py` 05dd33e5, `b01_analysis.py` 6632de0f, `analyze.py` c70e6227 (byte-identical; `verify_artifacts.py` re-hashes them) | SOURCE |
| Live trycua/cua PR 4316 head (gh) | start 05:07:15Z and end 05:18:06Z: `a0bca744067d04f05904319d3d919be30c336556`, open, unchanged and equal to the head merged into the base | SOURCE |
| Upstream main | gh `bc55ff2d236a62075c981ebadf0ff97dd90d45be` at the start (13 commits ahead of `229b65b28`) and `6fbcdf97b6ed953e70ea5efad5a61d3ffb490a2f` at the end (14 ahead). Both have 0 files under `libs/cua-driver` (gh compare), so the tested Driver tree equals current upstream plus the lane commits | SOURCE |
| Provider | mock chooser and non-browser tools only. TypeSafe attempts 0, reached 0. Runner manifests record 0 non-loopback connects | REAL |

## Environment

- Linux 7.2.2 x86_64, 10 CPUs. About 660 host processes during the lane (relevant to the endpoint proof's host-wide `/proc` scan).
- Every code-executing command ran as `hostless …`. GUI and Driver work also ran inside `cua-x11-session.sh`: private rootless Xvfb, openbox, picom, private dbus, `env -i`. DISPLAY per block: STEP 0 `:99`, step0-dbg1 `:100`, version read `:100`, vmicro `:99`, N-V `:101` (`raw/*/session.log`, `run-manifest-*.json`). No AT-SPI bus.
- Locks (`raw/lock-ledger.jsonl`):
  - vmicro ran in one EXCLUSIVE quiet-timed window, 05:10:51.908Z–05:11:24.105Z (`b02-vmicro`).
  - STEP 0 ran in EXCLUSIVE `b02-step0`, 05:02:04.352Z–05:02:26.755Z.
  - N-V ran in 1 SHARED acquisition of 10 trials.
  - The debug run (3 trials) and both shakedowns each ran in one SHARED acquisition of at most 10 trials.
  - The build, unit compile and unit run each held `flock -s quiet` + `flock cargo-build`, receipted.
- 1-minute loadavg before each vmicro trial: 2.59–2.79 (every value is in the trial records).

## STEP 0: localization (excluded from gates)

**(a) Owned-endpoint re-proof (SOURCE; REAL magnitude from B-01's traces).** Every mutation runs `BrowserEngine::revalidate_for_mutation` (`engine.rs:1539`). After the lifecycle, fingerprint (`:1633`, `/proc/<pid>/stat` + `exe`) and native-window checks, step 3 (`:1657`) calls `owned_endpoint` (`:1046`), which calls the Linux `discover_owned_endpoint` (`browser_platform.rs:963`). That function runs:

- `loopback_ports_for_pid` (`:285`);
- `socket_inodes_for_process_tree` (`:257`);
- `process_family_pids` (`:232`). This does a `read_dir("/proc")` at `:239` and reads `/proc/<pid>/status` for **every process on the host** to build the parent map. Then it readlinks every fd of the browser family and parses all of `/proc/net/tcp` and `tcp6`;
- for each owned loopback port, `browser_websocket_url` (`:511`): TCP connect, `GET /json/version`, JSON parse. The first port that answers wins.

All of this runs per mutation. It runs once more at bind (`engine.rs:1386`), outside T. B-01's committed traces give a median of 9.896 / 9.881 / 9.881 ms per mutation (fill/toggle/modal; `raw/b01-trace-reanalysis.json`, read-only, B-01 pending). The split between the `/proc` scan and the HTTP probe was to come from the new `ep.*` marks. That needs a Driver-launched browser: **BLOCKED**.

**(b) MCP admission (SOURCE + BENCHMARK).**

- `SdkAdapter::tools_list()` (`sdk_adapter.rs:146`) is `self.tools_list.clone()`, a deep clone of the inventory parsed once in `SdkAdapter::load` (`:95`, stored at `:136`). The field (`:47`) is never reassigned and has no interior mutability, so the inventory is **static for the process lifetime**.
- At the base, `run_direct` evaluated `&sdk.tools_list()` for every `tools/call` (proxy admission), and `handle_request_inner` evaluated `&provider.tools_list()` again: two deep clones and two `validate_tool_call` runs per call.
- `validate_tool_call` (`mcp_wire.rs:147`) itself only parses the call, checks that the arguments are an object and, in the modern era only, scans tool names.
- Between the two validations, `apply_direct_session_identity` (`proxy.rs:138`) only inserts `_session_id` / `_transport_session_id` into an arguments object that already exists. It changes neither the era nor the validation outcome (`b02_identity_stamping_preserves_admission_outcome`).
- Measured sub-spans per legacy call, K5: proxy clone 0.408 ms + validate-and-drop 0.281 ms + inner clone 0.387 ms + inner validate-and-drop 0.264 ms. That is ≈1.34 of the 1.573 ms span. The rest (parse, protocol-session validation, identity, `begin_tool_call`, timer, classify) is about 0.03–0.05 ms each.

**(c) Cold first `semantic_v2` snapshot (SOURCE + B-01's REAL traces; probes BLOCKED).**

- Each `get_browser_state` snapshot reuses the pooled CDP connection, made at bind before T (`connect`, `engine.rs:835`).
- It attaches a **new** flattened session that is never detached (`engine.rs:2781`, BUG-01 B). Then it calls `DOM.getDocument {depth:-1, pierce}` (`:2498`), `Page.getFrameTree`, `DOMSnapshot.captureSnapshot` + `Page.getLayoutMetrics` (`:2418`) and `Accessibility.getFullAXTree` (`:2439`). It never calls `DOM.enable` or `Accessibility.enable`.
- In B-01's 440 traces the first snapshot exceeds the second by 13.6 ms (fill) and 6.9 ms (toggle, modal). By sub-span:

| Sub-span | fill excess | toggle excess | modal excess |
|---|---|---|---|
| `DOM.getDocument` | 7.17 | 4.09 | 4.10 |
| `Accessibility.getFullAXTree` | 3.32 | 0.37 | 0.22 |
| attach | 1.14 | 1.24 | 1.23 |
| `Page.getFrameTree` | 0.75 | 0.53 | 0.54 |

- The second snapshot also opens a new session and uses the same connection. So the excess is **not per process or connection**, and **not per new session**.
- What is left is per document (the first serialization and AX build after the navigation commit) or load timing (navigate returning before the document settles).
- The probes that would decide between them are re-navigation, a second process on a warm document, and a 1 s delay. All need the browser (`step0_probe.py`): **BLOCKED**.
- The spec's example knob, per-target session reuse, could remove at most the attach part (≈1.2 ms excess plus ≈0.3 ms per call), not `DOM.getDocument`'s 4–7 ms.
- No `CUA_DRIVER_EXP_CDP_WARM` was built. The W verdict is BLOCKED, not IRREDUCIBLE.

## Method (runnable blocks)

- **vmicro (H_V per call).**
  - Design: 20 rounds of AB/BA pairs, K5 (knobs unset) vs K5V (`CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`). Same binary, same session type. One fresh `cua-driver mcp` per trial.
  - Client: a raw stdio JSON-RPC client (`run_b02_admission.py`). It sends a legacy initialize and `tools/list`, then 25 legacy-era and 25 modern-era `tools/call get_config`, one at a time.
  - Measurement: the Driver phase trace is on in both arms. The admission span per call is `mcp.line_read` → `mcp.inner_validated` (CLOCK_MONOTONIC marks). The per-trial statistic is the median over its 25 legacy calls. Legacy is the era of the jev-use MCP client that B-01 used.
  - Statistics: paired K5−K5V within each round, with a seeded percentile bootstrap (10000 resamples, seed 20261002, B-01's `b01_analysis.boot_ci`).
- **nv (N-V).** 5 trials per arm (AB/BA). Each trial sends 8 invalid `tools/call`s and keeps each reply line byte-exact:
  - V1 wrong argument type (`browser_navigate` with an integer `target_id`);
  - V2 missing required arguments;
  - V3 unknown tool;
  - V4 arguments not an object (extra);
  - each case in the legacy and the modern era.
- **Oracle and forced path.**
  - For vmicro, the oracle is the Driver's own marks for the work itself. K5V must show `mcp.inner_validation_skipped` and no `mcp.inner_tools_list_built` on every call. K5 must show the reverse. Every call must return a non-error result.
  - For N-V, the oracle is the reply bytes.
  - This is not a target-owned task outcome, because no browser task ran.

## Results

**vmicro: per-call admission (n = 20 paired rounds, 40/40 trials valid, 2000 calls; BENCHMARK)**

| Metric (median of per-trial medians, ms) | K5 | K5V | Paired saving K5−K5V [95% CI] | Rounds positive | Evidence class |
|---|---|---|---|---|---|
| Admission span, legacy era (primary) | 1.573 | 0.32 | **1.257** [1.22, 1.28] | 20/20 | BENCHMARK |
| Admission span, modern era | 1.486 | 0.323 | 1.162 [1.14, 1.223] | 20/20 | BENCHMARK |
| Client round trip per call, legacy | 2.255 | 0.941 | 1.338 [1.268, 1.368] | 20/20 | BENCHMARK |

- Gate `gate_V_call` (pre-registered): the CI excludes 0 and the saving is 79.9% of the K5 span (≥ 50%): **PASS**.
- Forced path held on every call: K5V had 1000/1000 calls skip the inner validation with 0 inner inventory builds. K5 had 1000/1000 inner builds and 0 skips. The K5 arm is also the default-off evidence for the V knob.

**N-V envelopes (REAL; 10 trials, 5 per arm)**

| Case | legacy-era reply | modern-era reply | distinct replies across 10 trials |
|---|---|---|---|
| V1 wrong argument type | tool refusal `protected_resource_scope_invalid` | same | 1 / 1 |
| V2 missing required argument | tool refusal `protected_resource_scope_invalid` | same | 1 / 1 |
| V3 unknown tool | tool result `permission_denied` | JSON-RPC −32602 `Unknown tool` (proxy admission) | 1 / 1 |
| V4 arguments not an object | JSON-RPC −32602 (proxy admission) | JSON-RPC −32602 (proxy admission) | 1 / 1 |

All 8 envelopes are byte-identical between K5 and K5V and between repeated trials: **PASS**. V1 and V2 are refused by the browser authorization layer ("requires an exact target_id") before any schema check (Deviation 4).

**UNIT (inside the session, receipted):**

| Suite | Result | B-02 tests |
|---|---|---|
| `cua-driver-core` lib | 827 passed, 0 failed (818 at base + 9) | 6 endpoint-knob, 3 admission-knob |
| `platform-linux` lib | 603 passed, 10 ignored (602 + 1) | bound-check guard test (decoy inode, gone listener, non-LISTEN, non-loopback, fd moved, fd closed, start time changed, pid gone) |
| `cua-driver` bins | 291 passed (290 + 1) | identity stamping preserves the admission outcome |
| `cua-driver-sdk` lib | 95 passed | — |

The unit tests show unset = shipped behaviour for both knobs: full discovery on every mutation, inner validation on every call, identical wire bytes. They show set = path taken: one proof then bound checks, any mismatch falling back to the full proof, entries never shared across sessions or pids; the inner validation skipped only for the same-era admitted request.

**Browser blocks (BLOCKED, REAL refusal evidence)**

| Block | Status | Evidence |
|---|---|---|
| STEP 0 browser probes (`b02-step0`, 15 trials) | BLOCKED | 15/15 Driver traces end at `browser_prepare`. The first run's error capture kept only the exception group (Deviation 2) |
| STEP 0 debug run (`b02-step0-dbg1`, 3 trials) | BLOCKED | 3/3 `browser_prepare refused: browser_route_unavailable, no root-owned, non-writable system Chromium executable is available for isolated launch` |
| Measured A/B (3 classes × K5/K5E/K5V/K5EV × 20), N-E1, N-E2, N-E3, N-W1, N-W2, browser default-off smoke | BLOCKED | Not attempted after the blocker (would refuse identically). Pre-registered in `PREREG.json` → `blocked_blocks_as_specified`; `run_b02.py` implements them but has never run against a browser |

## Hypotheses and verdicts

| Hypothesis | Pre-registered rule | Result | Verdict | Evidence class |
|---|---|---|---|---|
| H_V | whole task: T_oracle saving CI excludes 0, ≥ 50% of the localized admission component, identical envelopes | Per call: 1.257 ms [1.22, 1.28] = 79.9% of the span, envelopes identical. Whole task: not run | **per-call deletion confirmed; whole-task verdict BLOCKED** | BENCHMARK + REAL + UNIT |
| H_E | OWNER_DECISION only with a causal T_oracle saving and discriminating N-E1/N-E2/N-E3 | bound check implemented and unit-tested (every guard refuses alone; mismatch → full proof); no REAL path | **BLOCKED** | UNIT |
| H_W | knob only if STEP 0 justifies; IRREDUCIBLE only if STEP 0 shows per-document work | excess localized to `DOM.getDocument`/AX/attach on the first snapshot; not per connection, not per session; per-document vs load timing undecided | **BLOCKED** (not IRREDUCIBLE) | SOURCE + REAL (B-01's traces) |

## E2: what remains (no measured change to the untested share)

| Class | B-01 composed mean T | B-01 untested share | V PROJECTION (1.257 ms × 4 calls in T) | Untested share if the projection held |
|---|---|---|---|---|
| fill | 84.9 ms | 51.2% | 5.03 ms = 5.9% | 45.3% |
| toggle | 53.1 ms | 70.2% | 5.03 ms = 9.5% | 60.7% |
| modal | 54.5 ms | 69.3% | 5.03 ms = 9.2% | 60.1% |

The projection is labelled PROJECTION: it is not measured on a browser task and not a gate, and B-01 is pending. The < 5% target is not met. The time that remains untested is:

1. The owned-endpoint re-proof: ≈9.9 ms per mutation, ≈19.8 ms per task (BLOCKED).
2. The cold-first-snapshot excess: 6.9–13.6 ms per task (BLOCKED).
3. The admission span left after V: 0.32 ms per call, about 1.3 ms per task. Its parts are each ≤ 0.05 ms per call and have no causal verdict.
4. B-01's unattributed time: 0.

## Work deleted vs wall-clock saved

| Knob | Work deleted (structural) | Wall-clock saved | Evidence class |
|---|---|---|---|
| V (`CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`) | Per `tools/call`: 2 deep clones (and their drops) of the full tool inventory, plus the repeated inner `validate_tool_call`. What remains is 1 validation against the borrowed, process-lifetime inventory | 1.257 ms per call (admission span); 1.338 ms per call (client round trip); whole task not measured | BENCHMARK |
| E (`CUA_DRIVER_EXP_ENDPOINT_REPROOF=bound`) | Per mutation after a full proof in the same session: the host-wide `/proc/*/status` scan, the family fd scan, the full `/proc/net` listener parse and one HTTP `/json/version` round trip. They become one fd readlink, one `/proc/net` read and one `/proc/<pid>/stat` read. The full proof still runs at bind, on any mismatch, and in every fresh process | not measured (BLOCKED) | UNIT |
| W | none (not built) | — | — |

## Controls

| Control | Result | Evidence class |
|---|---|---|
| N-V1..3 (+V4) envelopes K5 vs K5V | 8/8 cases byte-identical across 10 trials | REAL |
| V default-off (knob unset) | 1000/1000 calls ran the inner inventory build and validation, 0 skips; wire bytes identical (unit) | BENCHMARK + UNIT |
| E default-off (knob unset) | full discovery on every mutation, 0 bound checks, 0 entries (unit) | UNIT |
| E guards: decoy inode on the same port, listener gone, non-LISTEN, non-loopback, fd moved or closed, start time changed, pid gone | each refuses alone (unit) | UNIT |
| N-E1 takeover, N-E2 restart, N-E3 fresh-process full proof, N-W1 stale ref, N-W2 DOM replacement, browser default-off smoke | not run | BLOCKED |

## Deviations

1. **Infrastructure blocker (all browser blocks).** See the result paragraph. I did not attempt any workaround: no trust-check knob, no user-owned browser copy, no run outside `hostless`, no `*-e2e` wrapper, no sandbox or permission override. The lane spec's browser design is pre-registered verbatim as BLOCKED.
2. The first STEP 0 run (15 trials, EXCLUSIVE) recorded only `ExceptionGroup` messages. `step0_probe.py` was then changed to record leaf exceptions, and the 3-trial debug run (SHARED) captured the refusal code. Both runs are kept and excluded. Both changes came before the PREREG commit.
3. Shakedown `shake-vmicro` (SHARED) crashed reading the `tools/list` reply: the asyncio stream limit was too small for the inventory. No trial completed and its directory was deleted; its lock receipt remains. The reader limit was raised in `run_b02.py` and `run_b02_admission.py`. Shakedown `shake-vmicro2` (4 trials, SHARED) is kept in `raw/` and excluded. All of this came before the PREREG commit.
4. N-V V1 ("wrong argument type") and V2 ("missing required") get the same browser authorization refusal before any schema check, so V1 does not exercise type validation as such. Rejections at proxy admission (legacy V4, modern V3/V4) never reach the inner skip, which by construction applies only to admitted requests. V4 was added beyond the spec's three cases.
5. The "validate" admission sub-spans include the drop of the cloned inventory, because the marks sit after the block that owns the clone (`proxy_validate_and_drop`, `inner_validate_and_drop`).
6. vmicro uses a non-browser tool (`get_config`) and a raw client. It measures the Driver-side admission work, which happens before dispatch and does not depend on the tool. It does not measure a browser task's T_oracle.
7. `run_b02.py` (browser runner with the N-E1/N-E2/N-W2 controls) and `cdp_raw.py` are written but have never run against a browser. They need a shakedown before any measured use.
8. rustfmt was not run over the touched files (as in B-01 and R2-01).
9. The STEP 0 and vmicro numbers are on the B-02 binary. The STEP 0 localization numbers for (a) and (c) come from B-01's committed traces (binary `2e0248ad…`). They are not compared with B-02 numbers in any gate.

## Limits

- No browser task ran, so no T_oracle, no target-owned outcome and no E4 browser invariant was measured in this lane.
- The vmicro saving depends on the size of this binary's Linux tool inventory, which the clone copies.
- The endpoint proof's cost scales with the host's process count. B-01's 9.9 ms was measured on this shared machine with other tracks active.
- n = 20 paired rounds. One binary, one session type, loadavg 2.6–2.8.

## Claim boundary

This configuration only: Linux X11 (private Xvfb/openbox/picom) under `hostless`, Driver `f5c991e59` + `560bd8247` (binary `7e6c0609…`, 0.32.0), raw MCP stdio, `get_config`, legacy and modern MCP eras.

On it, the admission knob deletes two inventory clones and one repeated validation per `tools/call`. That saves 1.257 ms [1.22, 1.28] of a 1.573 ms admission span, and the invalid-call envelopes are byte-identical.

Nothing here is a browser-task, LIVE_PROVIDER, Wayland, macOS or Windows claim, and nothing is a default change. Both knobs stay default off. Any product change is a separate reviewed fix.

## Disposition

- **H_V:** per-call deletion confirmed (BENCHMARK + REAL + UNIT). The whole-task verdict is **BLOCKED**. For R2-10 (E3 prep): V is the only Driver-side candidate this lane can support, as a default-off knob. Whether it joins the composed arm needs either the browser A/B once unblocked or the planner's acceptance of the per-call evidence.
- **H_E:** **BLOCKED** (UNIT only). Even with a causal saving it is an OWNER_DECISION (security policy).
- **H_W:** **BLOCKED** (not IRREDUCIBLE). No knob was built.
- **E2:** not met. The untested share is unchanged by measurement (PROJECTION 45.3% / 60.7% / 60.1% if V carries over).
- **Blocker for the planner/owner:** the `hostless` user namespace makes root-owned Chromium appear as uid 65534, and the Driver refuses isolated launch. Browser lanes need an owner ruling on the isolation wrapper (for example a privileged or setuid sandbox that keeps root ownership, or a reviewed exception) before any browser experiment can run.
- TypeSafe: 0 attempts, 0 reached.

## Files

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration: the blocker, the BLOCKED browser design, the runnable blocks and their gates |
| `run_b02_admission.py` | vmicro and N-V runner (ran) |
| `step0_probe.py` | STEP 0 browser probes (ran; blocked at `browser_prepare`) |
| `run_b02.py`, `cdp_raw.py` | browser A/B runner, the N-E1/N-E2/N-W2 controls and a raw CDP client/decoy (not run, blocked) |
| `run_critpath.py`, `b01_fixtures.py`, `b01_tasks.py`, `b01_analysis.py`, `analyze.py` | B-01 harness, byte-identical copies |
| `analyze_b02.py` | recomputes `b02-summary.json` from `raw/` |
| `b01_snapshot_reanalysis.py` | read-only STEP 0 re-analysis of B-01's committed traces → `raw/b01-trace-reanalysis.json` |
| `verify_artifacts.py` | recomputation, headline numbers, lock receipts, PREREG order, harness blobs, provider, privacy |
| `b02-summary.json`, `headline-numbers.json`, `provenance.json` | summary, README numbers, provenance |
| `raw/` | sanitized raw outputs: `vmicro-trials.tar.gz`, `nv-trials.tar.gz`, `step0*-trials.tar.gz`, `shake-vmicro2-trials.tar.gz`, manifests, session logs, unit logs, build receipt, `lock-ledger.jsonl` |

Raw outputs are mirrored, unsanitized, in the lane artifacts directory `artifacts/r2/B-02/`.
