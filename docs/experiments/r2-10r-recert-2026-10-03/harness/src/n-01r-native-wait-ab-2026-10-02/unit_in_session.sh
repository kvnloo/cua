#!/usr/bin/env bash
# usage (hostless, inside cua-x11-session.sh, under the quiet (shared) + cargo-build locks):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home>
# Runs the touched platform-linux lib unit suites (knob tests included) and the
# cua-driver-core phase_trace tests.
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "head=$(git rev-parse HEAD) rustc=$(rustc --version)"
run() { echo "### cargo test $*"; cargo test --locked "$@" 2>&1 | grep -E '^test |^test result|error|panicked' ; echo "rc=${PIPESTATUS[0]}"; }
run -p platform-linux --lib -- exp_post_action_sleep_tests input::focus_guard::tests::unset_or_invalid_settle_knob_keeps_the_constants input::focus_guard::tests::set_settle_knob_value_is_used
run -p platform-linux --lib -- input::focus_guard atspi:: tools::
run -p cua-driver-core --lib -- phase_trace
