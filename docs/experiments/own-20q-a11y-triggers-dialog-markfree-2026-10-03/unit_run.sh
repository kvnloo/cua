#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   unit_run.sh <worktree> <lanes-dir> <locks-dir> <target-dir> <phase>
# Takes the cargo-build lock ONLY (never the quiet-lane lock: builds take the cargo lock, and no lane
# waits on one lock while holding the other), then runs unit_in_session.sh inside a private
# cua-x11-session.sh session (AT-SPI on, telemetry off). Prints one receipt line (lane-local).
set -uo pipefail
WT="$1"; LANES="$2"; LOCKS="$3"; TD="$4"; PHASE="$5"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
HERE="$(cd "$(dirname "$0")" && pwd)"
CH="${CUA_CARGO_HOME:?set CUA_CARGO_HOME to the lane kit cargo home (as in build-driver.sh)}"; RH="$HOME/.rustup"
export PATH="$HOME/.cargo/bin:$PATH"
exec 7>"$LOCKS/cargo-build.lock"; flock -x 7
acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
# shared target dirs are mtime-fresh: make this worktree's sources the newest
find "$WT/libs/cua-driver/rust" -path "$WT/libs/cua-driver/rust/target" -prune -o -type f -name '*.rs' -exec touch {} +
env CUA_SESSION_ATSPI=1 "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1" \
  "$LANES/cua-x11-session.sh" "$HERE/unit_in_session.sh" "$WT" "$CH" "$TD" "$RH" "$PHASE"
rc=$?
rel="$(date -u +%FT%T.%3NZ)"
printf '{"lane":"OWN-20Q","label":"own20q-unit-%s","lock":"cargo-build only","acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$PHASE" "$acq" "$rel" "$rc" "$la"
exit $rc
