# OWN-75: exact-head validation of trycua/cua PR 4336 (native jev-use timing-field parity)

Owner rows: kvnloo/cua#75 (WAIT / promotion-only directive of 2026-10-01) and kvnloo/cua#10 (consumer only).
This packet resumes the wave-2 OWN-75 lane as lane OWN-75R (wave 3). It uses the committed PREREG
(`PREREG.json`, commit cd1878872, unchanged) plus `PREREG-AMENDMENT-1.json` (commit c1fe992b0). The
amendment was committed before any reported run of this lane. All 160 pre-registered REAL trials ran
fresh in this lane: t001-t100 in a first batch (17:25-18:24Z) and t101-t160 in a resumed batch
(18:49:42-19:52:24Z) after the first batch was stopped between blocks (Deviation D9).

**Disposition: KEEP** (pre-registered gates; see "Gates" below).

## What PR 4336 does, and what this packet checks

trycua/cua PR 4336 (head `8391cf802`) touches 7 files, all under `libs/cua-driver/examples/jev-use`.
The native runners `python/run_native.py` and `typescript/run_native.ts` now add the browser
runners' seven common timing fields to every step event: `semantic_observe_ms`, `visual_observe_ms`,
`candidate_build_ms`, `provider_decision_ms`, `decision_ms`, `action_ms` and `total_step_ms`. They
also add `visual_observe_scope: "parse_only"`. Every old native field (`observation.observe_ms`,
`visual.parse_ms`, `decide_ms`, `act_ms`) is kept. The PR also adds a contract fixture, a fake driver
and one parity test per language. It adds telemetry only: no `.rs` file, no Driver change and no new
service. The new fields are emitted unconditionally (not env-gated) by the example runners; they are
log fields only and change no behaviour (diff review plus the REAL identity result below).

The #75 directive says: validate the exact head, keep the old fields, keep
`visual_observe_scope=parse_only`, and behaviour must be identical once the timing fields are
stripped. Timing **values** are never results here, so this packet makes no timing claim.

## #73 mechanism requirements

| Requirement | This packet |
|---|---|
| Forced path | The jev-use native runners (Python and TypeScript, `--provider mock`) talk to the real Driver over MCP stdio, which drives AT-SPI on the canonical GTK3 fixture in task mode. A fresh fixture process and a fresh state file are used for every trial. |
| Actual route / producer | Runner step events (`events.jsonl.gz`) plus a transparent MCP tee (`harness/mcp_tee.py`, `mcp.jsonl.gz`) that logs every JSON-RPC line between runner and Driver without changing the bytes. Every action receipt reports `route=accessibility`, `delivery=background` (320/320 action receipts over the 160 trials). Tools called per trial, identical in both languages and both arms: choose-size `list_windows, get_window_state, click, get_window_state, click`; save-note `list_windows, get_window_state, set_value, get_window_state, click`. |
| Independent target-owned oracle | The fixture's own state file (`cua.gtk3_task_state_v1`, `pid` == the launched fixture). choose-size is verified iff `size == large` and `agreed == true`; save-note is verified iff `note_saved` == the note text. Runner outcome events are not the oracle. |
| Negative / fallback controls | (1) 16 pre-registered mutants (M1-M8 x 2 languages) must fail the PR's parity tests, and the 2 unmutated copies must pass. (2) M0 lacks every new field: discriminating, checked on every m0 step (160 steps, 80 trials). (3) The comparator check shows that a non-timing edit changes a digest and a timing edit does not. (4) Network-guard self-test: a deliberate TEST-NET connect from each runtime is refused in every block. |
| Exact provenance | `provenance.json`: PR head `8391cf80275d2a5e7288f9d7c6b0a3e5f7822939` (gh reads at start and end), M0 `2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4`, Driver `cua-driver-r2-main-229b65b28` sha256 `8b03796185055cc40c1a9ef0b2b4bbe9595a3eefa4f9a3aa64f34e5ce1974cd3` (hashed at start and end) with the version recorded per block, and upstream main `da46c4bc8` (merge-tree rc 0, no conflicts). |

