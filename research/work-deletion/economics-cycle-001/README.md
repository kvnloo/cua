# Economics cycle 001 — c78 guarded completion

## Status: live results are **focus-isolation-unqualified**

The user reported physical Hyprland mouse movement and required verified **headless Sway**. All live trials stopped immediately; the last batch had already exited. The scoped `/proc` check found **zero owned live marked processes**, and the session launchers had removed their private runtime/profile roots. No owned PID/runtime is known to remain. `SAFETY_HALT.json` overrides every earlier `qualifies`, `private_session`, and checker-pass field in the preserved receipts. The current live launch paths refuse before spawning a GUI.

**Do not rerun the historical Xvfb commands or frozen harnesses.** Their environment checks did not establish the actual input backend or exclude resident Driver authority. Live certification is blocked pending a parent-verified headless-Sway harness with private HOME/runtime/Wayland/SWAYSOCK/Driver authority and actual backend verification. Never use the user's compositor, physical outputs, or Sway nested in Hyprland.

This packet therefore delivers source/hermetic findings and an offline analysis of preserved, unqualified traces—not an accepted live performance benchmark. Same-author source-independent checking is not independent-person certification.

## Outcomes

- **SRC / UNIT:** accepted guarded completion deletes one chooser invocation, not an observation or an action. The exact c78 Python and TypeScript hermetic runner tests passed: **7 Python + 20 TypeScript**, plus **5 evidence-contract tests**.
- **Preserved trace evidence, focus-unqualified:** baseline has **2 actual chooser entries**, accepted guarded has **1**, and explicit declined fallback has **2**. These are entry hooks around the original deterministic mock chooser—not an inference from `provider_decision_ms == 0`, and not paid/network provider calls.
- Both arms have **2 fresh semantic observations + 1 browser-binding observation**, **2 distinct action RPCs**, **10 total request/response MCP calls**, and **0 explicit MCP wait tools** in the repeated trials. Window readiness required one `list_windows` call. HTTP verification/read polling is counted separately in each journal; it is not a model or semantic observation.
- The two declined cells add a second real Submit control on the fixture's first input event. Both emit `declined/submit_not_unique`, call the chooser again, use a fresh ref, and reach the independent HTTP oracle. No synthetic Driver response is inserted into these traces.
- **Observation-dependent break-even premise falsified for this recipe.** The measured marginal count vector is **(provider, semantic observation, action) = (1, 0, 0)** in both languages. This is neither observation deletion nor batching.

## Scope and provenance

| Item | Pin / treatment |
|---|---|
| Exact runner source | `c78f50efed1ee7b289ab8947ec997904ea18fd72` |
| Source worktree, read-only | `/mnt/zer0models/github/cua-lanes/c4316` |
| Evidence worktree / branch | `/mnt/zer0models/github/cua-lanes/speed-economics` / `research/guarded-economics-20260929` |
| Driver binary SHA-256 | `f1d7f2d4ce929a8df80338ac57942bc6535ee5bef4f441f6173688b62da722f7` |
| Matching c78 Rust tree | `71e08f221ebdc86ffee0cd8f37085e1fc434f3e6` |
| Driver build receipt source HEAD | `1027f8a77288e0ae2e94f7f6d6fd685f84b518be` — same Rust tree, not claimed to be c78 |
| Python `run.py` SHA-256 | `b088056874dbd126de2cb7d5bb057a7f44d2ae1a18bec5c4cd4d2348ac9896e6` |
| TypeScript `run.ts` SHA-256 | `ea625bbb7137590ed554b4c4d8c3625810def4adae38f168b120e5c9da89619c` |
| Upstream pin supplied | `fe9b0c6d3c0307537bccbfd69f4f801ec219adc0` |
| Upstream fetched before experiment | `db5d0f4caf3a66eb31c8d6e24394cec962899257` — drift recorded; source was not changed |
| Provider | Original deterministic mock chooser with independent recipe-local entry/exit counter and optional deterministic delay |

The original #10 harness/proxy and c4316 product/dependency contents were not edited. Python executes the exact source entrypoint via `runpy` after wrapping the imported chooser; TypeScript imports the exact entrypoint and instruments only the adapter in memory using an ESM load hook. Each run freezes its evidence tooling under `harness-source/` and records those hashes separately from runner source. TypeScript also records original/instrumented transpiled adapter hashes. The live harness git HEAD at execution was the c78 base before the evidence packet commit; it is not misrepresented as the later packet commit.

