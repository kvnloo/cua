#!/usr/bin/env bash
# B-07 unit suites for the touched crates on the lane tree (B-05 unit.sh plus the B-07 mcp_result knob
# tests). Run under hostless and the cargo-build lock. Machine paths come from the environment:
# CARGO_HOME, CARGO_TARGET_DIR, RUST_TOOLCHAIN_BIN, TMPDIR.
#   unit.sh <worktree> <out-dir>
set -uo pipefail
WT="$1"; OUT="$2"; mkdir -p "$OUT"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
: "${CARGO_HOME:?}" "${CARGO_TARGET_DIR:?}" "${RUST_TOOLCHAIN_BIN:?}" "${TMPDIR:?}"
export PATH="$RUST_TOOLCHAIN_BIN:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS CUA_DRIVER_PHASE_TRACE_FILE CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM
cd "$WT"
echo "head=$(git rev-parse HEAD) tree_rust=$(git rev-parse HEAD:libs/cua-driver/rust) dirty_rust=$(git status --porcelain -- libs/cua-driver/rust | wc -l) rustc=$(rustc --version)" > "$OUT/env.txt"
: > "$OUT/steps.txt"
step() { local name="$1"; shift; "$@" > "$OUT/$name.txt" 2>&1; echo "$name rc=$?" >> "$OUT/steps.txt"; }
M=libs/cua-driver/rust/Cargo.toml
find libs/cua-driver/rust -path libs/cua-driver/rust/target -prune -o -type f -exec touch {} +
step core-mcp-result-tests nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- mcp_result::
step core-browser-tests nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- browser::
step core-phase-trace-tests nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- phase_trace
step driver-proxy-tests nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver --features portal-input --bin cua-driver -j 8 -- proxy::
step linux-focus-guard-tests nice -n 10 cargo test --locked --manifest-path "$M" -p platform-linux --lib -j 8 -- focus_guard
cat "$OUT/steps.txt"
