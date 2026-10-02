#!/usr/bin/env bash
# usage (inside cua-x11-session.sh):
#   run_in_session.sh <worktree> <driver-bin> <raw-out-dir> <scratch-dir> [modality_truth.py args]
# Records the Driver version inside the session, then runs the harness.
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"; WORK="$4"; shift 4
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
mkdir -p "$OUT" "$WORK"
{ echo "driver_version=$("$DRV" --version 2>&1 | head -1)"
  echo "driver_sha256=$(sha256sum "$DRV" | cut -d' ' -f1)"
  echo "session_atspi=${CUA_SESSION_ATSPI:-unset}"
  echo "xvfb_display_set=$([ -n "${DISPLAY:-}" ] && echo yes)"; } > "$OUT/session-env.txt"
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" \
  "$WT/docs/experiments/own-16-modality-truth-2026-10-02/modality_truth.py" \
  --wt "$WT" --driver "$DRV" --out "$OUT" --work "$WORK" "$@"
