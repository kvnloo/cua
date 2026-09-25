# Issue 48

Blocked. The provider parity sessions were not run.

Missing machine: this Linux host. No Jev session and no local S1 server are running here (`cua-driver 0.28.2` is installed and the daemon is not running).

Missing on this Linux host: a live Jev session against the pinned head, and a local S1 server. A TypeSafe key name is present in the environment. It was not used. The installed driver is `cua-driver 0.28.2`, the daemon is not running, and there are no top-level windows (`scripts/repro/handoff/linux-host-probe.txt`). Pinned head: `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

Asked for a parity matrix across mock, Jev, and S1. Not produced. `choose_mock` remains the offline chooser.
