#!/usr/bin/env bash
# usage (always: hostless -> lock wrapper -> cua-x11-session.sh -> this script):
#   run_block.sh <worktree> <harness args...>
# Refuses outside a private X11 session. Default Driver safety settings; no overrides; no key.
set -uo pipefail
WT="$1"; shift
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
# hostless evidence: the host runtime dir is a private empty tmpfs and only our Xvfb socket exists.
host_rt="/run/user/$(id -u)"
if ls "$host_rt"/wayland-* "$host_rt"/bus "$host_rt"/hypr >/dev/null 2>&1; then echo "refusing: host runtime dir visible" >&2; exit 96; fi
x11_sockets=$(ls /tmp/.X11-unix 2>/dev/null | tr '\n' ' ')
echo "[fix01] host_runtime_entries=$(ls -A "$host_rt" 2>/dev/null | wc -l) x11_sockets=$x11_sockets"
[ -z "${TYPESAFE_API_KEY:-}" ] || { echo "refusing: provider key present (lane cap 0)" >&2; exit 98; }
EX="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
echo "[fix01] DISPLAY=$DISPLAY loadavg=$(cut -d' ' -f1-3 /proc/loadavg) args=$*"
exec "$EX/.venv/bin/python" "$HERE/fix01_harness.py" --examples "$EX" "$@"
