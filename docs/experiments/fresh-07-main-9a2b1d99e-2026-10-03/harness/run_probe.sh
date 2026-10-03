#!/usr/bin/env bash
# FRESH-07 probe runner, executed INSIDE cua-x11-session.sh (CUA_SESSION_ATSPI=1), under hostless.
#   run_probe.sh <worktree> <out-dir> <runs> NAME=BIN:SHA256 ...
set -uo pipefail
WT="$1"; OUT="$2"; RUNS="$3"; shift 3
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
mkdir -p "$OUT"
echo "[probe] display_set=yes atspi=${CUA_SESSION_ATSPI:-0} loadavg=$(cut -d' ' -f1-3 /proc/loadavg) start=$(date -u +%FT%TZ)" | tee "$OUT/session.txt"
HERE="$(cd "$(dirname "$0")" && pwd)"
"$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" "$HERE/probe.py" --wt "$WT" --out "$OUT" --runs "$RUNS" "$@"
rc=$?
echo "[probe] rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg) end=$(date -u +%FT%TZ)" | tee -a "$OUT/session.txt"
exit $rc
