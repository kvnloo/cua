#!/usr/bin/env bash
# B-08 session entry (B-06 in-session.sh with the lane names changed) (runs INSIDE cua-x11-session.sh; always reached as hostless -> run-chunk.sh | run-pilot.sh |
# shared-locked.sh -> session-retry.sh -> cua-x11-session.sh -> this script).
#   in-session.sh <worktree> <script.py> [args...]     run a packet script with the worktree's jev-use venv
#   in-session.sh <worktree> --versions <driver>        Driver --version + sha256, browser versions
# Refuses outside a private X11 session, when the hostless marker was not forwarded, with a host
# runtime dir or session bus, or with any permission/approval/sandbox override. Exit 97 (no trial
# written) when the private Xvfb is unreachable, so session-retry.sh can retry a display collision.
set -uo pipefail
WT="$1"; shift
refuse() { echo "refusing: $*" >&2; exit 96; }
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || refuse "not inside the isolated X11 session"
[ "${B08_HOSTLESS:-0}" = "1" ] || refuse "caller is not under hostless"
case "${XDG_RUNTIME_DIR:-}" in "$(dirname "$TMPDIR")"/xdg-runtime) ;; *) refuse "XDG_RUNTIME_DIR not session-private" ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) refuse "host session bus" ;; esac
for v in CUA_DRIVER_PERMISSION_MODE CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_E2E_BROWSER_NO_SANDBOX; do
  [ -z "${!v:-}" ] || refuse "$v set"
done
xdpyinfo >/dev/null 2>&1 || { echo "[b08] session_failed_to_start: display $DISPLAY unreachable" >&2; exit 97; }
[ -n "${B08_TMPDIR:-}" ] && export TMPDIR="$B08_TMPDIR"
EX="$WT/libs/cua-driver/examples/jev-use"
export JEV_USE_DIR="$EX" PYTHONDONTWRITEBYTECODE=1
echo "[b08] display=$DISPLAY xdpyinfo=ok start_utc=$(date -u +%FT%T.%3NZ) loadavg=$(cut -d' ' -f1-3 /proc/loadavg) telemetry_env=${CUA_DRIVER_RS_TELEMETRY_ENABLED:-unset} dnt=${DO_NOT_TRACK:-unset} lock=${B08_LOCK:-unset} wayland=${WAYLAND_DISPLAY:-unset} hostless=${B08_HOSTLESS:-unset}" >&2
if [ "${1:-}" = "--versions" ]; then
  echo "driver_version: $("$2" --version 2>&1 | head -1)"
  echo "driver_sha256: $(sha256sum "$2" | cut -d' ' -f1)"
  echo "google-chrome-stable: $(google-chrome-stable --version 2>&1 | head -1)"
  echo "google-chrome: $(google-chrome --version 2>&1 | head -1)"
  echo "chromium: $(chromium --version 2>&1 | head -1)"
  exit 0
fi
cd "$WT/docs/experiments/b-08-per-process-cold-b7-2026-10-03"
"$EX/.venv/bin/python" "$@"; rc=$?
echo "[b08] end_utc=$(date -u +%FT%T.%3NZ) rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg)" >&2
exit $rc
