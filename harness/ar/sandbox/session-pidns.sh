#!/usr/bin/env bash
# session-pidns.sh <cmd...>: run a whole private session (cua-x11-session.sh and everything it starts)
# in its own pid namespace with a fresh /proc. The per-trial Driver sandbox then shares THIS namespace
# (AR_SANDBOX_PIDNS=session, the default): it sees only the session's processes (Xvfb, buses, window
# manager, fixture, caller, itself), never the host's, and the pids it reads from X (_NET_WM_PID), the
# AT-SPI bus (peer credentials) and /proc agree. See sandbox-driver.sh for why a per-trial private pid
# namespace is not used.
set -euo pipefail
exec bwrap --dev-bind / / --unshare-pid --die-with-parent --proc /proc --setenv AR_SESSION_PIDNS 1 -- "$@"