## Trial design and accounting

**30 preserved receipts, 14 scientific cells:**

| Run directory | Receipts | Purpose |
|---|---:|---|
| `runs/pilot-001` | 4 | Initial real traced smoke, original checker; Python event output buffered |
| `runs/pilot-002` | 4 | Strengthened oracle/file bindings, unbuffered Python events, disposable-session cleanup |
| `runs/fallback-001` | 2 | Explicit real DOM uniqueness decline, one per language |
| `runs/repeat-001` | 12 | Three paired baseline/guarded blocks per language |
| `runs/grid-001` | 8 | Paired deterministic latency points `(P,O)=(250,0),(250,250)` ms, both languages |

Seed `20260929`; paired arms and language order are randomized within each block and recorded in each `plan.json`. No failures were silently dropped. Timing summaries use **only** the 12 `repeat-001` trials. The grid is a small fractional design, not a fitted two-dimensional response surface.

A globally unique trial key is **`run_id/trial_id`**. Historical trial IDs are local to their immutable run directory (the two pilots intentionally retain the same local design labels). `scientific_cell` excludes block/trial identity. `analyze.py` checks uniqueness, counts, complete plans, exact frozen tooling hashes and the receipt set before aggregating.

## Measurement and privacy

- Real MCP request/response pairs are intercepted transparently. Raw bytes are never written; only tool enums, booleans, counts, opaque refs/session/target IDs, timestamps and permitted status fields survive the allowlist.
- The token is generated in memory and delivered to the bootstrap over stdin. It is not in persisted process command metadata, stdout/stderr, final state, or trace content. The independent oracle stores equality booleans, not field values. Each live cell scanned its artifacts for its ephemeral token before saving the receipt.
- HTTP `/submit`, `/reset`, and `/state` journals are independent of runner telemetry. They distinguish runner, browser and independent-observer requests, record server-side mutation time, and retain the first independent verified-state timestamp. Observer interval is 10 ms; scheduling and polling uncertainty are visible rather than subtracted away.
- Whole-task timing is process spawn → first independent verified observation. Runner lifetime, startup to first semantic request, post-verified runner tail, and external cleanup are separate. `browser_prepare`, initialization, discovery, readiness and binding have separate RPC spans. This does not pretend to be a browser-internal startup breakdown.
- Named intervals are unioned on the monotonic time axis, clipped to the chosen envelope. Overlaps are not double-counted. Residuals are retained; they include interpreter/client setup, gaps, local proof/candidate work, serialization and client-side HTTP time outside server handlers. Runner self-reported phase timings are separate and are not added to enclosing MCP spans.
- All live runs were traced. Trace/entry-hook overhead is part of the envelope. There is no uninstrumented production speedup claim.

The checker validates intended flag, bootstrap source hash, actual event route, provider-entry journal, ordering, fresh/current refs, session binding, independent field equality and HTTP submission/oracle evidence. Corruption tests reject wrong route, flag, call count, oracle, source, Driver, ref, command, bootstrap, missing journals and contamination. Every receipt carries the checker corruption result. The source-independent auditor additionally reads the exact artifact files back and binds them to the receipt, rather than trusting scalar success metadata. Historical schema-1 pilots retain their weaker original checks; they are not used for quantitative estimates.

## Offline economics and boundaries

For this accepted two-step path, with `P` as added per-chooser delay and `O` as added per-fresh-semantic-observation delay:

```text
added baseline time = 2P + 2O
added guarded time  =  P + 2O
added saved time    =  P
```

For full task costs, let `H` be the incremental guarded planning/proof overhead and `R` the remaining non-provider/non-semantic work:

```text
T_baseline - T_guarded = P - H + (R_baseline - R_guarded)
break-even condition: P > H + R_guarded - R_baseline
coefficient of O: 0
```

`deterministic-count-surface-qualified-offline.json` explicitly contains a **count-accounting replay**, not a simulated Driver result or an exact-runner timing replay: 20 provider/observation cost points per language, grounded in audited repeat-trial counters. The pre-halt version is also preserved as `deterministic-count-surface.json`; the global safety override applies to both inputs.

A stable empirical provider threshold is **not identified**: source proof overhead was not isolated as its own interval, startup/residual differences are noisy, the sample is small, and all live trials are focus-unqualified. No observation-price threshold or cross-platform conclusion is claimed. Paid-model price/reliability effects were not measured. A declined guard removes zero provider calls and can add proof overhead.

