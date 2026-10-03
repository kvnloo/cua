#!/usr/bin/env bash
# usage (hostless, inside cua-x11-session.sh, under the cargo-build lock):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home> <phase>
# Runs: the two new red/green tests by name (DLG, A2); every input::focus_guard test; the AT-SPI
# link and unanswered-call tests; the whole platform-linux lib.
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"; PHASE="$5"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "phase=$PHASE head=$(git rev-parse HEAD) tracked_diff_lines=$(git diff HEAD -- . | wc -l) rustc=$(rustc --version)"
for f in crates/platform-linux/src/input/focus_guard.rs crates/platform-linux/src/atspi/native.rs; do
  echo "$f blob=$(git hash-object "$f")"
done
run() { echo "### cargo test $*"; cargo test --locked "$@" 2>&1 | grep -E '^test |^test result|^error|panicked|assertion|left:|right:|skipped|FAILED|failures:' ; echo "rc=${PIPESTATUS[0]}"; }
run -p platform-linux --lib -- --exact \
  input::focus_guard::tests::a_steal_seen_before_the_active_window_follows_is_not_the_apps_dialog \
  atspi::native::unanswered_call_tests::an_unanswered_call_keeps_the_bus_while_its_daemon_answers_and_loses_a_hung_one \
  --nocapture
run -p platform-linux --lib -- input::focus_guard
run -p platform-linux --lib -- atspi::native::link_tests atspi::native::unanswered_call_tests
run -p platform-linux --lib
