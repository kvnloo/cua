#!/usr/bin/env bash
# usage (always: hostless -> run_chunk.sh -> cua-x11-session.sh -> this script):
#   in_session.sh <worktree> <python-script> [args...]
# Refuses outside a private X11 session or when the outer hostless marker was not forwarded.
# Before trusting the session: 0-3 s start jitter, then an xdpyinfo probe of the private display.
# Reads the Driver's sha256 and --version inside the session (from the script's --driver argument).
# Default Driver safety settings; no permission/approval overrides; no sandbox bypass. (B-05
# in_session.sh with the lane name changed, plus the jitter, probe and Driver identity lines.)
set -uo pipefail
WT="$1"; shift; SCRIPT="$1"; shift
refuse() { echo "refusing: $*" >&2; exit 96; }
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || refuse "not inside the isolated X11 session"
[ "${R2_10_OUTER_HOSTLESS:-0}" = "1" ] || refuse "caller is not under hostless"
case "${XDG_RUNTIME_DIR:-}" in "$(dirname "$TMPDIR")"/*) ;; *) refuse "XDG_RUNTIME_DIR not private" ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) refuse "host session bus" ;; esac
for v in CUA_DRIVER_PERMISSION_MODE CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_E2E_BROWSER_NO_SANDBOX TYPESAFE_API_KEY; do
  [ -z "${!v:-}" ] || refuse "$v set"
done
jitter_ms=$(( RANDOM % 3001 ))
sleep "$(printf '%d.%03d' $((jitter_ms / 1000)) $((jitter_ms % 1000)))"
if xdpyinfo >/dev/null 2>&1; then probe=ok; else refuse "xdpyinfo probe failed on $DISPLAY"; fi
drv=""; prev=""
for a in "$@"; do [ "$prev" = "--driver" ] && drv="$a"; prev="$a"; done
if [ -n "$drv" ]; then
  echo "[b-07] driver_sha256=$(sha256sum "$drv" | cut -d' ' -f1) driver_version=$("$drv" --version 2>&1 | head -1)"
fi
EX="$WT/libs/cua-driver/examples/jev-use"
export JEV_USE_DIR="$EX" PYTHONDONTWRITEBYTECODE=1
echo "[b-07] display=$DISPLAY xdpyinfo=$probe jitter_ms=$jitter_ms xdg_runtime_private=yes loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
exec "$EX/.venv/bin/python" "$SCRIPT" "$@"