## Provenance (all SHAs kept separate)

- **Live PR head:** trycua/cua PR 4336 = `8391cf80275d2a5e7288f9d7c6b0a3e5f7822939` (OPEN). Read with gh at 2026-10-02T17:18:53Z (start, `raw/provenance/pr-head-start.json`), at an interim read at 18:43:30Z before the resume, and at 2026-10-02T19:52:36Z (end, `raw/provenance/pr-head-end.json`); every read matches. The kvnloo/cua#75 body still cites the older head `d301a076c`. That drift is disclosed, and nothing here speaks for `d301a076c`.
- **Tested source, head arm:** `8391cf802` (jev-use tree `f3ba27c4`) on branch `exp/own-75r-timing-parity-4336-20261002`. The commits after `8391cf802` (cd1878872 PREREG, c1fe992b0 amendment, c7614a2dd tooling, and the packet commit) only add files under this directory.
- **Tested source, m0 arm:** `2ca90d338` = merge-base(PR head, upstream main), jev-use tree `635a4f58`.
- **GTK3 fixture:** blob `fa4b5ad3`, identical at head and m0.
- **Driver:** built from upstream main `229b65b28` (M0 is an ancestor; jev-use is identical between them). The same binary serves both arms. sha256 read at 17:19:13Z (start), 18:43:30Z (before the resume) and 2026-10-02T19:52:45Z (end); all equal the pinned value. `cua-driver 0.32.0` in all 16 blocks.
- **Upstream main freshness:** `da46c4bc8` (2026-10-02T10:25:37-07:00), which superseded `989cc76ce` cited in the amendment. `git merge-tree --write-tree da46c4bc8 8391cf802` returns rc 0 with tree `2641ae766`, no conflicts (the amendment's `989cc76ce` check gave rc 0, tree `e7fc835fc`). jev-use and the GTK3 fixture are unchanged on main since M0 (0 files). Main has changed 18 `libs/cua-driver` files since the binary's source `229b65b28`; none of them is in jev-use or the fixture. The REAL rows speak for the 229b65b28 Driver.
- **Publication SHA:** the branch tip that contains this README. The Publish agent records the pushed SHA.

## Environment

- **Wrapper:** every code-executing command of the measured runs ran under `bin/hostless` (v2: environment scrub + Landlock). Exceptions are the disclosed near misses (Deviation D3).
- **REAL session:** inside `cua-x11-session.sh`, a private rootless Xvfb (1920x1080x24, `-nolisten tcp`) with a private `dbus-run-session` bus, openbox + picom, and `at-spi-bus-launcher` + `at-spi2-registryd` started on that private bus. `AT_SPI_BUS_ADDRESS` is neither inherited nor exported (AT-SPI clients find the bus through `org.a11y.Bus` on the private session bus; Deviation D10). Extra session variables: `CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1`. The values each block actually saw are in `raw/real/session-env/`.
- **Runtimes:** jev-use `.venv` Python 3.12 and Node 22.23.2, installed by `lane-deps.sh` (`uv sync --frozen`, `npm ci --ignore-scripts`). The fixture ran on system Python + PyGObject.
- **Lock:** one `bin/quiet-timed` EXCLUSIVE quiet-lane acquisition per block of 10 trials (`harness/run_batch_qt.sh`). Packet receipts are in `raw/real/lock-ledger.jsonl`, and the matching shared-ledger lines are in `raw/real/quiet-lane-ledger-excerpt.jsonl`. The lock gives exclusivity among quiet-timed users only: host loadavg (1 min) during the trials was 3.16-23.85, so the windows were not quiet. That does not matter here, because no timing value is a result.
- **Provider:** TypeSafe 0 attempts / 0 reached. The chooser is `--provider mock` (deterministic `task.mock_preferences`).

## Results (N of M, evidence class per row)

| Row | Class | Result |
|---|---|---|
| S1 unit, head | UNIT | 7/7 commands rc 0: `python -m unittest discover` 231 tests (1 skipped: cua-s1 not installed), the 4 verify_* CLIs, `node --import tsx --test` 107/107, `tsc --noEmit`. The PR's 2 Python + 2 TypeScript parity tests ran and passed. |
| S1 unit, m0 | UNIT | 7/7 commands rc 0: Python 229 tests (1 skipped), TypeScript 105/105. The only test identities that differ from head are the PR's 4 parity tests. |
| S2 field contract, source | SOURCE | Line review of both runners (below). No PR-introduced cross-language mismatch. Two INHERITED asymmetries are named. |
| S2 field contract, unit | UNIT | The PR parity tests (counter and canvas scenarios on `fake_native_driver.py`) pass in both languages and catch every boundary mutant (S4). `parse_ms == visual_observe_ms` is covered by these UNIT tests only. |
| S2 field contract, REAL | REAL | Head: 160/160 step events carry all 7 common fields, `visual_observe_scope=parse_only`, `provider_decision_ms == decide_ms`, `action_ms == act_ms`, and the legacy `decide_ms`, `act_ms`, `observation.observe_ms`. m0: 160/160 steps carry the legacy fields and 0/160 carry any common field or the scope (the control discriminates). Step counts are equal between arms (160 vs 160). Visual status was `skipped` on every step, so `parse_ms` never occurred in REAL (0 steps). |
| S3 behaviour identity | REAL | 160/160 trials ran (80 head, 80 m0; 40 per cell), runner rc 0 and outcome `verified` in 160/160, 0 harness errors. Every cell has exactly one primary digest, shared by 20/20 head and 20/20 m0 trials: behaviour is identical after stripping the timing fields. KILL trigger: not met. |
| S3 oracle | REAL | Target-owned state file verified in 160/160 trials (40/40 per cell, 20/20 per arm per cell). |
| Trace-identity analysis (secondary: observation responses) | REAL | One secondary digest (normalized `get_window_state` / `list_windows` responses) per cell, 20/20 head and 20/20 m0. |
| S4 mutation | UNIT | 16/16 mutants detected (each by a test assertion, or by a KeyError on the dropped field for M2-py/M4-py), and none-py/none-ts pass. PREREG gate (M1, M2 in both languages): met. Amendment gate (all 16): met. |
| Network guard (runner processes only) | REAL | Armed in 160/160 trials, with 0 non-loopback connect attempts by a runner. The self-test refused 2/2 in 16/16 blocks. |
| Live provider | NOT_RUN | Cap 0. No TypeSafe request. |
| macOS / Windows / Wayland / canvas visual parse REAL | NOT_RUN | Outside the claim boundary. The visual-parse path is covered only by the fake-driver UNIT tests. |

### S3 per cell (primary trace = runner events + every client-to-Driver request + every action receipt + runner rc/outcome + oracle final state, after timing strip and id normalization)

| Cell | n head / m0 | Oracle verified head / m0 | Distinct primary digests | head / m0 matching the reference | Secondary digests | Reference primary digest |
|---|---|---|---|---|---|---|
| python:gtk3-choose-size | 20 / 20 | 20 / 20 | 1 | 20 / 20 | 1 | `4dd9a0e6face2075` |
| python:gtk3-save-note | 20 / 20 | 20 / 20 | 1 | 20 / 20 | 1 | `2fa3ffa39084f678` |
| typescript:gtk3-choose-size | 20 / 20 | 20 / 20 | 1 | 20 / 20 | 1 | `2b5661ec651e2032` |
| typescript:gtk3-save-note | 20 / 20 | 20 / 20 | 1 | 20 / 20 | 1 | `af57d5d7a696c2d8` |

Every cell has 10 AB + 10 BA pairs. Each pair is one head and one m0 trial run back to back in the same block, same session and same binary.

### S2 SOURCE review: named asymmetries

Both runners take the same measurements:
- They start one `started` timer per step and accumulate `semantic_observe_ms` around each `get_window_state` (the first call, plus the reobservation when it happens).
- `candidate_build_ms` covers source construction and every `task.plan` call: the preliminary plan inside `observe_step`, the one in the visual-fallback check, and the final plan.
- `visual_observe_ms` covers `parse_visual_regions` only, and is also counted on a failed parse. On success, the single `add_phase` return value feeds both `parse_ms` and `visual_observe_ms`.
- `provider_decision_ms` = `decide_ms`, `decision_ms` = step start through the validated in-scope choice, `action_ms` = `act_ms` (0 for reobserve), and `total_step_ms` = step start through the end of the action or the reobserve decision.

Rounding: Python rounds each phase with `round(x, 2)` before `decision_timing_fields`, and TypeScript rounds with `Math.round(x*100)/100` inside `decisionTimingFields`. That is the runners' existing per-language rounding convention, and it only differs at exact half-hundredths, so it is a value-level difference and not a span difference.

INHERITED (present at M0; does not trigger REVISE under the PREREG mismatch rule):
1. **INHERITED-A: decide_ms span.** TypeScript's `decide_ms`, and therefore `provider_decision_ms` because it is the alias, also spans `task.expectedNext(history)` and the build of the offered set. Python stops the decide timer right after the choice. This was already true at M0, and changing it would change an old field's meaning, which the directive forbids.
2. **INHERITED-B: preliminary plan count.** Python always runs one preliminary `task.plan` after the first observation. TypeScript runs it only when the tree is neither truncated nor complete, because of short-circuit evaluation in `needsReobserve`. The definition of `candidate_build_ms` is the same in both languages; only the amount of work inside it differs. The PR README documents this.

No PR-introduced cross-language field mismatch was found, so the REVISE trigger does not fire.

## Work deleted vs wall-clock saved

None. This PR is measurement-only: it deletes no work and claims no wall-clock saving. Its value for kvnloo/cua#10 is that native logs can be compared field by field with browser logs. It adds a small `perf_counter`/`performance.now()` bookkeeping cost per phase. That cost was not measured as a result.

## Gates (pre-registered) and disposition

- KEEP needs all of: S1 passes; every cell has one primary digest (20/20 head and 20/20 m0); the oracle verifies 40/40 per cell; the S2 field checks hold on every head step; the S4 gate holds (amendment: all 16 mutants).
- REVISE: a PR-introduced Python-vs-TypeScript field-semantics mismatch.
- KILL: any primary-trace or oracle difference between head and m0.

**Result: KEEP.** S1 passes in both arms (7/7 commands rc 0 each). Every cell has one primary digest (20/20 head, 20/20 m0) and the oracle verifies 40/40 per cell. The S2 field checks hold on 160/160 head steps, and m0 has no new field on any step. S4: 16/16 mutants caught and both controls pass. No PR-introduced cross-language field mismatch (REVISE does not fire); no head-vs-m0 difference (KILL does not fire). `verify_artifacts.py`: 112/112 checks pass.

## Deviations

D1-D8 are disclosed in PREREG-AMENDMENT-1.json (committed before any reported run). D9-D14 happened after it and are disclosed here.

1. **D1 Aborted wave-2 attempt.** 42/160 REAL trials ran (all verified) and were stopped by a host-isolation breach at 2026-10-02T04:51:47Z, which happened outside the REAL harness. None of that data is used. Its m05 lock was acquired and never released. All 160 trials were re-run.
2. **D2 PREREG timestamp.** `written_utc` says 04:50Z, but the commit time is 04:46:25Z.
3. **D3 Near misses.**
   - Missing from the wave-2 report: 04:41:15Z, `zcat | python3` in the host shell.
   - This lane: about 17:17Z, `python3 -c 1` in the host shell, a no-op that could not reach the desktop.
4. **D4 Network claim scope.** The "0 non-loopback connects" result covers the guarded runner processes only. Driver telemetry is disabled in both arms (the PREREG had said default); the Driver's own sockets are not monitored.
5. **D5 Provenance drift.** PR head `8391cf802` vs `d301a076c` in the kvnloo/cua#75 body.
6. **D6 Lock.** Each block ran as a `quiet-timed` EXCLUSIVE phase through `run_batch_qt.sh`, instead of the PREREG's `flock -s` in `run_batch.sh`. `run_batch.sh` is unchanged and unused, because a nested shared flock would deadlock inside quiet-timed.
7. **D7 Mutation gate.** The stricter all-16 gate was adopted after the aborted attempt had already shown 16/16.
8. **D8 Added files.** `summarize.py`, `verify_artifacts.py`, `provenance.json` and this README only read raw outputs.
9. **D9 Stop at 100/160 and resume.** The first batch (a background task of the lane agent) was stopped by the agent harness when the agent returned an interim result at about 18:33:52Z, while block m11 was still waiting for the lock. No m11 lock was taken: the shared quiet-lane ledger had no own75r-block-m11 receipt, the packet ledger had no m11 entry, `raw/real/blocks/block-m11` did not exist and `session-block-m11.log` was empty. So no block was partial and t101-t160 were cleanly unrun. The resumed batch (18:49:42-19:52:24Z) ran exactly the pre-registered plan files block-m11..m16 with the same unchanged harness, binary, worktrees and session variables; `run_batch_qt.sh` refuses any block that already ran, so no trial was re-run. No trial was added or dropped.
10. **D10 Verifier changed after seeing data (AT-SPI address).** `verify_artifacts.py` (c7614a2dd, committed after blocks m01-m10 ran) required `meta.at_spi_bus_set` and `session-env AT_SPI_BUS_ADDRESS_set` to be true. Both are false in every block: `cua-x11-session.sh` starts `at-spi-bus-launcher` on the private `dbus-run-session` bus and never exports `AT_SPI_BUS_ADDRESS`. The check was wrong, not the environment, which was not changed. The checks now require the variable to be unset (nothing inherited from the host), and add two replacement checks: each block's session log shows one private session dbus-daemon serving the at-spi-bus-launcher request, and every action receipt has `route=accessibility`, `delivery=background`. Every self-test printed `REFUSED True` / `REFUSED true` (2/2). A second verifier fix, independent of the data: `verify_prereg` ran `git log -- <repo-relative path>` from the packet directory, which matched nothing; `git()` now runs from the worktree top.
11. **D11 Interim analysis.** At 18:00:32Z the lane ran the pre-registered `analyze.py` over the first 80 trials while collection was still running. S3 is an identity gate with no stopping rule, and collection continued to the pre-registered 160 regardless, so this cannot bias the result.
12. **D12 Amendment timestamp edit.** The amendment's `written_utc` was changed from 17:23Z to 17:21Z with `commit --amend --reset-author` at 17:21:29Z, before any reported run; c1fe992b0 is the only committed version.
13. **D13 Harness smoke test.** At 17:20:34Z `run_batch_qt.sh` was smoke-tested once under `bin/hostless` with a stub driver (`/bin/true`) and a scratch plan outside the packet; no trial ran and nothing from it is in the packet.
14. **D14 Session-log scrub.** After the batches, the private dbus socket path (a `dbus-...` socket in the system temp directory) in the 16 `raw/real/session-block-*.log` files was rewritten to `<tmp>/dbus-...` to keep local paths out of the packet. Nothing else in those logs was changed; the unscrubbed logs are in the artifact mirror only.

## Publication errata (r1b repair, 2026-10-03)

Evidence class: SOURCE (packet hygiene only; no new run, no new evidence).

- **What was wrong.** The published head `e02621fdc` (branch `exp/own-75r-timing-parity-4336-20261002`) did not reproduce from a clean checkout: the repository-wide `.gitignore` rule `*.log` kept 48 cited raw logs out of the commit (14 `raw/unit/*.log`, 18 `raw/mutation/*.log`, 16 `raw/real/session-block-*.log`), so `verify_artifacts.py` stopped with `FileNotFoundError` on `raw/unit/head-python-unittest.log`.
- **Fix.** This branch (`exp/own-75r-timing-parity-4336-r1b-20261003`) carries commit `823ff9784` (parent `e02621fdc`), which adds a packet-local `.gitignore` (`!*.log`, `!build/`) and force-adds the 48 logs. They were copied from the wave-3 lane worktree, where they are byte-identical to the artifact-mirror copy of the packet. Before they were added, they went through the packet's own scrubber (the `Sanitizer` in `harness/real_block.py` plus the D14 dbus-socket rule): 0 files changed, and the verifier's `privacy_hits` found 0 hits. One more scrub followed, in the same spirit as D14. In the 16 `raw/real/session-block-*.log` files, the scrubber's `<mnt>` placeholder was still followed by local directory names: a truncated gvfs `comm=` field and the session `run_dir=` line. These were rewritten to the placeholders `<lanes>/` (the lanes directory) and `<lane-tmp>/` (the lane temp directory), 48 occurrences in total. No check reads those lines, and nothing else changed. The 14 unit and 18 mutation logs needed no change. `raw/force-added-logs.sha256` holds the sha256 of every committed log (`sha256sum -c` format). `raw/force-added-logs.pre-rescrub.sha256` holds the pre-rescrub sha256 of the 16 session logs, and those equal the artifact-mirror copies. No manifest or verifier in this packet recorded hashes for these files, so the artifact-mirror copy was the only reference to compare against.
- **Unchanged.** Every measured number, raw trial record, analysis script, `verify_artifacts.py`, `PREREG.json` and `PREREG-AMENDMENT-1.json` is the same as at `e02621fdc`. No cited file was missing, so nothing is marked missing.
- **Review of `823ff9784` (r1b, SOURCE).** Every one of the 48 committed logs was re-derived from the wave-3 lane worktree: the 14 unit and 18 mutation logs are byte-identical to it, and each of the 16 session logs equals its worktree copy after the two placeholder rules above. All 48 committed hashes equal `raw/force-added-logs.sha256`, the 16 pre-rescrub hashes equal the worktree copies, and the worktree copies are byte-identical to the artifact mirror. No cited file is missing anywhere, so this errata lists no missing file. The privacy scan of `823ff9784` (every blob, path, message and identity) found no absolute path, host name, local directory name or secret pattern.
- **Reproduction.** `verify_artifacts.py`, run under `bin/hostless` from a clean clone of this branch head, prints `112/112 checks passed`. The audit in `docs/experiments/packet-audit-2026-10-03/` (branch `docs/packet-template-audit-a2-20261003`) records the repair head SHA and the clean-clone run.

## Limits and claim boundary

trycua/cua PR 4336 at `8391cf802` vs M0 `2ca90d338`. Linux X11 (Xvfb) with the canonical GTK3 fixture and two tasks (choose-size, save-note). Python and TypeScript native runners with the deterministic mock chooser. Driver 0.32.0, binary `8b037961...`. Not covered:
- live or S1 providers;
- macOS, Windows or Wayland;
- REAL visual-parse or reobservation paths (visual status was `skipped` on every REAL step, so `parse_ms == visual_observe_ms` was never exercised in REAL; the fake-driver UNIT tests cover it);
- d301a076c;
- any merged tree with current main (object-level merge-tree only).

Timing values are not claims. Upstream promotion stays with the owner; nothing is posted upstream.

## Reproduce

All commands run under `bin/hostless`.
- `harness/run_unit.sh <wt> raw/unit <arm>`
- `harness/mutate.py <head-wt> <scratch> raw/mutation`
- `harness/make_plan.py raw/real/plan`
- `harness/run_batch_qt.sh <lanes> raw/real/plan raw/real <work> <driver> <head-wt> <m0-wt> [block-glob]`
- `summarize.py`
- `verify_artifacts.py`, which recomputes everything and prints `112/112 checks passed`.

## Next

- For kvnloo/cua#75: the exact head 8391cf802 is validated within the claim boundary; promotion upstream (trycua/cua PR 4336) stays with the owner. If the PR head moves, re-run this packet against the new head; the issue body should be updated from d301a076c to 8391cf802.
- For kvnloo/cua#10: the native and browser runners now share field names. The INHERITED-A asymmetry means a per-language `provider_decision_ms` comparison of mock runs includes the TypeScript `expectedNext` + offered-set work.
