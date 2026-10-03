# B-08: browser per-process cold first-snapshot excess on binary B7, plus a one-binary E2 re-read, 2026-10-03

Lane B-08, wave 6 of the CUA RFC loop. Owners: kvnloo/cua#93 (experiment specs, invariants), kvnloo/cua#10
(whole-task accounting), kvnloo/cua#73 (E2). Lineage: B-04 / B-06 (per-process cold excess), B-07 (transport
sub-span verdicts on the same binary). Upstream items are named as plain text (trycua/cua PR 4316).

This is a NEW pre-registration (PREREG.json), not an amendment of B-06. B-06's primary verdict was UNDECIDED
because its positive control sat before snapshot1 and overlapped the first snapshot's wait; its OWNER_DECISION
rested on a post-hoc Amendment 1. This lane puts the 15 ms positive control right after snapshot1 from the start,
runs all three classes, uses a journal-based primary metric (T_j) instead of the 2 ms sampler grid, and permits no
amendment.

## Result in one paragraph

384 of 384 measured trials (C, Wa, Wb, P2; 32 per arm per class) were valid by the target-owned oracle, with
exactly one completion mutation each. SMOKE passed 5/5 per class and the FIX-01 detached-node control (N-W2)
passed 1/1 per class. E4 total 0. Every round started at 1-minute loadavg ≤ 4.0. The pre-registered agreement
check of T_j against the 2 ms sampler held: agreement 100.0% of trials within 2.5 ms. Both controls passed in
every class, and every class reached a terminal per-process verdict:

- fill: OWNER_DECISION, D 10.58 [9.50, 11.41] ms (T_C 61.55);
- toggle: OWNER_DECISION, D 3.05 [2.62, 5.38] ms (T_C 48.52);
- modal: OWNER_DECISION, D 4.56 [2.98, 5.92] ms (T_C 48.59).

So a fresh Driver + Chrome process pays a material per-process cold excess in every browser class. Only process
or session reuse kept outside T removes it, and that is product policy. **Disposition: KEEP.**

