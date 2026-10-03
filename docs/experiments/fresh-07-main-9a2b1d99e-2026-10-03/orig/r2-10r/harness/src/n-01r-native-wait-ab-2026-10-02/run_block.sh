#!/usr/bin/env bash
# usage (inside hostless + cua-x11-session.sh with CUA_SESSION_ATSPI=1):
#   run_block.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <block> <label> <raw-out-dir> <work-dir>
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; BLOCK="$5"; LABEL="$6"; OUT="$7"; WORK="$8"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
actual="$(sha256sum "$DRV" | cut -d' ' -f1)"
[ "$actual" = "$DSHA" ] || { echo "refusing: driver sha256 $actual != $DSHA" >&2; exit 98; }
mkdir -p "$OUT" "$WORK"
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" "$HERE/n01r_harness.py" \
  --wt "$WT" --driver "$DRV" --driver-sha256 "$DSHA" --plan "$PLAN" \
  --plan-sha256 "$(sha256sum "$PLAN" | cut -d' ' -f1)" --block "$BLOCK" --label "$LABEL" \
  --out "$OUT" --work "$WORK"
