#!/usr/bin/env bash
# FRESH-07 Phase 1d: unit suites on the 9a2b1d99e tree.
# Run as: hostless flock <cargo-build.lock> flock -s <quiet-lane.lock> cua-x11-session.sh unit.sh <worktree> <out-dir>
# (inside the private Xvfb session, so platform-linux tests that open an X display get a private server).
# Machine paths come from the environment (CUA_SESSION_EXTRA_ENV): CARGO_HOME, CARGO_TARGET_DIR, RUST_TOOLCHAIN_BIN.
set -uo pipefail
WT="$1"; OUT="$2"; mkdir -p "$OUT"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
: "${CARGO_HOME:?}" "${CARGO_TARGET_DIR:?}" "${RUST_TOOLCHAIN_BIN:?}"
export PATH="$RUST_TOOLCHAIN_BIN:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT"
echo "head=$(git rev-parse HEAD) tree_rust=$(git rev-parse HEAD:libs/cua-driver/rust) dirty_rust=$(git status --porcelain -- libs/cua-driver/rust | wc -l) rustc=$(rustc --version) display_set=yes atspi=${CUA_SESSION_ATSPI:-0} start=$(date -u +%FT%TZ)" > "$OUT/env.txt"
: > "$OUT/steps.txt"
step() { local name="$1"; shift; local t0; t0=$(date +%s); timeout 1800 "$@" > "$OUT/$name.log" 2>&1; local rc=$?; echo "$name rc=$rc seconds=$(( $(date +%s) - t0 ))" >> "$OUT/steps.txt"; }
M=libs/cua-driver/rust/Cargo.toml
step core-expectation nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core -j 8 expectation
step core-full nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core -j 8
step linux-overlay nice -n 10 cargo test --locked --manifest-path "$M" -p platform-linux --lib -j 8 overlay
step linux-full nice -n 10 cargo test --locked --manifest-path "$M" -p platform-linux -j 8
echo "end=$(date -u +%FT%TZ)" >> "$OUT/env.txt"
cat "$OUT/steps.txt"