E2 re-read on B7 (Part E, this lane's own C arm = a fresh process, corrected view): the untested share is
toggle 0.4% / 3.6% and modal 0.4% / 3.3% (BELOW_GATE counted as IRREDUCIBLE / as UNTESTED). Fill stays at
16.9% / 19.0% under the pre-registered labels. Almost all of fill's remainder is R2-10's `runner` component
(9.82 ms). A post-hoc look shows it is the compiled routine's 10 ms verify-poll sleep, which B-04's harness does
not stamp; counted as a poll (descriptive only), fill would be 2.3% / 4.4% (Deviation 4). Provider: 0 attempts,
0 reached.

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | `browser_*` tools over MCP stdio, R2-10 scripted COMP in every measured arm: feedback off, focus settle 0 on fill, 10 ms completion poll (2.0 s deadline), caller-compiled output validators, `CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE=1`, guarded completion + compiled replay on fill (R2-10R scripted COMP artifact), R2-10 step loop on toggle/modal; phase trace on (with the B-05/B-07 transport marks in B7); B-07 stamped stdio client, default variant; `CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM` and PREP_FAST unset; scripted chooser; telemetry `false`; no provider key forwarded. Per trial: fresh `cua-driver mcp`, fresh Driver-launched system Chrome (`isolated_new`, sandbox on), fresh fixture servers, token and session label | REAL |
| Actual route / producer | From receipts and phase marks, every valid measured trial: fill `browser_type` route `trusted_input` with `type.insert_send` in the call window, then `browser_click` route `dom` with `click.cdp_send`, both produced by the compiled routine (128 + 128 actions); toggle and modal two `browser_click` route `dom` with `click.cdp_send`, producer `provider` (scripted chooser), input route `dom_event` (256 + 256 actions). Cold vs warm from the snapshot1 marks (table below). Driver pid + Chrome pid with /proc start time: warm arms identical at warm-up and task start in 288/288; every (pid, start time) unique across all 399 trials, so C always had new processes | REAL |
| Independent target-owned oracle | jev-use fixture server (fill `submitted == token`) and the kvnloo/cua#24 pages (toggle `checked`, modal action applied); the server's CLOCK_MONOTONIC journal must show exactly one completion mutation. PRIMARY T_j = max(journal completion ts, caller-side return of the last accepted mutation) − task_start (return of the task `browser_navigate`); journal and caller stamps are `time.monotonic_ns` in one process. SECONDARY T_oracle on the 2 ms sampler | REAL (FIXTURE) |
| Negative / fallback controls | NC A/A (Wa − Wb), PC2 (P2 − Wa, 15.0 ms right after snapshot1), FIX-01 N-W2 detached-node refusal 1 per class, SMOKE 5 per class (product default), E4 counters per arm | BENCHMARK+REAL (FIXTURE) |
| Tested source SHA | `ac319cbe90d6cdf0cc8cd8984f99f5b04b68fdac` = R' 45dff8f32 + B-05 mark picks + the default-off POST_FAST knob; rust tree `20c9f051248a`; libs/cua-driver Linux tree = upstream 0f1955d2f. Nothing built in this lane | SOURCE |
| Driver binary | B7 `cua-driver-b07-231f6e8bb`, sha256 `6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa`, `cua-driver 0.32.0`. Re-hashed on the host at lane start (13:04Z) and end (14:04Z), identical; read inside the session at start and end (`raw/logs/versions-start.log`, `raw/logs/versions-end.log`); the runner refused on any mismatch and wrote name, sha256 and version into every trial record (399/399) and manifest. B7's relation to R' rests only on B-07's default-off smoke (SOURCE), so absolute T is never compared with B-06 or R2-10R | REAL |
| Browser | Driver-chosen system Google Chrome 151.0.7922.71 (Chromium 151.0.7922.173 also installed), read in session at start and end | SOURCE |
| Environment | One Linux host shared with other tracks; `bin/hostless` around every code-executing command; `cua-x11-session.sh` private rootless Xvfb + private dbus; 0-3 s start jitter + `xdpyinfo` probe before each session; 1-min loadavg at trial start median 2.1-2.2, max 3.9 per arm | SOURCE |
| Base / harness | branch from `eab1e87a3` (B-07 packet head); first commit `ce27df80e` copies B-06's harness from `31bc98a95` blob-identically (blob ids in provenance.json); every later change is a reviewed diff (`git log -p`) | SOURCE |
| PREREG commit | `f577426fe` at 2026-10-03T13:22:06Z, before the first measured trial (first measured chunk started 13:44:54Z). Never amended | SOURCE |
| Live heads | start 13:15Z and end 14:04Z: trycua/cua main `c8edda06b` both times (33 commits ahead of 0f1955d2f; its libs/cua-driver changes are platform-macos, platform-windows, the AppKit/WinUI3/WPF e2e harness tests, Skills docs, macOS/Windows fixtures, `tests/fixtures/shared`, release-version files and the Python/TypeScript packaging; nothing in cua-driver-core, platform-linux or jev-use); trycua/cua PR 4316 `a0bca7440`, open, unchanged | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); never equal-by-assumption to the tested SHA | SOURCE |
| Provider | none (scripted chooser); TypeSafe cap 0: 0 attempts, 0 reached | NOT_RUN |

## Method

- **Arms.** C (cold: the task document is the process's first); Wa and Wb (warm A/A: outside T, `browser_navigate`
  to B-04's matched-content sibling page plus one semantic_v2 snapshot, timed separately, then the task navigate in
  the same tab, Driver and Chrome); P2 (Wa plus a 15.0 ms CLOCK_MONOTONIC sleep inside T right after snapshot1
  returns; measured 15.0001 ms median, maximum 15.0009); SMOKE (product default, cold).
- **Design.** A 4x4 Williams square over C/Wa/Wb/P2, 32 rounds per class (8 squares), class order rotated per
  round, so every contrast has 32 pairs per class. SMOKE at the end of rounds 0-4, N-W2 at the end of rounds 5-7.
  384 measured + 15 smoke + 3 N-W2 trials; no round was cut, so every round ran in attempt 1.
- **Load rule.** A round starts only at 1-min loadavg ≤ 4.0 (1 s polls, ≤ 60 s, else the chunk ends with exit 75).
  No chunk ended on it; some rounds waited inside the window (every check is in the manifests). Every trial started
  at ≤ 4.0, so the load-sensitivity view equals the main view (32/32 rounds kept per class).
