# Issue 10

Blocked. The 4-arm benchmark was not run.

This Linux host is present. It is not the missing machine.

Missing prerequisite: pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23` is not an installed release, and there is no model session. The installed release is `cua-driver 0.28.2`. The daemon is not running and there is no top-level window. See `scripts/repro/handoff/linux-host-probe.txt`.

Asked for task × arm × trial JSONL, an analysis script over those trials, raw logs, exact commands, and a summary table.

Not produced: that JSONL or table. Not invented: trial milliseconds.

The clock split that was unit-tested, and is not that benchmark, is `task_accounting.outcome_time`. It returns verified-outcome time and not runner lifetime.
