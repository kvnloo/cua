#!/usr/bin/env bash
# run_all.sh <runs-root>   the preregistered MULTISEAT schedule (PREREG.json), host side, under hostless.
#   main:      8 pairs x {seq, conc} rounds of 4 Hermes agents; order alternates per pair; each round inside
#              quiet-timed (exclusive quiet-lane lock + ledger) because makespans are reported.
#   lookalike: 5 rounds of 2 concurrent Hermes agents on look-alike windows (correctness only; no timing claim).
#   crosswire: 3 reps of the deliberate cross-session attempts.
#   seat-lookalike: 3 reps (2-seat single compositor, non-Driver).  seat-driver: 2 reps (2 Driver agents, 2 seats).
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
ROOT="$1"; H="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT"/{main,lookalike,crosswire,seat-lookalike,seat-driver}
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$ROOT/schedule.log"; }
hex() { od -An -N2 -tx1 /dev/urandom | tr -d ' \n'; }
specs() {  # round-id n -> "A1:MS-<round>-A1-<hex>:0 ..."
  local r="$1" n="$2" i out=""
  for i in $(seq 1 "$n"); do out="$out A$i:MS-$r-A$i-$(hex):0"; done
  echo "$out"
}
for p in $(seq -w 1 8); do
  if [ $((10#$p % 2)) = 1 ]; then order="seq conc"; else order="conc seq"; fi
  for arm in $order; do
    r="p$p-$arm"
    log "main $r start"
    # shellcheck disable=SC2046
    "${MS_QUIET:?}" "ms-main-$r" "$H/run_round.sh" "$ROOT/main/$r" "$arm" hermes $(specs "$r" 4) >> "$ROOT/schedule.log" 2>&1
    log "main $r rc=$?"
  done
done
for l in $(seq -w 1 5); do
  r="l$l"; log "lookalike $r start"
  # shellcheck disable=SC2046
  "$H/run_round.sh" "$ROOT/lookalike/$r" conc hermes $(specs "$r" 2) >> "$ROOT/schedule.log" 2>&1
  log "lookalike $r rc=$?"
done
for x in 1 2 3; do
  log "crosswire x$x start"; "$H/run_crosswire.sh" "$ROOT/crosswire/x$x" "MSX$x-$(hex)" >> "$ROOT/schedule.log" 2>&1
  log "crosswire x$x rc=$?"
done
seat() {  # kind rep
  ( cd "$H/../../../.." && CUA_SWAY_SEATS=2 CUA_SWAY_OUTPUTS=1280x720 CUA_SWAY_TIMEOUT=300 \
      CUA_SESSION_EXTRA_ENV="MS_VENV_PY=$MS_VENV/bin/python CUA_DRIVER_BIN=$CUA_DRIVER_BIN" \
      exec "${MS_SESSION_SCRIPT:?}" "$H/seat_controls.sh" "$1" "$ROOT/seat-$1/$2" "$2" ) >> "$ROOT/schedule.log" 2>&1
}
for s in 1 2 3; do log "seat-lookalike sl$s"; seat lookalike "sl$s"; log "rc=$?"; done
for s in 1 2; do log "seat-driver sd$s"; seat driver "sd$s"; log "rc=$?"; done
log "schedule complete"
