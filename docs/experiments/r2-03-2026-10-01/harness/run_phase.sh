#!/usr/bin/env bash
# usage (always through the isolated session):
#   cua-x11-session.sh <packet>/harness/run_phase.sh <phase> <pairs> <worktree> <driver-bin> <driver-sha256> <out> <budget-file>
# Refuses to run outside a private X11 session. Default Driver safety settings; no overrides.
set -uo pipefail
PHASE="$1"; PAIRS="$2"; WT="$3"; DRV="$4"; DSHA="$5"; OUT="$6"; BUDGET="$7"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
EX="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
echo "[r2-03] phase=$PHASE pairs=$PAIRS loadavg=$(cut -d' ' -f1-3 /proc/loadavg) key_present=$([ -n "${TYPESAFE_API_KEY:-}" ] && echo yes || echo no)"
exec "$EX/.venv/bin/python" "$HERE/r2_03_harness.py" --phase "$PHASE" --pairs "$PAIRS" --examples "$EX" \
  --driver "$DRV" --tested-sha a0bca744067d04f05904319d3d919be30c336556 --driver-sha256 "$DSHA" \
  --out "$OUT" --budget-file "$BUDGET"
