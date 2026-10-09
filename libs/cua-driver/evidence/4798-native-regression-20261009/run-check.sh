#!/usr/bin/env bash
set -u
export CARGO_HOME=/workspace/cua-gate-support/cargo
export RUSTUP_HOME=/workspace/cua-gate-support/rustup
export PATH="$CARGO_HOME/bin:$PATH"
export CARGO_BUILD_JOBS=4
label=$1
shift
log=/workspace/cua-gate-support/receipts/$label.log
{ date -u +%FT%TZ; printf 'COMMAND:'; printf ' %q' "$@"; printf '\n'; "$@"; result=$?; printf '\nEXIT_CODE=%s\n' "$result"; date -u +%FT%TZ; exit "$result"; } > "$log" 2>&1