## Preserved descriptive timing — **not qualified benchmark results**

Repeated-trial means, milliseconds. These figures describe the quarantined traces only.

| Language | Baseline verified | Guarded verified | Baseline − guarded, paired mean | Descriptive 95% t interval | Baseline slower pairs |
|---|---:|---:|---:|---:|---:|
| Python | 4146.04 | 4224.90 | −78.85 | [−514.94, 357.23] | 1/3 |
| TypeScript | 4353.41 | 4202.68 | 150.74 | [35.47, 266.01] | 3/3 |

The t interval uses df=2 and assumes independent approximately normal pair differences; it is not robust certification or evidence of model-free wall-clock speedup. Full pair directions/order, medians, ranges, envelope timings and exact values are in `analysis.json`.

Guarded repeated-trial critical-path observations:

| Span / envelope | Python mean ms | TypeScript mean ms |
|---|---:|---:|
| `browser_type` | 1604.94 | 1603.89 |
| `browser_click` | 1536.77 | 1539.83 |
| Outcome-event → process exit | 541.55 | 486.61 |
| `browser_prepare` | 280.17 | 252.79 |
| MCP `initialize` | 171.96 | 159.40 |
| Both semantic observations | 31.24 | 34.60 |
| Spawn → first semantic request | 1032.90 | 1004.19 |
| Full runner lifetime | 4766.80 | 4784.07 |
| Named-span union within lifetime | 4297.26 | 4221.84 |
| Honest residual within lifetime | 469.54 | 562.23 |
| External cleanup | 66.49 | 71.32 |

Startup/envelope rows overlap component rows and must not be summed. The remaining action RPCs dominate these traces; the deleted mock chooser cost is tiny. Source/native-input internals were not causally decomposed in this packet.

The Python `(250,250)` grid pair had startup spans **5409.02/4486.12 ms** (baseline/guarded), versus roughly one second in most other cells. Its 815.09 ms whole-task delta is not attributed to a 250 ms chooser deletion. The smaller grid cells similarly remain descriptive single pairs; counts identify the marginal work, not all wall-time variation.

## Reproduce the safe, offline checks

From the evidence worktree:

```bash
cd /mnt/zer0models/github/cua-lanes/speed-economics/research/work-deletion/economics-cycle-001
python3 tools/offline_verify.py
```

This runs only evidence tests, exact c78 **hermetic** runner tests (MCP transport mocked; Python fixture HTTP is loopback-only), source-independent receipt checks, aggregation and count-surface projection. It removes inherited display/compositor authority and `PYTHONPATH`/`PYTHONHOME` when starting source tests. The first offline Python attempt failed because the agent's inherited Python 3.14 `PYTHONPATH` contaminated the source's Python 3.12 venv; that failed receipt is preserved in `offline-verification-first-import-failure.json`. Clearing interpreter-path variables fixed the test environment; source code was not changed.

Individual offline commands:

```bash
python3 tools/audit.py runs/repeat-001 --out /absolute/new-audit.json
python3 tools/analyze.py
python3 tools/count_surface.py runs/repeat-001 --out /absolute/new-surface.json
```

Historical exact live commands are retained in each `launcher-receipt.json` and each cell's safe `command` field, with frozen code and hashes in `harness-source/`. **They are provenance, not authorization to rerun Xvfb.** The live entrypoint currently returns code 4 before allocating a session; direct harness preflight also blocks.

## Files and remaining work

- `runs/*/cells/*/receipt.json`: complete envelopes, safe proof/counters/spans, exact code hashes, negative controls.
- `runs/*/cells/*/{mcp.jsonl,provider.jsonl,http-journal.json,runner-events.json}`: scrubbed independent evidence.
- `source-independent-audit.json`: current aggregate data-consistency audit plus explicit live-safety override.
- `analysis.json`: paired uncertainty, spans, grid descriptions, globally unique trial bindings and safety qualification.
- `offline-verification.json`: actual successful offline execution receipts.
- `SAFETY_HALT.json`: user steering, cleanup status and mandatory stop gate.

Unresolved: verified headless-Sway rerun; actual input/backend/authority containment proof; independent-person audit; isolated guard-overhead timing; exact-runner hermetic timing grid (only source hermetic tests and count-accounting replay were completed); live-provider cost/reliability measurements. No product changes, pushes or upstream posts were made.
