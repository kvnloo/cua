#!/usr/bin/env bash
# usage (on the host, ALWAYS as: hostless hostless-strict run_all.sh ...):
#   run_all.sh <worktree> <binaries.json> <plan.json> <runs-dir> <locks-dir> <lanes-dir> <label-prefix> [block ...]
# Derived from the OWN-20G run_all.sh. <binaries.json> maps each role (U0, G0, U0m, G0m, GA) to
# {"path", "sha256"} (a lane-local file, never committed). Each plan block runs in its own private
# X11 session (Xvfb + openbox + private session bus + private AT-SPI bus/registry; telemetry off),
# under the quiet-lane lock in SHARED mode (<= 10 trials per acquisition) with one receipt per block
# in the quiet-lane ledger. Before each session: a 0-3 s random start jitter; inside it,
# session_entry.sh probes the display with xdpyinfo (rc 97: nothing ran, a new session is started,
# at most 3 attempts). Every block attempt is kept.
set -uo pipefail
WT="$1"; BINS="$2"; PLAN="$3"; RUNS="$4"; LOCKS="$5"; LANES="$6"; PREFIX="$7"; shift 7
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
if ls -A "/run/user/$(id -u)" 2>/dev/null | grep -qE '^(wayland-|hypr|bus$|at-spi$|pipewire)' \
   || ls -A /tmp/.X11-unix 2>/dev/null | grep -q .; then
  echo "refusing: host desktop sockets visible (run as: hostless hostless-strict run_all.sh ...)" >&2; exit 95
fi
LOCK="$LOCKS/quiet-lane.lock"; LEDGER="$LOCKS/quiet-lane-ledger.jsonl"
[ -e "$LOCK" ] || { echo "refusing: quiet-lane lock missing" >&2; exit 94; }
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$RUNS"
role() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]])' "$BINS" "$1" "$2"; }
mapfile -t order < <(python3 -c 'import json,sys; [print(b["block"]) for b in json.load(open(sys.argv[1]))["blocks"]]' "$PLAN")
blocks=("$@")
[ ${#blocks[@]} -eq 0 ] && blocks=("${order[@]}")
for b in "${blocks[@]}"; do
  read -r ru rg < <(python3 -c 'import json,sys; b=[x for x in json.load(open(sys.argv[1]))["blocks"] if x["block"]==sys.argv[2]]; print(b[0]["bins"]["U"], b[0]["bins"]["G"]) if b else print("- -")' "$PLAN" "$b")
  [ "$ru" != "-" ] || { echo "unknown block $b" >&2; exit 2; }
  DRVU="$(role "$ru" path)"; SHAU="$(role "$ru" sha256)"; DRVG="$(role "$rg" path)"; SHAG="$(role "$rg" sha256)"
  label="$PREFIX-$b"; n=0
  while [ -e "$RUNS/$label" ]; do n=$((n+1)); label="$PREFIX-$b-r$n"; done
  dir="$RUNS/$label"; mkdir -p "$dir"
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label U=$ru G=$rg loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  session=(env CUA_SESSION_ATSPI=1
           "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
           "$LANES/cua-x11-session.sh"
           "$HERE/session_entry.sh" "$WT" "$DRVU" "$SHAU" "$DRVG" "$SHAG" "$PLAN" "$b" "$label" "$dir/raw" "$(dirname "$RUNS")/runs-work/$label")
  ( cd "$WT" && flock -s "$LOCK" bash -c '
      label="$1"; ledger="$2"; shift 2
      acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d" " -f1-3 /proc/loadavg)"
      rc=97; attempt=0
      while [ "$rc" = 97 ] && [ "$attempt" -lt 3 ]; do
        attempt=$((attempt+1)); j=$((RANDOM % 3001))
        sleep "$((j / 1000)).$(printf %03d $((j % 1000)))"
        echo "[session] attempt=$attempt jitter_ms=$j"
        "$@"; rc=$?
      done
      rel="$(date -u +%FT%T.%3NZ)"
      printf "{\"lane\":\"OWN-20P\",\"label\":\"%s\",\"mode\":\"shared\",\"pid\":%d,\"acquired\":\"%s\",\"released\":\"%s\",\"rc\":%d,\"attempts\":%d,\"loadavg_at_acquire\":\"%s\"}\n" \
        "$label" "$$" "$acq" "$rel" "$rc" "$attempt" "$la" >> "$ledger"
      exit $rc' _ "$label" "$LEDGER" "${session[@]}" ) > "$dir/session.log" 2>&1
  rc=$?
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(grep -E '^done:' "$dir/session.log" | tail -1 | cut -c1-160)"
done
