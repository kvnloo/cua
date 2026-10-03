#!/usr/bin/env bash
# FIX-03: one unit step = one cargo-lock acquisition (never the quiet-lane lock) + one private X11 session.
# usage (under hostless): run_unit.sh <worktree> <outdir> <step-name> <cargo test args...>
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
WT="$1"; OUT="$2"; NAME="$3"; shift 3
mkdir -p "$OUT"
echo "[$(date -u +%FT%TZ)] waiting cargo lock step=$NAME" >> "$OUT/steps.txt"
CUA_SESSION_EXTRA_ENV="RUSTUP_HOME=<scrubbed2>/.rustup CARGO_HOME=<scrubbed3>/cargo-home-cua CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1" \
  flock <scrubbed0>/locks/cargo-build.lock \
  <scrubbed1>/cua-x11-session.sh "$here/unit_in_session.sh" "$WT" "$OUT" "$NAME" "$@" \
  > "$OUT/$NAME.session.log" 2>&1
rc=$?
echo "[$(date -u +%FT%TZ)] step=$NAME rc=$rc" >> "$OUT/steps.txt"
exit $rc
