#!/usr/bin/env bash
# usage (hostless, inside cua-x11-session.sh, under the cargo-build lock):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home>
# Runs the new R2-09 knob tests, the N-01R knob tests and the touched
# platform-linux suites (atspi:: input::focus_guard tools::).
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"
export PATH="$(dirname "$RUSTUP_HOME")/.cargo/bin:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "head=$(git rev-parse HEAD) rustc=$(rustc --version)"
run() { echo "### cargo test $*"; nice -n 10 cargo test --locked -j 8 "$@" 2>&1 | grep -E '^test |^test result|^error|panicked' ; echo "rc=${PIPESTATUS[0]}"; }
run -p platform-linux --lib -- exp_post_action_wake_tests exp_post_action_sleep_tests
run -p platform-linux --lib -- input::focus_guard atspi:: tools::
