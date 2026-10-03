#!/usr/bin/env bash
# FIX-20O row orchestrator (derived from the original OWN-20P / OWN-20Q run_all.sh, which stay
# blob-identical under ../orig/). Run on the host ALWAYS as: hostless hostless-strict run_rows.sh ...
#   run_rows.sh <mode> <worktree> <binaries.json> <plan.json> <runs-dir> <label-prefix> [block ...]
# mode: own20p | own20q  -> the original orig/<lane>/session_entry.sh -> harness/run_block.sh (U/G roles)
#       popup            -> harness/popup_entry.sh (this packet's popup / tools-list harness)
#       probe            -> orig/fresh-07/run_probe.sh (FRESH-07's window-tree probe)
# <binaries.json> maps each role / name to {"path", "sha256"} (lane-local, never committed).
# Changes against the original run_all.sh, nothing else:
#   * before each block: wait while /proc/locks shows a queued EXCLUSIVE waiter on the quiet-lane lock
#     inode (yield to the loop's timing lanes), and >= 30 s after this lane's previous release;
#   * the quiet lane is taken SHARED with flock -o (the session runs with the lock fd closed) and one
#     receipt per block ('mode':'shared', lane FIX-20O) goes to the quiet-lane ledger; blocks are sized
#     to hold it <= 300 s;
#   * the session also gets PYTHONPATH=harness/focuslog and FIX20O_FOCUS_LOG=1, so the GTK3 fixture
#     writes its own focus log (focuslog/sitecustomize.py); after the block the logs are copied next
#     to the raw trials (raw/focuslog/<trial>.jsonl).
set -uo pipefail
MODE="$1"; WT="$2"; BINS="$3"; PLAN="$4"; RUNS="$5"; PREFIX="$6"; shift 6
LANES="${FIX20O_LANES:?lanes dir (cua-x11-session.sh)}"; LOCKS="${FIX20O_LOCKS:?locks dir (quiet-lane.lock + ledger)}"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
if ls -A "/run/user/$(id -u)" 2>/dev/null | grep -qE '^(wayland-|hypr|bus$|at-spi$|pipewire)' \
   || ls -A /tmp/.X11-unix 2>/dev/null | grep -q .; then
  echo "refusing: host desktop sockets visible (run as: hostless hostless-strict run_rows.sh ...)" >&2; exit 95
fi
LOCK="$LOCKS/quiet-lane.lock"; LEDGER="$LOCKS/quiet-lane-ledger.jsonl"
[ -e "$LOCK" ] || { echo "refusing: quiet-lane lock missing" >&2; exit 94; }
HERE="$(cd "$(dirname "$0")" && pwd)"; PKT="$(dirname "$HERE")"
case "$MODE" in
  own20p) ENTRY="$PKT/orig/own-20p/session_entry.sh"; TEL=0 ;;
  own20q) ENTRY="$PKT/orig/own-20q/session_entry.sh"; TEL=false ;;
  popup)  ENTRY="$HERE/popup_entry.sh"; TEL=0 ;;
  probe)  ENTRY="$PKT/orig/fresh-07/run_probe.sh"; TEL=0 ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
