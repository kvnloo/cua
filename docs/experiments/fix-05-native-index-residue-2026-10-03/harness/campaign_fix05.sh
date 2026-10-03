#!/usr/bin/env bash
# FIX-05 campaign (pattern of FIX-04 harness/campaign_fix04.sh): one SHARED quiet-lane acquisition per block
# (qlock_fix05.sh: lock fd closed for children, <= 300 s hold, receipt in the packet ledger and the loop-wide
# ledger), >= 30 s between acquisitions, 0-3 s jitter, one private X11 session (AT-SPI) per block, a fresh
# daemon per block and a fresh fixture per attempt. Session output is sanitized at capture.
#
# usage (under hostless): campaign_fix05.sh <raw-dir> <plan-file>
#   CT <arm F5m|F6m|F7m> <block> <attempts lo-hi>          FIX-04 CT, the blob-identical FIX-04 harness + fixture
#   N  <arm F5m|F6m|F7m> <row RPA|RSC|RSV|RCF|NC|NS> <block> <attempts lo-hi>   fix05_native.py rows
# Required environment: FX_LANES, FX_DRIVER_F5M, FX_DRIVER_F6M, FX_DRIVER_F7M, FX_WORKROOT, FX_SCRUB,
#   CUA_LANE_LOCKDIR
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
f3="$here/copied/fix-03-toctou-session-routing-2026-10-03/harness"
f4="$here/copied/fix-04-unknown-delivery-effect-2026-10-03/harness"
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
  case "$arm" in F5m) drv="$FX_DRIVER_F5M" ;; F6m) drv="$FX_DRIVER_F6M" ;; F7m) drv="$FX_DRIVER_F7M" ;;
    *) echo "bad arm $arm"; continue ;; esac
  for suffix in "" R; do
    [ "$first" = 1 ] || sleep 30   # >= 30 s between acquisitions
    first=0
    jitter_ms=$((RANDOM % 3001))
    sleep "$(printf '%d.%03d' $((jitter_ms / 1000)) $((jitter_ms % 1000)))"
    common="CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 CUA_GTK3_NOTE_TEXT_STATE=1 CUA_GTK3_FOCUS_STATE=1 OWN36_DRIVER=$drv OWN36_SCRUB=$FX_SCRUB OWN36_PYTHON=$f3/a3/probe_python.sh"
    case "$kind" in
      CT)
        row=CT block=${f[2]}$suffix attempts=${f[3]}
        out="$raw/native/$arm/CT/b$block.jsonl"; mkdir -p "$(dirname "$out")"
        work="$FX_WORKROOT/$arm/CT-$block"; mkdir -p "$work"
        label="fix05-CT-$arm-$block"
        extra="$common OWN36_FIXTURE=$f4/gtk3_main_two_windows.py OWN36_WORK=$work"
        script=("$f4/native/fix04_native.py" --row CT --block "$arm-$block" --attempts "$attempts" --out "$out")
        ;;
      N)
        row=${f[2]} block=${f[3]}$suffix attempts=${f[4]}
        out="$raw/native/$arm/$row/b$block.jsonl"; mkdir -p "$(dirname "$out")"
        work="$FX_WORKROOT/$arm/$row-$block"; mkdir -p "$work"
        label="fix05-$row-$arm-$block"
        extra="$common CUA_GTK3_SCROLL_STATE=1 CUA_GTK3_FOCUS_LOG=1 OWN36_FIXTURE=$here/gtk3_main_two_windows.py OWN36_WORK=$work"
        script=("$here/native/fix05_native.py" --row "$row" --block "$arm-$block" --attempts "$attempts" --out "$out")
        ;;
      *) echo "bad kind $kind"; continue 2 ;;
    esac
    count() { local c; c=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); echo "${c:-0}"; }
    before=$(count)
    echo "[$(date -u +%FT%TZ)] block $label jitter_ms=$jitter_ms loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
    env CUA_LANE_LOCKDIR="$CUA_LANE_LOCKDIR" "$here/qlock_fix05.sh" "$label" "$ledger" 300 \
      env CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="$extra" \
      "$FX_LANES/cua-x11-session.sh" "$f3/a3/probe_python.sh" "${script[@]}" 2>&1 \
      | sanitize > "$raw/session-$label.log"
    rc=${PIPESTATUS[0]}
    n=$(( $(count) - before ))
    echo "  rc=$rc recorded=$n"
    # A block that recorded nothing (session or fixture start failure) is kept and re-run once as <block>R.
    [ "$n" -gt 0 ] && break
  done
done < "$plan"
echo "[$(date -u +%FT%TZ)] plan done $(basename "$plan")"
