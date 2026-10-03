#!/usr/bin/env bash
# FIX-03 browser block, INSIDE cua-x11-session.sh (always: hostless -> qlock.sh shared -> session -> this).
# Pattern of harness/fix02-w3/browser/run_block.sh (RECERT a3 copy); runs fix03_browser.py.
# usage: run_block_fix03.sh <worktree> <harness args...>
set -uo pipefail
WT="$1"; shift
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
[ "${FIX03_OUTER_HOSTLESS:-0}" = "1" ] || { echo "refusing: caller is not under hostless" >&2; exit 96; }
case "${XDG_RUNTIME_DIR:-}" in "$(dirname "$TMPDIR")"/*) ;; *) echo "refusing: XDG_RUNTIME_DIR not private" >&2; exit 96 ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) echo "refusing: host session bus" >&2; exit 96 ;; esac
[ -z "${TYPESAFE_API_KEY:-}" ] || { echo "refusing: provider key present (lane cap 0)" >&2; exit 98; }
[ -z "${CUA_DRIVER_EXP_SET_FILES_GAP_MS:-}" ] || { echo "refusing: seam variable set outside the harness" >&2; exit 96; }
xdpyinfo > /dev/null 2>&1 || { echo "[fix03-probe] xdpyinfo FAILED DISPLAY=$DISPLAY" >&2; exit 95; }
echo "[fix03-probe] xdpyinfo ok DISPLAY=$DISPLAY outer_hostless=$FIX03_OUTER_HOSTLESS"
echo "[fix03] loadavg=$(cut -d' ' -f1-3 /proc/loadavg) phase_args=$(printf '%s ' "$@" | sed -E 's#[^ ]*/##g')"
EX="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec "$EX/.venv/bin/python" "$HERE/fix03_browser.py" --examples "$EX" "$@"
