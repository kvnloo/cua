# R2-07f: compiled replay toggle/modal on B7, scripted BASE vs COMP vs COMP+CR, one-binary decomposition and E3, 2026-10-03

Lane R2-07f, wave 7 of the CUA RFC loop. Owners: kvnloo/cua#93 (R2-07, R2-10), kvnloo/cua#10 (whole-task
accounting), kvnloo/cua#73 (E2/E3). Lineage: R2-07c/R2-07d/R2-07e (branch `exp/r2-07e-modal-gate-phase-l-20261003`,
67b99ddc6) for the compiled toggle/modal routine, and B-08 (branch `exp/b-08-per-process-cold-b7-20261003`, 49ae94590)
for binary B7, the B-07 stamped stdio client and the B-05 sub-span decomposition. Upstream items are named as plain
text (trycua/cua PR 4316).

## Result in one paragraph

**Disposition: BLOCKED.** No measured trial ran. The pre-registration (PREREG.json, commit a0d9ebff9) and the
harness are committed, unit tests pass 12/12, and the SHARED-lock pilot showed the R2-07c runner works on B7
(pilot 9/9 trial records valid). The measured block needs the EXCLUSIVE quiet-lane lock (`bin/quiet-timed`). The
lane queued for it at 16:14:44Z and never got it. The quiet-lane lock was held SHARED the whole time by long-lived
processes of another track on the machine. They had inherited the lock's file descriptor from a `flock -s` wrapper
and kept running after their command ended. At 17:20Z four exclusive waiters were starved (this lane and three others), with 13 shared locks held. At the final
check (17:42Z, after this lane and one other lane had stopped waiting): 2 exclusive waiters, 12 shared locks held,
last exclusive receipt 2026-10-03T14:11:00.905Z. The oldest holder had been running for about 2 h 43 min. This
lane waited 1 h 28 min in the queue. This lane did not
signal or kill those processes (it did not start them). It also did not measure under the SHARED lock, because a
reported number taken outside the exclusive quiet lane is a hard-rule breach. E2/E3/E1 for this row stay open. The
blocker is infrastructure: the quiet-lane lock must be freed (the leaked holders exit, or their owner releases them).
After that, the committed plan runs unchanged (`driver/loop_f.sh`: train -> main -> fallback -> controls). Provider:
TypeSafe cap 0, 0 attempts / 0 reached.

## Headline (evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| Pilot (SHARED, store `pilot`, excluded) | 9 of 9 | pilot 9/9 trial records valid; trainings admitted, authority scan clean; CRa 0 decisions, routes `compiled`; PC sleep placed after snapshot1; B-07 caller stamps present; B-05 decomposition consistency 0.0 ms, coverage 1.0 | REAL (FIXTURE), pipeline check only |
| Unit (`driver/test_r2_07f.py`) | 12 of 12 | Williams balance, 40-round plan, load gate, PC sleep, bootstrap determinism, T_j / PC order | UNIT |
| Quiet-lane EXCLUSIVE acquisition (queued 16:14:44Z-17:42Z) | 0 of 1 | 2 exclusive waiters, 12 shared locks held, last exclusive receipt 2026-10-03T14:11:00.905Z | BLOCKED |
| Training + compile + admission (EXCLUSIVE) | 0 of 2 | not run (waiting for the lock) | BLOCKED |
| Measured Williams block BASE/COMP/CRa/CRb/PC, 40 rounds x 2 classes | 0 of 400 | not run | BLOCKED |
| Forced fallback n7_presat (EXCLUSIVE) | 0 of 6 | not run | BLOCKED |
| Controls N4a, N4b, N5, N8, N-W2, N1, default smoke (SHARED, after the measured block) | 0 of 36 | not run (they follow the measured block and need its admitted artifacts) | NOT_RUN |
| G0-G4, H_CR, S_E3, H_D, amortized cost | - | not computed (no measured trial) | BLOCKED |
| E4 | pilot only | E4 total 0 | REAL (FIXTURE) |
| Provider | 0 / 0 | TypeSafe cap 0; no key forwarded | NOT_RUN |

## The five mechanism requirements (as pre-registered, and what was exercised)

