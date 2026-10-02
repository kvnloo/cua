#!/usr/bin/env bash
# usage: hostless run_batch.sh <lanes-dir> <worktree> <driver> <raw-root> <scratch-root> <schedule.json> [first-seq] [last-seq]
# Runs each pre-registered block in its OWN isolated X11 session (private Xvfb + private AT-SPI bus),
# each block under bin/quiet-timed (EXCLUSIVE quiet-lane lock + ledger receipt), <= 10 measured
# mutations per acquisition. Every block is kept, whatever its exit code. Must run under hostless.
set -uo pipefail
LANES="$1"; WT="$2"; DRV="$3"; RAW="$4"; SCR="$5"; SCHED="$6"; FIRST="${7:-1}"; LAST="${8:-999}"
[ "${CUA_HOSTLESS:-}" = "1" ] || { echo "refusing: run_batch.sh must run under bin/hostless" >&2; exit 97; }
PKT="$WT/docs/experiments/own-20-atspi-invalidation-census-2026-10-02"
mkdir -p "$RAW" "$SCR"
: "${TMPDIR:?set TMPDIR to the lane temp root}"
n=$(grep -c '"block_id"' "$SCHED")
for i in $(seq 0 $((n - 1))); do
  seq_no=$((i + 1)); [ "$seq_no" -lt "$FIRST" ] && continue; [ "$seq_no" -gt "$LAST" ] && continue
  bid=$(grep '"block_id"' "$SCHED" | sed -n "$((i + 1))p" | sed 's/.*"block_id": "\([^"]*\)".*/\1/')
  btype=$(grep '"block_type"' "$SCHED" | sed -n "$((i + 1))p" | sed 's/.*"block_type": "\([^"]*\)".*/\1/')
  d="$RAW/$bid"; mkdir -p "$d"
  t0=$(date -u +%FT%T.%3NZ); la0=$(cut -d' ' -f1-3 /proc/loadavg)
  ( cd "$WT" && CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" \
      "$LANES/bin/quiet-timed" "own20-$bid" "$LANES/cua-x11-session.sh" "$PKT/run_in_session.sh" \
      "$WT" "$DRV" "$d" "$SCR/$bid" --block-type "$btype" --block-id "$bid" > "$d/session.log" 2>&1 )
  rc=$?
  printf '{"seq":%d,"block_id":"%s","block_type":"%s","start_utc":"%s","end_utc":"%s","rc":%d,"loadavg_before":"%s","loadavg_after":"%s","hostless":"%s"}\n' \
    "$seq_no" "$bid" "$btype" "$t0" "$(date -u +%FT%T.%3NZ)" "$rc" "$la0" "$(cut -d' ' -f1-3 /proc/loadavg)" "${CUA_HOSTLESS:-}" >> "$RAW/batch.jsonl"
done
