#!/usr/bin/env bash
# usage (on the host): run_unit.sh <worktree> <lanes> <out-file> <mode>
# Takes the cargo-build lock FIRST, then the shared quiet-lane lock, then runs unit_in_session.sh
# through hostless + hostless-strict inside a private cua-x11-session.sh. Lock receipts go to the
# first lines of <out-file>.
set -uo pipefail
WT="$1"; LANES="$2"; OUT="$3"; MODE="$4"
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCKS=/mnt/zer0models/cua-lane-tmp/locks
printf '{"locks":"cargo-build then quiet-shared","mode":"%s","requested":"%s"}\n' "$MODE" "$(date -u +%FT%T.%3NZ)" > "$OUT"
flock "$LOCKS/cargo-build.lock" flock -s "$LOCKS/quiet-lane.lock" bash -c '
  printf "{\"locks\":\"cargo-build+quiet-shared\",\"acquired\":\"%s\",\"loadavg\":\"%s\"}\n" "$(date -u +%FT%T.%3NZ)" "$(cut -d" " -f1-3 /proc/loadavg)" >> "$1"
  shift
  TMPDIR=/mnt/zer0models/cua-lane-tmp/own20g "$@"' _ "$OUT" \
  "$LANES/bin/hostless" "$LANES/bin/hostless-strict" env CUA_SESSION_ATSPI=1 \
  "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
  "$LANES/cua-x11-session.sh" "$HERE/unit_in_session.sh" "$WT" /mnt/zer0models/cargo-home-cua \
  /mnt/zer0models/cargo-targets/cua-release-n02 /home/kvn/.rustup "$MODE" >> "$OUT" 2>&1
rc=$?
printf '{"released":"%s","rc":%d}\n' "$(date -u +%FT%T.%3NZ)" "$rc" >> "$OUT"
exit $rc