- **Locks.** Each measured chunk: one EXCLUSIVE `bin/quiet-timed b08-<chunk>` acquisition, then the cargo-build lock
  tried inside it with `flock -w 60` (exit 74 = not acquired, nothing ran, retry later), `timeout 600` around
  everything inside. Pilot, version reads, analyzer and headline writer ran under the SHARED lock with receipts.
- **Statistics.** Paired within-round differences of T_j; median; percentile bootstrap, 10 000 resamples, a fresh
  `random.Random(20261003)` per contrast, 95% CI.
- **Commands** (machine paths from the environment, never the packet): `hostless python3 lane-scripts/run_all.py`
  (drives `lane-scripts/run-chunk.sh` → `session-retry.sh` → `cua-x11-session.sh` → `in-session.sh` → `run_b08.py`);
  `hostless bash lane-scripts/run-pilot.sh`; `hostless bash lane-scripts/shared-locked.sh <label> python3 analyze_b08.py`,
  then `make_headlines.py`, then `verify_artifacts.py`.

## Results (N of M, evidence class per row)

### Gates and verdict (PREREG.json, primary T_j, ms)

| class | NC Wa−Wb median [CI] (inside [-2, 2]) | PC2 P2−Wa median [CI] (in [12, 18], CI excl. 0) | validity C / Wa / Wb / P2 | E4 | D = C−Wa median [CI] | 5% of T_C | D' = C−Wb | verdict | evidence class |
|---|---|---|---|---|---|---|---|---|---|
| fill | Wa-Wb -0.11 [-0.47, 0.59] pass | P2-Wa 15.88 [15.10, 16.59] pass | C 32/32, Wa 32/32, Wb 32/32, P2 32/32 | 0 | D 10.58 [9.50, 11.41] | 3.08 (T_C 61.55) | D' 10.07 | fill: OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |
| toggle | Wa-Wb 0.26 [-0.70, 0.93] pass | P2-Wa 14.99 [14.24, 15.92] pass | C 32/32, Wa 32/32, Wb 32/32, P2 32/32 | 0 | D 3.05 [2.62, 5.38] | 2.43 (T_C 48.52) | D' 3.64 | toggle: OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |
| modal | Wa-Wb -0.39 [-0.65, 0.49] pass | P2-Wa 14.94 [14.37, 15.35] pass | C 32/32, Wa 32/32, Wb 32/32, P2 32/32 | 0 | D 4.56 [2.98, 5.92] | 2.43 (T_C 48.59) | D' 4.64 | modal: OWNER_DECISION | BENCHMARK+REAL (FIXTURE) |

OWNER_DECISION needs CI(D) lower bound > 1.0 ms and median D ≥ 5% of T_C (or ≥ 50 ms). In every class the CI
lower bound itself is above 5% of T_C (toggle, the closest: 2.62 against 2.43), so the verdict does not hang on
the point estimate.

Median T_j per arm, ms: fill C 61.55, Wa 51.37, Wb 51.29, P2 67.34; toggle C 48.52, Wa 44.31, Wb 44.20,
P2 59.46; modal C 48.59, Wa 44.16, Wb 44.06, P2 58.89. Evidence class: BENCHMARK+REAL (FIXTURE).

Secondary (2 ms sampler T_oracle, same pairs; reported, not gated): fill D 10.01 [9.99, 11.99], NC 0.00
[-0.03, 0.01], PC2 16.00 [15.91, 16.17]; toggle D 3.92 [2.11, 5.74], NC -0.01 [-0.14, 0.20], PC2 15.86
[14.03, 15.98]; modal D 4.42 [3.81, 5.96], NC -0.01 [-0.14, 0.17], PC2 15.06 [14.01, 15.92]. The verdicts would
be the same. Agreement check: agreement 100.0% (384/384 within 2.5 ms; median |T_j − T_oracle| 0.69 ms,
maximum 1.91 ms). Evidence class: BENCHMARK+REAL (FIXTURE).

### Cold vs warm attribution (snapshot1 phase marks, median ms; descriptive)

