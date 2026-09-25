# Issue 4

Blocked. The interleaved fixture trial was not run.

Missing machine: this Linux host. The pinned driver session is not running here (`cua-driver 0.28.2` is installed and the daemon is not running).

Missing on this Linux host: an exact-head Driver session and an independent task oracle. Installed binary: `cua-driver 0.28.2`. Daemon: not running. Top-level windows: none. See `scripts/repro/handoff/linux-host-probe.txt`. Pinned head: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Asked for: success, model requests, decisions, actions, observations, wall time, and the cases where Jev would reobserve but the rule would act.

Not produced: those measurements or an eligibility verdict.
Not invented: hit rate or wall time.

The predicate that was unit-tested, and is not that trial, is `single_executable_candidate`. The default chooser is unchanged.
