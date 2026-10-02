#!/usr/bin/env bash
# usage (inside cua-x11-session.sh, which runs under bin/hostless):
#   run_in_session.sh <worktree> <driver-bin> <raw-block-dir> <scratch-dir> [census.py args]
# Refuses to run outside an isolated X11 session, records the Driver version and sha256 INSIDE the
# session plus the session's DISPLAY, then runs the census harness for one block.
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"; WORK="$4"; shift 4
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  && [ "${CUA_SESSION_ATSPI:-0}" = "1" ] || { echo "refusing: not inside an isolated AT-SPI X11 session" >&2; exit 97; }
mkdir -p "$OUT" "$WORK"
{ echo "driver_version=$("$DRV" --version 2>&1 | head -1)"
  echo "driver_sha256=$(sha256sum "$DRV" | cut -d' ' -f1)"
  echo "display=${DISPLAY}"
  echo "session_atspi=${CUA_SESSION_ATSPI:-unset}"
  echo "loadavg_start=$(cut -d' ' -f1-3 /proc/loadavg)"; } > "$OUT/session-env.txt"
"$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" \
  "$WT/docs/experiments/own-20-atspi-invalidation-census-2026-10-02/census.py" \
  --wt "$WT" --driver "$DRV" --out "$OUT" --work "$WORK" "$@"
rc=$?
echo "loadavg_end=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT/session-env.txt"
exit $rc
