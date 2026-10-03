#!/usr/bin/env bash
# FIX-04 campaign (pattern of FIX-03 harness/campaign_fix03.sh): one SHARED quiet-lane lock acquisition
# per block (qlock_fix04.sh: <= 300 s hold, receipt in the packet ledger and the loop-wide ledger),
# >= 30 s between acquisitions, 0-3 s jitter, one private X11 session per block, a fresh Driver per
# browser cell, a fresh daemon per native block and a fresh fixture per native attempt. Session output
# is sanitized at capture (lane paths, home, /tmp/dbus-* addresses).
#
# usage (under hostless): campaign_fix04.sh <raw-dir> <plan-file>
#   B <arm F6|F5|U> <phase a1> <block> <start-rep> <reps>         browser (Part D, seam-forced race)
#   N <arm F6|F5|U> <row CT|CF|W2dX> <block> <attempts lo-hi>      native two-window (Parts C, D)
# Required environment: FX_LANES, FX_DRIVER_F6, FX_DRIVER_F5, FX_DRIVER_U, FX_WT (worktree with the
#   jev-use venv), FX_FIXTURE (this packet's two-window GTK3 copy), FX_WORKROOT, FX_SCRUB,
#   CUA_LANE_LOCKDIR
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
f3="$here/../../fix-03-toctou-session-routing-2026-10-03/harness"
mkdir -p "$raw"
ledger="$raw/lock-ledger.jsonl"
sed_args=(-E -e 's#/tmp/dbus-[A-Za-z0-9_.-]+#/tmp/dbus-<redacted>#g')
IFS=: read -r -a scrub_prefixes <<< "${FX_SCRUB:?set FX_SCRUB}"
i=0
for prefix in "${scrub_prefixes[@]}"; do
  [ -n "$prefix" ] && sed_args+=(-e "s#${prefix}#<scrubbed${i}>#g")
  i=$((i + 1))
done
sanitize() { sed "${sed_args[@]}"; }
first=1
while read -r -a f; do
  [ "${#f[@]}" -eq 0 ] && continue
  case "${f[0]}" in \#*) continue ;; esac
  kind=${f[0]} arm=${f[1]}
  case "$arm" in F6) drv="$FX_DRIVER_F6" ;; F5) drv="$FX_DRIVER_F5" ;; U) drv="$FX_DRIVER_U" ;;
    *) echo "bad arm $arm"; continue ;; esac
  for suffix in "" R; do
    [ "$first" = 1 ] || sleep 30   # >= 30 s between acquisitions
    first=0
    jitter_ms=$((RANDOM % 3001))
    sleep "$(printf '%d.%03d' $((jitter_ms / 1000)) $((jitter_ms % 1000)))"
    case "$kind" in
      B)
        phase=${f[2]} block=${f[3]}$suffix start=${f[4]} reps=${f[5]}
        out="$raw/browser/$block-$phase-$arm"; mkdir -p "$raw/browser"
        label="fix04-B-$arm-$phase-$block"
        cmd=(env CUA_SESSION_EXTRA_ENV="FIX03_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1"
             "$FX_LANES/cua-x11-session.sh" "$here/browser/run_block_fix04.sh" "$FX_WT" --phase "$phase"
             --arm "$arm" --driver "$drv" --out "$out" --start-rep "$start" --reps "$reps")
        count() { local c; c=$(grep -c . "$out/cells.jsonl" 2>/dev/null); echo "${c:-0}"; }
        ;;
      N)
        row=${f[2]} block=${f[3]}$suffix attempts=${f[4]}
        out="$raw/native/$arm/$row/b$block.jsonl"; mkdir -p "$(dirname "$out")"
        work="$FX_WORKROOT/$arm/$row-$block"; mkdir -p "$work"
        label="fix04-N-$arm-$row-$block"
        cmd=(env CUA_SESSION_ATSPI=1
             CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 CUA_GTK3_NOTE_TEXT_STATE=1 CUA_GTK3_FOCUS_STATE=1 OWN36_DRIVER=$drv OWN36_FIXTURE=$FX_FIXTURE OWN36_WORK=$work OWN36_SCRUB=$FX_SCRUB OWN36_PYTHON=$f3/a3/probe_python.sh"
             "$FX_LANES/cua-x11-session.sh" "$f3/a3/probe_python.sh" "$here/native/fix04_native.py"
             --row "$row" --block "$arm-$block" --attempts "$attempts" --out "$out")
        count() { local c; c=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); echo "${c:-0}"; }
        ;;
      *) echo "bad kind $kind"; continue 2 ;;
    esac
    before=$(count)
    echo "[$(date -u +%FT%TZ)] block $label jitter_ms=$jitter_ms loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
    env CUA_LANE_LOCKDIR="$CUA_LANE_LOCKDIR" "$here/qlock_fix04.sh" shared "$label" "$ledger" "${cmd[@]}" 2>&1 \
      | sanitize > "$raw/session-$label$suffix.log"
    rc=${PIPESTATUS[0]}
    n=$(( $(count) - before ))
    echo "  rc=$rc recorded=$n"
    # A block that recorded nothing (session or fixture start failure) is kept and re-run once as <block>R.
    [ "$n" -gt 0 ] && break
  done
done < "$plan"
echo "[$(date -u +%FT%TZ)] plan done $(basename "$plan")"
