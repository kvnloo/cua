#!/usr/bin/env bash
# usage (hostless-strict, inside cua-x11-session.sh, under the cargo-build lock then the shared quiet lock):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home> <mode>
# Derived from the N-02 unit_in_session.sh. mode:
#   new   - only the two injected-stall tests (red/green evidence);
#   full  - every focus_guard test, then the whole platform-linux lib (regression gate on G).
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"; MODE="$5"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "head=$(git rev-parse HEAD) dirty_files=$(git status --porcelain -- . | wc -l) rustc=$(rustc --version)"
git diff --stat HEAD -- . | tail -3
run() { echo "### cargo test $*"; cargo test --locked "$@" 2>&1 | grep -A2 -E '^test |^test result|^error|panicked|^failures' | grep -v -E '^--$' ; echo "rc=${PIPESTATUS[0]}"; }
case "$MODE" in
  new)  run -p platform-linux --lib -- input::focus_guard::tests::a_steal_during_a_read_stalled_past_the_watch_is_restored input::focus_guard::tests::a_change_first_seen_after_the_restore_budget_is_still_verified ;;
  full) run -p platform-linux --lib -- input::focus_guard
        run -p platform-linux --lib ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