mkdir -p "$RUNS"
INO="$(stat -c %i "$LOCK")"
role() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]])' "$BINS" "$1" "$2"; }
mapfile -t order < <(python3 -c 'import json,sys; [print(b["block"]) for b in json.load(open(sys.argv[1]))["blocks"]]' "$PLAN")
blocks=("$@")
[ ${#blocks[@]} -eq 0 ] && blocks=("${order[@]}")
GAP_FILE="$(dirname "$RUNS")/.fix20o-last-release-epoch"
for b in "${blocks[@]}"; do
  label="$PREFIX-$b"; n=0
  while [ -e "$RUNS/$label" ]; do n=$((n+1)); label="$PREFIX-$b-r$n"; done
  dir="$RUNS/$label"; mkdir -p "$dir"
  work="$(dirname "$RUNS")/runs-work/$label"
  case "$MODE" in
    own20p|own20q)
      read -r ru rg < <(python3 -c 'import json,sys; b=[x for x in json.load(open(sys.argv[1]))["blocks"] if x["block"]==sys.argv[2]]; print(b[0]["bins"]["U"], b[0]["bins"]["G"]) if b else print("- -")' "$PLAN" "$b")
      [ "$ru" != "-" ] || { echo "unknown block $b" >&2; exit 2; }
      inner=("$ENTRY" "$WT" "$(role "$ru" path)" "$(role "$ru" sha256)" "$(role "$rg" path)" "$(role "$rg" sha256)" \
             "$PLAN" "$b" "$label" "$dir/raw" "$work")
      desc="U=$ru G=$rg" ;;
    popup|probe)
      mapfile -t names < <(python3 -c 'import json,sys; b=[x for x in json.load(open(sys.argv[1]))["blocks"] if x["block"]==sys.argv[2]][0]; [print(n) for n in b["bins"]]' "$PLAN" "$b")
      specs=(); for nm in "${names[@]}"; do specs+=("$nm=$(role "$nm" path):$(role "$nm" sha256)"); done
      if [ "$MODE" = popup ]; then
        inner=("$ENTRY" "$WT" "$PLAN" "$b" "$label" "$dir/raw" "$work" "${specs[@]}")
      else
        runs="$(python3 -c 'import json,sys; print([x for x in json.load(open(sys.argv[1]))["blocks"] if x["block"]==sys.argv[2]][0]["runs"])' "$PLAN" "$b")"
        inner=("$ENTRY" "$WT" "$dir/raw" "$runs" "${specs[@]}")
      fi
      desc="bins=${names[*]}" ;;
  esac
  waited=0
  while grep -qE -- "-> FLOCK +ADVISORY +WRITE +[0-9]+ +[0-9a-f]+:[0-9a-f]+:${INO} " /proc/locks; do sleep 5; waited=$((waited+5)); done
  if [ -f "$GAP_FILE" ]; then
    wait_s=$(( $(cat "$GAP_FILE") + 30 - $(date +%s) )); [ "$wait_s" -gt 0 ] && sleep "$wait_s"
  fi
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label $desc yield_waited_s=$waited loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  session=(env CUA_SESSION_ATSPI=1
           "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=$TEL DO_NOT_TRACK=1 PYTHONPATH=$HERE/focuslog FIX20O_FOCUS_LOG=1"
           "$LANES/cua-x11-session.sh" "${inner[@]}")
  ( cd "$WT" && flock -s -o "$LOCK" bash -c '
      label="$1"; ledger="$2"; mode="$3"; waited="$4"; shift 4
      acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d" " -f1-3 /proc/loadavg)"
      rc=97; attempt=0
      while [ "$rc" = 97 ] && [ "$attempt" -lt 3 ]; do
        attempt=$((attempt+1)); j=$((RANDOM % 3001))
        sleep "$((j / 1000)).$(printf %03d $((j % 1000)))"
        echo "[session] attempt=$attempt jitter_ms=$j"
        "$@"; rc=$?
      done
      rel="$(date -u +%FT%T.%3NZ)"
      printf "{\"lane\":\"FIX-20O\",\"label\":\"%s\",\"row_mode\":\"%s\",\"mode\":\"shared\",\"pid\":%d,\"yield_waited_s\":%d,\"acquired\":\"%s\",\"released\":\"%s\",\"rc\":%d,\"attempts\":%d,\"loadavg_at_acquire\":\"%s\"}\n" \
        "$label" "$mode" "$$" "$waited" "$acq" "$rel" "$rc" "$attempt" "$la" >> "$ledger"
      exit $rc' _ "$label" "$LEDGER" "$MODE" "$waited" "${session[@]}" ) > "$dir/session.log" 2>&1
  rc=$?
  date +%s > "$GAP_FILE"
  if [ -d "$work" ]; then
    mkdir -p "$dir/raw/focuslog"
    for f in "$work"/*/state.json.focus.jsonl; do
      [ -f "$f" ] && cp "$f" "$dir/raw/focuslog/$(basename "$(dirname "$f")").jsonl"
    done
  fi
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(grep -E '^done:' "$dir/session.log" | tail -1 | sed -E 's#^done: [^ ]*#done:#' | cut -c1-160)"
done
