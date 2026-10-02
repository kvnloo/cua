#!/usr/bin/env bash
# usage: hostless run_controls.sh <lanes-dir> <worktree> <driver> <raw-root> <scratch-root> <base-main.py>
# Count-only controls, each in its own isolated AT-SPI X11 session under flock -s on the quiet-lane lock
# (receipt lines in <raw-root>/lock-ledger.jsonl):
#   D1  default-off smoke of the test-only fixture control channel (base vs modified fixture)
#   G1  Chromium gate: does the Driver-chosen Chrome expose AT-SPI here without a forbidden flag?
set -uo pipefail
LANES="$1"; WT="$2"; DRV="$3"; RAW="$4"; SCR="$5"; BASE="$6"
[ "${CUA_HOSTLESS:-}" = "1" ] || { echo "refusing: run_controls.sh must run under bin/hostless" >&2; exit 97; }
: "${TMPDIR:?set TMPDIR to the lane temp root}"
PKT="$WT/docs/experiments/own-20-atspi-invalidation-census-2026-10-02"
PY="$WT/libs/cua-driver/examples/jev-use/.venv/bin/python"
LOCK="$TMPDIR/locks/quiet-lane.lock"
run() {  # label outdir script args...
  local label="$1" d="$2"; shift 2; mkdir -p "$d"
  exec 8>"$LOCK"; flock -s 8
  local acq; acq=$(date -u +%FT%T.%3NZ); local la; la=$(cut -d' ' -f1-3 /proc/loadavg)
  ( cd "$WT" && CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" "$LANES/cua-x11-session.sh" "$PY" "$@" > "$d/session.log" 2>&1 )
  local rc=$?
  printf '{"label":"%s","mode":"shared","acquired":"%s","released":"%s","rc":%d,"loadavg":"%s"}\n' \
    "$label" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la" >> "$RAW/lock-ledger.jsonl"
  flock -u 8; exec 8>&-
}
run own20-D1-default-off "$RAW/D1-default-off" "$PKT/default_off_smoke.py" "$WT" "$DRV" "$BASE" "$RAW/D1-default-off" "$SCR/D1"
run own20-G1-chrome-gate "$RAW/G1-chrome-gate" "$PKT/chrome_atspi_probe.py" "$WT" "$DRV" "$RAW/G1-chrome-gate"
