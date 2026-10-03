#!/usr/bin/env bash
# usage (hostless, inside cua-x11-session.sh, under the cargo-build lock):
#   unit_in_session.sh <worktree> <cargo-home> <target-dir> <rustup-home> <phase> [core]
# Derived from the OWN-20G unit_in_session.sh. <phase> is a label only.
# Runs:
#  - the two settle tests by name (the Part A red/green pair);
#  - every platform-linux input::focus_guard test;
#  - the AT-SPI reconnect tests (Part B; "0 tests" on trees without them);
#  - the whole platform-linux lib;
#  - with "core": the cua-driver-core snapshot_store tests and the whole cua-driver-core lib.
set -uo pipefail
WT="$1"; export CARGO_HOME="$2"; export CARGO_TARGET_DIR="$3"; export RUSTUP_HOME="$4"; PHASE="$5"; CORE="${6:-}"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not in the isolated session" >&2; exit 97; }
cd "$WT/libs/cua-driver/rust"
echo "phase=$PHASE head=$(git rev-parse HEAD) tracked_diff_lines=$(git diff HEAD -- . | wc -l) rustc=$(rustc --version)"
for f in crates/platform-linux/src/input/focus_guard.rs crates/platform-linux/src/atspi/native.rs \
         crates/platform-linux/src/atspi/snapshot.rs crates/cua-driver-core/src/snapshot_store.rs; do
  echo "$f sha256=$(git hash-object "$f")"
done
run() { echo "### cargo test $*"; cargo test --locked "$@" 2>&1 | grep -E '^test |^test result|^error|panicked|assertion|left:|right:|stalled|unseen|FAILED|failures:' ; echo "rc=${PIPESTATUS[0]}"; }
run -p platform-linux --lib -- --exact input::focus_guard::tests::a_steal_during_a_read_stalled_past_the_watch_is_seen input::focus_guard::tests::a_quiet_watch_ends_on_a_read_after_its_deadline_without_an_extra_read
run -p platform-linux --lib -- input::focus_guard
run -p platform-linux --lib -- atspi::native::link_tests atspi::snapshot
run -p platform-linux --lib
if [ "$CORE" = core ]; then
  run -p cua-driver-core --lib -- snapshot_store
  run -p cua-driver-core --lib
fi
