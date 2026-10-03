#!/usr/bin/env bash
# RECERT-FIX a3 copy of harness/fix02-w3/browser/locked.sh (cea02cb74); only the ledger lane name differs.
# locked.sh shared|exclusive <label> <packet-ledger> <cmd...>
# Holds the quiet-lane lock (shared: flock -s; exclusive: flock -x) for the whole command and writes
# one receipt line to the packet ledger AND the loop-wide ledger, so lock compliance is evidenced by
# the harness. Exclusive timing phases may use bin/quiet-timed instead (same lock, same ledger).
set -euo pipefail
mode="$1"; label="$2"; ledger="$3"; shift 3
LOCKDIR="${CUA_LANE_LOCKDIR:?set CUA_LANE_LOCKDIR to the shared lock dir}"; GLOBAL="$LOCKDIR/quiet-lane-ledger.jsonl"
case "$mode" in shared) flag=-s ;; exclusive) flag=-x ;; *) echo "mode must be shared|exclusive" >&2; exit 64 ;; esac
exec 9>"$LOCKDIR/quiet-lane.lock"
flock "$flag" 9
acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(cut -d' ' -f1-3 /proc/loadavg)"
set +e; "$@"; rc=$?; set -e
rel="$(date -u +%FT%T.%3NZ)"
line=$(printf '{"lane":"RECERT-FIX-a3","label":"%s","mode":"%s","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s","cmd_sha256":"%s"}' \
  "$label" "$mode" "$$" "$acq" "$rel" "$rc" "$la_acq" "$(printf '%s\0' "$@" | sha256sum | cut -c1-16)")
printf '%s\n' "$line" >> "$ledger"
printf '%s\n' "$line" >> "$GLOBAL"
exit "$rc"
