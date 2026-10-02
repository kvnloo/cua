#!/usr/bin/env bash
# FIX-02 copy of harness/fix-01/run_block.sh (4a301d32a); runs fix02_browser.py instead of fix01_harness.py.
# usage (always: hostless -> lock wrapper -> cua-x11-session.sh -> this script):
#   run_block.sh <worktree> <harness args...>
# Refuses outside a private X11 session. Default Driver safety settings; no overrides; no key.
set -uo pipefail
WT="$1"; shift
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
# hostless evidence (hostless v2 strips desktop variables, privatizes XDG_RUNTIME_DIR and applies a
# Landlock scope; cua-x11-session.sh then scrubs the environment): the outer hostless marker must be
# forwarded by the caller, and every session variable must point at this private session.
[ "${FIX02_OUTER_HOSTLESS:-0}" = "1" ] || { echo "refusing: caller is not under hostless" >&2; exit 96; }
case "${XDG_RUNTIME_DIR:-}" in "$(dirname "$TMPDIR")"/*) ;; *) echo "refusing: XDG_RUNTIME_DIR not private" >&2; exit 96 ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) echo "refusing: host session bus" >&2; exit 96 ;; esac
echo "[fix02] outer_hostless=$FIX02_OUTER_HOSTLESS display=$DISPLAY xdg_runtime_private=yes"
[ -z "${TYPESAFE_API_KEY:-}" ] || { echo "refusing: provider key present (lane cap 0)" >&2; exit 98; }
EX="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
echo "[fix02] DISPLAY=$DISPLAY loadavg=$(cut -d' ' -f1-3 /proc/loadavg) phase_args=$(printf '%s ' "$@" | sed -E 's#[^ ]*/##g')"
exec "$EX/.venv/bin/python" "$HERE/fix02_browser.py" --examples "$EX" "$@"
