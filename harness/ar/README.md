# Autoresearch evaluator (segment 1, GTK3 checkbox toggle)

Evaluator-owned. Proposers never read or run anything here except `ar-submit`.

| Path | Role |
|---|---|
| `ar-submit` | The only proposer interface: writes one `ar.request.v1` file (branch + hypothesis) into `$AR_REQUEST_DIR`. |
| `ar-eval` | Evaluator CLI: `manifest`, `selfcheck`, `g0`, `tau`, `prereg`, `evaluate`, `verify`. |
| `areval/gates.py`, `areval/g0.py` | G0-G8 and GS as pure functions of raw rows, the pre-registration and the candidate diff. |
| `areval/stats.py`, `areval/lord.py` | Paired ln-ratio effect, bootstrap CI and p, AA-based tau, n_pairs/power, LORD++. |
| `areval/results.py` | Append-only, hash-chained `results.jsonl`. |
| `schema/*.schema.json` | `ar.prereg.v1`, `ar.result.v1`, `ar.trial.v1`, `ar.request.v1`. |
| `allowlist.json` | The segment-1 items a candidate may change (itemcheck item paths). |
| `rules/scanner_rules.json` | Diff scanner rules, each with a planted example. |
| `itemcheck/` | syn-based item-level checker (G0). |
| `manifest.json` | sha256 of the frozen candidate-tree files, the segment files' test items and the harness itself. |
| `sandbox/` | Per-trial bubblewrap sandbox for the Driver, the session pid namespace wrapper, and the probe. |
| `runner/` | Frozen scripted caller, session runner (10 Hz PSI), AB/BA planner, quiet-lane block runner, G1 log parser. |

## Rules the harness enforces

- Every code-executing step runs under the lane `hostless` wrapper; GUI work only inside a private
  `cua-x11-session.sh` session wrapped by `sandbox/session-pidns.sh`; every timed block goes through
  `quiet-timed` (one session of at most 48 trials, no new trial after 9 minutes).
- One fresh Driver per trial, inside `sandbox/sandbox-driver.sh`: read-only root from `/usr` and `/etc`,
  tmpfs HOME and runtime dir, only the X, session-bus and AT-SPI sockets bound, no network, the
  session's pid namespace (never the host's). The harness, results and fixture-state dirs are not
  mounted; `sandbox/probe.py` proves it with planted canaries.
- T = CLOCK_MONOTONIC from Driver spawn to the caller's oracle-verified done (the fixture's own state
  file), with the state file's mutation time checked to be <= done.
- Gates run in order and stop at the first failure; a LORD++ alpha index is consumed only when G5 runs.

## Unit tests

    hostless env AR_ITEMCHECK=<built itemcheck> python3 -m unittest discover -s harness/ar/tests -t harness/ar/tests
    (cd harness/ar/itemcheck && hostless cargo test --offline --release)
