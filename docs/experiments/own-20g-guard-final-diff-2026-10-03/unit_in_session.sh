#!/usr/bin/env bash
# usage (hostless, inside cua-x11-session.sh, under the cargo-build lock):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home> <phase>
# Derived from the N-02 unit_in_session.sh. <phase> is a label only (red | green).
# Runs:
#  - the two new settle tests by name (the red/green pair);
#  - every platform-linux input::focus_guard test;
#  - the whole platform-linux lib (spec: "the platform-linux lib passes on G").
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"; PHASE="$5"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "phase=$PHASE head=$(git rev-parse HEAD) worktree_diff_sha256=$(git diff HEAD -- . | sha256sum | cut -c1-16) rustc=$(rustc --version)"
echo "focus_guard.rs sha256=$(sha256sum crates/platform-linux/src/input/focus_guard.rs | cut -d' ' -f1)"
run() { echo "### cargo test $*"; cargo test --locked "$@" 2>&1 | grep -E '^test |^test result|^error|panicked|assertion|left:|right:|stalled|unseen' ; echo "rc=${PIPESTATUS[0]}"; }
run -p platform-linux --lib -- --exact input::focus_guard::tests::a_steal_during_a_read_stalled_past_the_watch_is_seen input::focus_guard::tests::a_quiet_watch_ends_on_a_read_after_its_deadline_without_an_extra_read
run -p platform-linux --lib -- input::focus_guard
run -p platform-linux --lib
