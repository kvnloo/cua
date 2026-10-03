#!/usr/bin/env bash
# usage (inside cua-sway-session.sh or cua-x11-session.sh):
#   run_in_session.sh <worktree> <driver-bin> <raw-out-dir> <scratch-dir> [modality_truth.py args]
# Adapted from OWN-16 run_in_session.sh: accepts the private sway session too. Records the Driver
# (RECERT-FIX a3: runs the modality_truth.py copy next to this file instead of the wave-3 packet path.)
# version/sha256 and the session facts inside the session, then runs the harness.
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"; WORK="$4"; shift 4
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: HYPRLAND_* set" >&2; exit 97; }
if [ -n "${CUA_SWAY_RUN:-}" ]; then
  case "${XDG_RUNTIME_DIR:-}" in "$CUA_SWAY_RUN"/*) ;; *) echo "refusing: not in private sway session" >&2; exit 97;; esac
  KIND=sway
else
  [ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
  KIND=x11
fi
mkdir -p "$OUT" "$WORK"
{ echo "session_kind=$KIND"
  echo "driver_version=$("$DRV" --version 2>&1 | head -1)"
  echo "driver_sha256=$(sha256sum "$DRV" | cut -d' ' -f1)"
  echo "session_atspi=${CUA_SESSION_ATSPI:-unset}"
  echo "wayland_debug=${WAYLAND_DEBUG:-unset}"
  echo "wayland_display_set=$([ -n "${WAYLAND_DISPLAY:-}" ] && echo yes || echo no)"
  echo "x_display_set=$([ -n "${DISPLAY:-}" ] && echo yes || echo no)"
  echo "swaysock_set=$([ -n "${SWAYSOCK:-}" ] && echo yes || echo no)"
  if [ "$KIND" = sway ]; then
    echo "sway_version=$(sway --version 2>&1 | head -1)"
    echo "x_record=$(xdpyinfo -queryExtensions -display "$DISPLAY" 2>/dev/null | grep -c ' RECORD ')"
  fi
  echo "telemetry=${CUA_DRIVER_RS_TELEMETRY_ENABLED:-unset} dnt=${DO_NOT_TRACK:-unset}"
  echo "utc_offset=$(date +%z)"; } > "$OUT/session-env.txt"
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" \
  "$(cd "$(dirname "$0")" && pwd)/modality_truth.py" \
  --wt "$WT" --driver "$DRV" --out "$OUT" --work "$WORK" "$@"
