#!/usr/bin/env bash
# usage (inside hostless + hostless-strict + cua-x11-session.sh with CUA_SESSION_ATSPI=1):
#   session_entry.sh <run_block.sh args...>
# Trust check before any trial: the private X display answers xdpyinfo (exit 97 otherwise, nothing
# run, so the orchestrator can start a new session), no Wayland/Hyprland variables, a private
# runtime dir. Then hands over to the blob-identical OWN-20G harness/run_block.sh.
set -uo pipefail
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 96; }
case "${XDG_RUNTIME_DIR:-}" in /run/user/*) echo "refusing: host runtime dir" >&2; exit 96 ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) echo "refusing: host session bus" >&2; exit 96 ;; esac
xdpyinfo >/dev/null 2>&1 || { echo "[session] xdpyinfo probe failed on $DISPLAY" >&2; exit 97; }
echo "[session] xdpyinfo=ok display=$DISPLAY atspi=${CUA_SESSION_ATSPI:-unset} telemetry=${CUA_DRIVER_RS_TELEMETRY_ENABLED:-unset} dnt=${DO_NOT_TRACK:-unset}" >&2
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/harness/run_block.sh" "$@"
