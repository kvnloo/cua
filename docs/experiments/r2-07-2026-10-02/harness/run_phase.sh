#!/usr/bin/env bash
# usage (always through the isolated session; locks are taken OUTSIDE by the caller):
#   cua-x11-session.sh <packet>/harness/run_phase.sh <phase> <worktree> <driver-bin> <driver-sha256> <out> <budget-file> [extra harness args...]
# Refuses to run outside a private X11 session. Default Driver safety settings; no overrides.
set -uo pipefail
PHASE="$1"; WT="$2"; DRV="$3"; DSHA="$4"; OUT="$5"; BUDGET="$6"; shift 6
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
EX="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
echo "[r2-07] phase=$PHASE loadavg=$(cut -d' ' -f1-3 /proc/loadavg) key_present=$([ -n "${TYPESAFE_API_KEY:-}" ] && echo yes || echo no)"
exec "$EX/.venv/bin/python" "$HERE/r2_07_harness.py" --phase "$PHASE" --examples "$EX" \
  --driver "$DRV" --driver-sha256 "$DSHA" --tested-sha 031ee5f58c222ea60ca0fcaf0a7858535a73c75b \
  --out "$OUT" --budget-file "$BUDGET" "$@"
