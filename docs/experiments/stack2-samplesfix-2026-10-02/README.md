# stack2-samplesfix-2026-10-02: repair of the SAMPLES packet

Lane: stack v2 SAMPLESFIX (kvnloo/hermes-agent#319). This is a text and analysis repair of
`docs/experiments/stack-samples-2026-10-02/`, which its fresh verifier did not accept. No data were
collected: no Hermes turns, model calls, scoring or Driver sessions. Every label, verdict, score and
metric in the SAMPLES packet is unchanged. `PREREG.json` (c26ac540) was committed before any repair
commit. It discloses what the lane owner had already read before writing it.

`python3 verify_artifacts.py` prints `RESULT PASS`, and `--tamper` also re-runs the tamper copies. It runs
the SAMPLES packet's own verifier (now 14 check groups) as one of its checks.

## Answer

**The CUA input-task failures were tool_call bridge failures, not approval fail-closes. The approval-bypass
request is withdrawn.** All figures below come from the committed private-home agent.log and errors.log
of the 12 CUA runs, cross-checked against the frozen observer rows:

| what the raw logs show (12 CUA runs) | count |
|---|---|
| API calls (agent.log = observer `post_api_request`) | 35 |
| tool calls (agent.log = observer `pre_tool_call` = `post_tool_call`) | 27 |
| ... completed | 0 |
| ... refused by `tool_call` before dispatch: `tool_call requires 'calls'` | 23 |
| ... refused: `'<name>' is not a known tool name` | 3 |
| ... refused: `tool_call cannot invoke 'tool_search'` | 1 |
| computer_use dispatches / Driver or computer_use logger lines | 0 / 0 |
| approval or fail-close lines (agent.log, errors.log, reply) | 0 |
| runs whose fixture GUI state changed | 0 |

- **Why it failed.** The CUA runs used `-t computer_use`. Default tool search deferred computer_use
  behind the `tool_search`/`tool_call` bridge (0 visible tools, 1 deferred). The 3B model never called
  `tool_search` and never formed a valid `tool_call`. The three refusal strings come from
  `tools/tool_search_validation.py` at 5d01f608, before dispatch (SOURCE).
- **Positive control.** Under the same logger at the parent commit, the SMOKE lane's logs hold 481
  `tool computer_use completed` lines across 117 agent.logs (`raw/smoke-positive-control.txt`), so a
  dispatch would have been logged.
- **Count reconciliation (PREREG C2).** The verifier reported "0 successful tool calls and 23 tool
  errors". The 0 holds. The total is 27: 23 is the largest class only.
- **What the run says about approvals and the Driver.** The approval gate and cua-driver were never
  reached. The preregistered approval expectation is a SOURCE-only statement this run did not test, and
  the run says nothing about Driver capability.
- **The 2 `cua_button_present` passes.** The model answered "No" in all 5 runs, so the passes are exactly
  the 2 tasks whose expected answer is "no".

## Checks (PREREG)

| check | result | evidence |
|---|---|---|
| C1 CUA attribution: 0 completed, all errors at tool_call, 0 approval lines, 0 computer_use, per-run log = observer counts, GUI unchanged, `-t computer_use` | PASS | SAMPLES verify group 11; `raw/analysis/cua-bridge-tally.json` in the SAMPLES packet |
| C2 count reporting | 27 = 23 + 3 + 1, reconciled with the verifier's 23 | both READMEs, `summary.json` |
| C3 SAMPLES verify after the edits; 4 tamper copies | RESULT PASS; 4/4 RESULT FAIL, each on the intended check | `raw/verify-samples-after.log`, `raw/tamper.log` |
| C4 tables reproducible | 7 generated README blocks byte-identical to `harness/make_tables.py`; summary.json byte-identical to a fresh `make_summary.py` run | SAMPLES verify group 12 |
| C5 manifest reproducible | MANIFEST file hashes, content hash 648e418e…, counts (112/105/7/1154) recomputed; identities == provenance | SAMPLES verify groups 2 and 13 |
| C6 numbers kept | every number of the original workload, api and turn tables is present in the corrected tables | `raw/numbers-kept.json` |
| C7 unit log | 25 passed, 2 skipped; 13 passed with z0int on PYTHONPATH (reproduces the original claim) | SAMPLES `raw/unit/unit-lab-5d01f608.log` |

## What changed in the SAMPLES packet

- **E2 (blocking item).**
  - CUA attribution rewritten in Results, Evidence classes and Claim boundary.
  - The BLOCKED row for CUA input tasks removed; approval fail-close moved to SOURCE-only / NOT_RUN.
  - The approval-bypass request withdrawn.
  - The 12 CUA agent.log/errors.log committed (sanitized by `harness/copy_cua_logs.py`, the same
    sanitizer as `build_packet.py`).
- **E1 wording.** Plainer: 30 of the 40 hex digits in the PREREG hermes hash were invented.
- **E3 decider_2b latency.**
  - The 180.1 s warm call at index 3 is disclosed.
  - A warm max column was added for every row.
  - "True cold start" was removed.
- **E4.** The 92 s median task wall time is labelled a descriptive workload figure, not a latency.
- **E5.** Exit reasons are 7 `max_iterations_reached(4/4)` + 1 `pending_tool_result` (t096).
- **E6.** The warm latency columns are labelled as the scorer wall-clock series. This was found while
  making the table reproducible: the old values match `warm_wall_ms_*`, not the reported `latency_ms`.
  No value changed.
- **Disclosures.**
  - The Ollama-adapter one-hot edge case: not triggered, and the code is unchanged.
  - The 4 harness scripts written after PREREG but before scoring.
  - Triplicate `rc=0` lines in `failopen.log`.
- **Reproducibility tooling.**
  - `harness/make_tables.py` generates every README table.
  - `harness/cua_bridge_tally.py` produces the tally.
  - `make_summary.py` adds exit reasons and the tally totals; existing keys are unchanged.
  - `verify_artifacts.py` gains check groups 11-14.

## Evidence classes

- SOURCE: re-derivation scripts; the bridge refusal strings in Hermes source.
- REAL: existing receipts of the 105 SAMPLES runs (no new runs).
- UNIT: lab suite log, run under `hostless` with a private HOME, dead egress proxy, fresh detached hermes
  worktree and its own venv.
- NOT_RUN: any new collection, scoring, model call or Driver session; the approval-gate path.
- No latency was measured, so `quiet-timed` was not needed.

## Shared infrastructure

`ollama-stack/users.d/samples.json` wrongly said SAMPLES uses the 11500 Ollama. It is now marked
`released`; the original is kept in the local mirror. This lane did not start, stop or signal any Ollama
process. Nobody has claimed the 11500 server (pid 3782390) yet. Assigning who stops it stays with the
orchestrator.

## Layout

- `PREREG.json`.
- `README.md`, `summary.json` (written by `harness/make_summary.py`), `provenance.json`.
- `verify_artifacts.py`.
- `harness/numbers_kept.py`, `harness/tamper.sh`, `harness/make_summary.py`.
- `raw/`:
  - `samples-README-at-4c1a4a95.md`: the README before repair.
  - `numbers-kept.json`.
  - `verify-samples-before-4c1a4a95.log`, `verify-samples-after.log`.
  - `tamper.log`.
  - `smoke-positive-control.txt`.
