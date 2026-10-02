#!/usr/bin/env bash
# Lane-D block entry, run INSIDE the private X11 session (cua-x11-session.sh), under hostless,
# under quiet-timed (the EXCLUSIVE quiet-lane lock is already held when this starts, so it is
# taken before the first MCP session of the block opens):
#
#   <lanes>/bin/hostless <lanes>/bin/quiet-timed i107-d-<block> \
#     <lanes>/cua-x11-session.sh <packet>/harness/session_entry.sh <block> <driver-bin> <out-dir>
#
# The worktree and jev-use paths are derived from this file's location; nothing host-specific
# is written into the packet.
set -euo pipefail
BLOCK="$1"; DRV="$2"; OUT="$3"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="$(cd "$HERE/../../../.." && pwd)"
JEV="$WT/libs/cua-driver/examples/jev-use"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
[ "${CUA_HOSTLESS:-}" = "1" ] || { echo "refusing: not under hostless" >&2; exit 98; }
SHA="f3a5c01a2c1b5bce75ccb611d0bacd491a7c3b1a8c3fac65889a1fc9d6977aed"
TREE="$(git -C "$WT" rev-parse HEAD:libs/cua-driver/examples/jev-use 2>/dev/null || echo unknown)"
mkdir -p "$OUT"
echo "[entry] block=$BLOCK version=$("$DRV" --version 2>&1) caller_tree=$TREE" >&2
cd "$HERE"
export JEV_USE_DIR="$JEV" PYTHONDONTWRITEBYTECODE=1
exec "$JEV/.venv/bin/python" run_d.py --driver "$DRV" --out "$OUT" --block "$BLOCK" \
  --binary-sha256 "$SHA" --caller-tree "$TREE" --lock-label "i107-d-$BLOCK"
