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
  `quiet-timed` (one session of at most 48 paired trials = 24 pairs, plus 2 warm-ups and 4 controls,
  no new trial after 9 minutes).
- One fresh Driver per trial, inside `sandbox/sandbox-driver.sh`: read-only root from `/usr` and `/etc`,
  tmpfs HOME and runtime dir, only the X, session-bus and AT-SPI sockets bound, no network, the
  session's pid namespace (never the host's). The harness, results and fixture-state dirs are not
  mounted; `sandbox/probe.py` proves it with planted canaries.
- Exception, the browser spot check (`spot_browser_fill_submit`): any unprivileged bwrap is a user
  namespace in which root-owned Chromium shows as the overflow uid, and the Driver's isolated launch
  refuses it. Browser spot pairs therefore run in their own sessions (`"pidns": false`), with no
  session-pidns.sh and no sandbox-driver.sh: the Driver runs in the private session under `hostless`
  with a fresh trial HOME and a short per-trial TMPDIR (Chromium aborts when its SingletonSocket path
  exceeds 107 bytes). The oracle is the evaluator's browser fixture
  (`docs/experiments/ar-harness-2026-10-02/fixtures`, in-process server journal): exactly one POST with
  the trial token, stamped <= done, after a trusted pointer sequence on Submit. G2 compares browser
  footprints only with champion browser rows and fails any Driver-tree process that outlives the Driver.
- `ar-eval aa` turns A/A rows (champion build vs a rebuild of the same commit) into sigma, Delta_AA and
  its CI, tau, n by power, the T_act fallback and the PSI discard threshold.
- T = CLOCK_MONOTONIC from Driver spawn to the caller's oracle-verified done (the fixture's own state
  file), with the state file's mutation time checked to be <= done.
- Gates run in order and stop at the first failure; a LORD++ alpha index is consumed only when G5 runs.

## Unit tests

    hostless env AR_ITEMCHECK=<built itemcheck> python3 -m unittest discover -s harness/ar/tests -t harness/ar/tests
    (cd harness/ar/itemcheck && hostless cargo test --offline --release)
