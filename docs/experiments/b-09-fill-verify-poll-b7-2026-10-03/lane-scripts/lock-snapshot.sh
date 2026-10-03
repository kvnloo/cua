#!/usr/bin/env bash
# lock-snapshot.sh <interval-s>: B-09R read-only holder snapshots of the quiet-lane lock and the cargo-build lock
# while the lane waits for an EXCLUSIVE window. Every <interval-s> (900 = 15 min) it appends one JSON line to
# $B09_TMPDIR/locks/holders.jsonl: utc, 1-min/5-min/15-min loadavg, and for each /proc/locks entry on the two lock
# inodes the lock type (READ/WRITE), whether it is granted or a blocked waiter ("->"), pid, ppid, elapsed seconds
# and the executable name (comm). Never command lines, environ or paths. It never signals anything. It stops when
# $B09_TMPDIR/locks/stop exists. Run under bin/hostless.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LT="${B09_TMPDIR:?}"; LOCKDIR="${B09_LOCKDIR:?}"; IV="${1:-900}"
mkdir -p "$LT/locks"
qi="$(stat -c %i "$LOCKDIR/quiet-lane.lock")"; ci="$(stat -c %i "$LOCKDIR/cargo-build.lock")"
while [ ! -e "$LT/locks/stop" ]; do
  utc="$(date -u +%FT%TZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
  ents=""
  while read -r line; do
    set -- $line
    waiter=false; [ "$2" = "->" ] && { waiter=true; set -- "$1" "${@:3}"; }
    typ="$4"; pid="$5"; ino="${6##*:}"
    case "$ino" in "$qi") lk=quiet ;; "$ci") lk=cargo ;; *) continue ;; esac
    ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"; et="$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')"
    comm="$(ps -o comm= -p "$pid" 2>/dev/null)"
    ents="$ents{\"lock\":\"$lk\",\"type\":\"$typ\",\"blocked_waiter\":$waiter,\"pid\":$pid,\"ppid\":${ppid:-null},\"elapsed_s\":${et:-null},\"comm\":\"${comm//\"/}\"},"
  done < <(grep -E ":($qi|$ci) " /proc/locks)
  printf '{"utc":"%s","loadavg":"%s","entries":[%s]}\n' "$utc" "$la" "${ents%,}" >> "$LT/locks/holders.jsonl"
  for _ in $(seq "$IV"); do [ -e "$LT/locks/stop" ] && break; sleep 1; done
done
