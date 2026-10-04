#!/usr/bin/env bash
# FRESH-07R in-session entry for the N-03 rows (inside hostless -> fresh07_chunks.sh -> cua-x11-session.sh with AT-SPI).
#   n03_session.sh <wt> <driver> <sha256> <plan> <runs> <work> <prefix> <soft-cap-s> <block>...
# Calls the ORIGINAL N-03 run_block.sh (orig/n-03/harness, blob-identical) once per plan block, as N-03's
# run_all.sh did, with the FRESH-07 timing rules added around it:
#   - a block with <runs>/<label>/DONE is skipped. N-03's failure rule: a block directory without DONE that has
#     trials is kept, marked INTERRUPTED and never re-run (it stays in the denominators); one without trials
#     (session failed before any trial) is kept and the block is re-run under the next label (-r1, -r2, ...);
#   - soft cap: no new block after <soft-cap-s> seconds (exit 76);
#   - load rule: a block starts only at 1-min loadavg <= 4.0 (re-read every second for up to 60 s, else exit 75);
#     FRESH07_NO_LOAD_GATE=1 (non-timing controls only) records the load and skips the rule.
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; RUNS="$5"; WORK="$6"; PREFIX="$7"; CAP="$8"; shift 8
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not inside the isolated X11 session" >&2; exit 96; }
[ "${R2_10_OUTER_HOSTLESS:-0}" = "1" ] || { echo "refusing: caller is not under hostless" >&2; exit 96; }
xdpyinfo >/dev/null 2>&1 || { echo "[n03s] display unreachable" >&2; exit 97; }
HERE="$(cd "$(dirname "$0")" && pwd)"; RB="$HERE/../orig/n-03/harness/run_block.sh"
mkdir -p "$RUNS"; GATE_LOG="$RUNS/load-gate.jsonl"; t0=$(date +%s)
gate() {
  local i l
  if [ "${FRESH07_NO_LOAD_GATE:-0}" = 1 ]; then
    echo "{\"t\":\"$(date -u +%FT%T.%3NZ)\",\"what\":\"$1\",\"load1\":$(cut -d' ' -f1 /proc/loadavg),\"gate\":\"off (non-timing)\"}" >> "$GATE_LOG"; return 0
  fi
  for i in $(seq 0 60); do
    l=$(cut -d' ' -f1 /proc/loadavg)
    if awk -v l="$l" 'BEGIN{exit !(l <= 4.0)}'; then echo "{\"t\":\"$(date -u +%FT%T.%3NZ)\",\"what\":\"$1\",\"waited_s\":$i,\"load1\":$l,\"ok\":true}" >> "$GATE_LOG"; return 0; fi
    sleep 1
  done
  echo "{\"t\":\"$(date -u +%FT%T.%3NZ)\",\"what\":\"$1\",\"waited_s\":60,\"load1\":$l,\"ok\":false}" >> "$GATE_LOG"; return 1
}
for b in "$@"; do
  label="$PREFIX-$b"; n=0; skip=0
  while [ -e "$RUNS/$label" ] && [ ! -e "$RUNS/$label/DONE" ]; do
    if [ -e "$RUNS/$label/INTERRUPTED" ]; then skip=1; break; fi
    if grep -q '"event": "trial"' "$RUNS/$label/trials.jsonl" 2>/dev/null; then : > "$RUNS/$label/INTERRUPTED"; skip=1; break; fi
    n=$((n + 1)); label="$PREFIX-$b-r$n"
  done
  [ "$skip" = 1 ] && continue
  [ -e "$RUNS/$label/DONE" ] && continue
  [ $(( $(date +%s) - t0 )) -gt "$CAP" ] && { echo "[n03s] soft cap before $b"; exit 76; }
  gate "$label" || { echo "[n03s] load rule: $label not started"; exit 75; }
  mkdir -p "$RUNS/$label"
  "$RB" "$WT" "$DRV" "$DSHA" "$PLAN" "$b" "$label" "$RUNS/$label" "$WORK/$label" > "$RUNS/$label/session-log.txt" 2>&1
  rc=$?; echo "[n03s] $label rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  [ "$rc" -eq 0 ] && : > "$RUNS/$label/DONE"
done
exit 0
