#!/usr/bin/env bash
# RECERT-FIX a3 Part C: OWN-09R counted rows on arm M (0f1955d2f + test-only m-tree.patch) and P'
# (ba611b51a). Adapted from harness/own09r-w3/run_rows.sh (wave-3 copy): same invocations, iteration
# counts and raw layout for phases sdk-main, sdk-stress and cabi; R8 is OWNER_DECISION and not re-run.
# Each invocation runs under hostless and holds the SHARED quiet-lane lock through qlock.sh (receipt
# in the packet ledger and the loop-wide ledger); no timing claims.
# usage: own09r_rows_a3.sh <raw-dir> <phase sdk-main|sdk-stress|cabi> <arm M|P>
# Required env: A3_LANES, OWN09R_BIN_DIR (frozen test binaries), OWN09R_SDK_DIR_M / OWN09R_SDK_DIR_P,
#   OWN09R_TMP, CUA_LANE_LOCKDIR
set -euo pipefail
RAW="$1"; PHASE="$2"; ARM="$3"
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$RAW/logs"
H="$A3_LANES/bin/hostless"
export TMPDIR="$OWN09R_TMP"
if [ "$ARM" = M ]; then SDK="$OWN09R_SDK_DIR_M"; ROWS="$OWN09R_BIN_DIR/own09_arm_m"; LIB="$OWN09R_BIN_DIR/sdk_lib_tests_m"
else SDK="$OWN09R_SDK_DIR_P"; ROWS="$OWN09R_BIN_DIR/own09_arm_p"; LIB="$OWN09R_BIN_DIR/sdk_lib_tests_p"; fi

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
  ( cd "$SDK" && "$H" env CUA_LANE_LOCKDIR="$CUA_LANE_LOCKDIR" "$here/qlock.sh" shared "$label" \
      "$RAW/lock-ledger.jsonl" "$@" ) >> "$log" 2>&1
  rc=$?
  set -e
  end="$(date -u +%FT%T.%3NZ)"
  receipt "$label" "$rc" "$start" "$end" "$@"
  return 0
}

case "$PHASE" in
  sdk-main|sdk-stress)
    pass="${PHASE#sdk-}"; threads=1; [ "$pass" = stress ] && threads=8
    out="$RAW/sdk/$pass"; mkdir -p "$out"; log="$RAW/logs/sdk-$pass-$ARM.txt"
    run "a3-own09r-sdk-$pass-$ARM-r1" "$log" env OWN09_ITERS=100 OWN09_RAW_DIR="$out" "$ROWS" r1_cancel_ --test-threads=$threads
    run "a3-own09r-sdk-$pass-$ARM-rows" "$log" env OWN09_ITERS=20 OWN09_RAW_DIR="$out" "$ROWS" --skip r1_cancel_ --test-threads=$threads
    ;;
  cabi)
    out="$RAW/cabi"; mkdir -p "$out"; log="$RAW/logs/cabi-$ARM.txt"
    run "a3-own09r-cabi-$ARM" "$log" env OWN09R_ITERS=40 OWN09R_ARM="$ARM" OWN09R_RAW_DIR="$out" "$LIB" own09r_r --test-threads=1
    ;;
  *) echo "unknown phase $PHASE" >&2; exit 2 ;;
esac
