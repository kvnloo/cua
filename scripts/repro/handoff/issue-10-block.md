# Issue 10

Blocked. The 4-arm benchmark was not run.

Missing machine: this Linux host. The pinned 4-arm session cannot run here (`cua-driver 0.28.2` is installed, the daemon is not running, and there are no top-level windows).

Missing on this Linux host: an exact-head Driver session and a model provider for the four arms. Installed binary: `cua-driver 0.28.2`. Daemon: not running. Top-level windows: none. See `scripts/repro/handoff/linux-host-probe.txt`. Pinned head: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Asked for: task × arm × trial JSONL, an analysis script over those trials, raw logs, exact commands, and a summary table.

Not produced: that JSONL or table.
Not invented: trial milliseconds.

The clock split that was unit-tested, and is not that benchmark, is `task_accounting.outcome_time`. It returns verified-outcome time and not runner lifetime.
