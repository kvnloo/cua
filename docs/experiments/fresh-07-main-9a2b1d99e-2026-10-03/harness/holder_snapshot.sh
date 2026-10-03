#!/usr/bin/env bash
# FRESH-07R: read-only snapshot of the quiet-lane lock (no signal, no write to any process).
#   holder_snapshot.sh <lockfile> <out-dir>   -> <out-dir>/holders-<UTC>.tsv
# One row per /proc/locks entry on the lock inode (holder or queued waiter, READ = SHARED, WRITE = EXCLUSIVE)
# and one row per process with an open fd on the lock file: pid, ppid, elapsed time, executable name (comm).
# No command lines or paths are written.
set -uo pipefail
L="$1"; OUT="$2"; mkdir -p "$OUT"
ino=$(stat -c %i "$L"); ts=$(date -u +%Y%m%dT%H%M%SZ); f="$OUT/holders-$ts.tsv"
{
  printf '# quiet-lane lock snapshot %s loadavg=%s\n' "$(date -u +%FT%TZ)" "$(cut -d' ' -f1-3 /proc/loadavg)"
  printf 'source\trole\tmode\tpid\tppid\tetime\tcomm\n'
  grep -E ":$ino " /proc/locks | while read -r line; do
    role=holder; case "$line" in *"->"*) role=waiter;; esac
    set -- ${line#*:}; [ "$1" = "->" ] && shift
    mode=$3; pid=$4
    printf 'proc_locks\t%s\t%s\t%s\t%s\t%s\t%s\n' "$role" "$mode" "$pid" "$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')" \
      "$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')" "$(cat /proc/$pid/comm 2>/dev/null)"
  done
  for d in /proc/[0-9]*; do
    p=${d#/proc/}
    for fd in "$d"/fd/*; do
      if [ "$(readlink "$fd" 2>/dev/null)" = "$L" ]; then
        printf 'open_fd\t-\t-\t%s\t%s\t%s\t%s\n' "$p" "$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')" \
          "$(ps -o etime= -p "$p" 2>/dev/null | tr -d ' ')" "$(cat "$d/comm" 2>/dev/null)"
        break
      fi
    done
  done 2>/dev/null
} > "$f"
echo "$f"
