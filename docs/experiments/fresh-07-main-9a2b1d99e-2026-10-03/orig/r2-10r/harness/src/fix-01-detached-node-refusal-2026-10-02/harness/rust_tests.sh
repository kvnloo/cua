#!/usr/bin/env bash
# rust_tests.sh <worktree> <out-dir> <target-dir-name> [cargo test filter...]
# Runs `cargo test -p cua-driver-core` (plus -p cua-driver-contract when no filter is given) for the
# worktree's Rust workspace. Run under hostless + locked.sh shared + flock cargo-build.lock.
set -uo pipefail
WT="$1"; OUT="$2"; TGT="$3"; shift 3
mkdir -p "$OUT"
# Machine paths come from the environment (never committed): CARGO_HOME, CARGO_TARGET_ROOT,
# RUST_TOOLCHAIN_BIN, TMPDIR.
: "${CARGO_HOME:?}" "${CARGO_TARGET_ROOT:?}" "${RUST_TOOLCHAIN_BIN:?}" "${TMPDIR:?}"
export CARGO_HOME TMPDIR CARGO_TARGET_DIR="$CARGO_TARGET_ROOT/$TGT"
export PATH="$RUST_TOOLCHAIN_BIN:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT"
find libs/cua-driver/rust -path libs/cua-driver/rust/target -prune -o -type f -exec touch {} +
echo "head=$(git rev-parse HEAD) tree_rust=$(git rev-parse HEAD:libs/cua-driver/rust) dirty=$(git status --porcelain -- libs/cua-driver/rust | wc -l) rustc=$(rustc --version)" > "$OUT/env.txt"
M=libs/cua-driver/rust/Cargo.toml
if [ "$#" -gt 0 ]; then
  nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- "$@" > "$OUT/core-filtered.log" 2>&1; echo "core-filtered rc=$?" >> "$OUT/steps.txt"
else
  nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core -j 8 > "$OUT/core.log" 2>&1; echo "cua-driver-core rc=$?" >> "$OUT/steps.txt"
  nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-contract -j 8 > "$OUT/contract.log" 2>&1; echo "cua-driver-contract rc=$?" >> "$OUT/steps.txt"
fi
grep -h -E "^test result:|^test .* (FAILED|ok)$" "$OUT"/*.log | grep -E "result|FAILED" > "$OUT/summary.txt" || true
cat "$OUT/steps.txt"