| class | arm | attach | DOM.getDocument | AX tree | E = span(s1) − span(s2) | evidence class |
|---|---|---|---|---|---|---|
| fill | C | 2.58 | 7.62 | 3.84 | E(C) 14.21 | BENCHMARK+REAL (FIXTURE) |
| fill | Wa | 2.20 | 2.06 | 0.86 | E(Wa) 4.19 | BENCHMARK+REAL (FIXTURE) |
| toggle | C | 2.21 | 4.50 | 0.77 | E(C) 7.57 | BENCHMARK+REAL (FIXTURE) |
| toggle | Wa | 2.04 | 1.46 | 0.49 | E(Wa) 3.42 | BENCHMARK+REAL (FIXTURE) |
| modal | C | 2.22 | 4.40 | 0.68 | E(C) 6.95 | BENCHMARK+REAL (FIXTURE) |
| modal | Wa | 1.93 | 1.43 | 0.45 | E(Wa) 2.91 | BENCHMARK+REAL (FIXTURE) |

The per-process excess sits mostly in the first DOM.getDocument and AX-tree fetch of a fresh process (the CDP
session attach is about the same cold and warm). A warm process still pays a per-document first-snapshot excess
(E(Wa)), which is B-04's IRREDUCIBLE part. Warm-up cost outside T (median): fill warm-up 37.7, toggle
warm-up 30.1, modal warm-up 29.6 ms.

### Controls

| control | n | result | evidence class |
|---|---|---|---|
| NC A/A (Wa − Wb) | 32 pairs per class | CI inside [-2, 2] ms in every class (table above) | BENCHMARK+REAL (FIXTURE) |
| PC2 (P2 − Wa, 15.0 ms after snapshot1) | 32 pairs per class | median in [12, 18] and CI excludes 0 in every class | BENCHMARK+REAL (FIXTURE) |
| FIX-01 N-W2 (node replaced between snapshot and action) | 1 per class | 3/3 pass: stale action `effect: refused`, code `browser_ref_stale`, 0 detached effects (0 completion mutations from it), marker visible in a fresh snapshot, re-derived action verified with exactly one completion mutation | REAL (FIXTURE) |
| SMOKE (product default: feedback on, no `CUA_DRIVER_EXP_*`, 0 skip marks), cold | 5 per class | fill smoke 5/5, toggle smoke 5/5, modal smoke 5/5 verified | REAL (FIXTURE) |
| E4 per arm (C, Wa, Wb, P2, SMOKE) | 399 trials | stale dispatch 0, ambiguous dispatch 0, duplicate mutation 0, unverified success 0, blind replay 0, refusal returned as success 0, non-loopback connect 0: E4 total 0 | REAL (FIXTURE) |

### Part E: one-binary E2 re-read (BENCHMARK analysis of this lane's C and Wa arms only)

