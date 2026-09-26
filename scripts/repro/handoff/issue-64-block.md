# Issue 64

Blocked. The exact-head outcome A/B for trycua/cua#4165 was not run on pinned commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

This Linux host is present. It is not the missing machine.

Missing prerequisite: pinned driver commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23` is not an installed release. The installed release is `cua-driver 0.28.2`. The daemon is not running and there is no top-level window. See `scripts/repro/handoff/linux-host-probe.txt`.

A later fake-driver artifact is on branch `muse/issue-64-exact-head-ab` at commit `147158cf9caed69489607f7e6736dc9282bdd815`, under `scripts/repro/handoff/issue-64/`. Its report uses head `24aaf8d1965b3b7c1530cbb9d58758ec89472d92`, not the pin above. The report's table says the default fixture verified in 2 steps with 0 visual tool calls on auto and 4 on always, and the visual fixture verified in 2 steps with 2 visual tool calls on auto and 4 on always. That report says the Driver was fake. It is not the pinned desktop session.

No helper was added on this branch. No verdict was issued.

