#!/usr/bin/env bash
# OWN-09R counted runs. Every invocation runs under hostless and the exclusive
# quiet-lane lock (quiet-timed, which writes the lock ledger receipt), and
# appends a receipt line here (raw/receipts.jsonl).
#
# usage: run_rows.sh <lanes-root> <phase> <arm>
#   lanes-root: directory holding bin/hostless, bin/quiet-timed, cua-x11-session.sh
#   phase:      sdk-main | sdk-stress | cabi | r8
#   arm:        M | P
# Required env: OWN09R_BIN_DIR (frozen test binaries + driver binaries),
#   OWN09R_SDK_DIR_M / OWN09R_SDK_DIR_P (cua-driver-sdk crate dir of each tree),
#   OWN09R_WT (worktree with the GTK fixture and jev-use helper),
#   OWN09R_VENV_PY (jev-use venv python), OWN09R_DRIVER_M / OWN09R_DRIVER_P,
#   OWN09R_TMP (lane temp dir).
set -euo pipefail
LANES="$1"; PHASE="$2"; ARM="$3"
PKT="$(cd "$(dirname "$0")" && pwd)"
RAW="$PKT/raw"
mkdir -p "$RAW"
H="$LANES/bin/hostless"; Q="$LANES/bin/quiet-timed"
export TMPDIR="$OWN09R_TMP"
if [ "$ARM" = M ]; then SDK="$OWN09R_SDK_DIR_M"; ROWS="$OWN09R_BIN_DIR/own09_arm_m"; LIB="$OWN09R_BIN_DIR/sdk_lib_tests_m"; DRV="$OWN09R_DRIVER_M"
else SDK="$OWN09R_SDK_DIR_P"; ROWS="$OWN09R_BIN_DIR/own09_arm_p"; LIB="$OWN09R_BIN_DIR/sdk_lib_tests_p"; DRV="$OWN09R_DRIVER_P"; fi

receipt() { # label rc start end cmd...
  local label="$1" rc="$2" start="$3" end="$4"; shift 4
  printf '{"label":"%s","arm":"%s","phase":"%s","rc":%d,"utc_start":"%s","utc_end":"%s","loadavg_end":"%s","cmd_sha256":"%s"}\n' \
    "$label" "$ARM" "$PHASE" "$rc" "$start" "$end" "$(cut -d' ' -f1-3 /proc/loadavg)" \
    "$(printf '%s\0' "$@" | sha256sum | cut -c1-16)" >> "$RAW/receipts.jsonl"
}

run() { # label log cmd...
  local label="$1" log="$2"; shift 2
  local start end rc
  start="$(date -u +%FT%T.%3NZ)"
  set +e
  ( cd "$SDK" && "$H" "$Q" "$label" "$@" ) >> "$log" 2>&1
  rc=$?
  set -e
  end="$(date -u +%FT%T.%3NZ)"
  receipt "$label" "$rc" "$start" "$end" "$@"
  return 0
}

mkdir -p "$RAW/logs"
case "$PHASE" in
  sdk-main|sdk-stress)
    pass="${PHASE#sdk-}"; threads=1; [ "$pass" = stress ] && threads=8
    out="$RAW/sdk/$pass"; mkdir -p "$out"; log="$RAW/logs/sdk-$pass-$ARM.txt"
    run "own09r-sdk-$pass-$ARM-r1" "$log" env OWN09_ITERS=100 OWN09_RAW_DIR="$out" "$ROWS" r1_cancel_ --test-threads=$threads
    run "own09r-sdk-$pass-$ARM-rows" "$log" env OWN09_ITERS=20 OWN09_RAW_DIR="$out" "$ROWS" --skip r1_cancel_ --test-threads=$threads
    ;;
  cabi)
    out="$RAW/cabi"; mkdir -p "$out"; log="$RAW/logs/cabi-$ARM.txt"
    run "own09r-cabi-$ARM" "$log" env OWN09R_ITERS=40 OWN09R_ARM="$ARM" OWN09R_RAW_DIR="$out" "$LIB" own09r_r --test-threads=1
    ;;
  r8)
    out="$RAW/r8_stdio/$ARM"; mkdir -p "$out"; log="$RAW/logs/r8-$ARM.txt"
    for variant in notification_mid_native control_no_cancel; do
      n=40; [ "$variant" = control_no_cancel ] && n=10
      run "own09r-r8-$ARM-$variant" "$log" env CUA_SESSION_ATSPI=1 \
        CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
        "$LANES/cua-x11-session.sh" "$OWN09R_VENV_PY" "$PKT/r8/r8_stdio.py" --wt "$OWN09R_WT" \
        --driver "$DRV" --arm "$ARM" --variant "$variant" --n "$n" \
        --out "$out/R8__$variant.jsonl" --work "$OWN09R_TMP/r8work/$ARM-$variant"
    done
    ;;
  *) echo "unknown phase $PHASE" >&2; exit 2 ;;
esac
