#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   unit_run.sh <worktree> <lanes-dir> <locks-dir> <target-dir> <phase> [core]
# Takes the cargo-build lock, then the quiet-lane lock in SHARED mode (a CPU-heavy build must not run
# inside an exclusive timing window; cargo first, the order every lane uses), appends one receipt to the quiet-lane ledger, and
# runs unit_in_session.sh inside a private cua-x11-session.sh session (AT-SPI on, telemetry off).
set -uo pipefail
WT="$1"; LANES="$2"; LOCKS="$3"; TD="$4"; PHASE="$5"; CORE="${6:-}"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
HERE="$(cd "$(dirname "$0")" && pwd)"
CH="${CUA_CARGO_HOME:?set CUA_CARGO_HOME to the lane kit cargo home (as in build-driver.sh)}"; RH="$HOME/.rustup"
export PATH="$HOME/.cargo/bin:$PATH"
label="own20p-unit-$PHASE"
exec 7>"$LOCKS/cargo-build.lock"; flock -x 7
exec 8>"$LOCKS/quiet-lane.lock"; flock -s 8
acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
# shared target dirs are mtime-fresh: make this worktree's sources the newest
find "$WT/libs/cua-driver/rust" -path "$WT/libs/cua-driver/rust/target" -prune -o -type f -name '*.rs' -exec touch {} +
env CUA_SESSION_ATSPI=1 "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
  "$LANES/cua-x11-session.sh" "$HERE/unit_in_session.sh" "$WT" "$CH" "$TD" "$RH" "$PHASE" "$CORE"
rc=$?
rel="$(date -u +%FT%T.%3NZ)"
printf '{"lane":"OWN-20P","label":"%s","mode":"shared+cargo","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$label" "$$" "$acq" "$rel" "$rc" "$la" >> "$LOCKS/quiet-lane-ledger.jsonl"
exit $rc
