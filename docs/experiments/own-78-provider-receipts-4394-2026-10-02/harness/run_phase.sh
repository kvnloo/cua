#!/usr/bin/env bash
# usage (always through the isolated session, under the shared quiet-lane lock):
#   flock -s <quiet-lane.lock> cua-x11-session.sh <packet>/harness/run_phase.sh <phase> <cells> <worktree> <driver-bin> <driver-sha256> <out> <budget-file> [tested-sha]
# Refuses to run outside a private X11 session. Default Driver safety settings; no overrides.
set -uo pipefail
PHASE="$1"; CELLS="$2"; WT="$3"; DRV="$4"; DSHA="$5"; OUT="$6"; BUDGET="$7"; TESTED="${8:-039257811e0bbb2348c616c52562409923d2856f}"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
EX="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
echo "[own78] phase=$PHASE cells=$CELLS loadavg=$(cut -d' ' -f1-3 /proc/loadavg) key_present=$([ -n "${TYPESAFE_API_KEY:-}" ] && echo yes || echo no) node=$(node --version)"
exec "$EX/.venv/bin/python" "$HERE/own78_harness.py" --phase "$PHASE" --cells "$CELLS" --examples "$EX" \
  --driver "$DRV" --driver-sha256 "$DSHA" --tested-sha "$TESTED" \
  --out "$OUT" --budget-file "$BUDGET"
