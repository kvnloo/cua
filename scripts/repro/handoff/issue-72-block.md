# Issue 72

Blocked. The exact-head `list_apps` A/B against trycua/cua#3492 was not run.

Missing machine: this Linux host. The pinned `list_apps` session is not running here (`cua-driver 0.28.2` is installed and the daemon is not running).

Missing on this Linux host: a running daemon built from pinned head `c5ee191c02b11448ffefcc38b78b064a87d8ef23`. Installed binary: `cua-driver 0.28.2`. `cua-driver status` exited 1 with `Cua Driver daemon is not running` (`scripts/repro/handoff/linux-host-probe.txt`).

Asked for that A/B and an upstream recommendation. Not produced. No second cache was implemented. No recommendation was invented.
