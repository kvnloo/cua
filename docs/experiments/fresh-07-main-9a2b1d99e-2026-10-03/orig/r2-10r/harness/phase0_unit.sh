#!/usr/bin/env bash
# Phase 0 (a): unit suites on the R tree. Run under hostless, the quiet-lane lock (shared) and the
# cargo-build lock. Machine paths come from the environment: CARGO_HOME, CARGO_TARGET_DIR,
# RUST_TOOLCHAIN_BIN, NODE_BIN, UV_BIN_DIR, TMPDIR.
#   phase0_unit.sh <worktree> <out-dir>
set -uo pipefail
WT="$1"; OUT="$2"; mkdir -p "$OUT"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
: "${CARGO_HOME:?}" "${CARGO_TARGET_DIR:?}" "${RUST_TOOLCHAIN_BIN:?}" "${NODE_BIN:?}" "${UV_BIN_DIR:?}" "${TMPDIR:?}"
export PATH="$RUST_TOOLCHAIN_BIN:$NODE_BIN:$UV_BIN_DIR:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT"
echo "head=$(git rev-parse HEAD) tree_rust=$(git rev-parse HEAD:libs/cua-driver/rust) dirty_rust=$(git status --porcelain -- libs/cua-driver/rust | wc -l) rustc=$(rustc --version) node=$(node --version)" > "$OUT/env.txt"
: > "$OUT/steps.txt"
step() { local name="$1"; shift; "$@" > "$OUT/$name.log" 2>&1; echo "$name rc=$?" >> "$OUT/steps.txt"; }
M=libs/cua-driver/rust/Cargo.toml
find libs/cua-driver/rust -path libs/cua-driver/rust/target -prune -o -type f -exec touch {} +
step core-browser nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- browser::
step core-phase-trace nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- phase_trace
# R2-10R additions (drift files of trycua/cua PR 4375): tool_schema incl.
# first_snapshot_grace_never_overrides_an_explicit_timeout, and snapshot_store incl.
# semantic_membership_ignores_capture_only_publication.
step core-tool-schema nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- tool_schema::
step core-snapshot-store nice -n 10 cargo test --locked --manifest-path "$M" -p cua-driver-core --lib -j 8 -- snapshot_store::
cd libs/cua-driver/examples/jev-use
step py-unittest uv run --frozen python -m unittest discover -s python/tests -v
step py-runner-refusal uv run --frozen python -m unittest discover -s python/tests -p test_runner_refusal.py -v
step py-guarded-runner uv run --frozen python -m unittest discover -s python/tests -p test_guarded_runner.py -v
step ts-npm-test npm test
step ts-run-refusal node --import tsx --test typescript/run_refusal.test.ts
step ts-typecheck npm run typecheck
cat "$OUT/steps.txt"
