#!/usr/bin/env bash
# usage (inside cua-x11-session.sh with CUA_SESSION_ATSPI=1 + CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1"):
#   run_in_session.sh <worktree> <driver-bin> <raw-out-dir> <scratch-dir> --arm <label> [profile_atspi.py args]
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"; WORK="$4"; shift 4
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
mkdir -p "$OUT" "$WORK"
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" \
  "$WT/docs/experiments/r2-04-2026-10-01/profile_atspi.py" \
  --wt "$WT" --driver "$DRV" --out "$OUT" --work "$WORK" "$@"
