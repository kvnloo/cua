# Issue 72

Blocked. The exact-head `list_apps` A/B against trycua/cua#3492 was not run.

This Linux host is present. It is not the missing machine.

Missing prerequisite: pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23` is not an installed release. A debug build of that commit finished and printed `cua-driver 0.29.1`. `cua-driver status` then exited 1 because the daemon is not running, and `cua-driver doctor` returned no top-level windows. See `scripts/repro/handoff/pin-build.md`. The `list_apps` trial was not run. The installed release is `cua-driver 0.28.2`. The daemon is not running. See `scripts/repro/handoff/linux-host-probe.txt`.

Asked for that A/B and an upstream recommendation. Not produced. No second cache was implemented. No recommendation was invented.
