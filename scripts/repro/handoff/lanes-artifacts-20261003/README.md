# CUA lane artifacts: snapshot 2026-10-03

This is an archive of local evidence. It copies the small text files from the host's `cua-lanes/artifacts/` mirror. Those are the loop state, judges, wave syntheses, drafts, per-lane summaries and the workflow scripts, none of which were committed anywhere else. The owner can review the whole CUA research programme from one place here. Nothing in this folder was posted upstream.

Selection rule: every `*.md`, `*.json`, `*.js`, `*.tsv`, `*.csv` and `*.txt` file at depth 3 or less that is under 512 KB. That gives 290 files, about 3.6 MB.

The full mirror is 5.9 GB and mostly raw run directories: `r2/` is 3.1 GB, `stack/` 2.3 GB, `bend-stack/` 248 MB and `i107/` 201 MB. It stays on the host. Each lane's verified packet, including its raw tarballs, is already committed on that lane's `exp/*` branch under `docs/experiments/<lane>/` on this fork.

Where to start:

| Path | Contents |
|---|---|
| `r2/SYNTHESIS.md`, `r2/SYNTHESIS-w1.md` … `-w6.md` | Synthesis of each RFC-loop wave |
| `r2/loop/` | `END_CONDITION.md` (E1 to E6), `STATE.json` (pins, wave state), seed judges, the unrun wave-4 plan |
| `r2/<LANE>/` | Top-level packet files for each lane (README, summary, verdict), e.g. `R2-10R/`, `FIX-04/`, `FRESH-07/` |
| `r2/drafts/` | Staged issue and PR text (not posted) |
| `ar/` | Autoresearch harness: calibration 1 and 2 (`CALIBRATION*.json`), fixes, synthesis |
| `stack/` | CUA × Hermes × z0int stack: setup, multiseat/sway, samples, v2, synthesis |
| `bend-stack/` | Hermes × CUA × z0 × Bend integration synthesis |
| `i107/` | #107 mirror-vs-scoped study |
| `exact/`, `p0-*`, `p1-*`, `fix-4318/`, `issue-76/`, `main-b8d619f57/`, `env/` | Earlier lanes (2026-09-28 and 2026-09-29) |
| `workflows/` | Workflow scripts (RFC loop v2, autoresearch v2b, Hermes/CUA/z0/Bend) |

`~` replaces `/home/kvn` and `<local-host>` replaces the host name. The `"token": "MS-…"` values in `stack/multiseat/grade-local.json` are task marker strings, not credentials.

Two lanes were still running when the snapshot was taken, and their branches were not pushed: `exp/fresh-07-main-9a2b1d99e-20261003` and `exp/r2-07g-live-fallback-ln-20261003`.