Decomposition of mean T_runner (R2-10's T: snapshot1 send → verified oracle read) into R2-10's e2_components plus
the B-05/B-07 transport sub-spans, with PREREG.json's verdict map. The primary view is corrected for the trace marks
at this lane's own per-mark cost, c_m = 31.72 us (median of 3072 in-situ null-pair intervals); the raw view is
secondary. Sub-spans add up to R2-10's components exactly (maximum deviation 0.0 ms per trial); B-05 coverage
1.0 and R2-10 coverage ≥ 0.983 in every trial; 32/32 trials per arm per class decomposed, none excluded.

Cold carve-out inside `observation`: E(Wa) is the per-document part (IRREDUCIBLE, B-04); in C the per-process part
is max(0, mean E(C) − mean E(Wa)): fill per-process 12.37 ms, toggle per-process 4.29 ms, modal
per-process 4.41 ms, with this lane's verdict (OWNER_DECISION).

Untested share of mean T_runner (BG = BELOW_GATE counted as IRREDUCIBLE / as UNTESTED):

| class | C (fresh process), corrected | C, raw | Wa, corrected | Wa, raw | mean T (corr) | evidence class |
|---|---|---|---|---|---|---|
| fill | C corr BG=IRR 16.9% / C corr BG=UNT 19.0% | C raw BG=IRR 15.4% / C raw BG=UNT 21.9% | Wa corr BG=IRR 20.3% / Wa corr BG=UNT 22.8% | Wa raw BG=IRR 18.1% / Wa raw BG=UNT 25.8% | mean T C 67.48 / mean T Wa 53.48 | BENCHMARK (REAL raw) |
| toggle | C corr BG=IRR 0.4% / C corr BG=UNT 3.6% | C raw BG=IRR 0.5% / C raw BG=UNT 10.1% | Wa corr BG=IRR 0.5% / Wa corr BG=UNT 3.6% | Wa raw BG=IRR 0.5% / Wa raw BG=UNT 10.7% | mean T C 41.01 / mean T Wa 36.96 | BENCHMARK (REAL raw) |
| modal | C corr BG=IRR 0.4% / C corr BG=UNT 3.3% | C raw BG=IRR 0.4% / C raw BG=UNT 9.8% | Wa corr BG=IRR 0.4% / Wa corr BG=UNT 3.8% | Wa raw BG=IRR 0.5% / Wa raw BG=UNT 10.9% | mean T C 41.18 / mean T Wa 36.56 | BENCHMARK (REAL raw) |

What stays untested (corrected, BG counted as IRREDUCIBLE):
- toggle / modal: only the runner gaps (0.13-0.15 ms), the mock decision (0.01 ms) and an unattributed sliver.
- fill: `runner` 9.82 ms, `input_prep` 0.95 ms, c_in.prep 0.59 ms (UNTESTED on fill by rule: B-07's fragile
  DELETED is not carried).
- Fill's `runner` is not harness overhead in the usual sense. It is the compiled routine's 10 ms verify-poll
  sleep after the first not-yet-verified read (unmarked poll 10.23 ms per C trial, post hoc; B-04's harness stamps the
  reads but not the sleep). If it is counted as a poll (`sleeps_polls`, IRREDUCIBLE in R2-10's map), fill's C
  share would be post-hoc fill C BG=IRR 2.3% and post-hoc fill C BG=UNT 4.4%. This is descriptive only, not the
  pre-registered result (Deviation 4).

Components ≥ 5% of mean T or ≥ 50 ms (corrected view), with verdict and source lane:

| class / arm | component (mean ms, share) → verdict [source] | evidence class |
|---|---|---|
| fill C | reval_endpoint 20.41 (30.2%) → OWNER_DECISION [B-02 H_E]; cold per-process 12.37 (18.3%) → OWNER_DECISION [B-08]; runner 9.82 (14.5%) → UNTESTED [R2-10]; observation rest 5.24 (7.8%) → IRREDUCIBLE [B-04]; cold per-document 4.44 (6.6%) → IRREDUCIBLE [B-04, SOURCE carry] | BENCHMARK |
| fill Wa | reval_endpoint 20.52 (38.4%) → OWNER_DECISION [B-02 H_E]; runner 9.41 (17.6%) → UNTESTED [R2-10]; observation rest 5.19 (9.7%) → IRREDUCIBLE [B-04]; cold per-document 4.44 (8.3%) → IRREDUCIBLE [B-04]; dispatch 2.92 (5.5%) → IRREDUCIBLE [R2-10]; mcp_transport 2.82 (5.3%) → per sub-span (largest d_out.post 0.87 IRREDUCIBLE [B-07]) | BENCHMARK |
| toggle C | reval_endpoint 20.47 (49.9%) → OWNER_DECISION [B-02 H_E]; cold per-process 4.29 (10.4%) → OWNER_DECISION [B-08]; observation rest 3.62 (8.8%) → IRREDUCIBLE [B-04]; cold per-document 3.58 (8.7%) → IRREDUCIBLE [B-04]; mcp_transport 2.47 (6.0%) → per sub-span (c_in.prep 0.61 IRREDUCIBLE [B-07], d_out.post 0.57 IRREDUCIBLE [B-07], c_out.route 0.35 BELOW_GATE) | BENCHMARK |
| toggle Wa | reval_endpoint 20.43 (55.3%) → OWNER_DECISION; observation rest 3.74 (10.1%) → IRREDUCIBLE; cold per-document 3.58 (9.7%) → IRREDUCIBLE; mcp_transport 2.26 (6.1%) → per sub-span | BENCHMARK |
| modal C | reval_endpoint 20.47 (49.7%) → OWNER_DECISION [B-02 H_E]; cold per-process 4.41 (10.7%) → OWNER_DECISION [B-08]; observation rest 4.26 (10.3%) → IRREDUCIBLE [B-04]; cold per-document 2.99 (7.3%) → IRREDUCIBLE [B-04]; mcp_transport 2.38 (5.8%) → per sub-span (d_out.post 0.62, c_in.prep 0.60 IRREDUCIBLE [B-07]) | BENCHMARK |
| modal Wa | reval_endpoint 20.41 (55.8%) → OWNER_DECISION; observation rest 4.21 (11.5%) → IRREDUCIBLE; cold per-document 2.99 (8.2%) → IRREDUCIBLE; mcp_transport 2.42 (6.6%) → per sub-span | BENCHMARK |

No single transport sub-span reaches 5% or 50 ms; the largest is d_out.post at 0.87 ms (IRREDUCIBLE, B-07). No
carried BELOW_GATE unit reaches B-07's 0.5 ms gate in this lane (`below_gate_carried_with_corr_mean_ge_0_5ms` is
empty in every class and arm). The admission tools-list cache is DELETED and already on: the re-validation it
removes is not in T (every in-T call carries `mcp.inner_validation_skipped`). Nothing here is added to or ratioed
with another lane's or binary's numbers.

## Work deleted vs wall-clock saved

| item | work deleted | wall-clock saved | evidence class |
|---|---|---|---|
| process / session reuse with the warm-up kept outside T (owner policy; not built, not endorsed here) | nothing in the product (no knob, no change). Mechanism: a reused process skips the cold first DOM.getDocument / AX-tree fetch of a fresh process | per task, median paired T_j: fill D 10.58, toggle D 3.05, modal D 4.56 ms; the warm-up it presupposes costs 37.7 / 30.1 / 29.6 ms outside T | BENCHMARK+REAL (FIXTURE) |
| this lane | none (measurement only; existing env-gated, default-off phase trace plus caller stamps) | none | SOURCE |

## Disposition

Disposition: KEEP. Every class reached a terminal per-process verdict (OWNER_DECISION in fill, toggle and
modal), NC and PC2 passed everywhere, validity 384/384, SMOKE 15/15, N-W2 3/3, E4 total 0.

- **E2:** the browser per-process cold excess is terminal on B7 (OWNER_DECISION, sized D above). With B-07's
  transport verdicts on the same binary, toggle and modal are below 5% untested in both BELOW_GATE views (C,
  corrected). Fill is not, under the pre-registered labels: its remaining untested time is the unmarked compiled
  routine poll (descriptively a poll). Closing it needs a run whose harness stamps the routine's verify sleep
  (R2-10R's harness does); this lane does not re-label it.
- **E1:** the B-04 / B-06 lineage ends here with a pre-registered terminal verdict. Per-document part:
  IRREDUCIBLE (B-04). Per-process part: OWNER_DECISION in all three classes.
- **E4:** 0 in every arm.

## Deviations and disclosures

1. **Telemetry value.** The spec says `CUA_DRIVER_RS_TELEMETRY_ENABLED=false` "as in B-07"; B-07 actually set `0`.
   This lane sets `false` (in `CUA_SESSION_EXTRA_ENV` and in the Driver environment). The Driver's
   `parse_env_bool` reads both as off. B-04's row validity checks the string `0`, so `b08_rows.py` re-states the
   same validity terms with `false`.
2. **Chunk driver after PREREG.** `lane-scripts/run_all.py` was committed (`88e51e1d3`, 13:23Z) after the PREREG
   commit and before the first measured trial. It is bookkeeping only:
   - it waits on the host for loadavg ≤ 4.0 before taking the lock (the runner's pre-registered rule still decides);
   - it retries exit 74 / 75;
   - it renames each manifest with its try number (`-kN`) so a retry cannot overwrite it.
3. **Cargo-lock misses.** Tries k1-k3 ended with exit 74: another track's Driver build held the cargo-build lock.
   Nothing ran in them; each held the EXCLUSIVE quiet lock for 60 s (ledger lines kept in `raw/lock-ledger.jsonl`).
4. **Post-hoc descriptive field (fill runner).** After the data, `analyze_b08.py` gained
   `post_hoc_unmarked_verify_poll`: the in-T gap between a routine read that did not verify and the next read,
   bounded by the runner component. It is documentation only. No gate, verdict or pre-registered share uses it.
5. **SMOKE has the phase trace on.** As in B-06, the trace file is set in SMOKE so the 0-skip-mark receipt can be
   checked. That is measurement-only and default-off; SMOKE is correctness-only.
6. **E4 definitions.** "Ambiguous dispatch" and "blind replay" are defined in PREREG.json for B-04-format records
   (no counter is in B-04's code). Both were 0.
7. **Pilot.** 28 trials (rounds 0 and 5 of the plan, SHARED lock, load rule off) ran before PREREG. The analyzer ran
   once on them to check the pipeline. They are excluded from every number (`raw/pilot-trials.tar.gz`).
8. **Packet helpers.** `verify_helper.py` and `.gitignore` are blob-identical copies from the B-07 packet
   (themselves from the PKT-01 template), not from B-06.
9. **PREREG commit rewrite before data.** The PREREG commit was amended once (13:22Z, before any measured trial)
   to stop `package_raw.py` from spelling a session-bus socket prefix literally (privacy scan hit). The branch was
   unpublished.

Near misses: none. Every code-executing command (Python, Driver, Chrome, analyzer, verifier) ran under `bin/hostless`;
browser and Driver work ran only inside the private Xvfb session. The plain host shell ran git, read-only `gh`,
file reads/edits, `ps` / `/proc` reads and the instructed host `sha256sum` of the binary. Hard-rule breaches: none.

## Limits and claim boundary

- One shared host, private Xvfb, Driver-chosen system Chrome 151.0.7922.71, binary B7 only, tested source
  `ac319cbe9`, scripted chooser, TypeSafe not used.
- The verdict covers process reuse outside T for a single task. It does not design or endorse a warm pool, a
  session lifecycle or any new service. No Driver behaviour change; the instrumentation is the existing env-gated,
  default-off phase trace plus caller-side stamps.
- Absolute T is not compared with B-06 or R2-10R (different binaries); B-07's labels, not its numbers, are carried.
- Part E rests on 32 trials per arm per class, and the corrected view depends on c_m (B-07 found the correction
  over-subtracts; the raw view is reported next to it).
- Upstream main moved before this lane (0f1955d2f → c8edda06b), but not on the Linux browser path. It did not move
  during the lane.

## Files

- **Pre-registration and results:** `PREREG.json`, `b08-summary.json` (recomputed from raw/ by `analyze_b08.py`),
  `headline-numbers.json` (`make_headlines.py`), `provenance.json`.
- **Verifier:** `verify_artifacts.py` (`hostless python3 verify_artifacts.py`; set CUA_PRIVACY_NAMES_FILE to an
  untracked names file), `verify_helper.py`.
- **Lane code:** `run_b08.py`, `b08_rows.py`, `analyze_b08.py`, `make_headlines.py`, `r10r_observation.py` (copied,
  unused here), `lane-scripts/run-chunk.sh`, `lane-scripts/run-pilot.sh`, `lane-scripts/run_all.py`,
  `lane-scripts/session-retry.sh`, `lane-scripts/in-session.sh`, `lane-scripts/shared-locked.sh`,
  `lane-scripts/package_raw.py`.
- **Harness copies:** `harness/b04/` (B-04 runner, from 31bc98a95), `harness/r2-10r/r2_10_browser.py`,
  `harness/r2-10r/scripted-COMP.json`, `harness/b07/b07_stdio.py`, `harness/b05/b05_spans.py`,
  `harness/r2-10r/analyze_r2_10.py`, `harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/b01_analysis.py`,
  `harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/analyze_browser.py`.
- **Raw:** `raw/main-trials.tar.gz` (399 trial records + Driver traces), `raw/pilot-trials.tar.gz` (excluded),
  `raw/main/run-manifest-main-m-a1-r00-09-k4.json`, `raw/main/run-manifest-main-m-a1-r10-19-k5.json`,
  `raw/main/run-manifest-main-m-a1-r20-29-k6.json`, `raw/main/run-manifest-main-m-a1-r30-31-k7.json`,
  `raw/pilot/run-manifest-pilot-pilot-a1-r00-05.json`, `raw/lock-ledger.jsonl`, `raw/logs/versions-start.log`,
  `raw/logs/versions-end.log`, `raw/logs/b08-run_all.log`, `raw/logs/b08-main-a1-r00-09-k4.log` (and the other
  chunk logs in `raw/logs/`).
