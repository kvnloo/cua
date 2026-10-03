#!/usr/bin/env bash
# RECERT-FIX a3 campaign: U' and F' blocks interleaved, one shared quiet-lane lock acquisition per
# block of <= 10 attempts/cells (qlock.sh: receipt in the packet ledger AND the loop-wide ledger),
# 0-3 s jitter before each block, one private X11 session (+ AT-SPI for native) per block, a fresh
# Driver and fixture per block. Bash only (arrays; never word-split a spec string).
#
# usage: campaign_a3.sh <raw-dir> <plan-file>
#   N <arm U|F> <topology T1|T2|T3> <row> <block> <attempts lo-hi> [--forged]   native (fix02-w3)
#   W <arm U|F> <row W2a..W2d|S1|S2> <block> <attempts lo-hi>                   two-window (w2)
#   B <arm U|F> <phase f3|f3ts|f4> <code|-> <block> <start-rep> <reps>           browser (a3)
# Required environment: A3_LANES (lanes root), A3_DRIVER_U, A3_DRIVER_F, A3_FIXTURE (GTK3 main.py),
#   A3_WT_F (F' worktree: browser examples), A3_WT_U (U' worktree: TS runner), A3_WORKROOT, A3_SCRUB,
#   CUA_LANE_LOCKDIR, TMPDIR
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
h="$(dirname "$here")"
mkdir -p "$raw"
ledger="$raw/lock-ledger.jsonl"
while read -r -a f; do
  [ "${#f[@]}" -eq 0 ] && continue
  case "${f[0]}" in \#*) continue ;; esac
  kind=${f[0]} arm=${f[1]}
  case "$arm" in U) drv="$A3_DRIVER_U" ;; F) drv="$A3_DRIVER_F" ;; *) echo "bad arm $arm"; continue ;; esac
  for suffix in "" R; do
    jitter_ms=$((RANDOM % 3001))
    sleep "$(printf '%d.%03d' $((jitter_ms / 1000)) $((jitter_ms % 1000)))"
    case "$kind" in
      N)
        topology=${f[2]} row=${f[3]} block=${f[4]}$suffix attempts=${f[5]} forged=${f[6]:-}
        out="$raw/native/$arm/$topology/$row/b$block.jsonl"; mkdir -p "$(dirname "$out")"
        label="a3-N-$arm-$topology-$row-$block"
        cmd=(env OWN36_LANES="$A3_LANES" OWN36_PYTHON="$here/probe_python.sh" OWN36_DRIVER="$drv"
             OWN36_FIXTURE="$A3_FIXTURE" OWN36_WORKROOT="$A3_WORKROOT/$arm" OWN36_SCRUB="$A3_SCRUB"
             "$h/fix02-w3/native/locked_block.sh" "$raw/native/block-ledger.jsonl" "$topology" "$row"
             "$arm-$block" "$attempts" "$out")
        [ -n "$forged" ] && cmd+=("$forged")
        count() { local c; c=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); echo "${c:-0}"; }
        ;;
      W)
        row=${f[2]} block=${f[3]}$suffix attempts=${f[4]}
        out="$raw/w2/$arm/$row/b$block.jsonl"; mkdir -p "$(dirname "$out")"
        label="a3-W-$arm-$row-$block"
        cmd=(env OWN36_LANES="$A3_LANES" OWN36_PYTHON="$here/probe_python.sh" OWN36_DRIVER="$drv"
             OWN36_FIXTURE="$A3_FIXTURE" OWN36_WORKROOT="$A3_WORKROOT/$arm" OWN36_SCRUB="$A3_SCRUB"
             "$h/w2/locked_w2.sh" "$raw/w2/block-ledger.jsonl" "$row" "$arm-$block" "$attempts" "$out")
        count() { local c; c=$(grep -c -E '"kind": "(attempt|smoke)"' "$out" 2>/dev/null); echo "${c:-0}"; }
        ;;
      B)
        phase=${f[2]} code=${f[3]} block=${f[4]}$suffix start=${f[5]} reps=${f[6]}
        out="$raw/browser/$block-$phase-$arm"; [ "$code" != "-" ] && out="$out-$code"
        mkdir -p "$raw/browser"
        label="a3-B-$arm-$phase-$code-$block"
        tsex="$A3_WT_F/libs/cua-driver/examples/jev-use"
        [ "$arm" = U ] && tsex="$A3_WT_U/libs/cua-driver/examples/jev-use"
        extra=()
        [ "$code" != "-" ] && extra+=(--code "$code")
        [ "$phase" = f3ts ] && extra+=(--ts-examples "$tsex")
        cmd=(env CUA_SESSION_EXTRA_ENV="FIX02_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
             "$A3_LANES/cua-x11-session.sh" "$here/run_block_a3.sh" "$A3_WT_F" --phase "$phase" --arm "$arm"
             --driver "$drv" --out "$out" --start-rep "$start" --reps "$reps" "${extra[@]}")
        count() { local c; c=$(grep -c . "$out/cells.jsonl" 2>/dev/null); echo "${c:-0}"; }
        ;;
      *) echo "bad kind $kind"; continue 2 ;;
    esac
    echo "[$(date -u +%FT%TZ)] block $label jitter_ms=$jitter_ms"
    "$A3_LANES/bin/hostless" env CUA_LANE_LOCKDIR="$CUA_LANE_LOCKDIR" \
      "$here/qlock.sh" shared "$label" "$ledger" "${cmd[@]}" > "$raw/session-$label.log" 2>&1
    rc=$?
    n=$(count)
    echo "  rc=$rc recorded=$n"
    # A block that recorded nothing (session or fixture start failure) is kept and re-run once as <block>R.
    [ "$n" -gt 0 ] && break
  done
done < "$plan"
echo "[$(date -u +%FT%TZ)] plan done $(basename "$plan")"
