# <LANE-ID>: <one-line question>, <YYYY-MM-DD>

Packet template (layout of kvnloo/cua PR #106). Copy this directory to `docs/experiments/<name>/`,
replace every `<...>` field, delete the guidance lines in italics, and keep the headings. Every row
of every table carries an evidence class: SOURCE, UNIT, FIXTURE, REAL, BENCHMARK, LIVE_PROVIDER,
BLOCKED or NOT_RUN.

## Result in one paragraph

<N of M verified by the oracle; the decision; the headline numbers with CIs; provider attempts / reached.>

## Provenance (each SHA kept separate)

| Item | Value | Evidence class |
|---|---|---|
| Forced path | <the exact path every trial is forced through, and how each trial's own records prove it> | <class> |
| Actual route / producer | <the route or producer the Driver reports per action; how it is attributed> | <class> |
| Independent target-owned oracle | <what the target itself records; how it is sampled; never the Driver receipt> | <class> |
| Negative / fallback controls | <each control, what it must show, and whether it discriminates> | <class> |
| Tested source SHA | <full SHA> (rust tree `git rev-parse <sha>:libs/cua-driver/rust` = <tree SHA>) | SOURCE |
| Driver binary | <name>, sha256 <64 hex>, `<cua-driver x.y.z>` (read inside the session at start and end) | SOURCE |
| Environment | <OS/kernel; hostless version; private session (X11/sway); browser/toolkit versions; loadavg range> | SOURCE |
| PREREG commit | <SHA>, committed <UTC>, before the first measured trial at <UTC> | SOURCE |
| Live PR heads at test time | <upstream main SHA; each PR head SHA, read with gh at UTC> | SOURCE |
| Publication SHA | set by Publish (`provenance.json: publication_sha`); never equal-by-assumption to the tested SHA | SOURCE |
| Live heads at publication | set by Publish (`provenance.json: live_heads_at_publication`) | SOURCE |
| Provider | <provider; attempts N, reached N; or "none (scripted)"> | <class> |

## Method

<Arms, design (AB/BA interleaving, rounds), metrics, statistics, locks (quiet-timed receipts), the
exact commands. Every failure stays in the denominator.>

## Results (N of M, evidence class per row)

| Row | N of M | Result | Evidence class |
|---|---|---|---|
| <row> | <n/m> | <value [CI]> | <class> |

## Work deleted vs wall-clock saved

| Candidate | Work deleted | Wall-clock saved | Evidence class |
|---|---|---|---|
| <candidate> | <component and ms, or "none"> | <paired median [CI]> | <class> |

## Deviations

<Every change after PREREG, with time and reason; every near miss.>

## Limits and claim boundary

<What the evidence covers (source, binary, environment, tasks) and what it does not.>

## Disposition

<KEEP / REVISE / KILL / BLOCKED, by the pre-registered rule.>

## Files

Cite every file by its path. `verify_helper.py` (from `docs/experiments/_template/`) fails the
verifier when a file cited here or in the headline JSON is not committed (git-ignored or untracked).
Its `check_privacy` fails on a private name (from the untracked `CUA_PRIVACY_NAMES_FILE`, plus the host
and user name) in plain, hex- or base64-encoded form, on a committed list of encoded name-like strings,
on an absolute local path and on secret-like values, in every tracked packet file (gzip members
included) and, with a base SHA, in every commit of the branch. Never commit private names, not even
encoded.

| File | Contents |
|---|---|
| `PREREG.json` | pre-registration, committed before the first measured trial |
| `README.md` | this file |
| `.gitignore` | packet-local `!*.log`, `!build/` so cited logs and build outputs are committed |
| `verify_artifacts.py` | recomputes every headline number from `raw/`; calls `verify_helper.check_cited` and `verify_helper.check_privacy` |
| `verify_helper.py` | cited-file check and privacy scan (copy of the template helper) |
| `<name>-summary.json` | headline numbers |
| `provenance.json` | the provenance fields above |
| `raw/<file>` | <one row per raw file or glob> |
