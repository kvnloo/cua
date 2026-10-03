#!/usr/bin/env bash
# usage (always: hostless -> run_chunk.sh -> cua-x11-session.sh -> this script):
#   in_session.sh <worktree> <python-script> [args...]
# Refuses outside a private X11 session or when the outer hostless marker was not forwarded.
# Default Driver safety settings; no permission/approval overrides; no sandbox bypass.
set -uo pipefail
WT="$1"; shift; SCRIPT="$1"; shift
refuse() { echo "refusing: $*" >&2; exit 96; }
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || refuse "not inside the isolated X11 session"
[ "${R2_10_OUTER_HOSTLESS:-0}" = "1" ] || refuse "caller is not under hostless"
case "${XDG_RUNTIME_DIR:-}" in "$(dirname "$TMPDIR")"/*) ;; *) refuse "XDG_RUNTIME_DIR not private" ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) refuse "host session bus" ;; esac
for v in CUA_DRIVER_PERMISSION_MODE CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_E2E_BROWSER_NO_SANDBOX; do
  [ -z "${!v:-}" ] || refuse "$v set"
done
EX="$WT/libs/cua-driver/examples/jev-use"
export JEV_USE_DIR="$EX" PYTHONDONTWRITEBYTECODE=1
key=absent; [ -n "${TYPESAFE_API_KEY:-}" ] && key=present
echo "[r2-10] display=$DISPLAY xdg_runtime_private=yes key=$key loadavg=$(cut -d' ' -f1-3 /proc/loadavg) atspi=${CUA_SESSION_ATSPI:-0}"
exec "$EX/.venv/bin/python" "$SCRIPT" "$@"
