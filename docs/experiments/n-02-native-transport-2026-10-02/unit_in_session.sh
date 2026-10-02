#!/usr/bin/env bash
# usage (hostless, inside cua-x11-session.sh, under the quiet (shared) + cargo-build locks):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home>
# Derived from the N-01R unit_in_session.sh (blob bbf2ea58cf0e). Runs the touched suites:
#  - platform-linux focus_guard (new clamp tests + the N-01R knob tests + the existing guard tests),
#    and the N-01R touched suites atspi:: tools:: (unchanged code, regression check);
#  - cua-driver binary proxy tests (new mcp_trace_scope test + the existing proxy tests);
#  - cua-driver-core phase_trace tests.
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "head=$(git rev-parse HEAD) rustc=$(rustc --version)"
run() { echo "### cargo test $*"; cargo test --locked "$@" 2>&1 | grep -E '^test |^test result|error|panicked' ; echo "rc=${PIPESTATUS[0]}"; }
run -p platform-linux --lib -- input::focus_guard::tests::clamp_knob_is_on_only_for_one input::focus_guard::tests::unclamped_poll_sleeps_a_whole_poll_past_the_deadline input::focus_guard::tests::clamped_poll_ends_at_the_deadline
run -p platform-linux --lib -- input::focus_guard atspi:: tools::
run -p cua-driver --features portal-input --bin cua-driver -- proxy::
run -p cua-driver-core --lib -- phase_trace
