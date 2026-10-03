#!/usr/bin/env bash
# FIX-04: one unit step = one cargo-lock acquisition (never the quiet-lane lock) + one private X11
# session, cut at 1200 s. Pattern of FIX-03 raw/unit/scripts/run_unit.sh.
# usage (under hostless): run_unit.sh <worktree> <outdir> <step-name> <cargo test args...>
# Environment: FX_LANES (lane kit dir), FX_LOCKDIR (cargo/quiet lock dir), FX_TARGET (cargo target dir),
#   FX_CARGO_HOME, FX_RUSTUP_HOME.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
WT="$1"; OUT="$2"; NAME="$3"; shift 3
mkdir -p "$OUT"
echo "[$(date -u +%FT%TZ)] waiting cargo lock step=$NAME" >> "$OUT/steps.txt"
CUA_SESSION_EXTRA_ENV="RUSTUP_HOME=${FX_RUSTUP_HOME:?} CARGO_HOME=${FX_CARGO_HOME:?} FX_TARGET=${FX_TARGET:?} CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1" \
  flock "${FX_LOCKDIR:?}/cargo-build.lock" \
  timeout --signal=TERM --kill-after=30 1200 \
  "${FX_LANES:?}/cua-x11-session.sh" "$here/unit_in_session.sh" "$WT" "$OUT" "$NAME" "$@" \
  > "$OUT/$NAME.session.log" 2>&1
rc=$?
echo "[$(date -u +%FT%TZ)] step=$NAME rc=$rc" >> "$OUT/steps.txt"
exit $rc