| Requirement | Pre-registered (PREREG.json) | Exercised here | Evidence class |
|---|---|---|---|
| Forced path | BASE = R2-10 BASE (feedback on, default motion, no guard, 100 ms poll, library validators); COMP = R2-10 scripted COMP step loop (`r2_07c.one_comp`; feedback off, 10 ms poll, compiled validators, admission tools cache, phase trace, scripted chooser, telemetry off, no key); CRa/CRb = COMP + compiled fresh-bound replay of the admitted artifact (`r2_07c.one_c`, kind warm); PC = CRa + 15.0 ms inside T after snapshot1 | pilot only: one trial each of BASE, COMP, CRa, PC on toggle and CRa on modal, all on B7 | REAL (pilot) |
| Actual route / producer | Receipts: `browser_click` route `dom`, input route `dom_event`, `click.cdp_send` in the call window; decision routes `provider` (BASE/COMP, scripted) vs `compiled` (CR, 0 decisions) | pilot: as pre-registered | REAL (pilot) |
| Independent target-owned oracle | kvnloo/cua#24 pages via the jev-use fixture server, exactly one completion mutation in the CLOCK_MONOTONIC journal; T_runner primary, T_oracle (2 ms sampler) and T_j secondary | pilot: 9/9 exact oracle, 1 completion mutation each | REAL (pilot) |
| Negative / fallback controls | NC A/A (CRa vs CRb), PC (+15 ms), N4a, N4b, N5, N8, N-W2, n7_presat forced fallback, N1, default smoke | not run | BLOCKED / NOT_RUN |
| Exact provenance | below | below | SOURCE |

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Branch / base | `exp/r2-07f-compiled-replay-b7-decomp-20261003` from 67b99ddc6a66a217c76dc491977de78180434751 (R2-07e packet head). The R2-07c, R2-07d and R2-07e packet trees are unchanged at every commit | SOURCE |
| Copied blob-identically | from 49ae94590 (B-08), commit ffa4cebfe: `b08/harness/b07/b07_stdio.py`, `b08/harness/b05/b05_spans.py`, `b08/harness/b04/b04_rows.py`, `b08/harness/r2-10r/analyze_r2_10.py` and the two B-02 analysis modules; blob ids in `provenance.json` | SOURCE |
| PREREG commit | a0d9ebff9 at 2026-10-03T16:14:17Z, after the pilot (16:05-16:13Z) and before any measured trial (none ran) | SOURCE |
| Tested Driver source | ac319cbe90d6cdf0cc8cd8984f99f5b04b68fdac (B7 source). No build | SOURCE |
| Driver binary | B7 `cua-driver-b07-231f6e8bb`, sha256 `6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa`, `cua-driver 0.32.0`. Hashed on the host under hostless at the start and end of the lane (identical) and read inside the session at the start and end (`raw/ident/`). Every pilot record and manifest carries name, sha256 and version; the runner refuses on a mismatch | SOURCE / REAL |
| Browser | Driver-chosen Google Chrome 151.0.7922.71, read in the session | SOURCE |
| Environment | One shared Linux host. Every code-executing command for trials and analysis ran under `hostless`; Driver and Chrome ran only inside `cua-x11-session.sh` (private Xvfb + D-Bus, `xdpyinfo` probe first) | SOURCE |
| Live heads | start 16:14:41Z: trycua/cua main `9a2b1d99ec8044ff58b2a2b46802edd2609c057b`; end 17:42:24Z: `6348741accb5e689c789e26cb92119c947a8df52` (5 commits later, 6 libs/cua-driver files, none in cua-driver-core, platform-linux or jev-use). Since the B7 base line 0f1955d2f, upstream main touched cua-driver-core `expectation.rs` (trycua/cua PR 4531, macOS verify_state) and platform-linux `overlay.rs` (trycua/cua PR 4529, idle X11 cursor overlays unmapped: relevant to the feedback/visualization path, to recertify if a later run uses a newer binary). trycua/cua PR 4316 head `a0bca744067d04f05904319d3d919be30c336556`, open, unchanged at start and end | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`) | SOURCE |
| Provider | none; TypeSafe cap 0: 0 attempts, 0 reached | NOT_RUN |

## Method (pre-registered; unchanged, ready to run)

- **Design.** Five arms in a Williams design for an odd number of arms (10 sequences: the cyclic rows plus their
  reversals), 40 rounds per class, so every contrast has 40 within-round pairs. Class order alternates per round.
  Each trial gets a fresh Driver, fresh Driver-launched Chrome (isolated_new, sandbox on), fresh fixture servers,
  token and session label.
- **Training.** Per class, one scripted training + compile + clean-reset admission into the lane-local store
  `timed-f` before round 0, EXCLUSIVE and timed. The authority scan runs on every artifact.
- **Locks.** Every measured chunk checks that the cargo-build lock is free, then runs EXCLUSIVE
  `bin/quiet-timed r207f-<chunk>`. Inside it, `flock -w 60` takes the cargo-build lock, with `timeout 900`. A round
  starts only at 1-min loadavg <= 4.0.
- **Gates.** G0 validity >= 95% per arm with identical outcomes. G1: CRa - CRb CI contains 0 and |median| <= 1.5 ms.
  G2: PC - CRa CI inside [12, 18] ms. G3: warm decisions, fallbacks and provider attempts all 0. G4: E4 = 0.
  H_CR: CRa - COMP CI upper <= +2.0 ms with all 40 pairs run. S_E3 = median T(BASE) / median T(CRa) with CI
  lower > 1; the amortized mean is reported separately. H_D uses the B-08 Part E decomposition with the
  verdict map in PREREG.json.
- **Commands** (machine paths come from the environment, never the packet): `hostless driver/loop_f.sh <plan> <lock>
  <out> ...` (drives `driver/run_chunk_f.sh` -> `cua-x11-session.sh` -> R2-07d `probe_then.sh` -> R2-07c
  `in_session.sh` -> `driver/r2_07f.py`); `hostless python driver/package_f.py`; `hostless python analyze_r2_07f.py`;
  `hostless python verify_artifacts.py`.

## Lock-wedge evidence (BLOCKED row)

`raw/lock-wedge.jsonl` holds counts only: no process names, paths or ids from the other track. Each line has the
shared locks held on the quiet-lane lock, the exclusive waiters, the number of fd holders, the oldest holder's age
and the last exclusive receipt in the quiet-lane ledger. `raw/lock-receipts-global.jsonl` holds this lane's shared
receipts (identity read, pilot). The ledger shows no `bin/quiet-timed` (EXCLUSIVE) receipt from any lane after
2026-10-03T14:11:00Z. The queued waiter of this lane was stopped by the lane (its own process) at the end.

## Work deleted vs wall-clock saved

Not measured in this lane (BLOCKED). The warm-path work deletion is carried as a cited verdict and is not added to
B7 numbers. R2-07e Part L (binary R, LIVE_PROVIDER) found 0 decisions on warm admitted COMP+CR, against 2 per
COMP invocation.

## Deviations

1. The pilot ran three shared chunks that ended on the runner's load gate (exit 75) before it completed. Its
   records are excluded and its timing is not reported (loadavg up to 14).
2. The first in-session identity read (16:01:55Z, shared receipt `r207f-ident-start`) failed with rc 1 because the Driver
   path was relative to the session cwd; it was re-run with an absolute path (`r207f-ident-start2`). The three
   manual pilot chunks used chunk ids p1-p3 under the lock labels `r207f-pilot-1..3`; the verifier maps them.
3. Nothing after PREREG ran. No amendment was made. The queued EXCLUSIVE waiter was stopped by the lane at
   17:42Z (its own process; it never acquired the lock, so it left no receipt).
4. The first line of `raw/lock-wedge.jsonl` (17:20:00Z) counted 0 shared locks because its `/proc/locks` pattern was
   wrong (it also took the first holder found, not the oldest). It is kept as written; the next two lines
   (17:20:12Z, 17:42:14Z) use the corrected pattern, and the verifier reads the shared-lock count from them only.

## Limits and claim boundary

Scripted chooser and binary B7 only. No number in this packet is a timing result: the pilot was SHARED and is a
pipeline check. The live-path reading, training and fallback provider costs remain R2-07e's (binary R,
LIVE_PROVIDER), cited, never added to B7 numbers. No paired live S is claimed (BLOCKED on budget). The routine
stays caller-side: no new service, registry, router or engine.

## Files

| File | What |
|---|---|
| `README.md` | this file |
| `PREREG.json` | pre-registration (committed before any measured trial) |
| `provenance.json` | SHAs, copied blob ids, Driver identity, live heads |
| `r2-07f-summary.json` | analysis output (BLOCKED summary: pilot rows, lock-wedge evidence) |
| `headline-numbers.json` | headline numbers with the exact README text |
| `analyze_r2_07f.py` | analysis: every gate, S_E3, amortized cost, B-08 Part E decomposition; BLOCKED branch when no measured trial exists |
| `verify_artifacts.py` | identity, PREREG timing, summary recompute, headlines, authority scan, provider, Driver identity, lock evidence, tracked files, privacy of every commit (word-boundary matcher) |
| `driver/r2_07f.py` | caller-side runner over the unchanged R2-07c harness |
| `driver/run_chunk_f.sh` | lock order + private session wrapper |
| `driver/loop_f.sh` | chunk retry loop (bookkeeping only) |
| `driver/package_f.py` | packaging + privacy scan |
| `driver/test_r2_07f.py` | unit tests |
| `b08/` | blob-identical B-08 copies (stamped stdio client, phase-mark readers) |
| `raw/pilot-trials.tar.gz`, `raw/pilot-manifests/`, `raw/pilot-routines/`, `raw/pilot-load-gate.jsonl`, `raw/pilot-progress-pilot.json`, `raw/pilot-chunk-logs/`, `raw/pilot-loop.log` | pilot (excluded) |
| `raw/artifacts/` | the two pilot compiled artifacts (authority scan) |
| `raw/ident/` | in-session Driver/Chrome identity at start and end |
| `raw/host-hash.jsonl` | host (hostless) sha256 of B7 at start and end |
| `raw/lock-wedge.jsonl` | quiet-lane lock state, counts only |
| `raw/lock-receipts-global.jsonl`, `raw/lock-receipts-lane.jsonl` | quiet-lane ledger lines labelled `r207f-*`; lane ledger |
| `raw/unit/unit-r2-07f.txt` | unit test output |
| `raw/package-report.json` | packaging report |
