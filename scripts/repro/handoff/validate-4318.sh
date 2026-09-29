#!/usr/bin/env bash
# Smallest exact local equivalents of the CI gates that cover trycua/cua#4318
# (libs/cua-driver/{contract,rust/crates/cua-driver-contract,rust/crates/cua-driver-core}).
#   CI: Cua Driver quick feedback   -> cargo fmt --check; cargo test -p cua-driver-core --lib
#   CI: cua-driver contract clients -> cua-contract-gen all --check; cargo test -p cua-driver-contract;
#                                      cargo test -p cua-driver-core --test contract_parity;
#                                      cargo test -p cua-driver --test schema_consistency_test
# usage: validate-4318.sh <worktree> <out-dir> [test-target-dir-name]
set -uo pipefail
WT="$1"; OUT="$2"; TGT="${3:-cua-test}"
mkdir -p "$OUT"
export CARGO_HOME=/mnt/zer0models/cargo-home-cua
export CARGO_TARGET_DIR=/mnt/zer0models/cargo-targets/$TGT
export TMPDIR=/mnt/zer0models/cua-lane-tmp
export PATH=/home/kvn/.cargo/bin:$PATH
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT/libs/cua-driver/rust"
echo "head=$(git rev-parse HEAD) rustc=$(rustc --version) cargo=$(cargo --version)" | tee "$OUT/env.txt"
: > "$OUT/steps.txt"
step() { # name, cmd...
  local name="$1"; shift
  local t0=$(date +%s%N)
  "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  local t1=$(date +%s%N)
  printf '%-44s rc=%d  %d ms\n' "$name" "$rc" "$(( (t1 - t0) / 1000000 ))" | tee -a "$OUT/steps.txt"
}
touch_all() { find . -path ./target -prune -o -type f -exec touch {} + ; }
touch_all   # see build-driver.sh: shared target dir + separate worktrees needs a forced rebuild of workspace crates
step 01-cargo-fmt-check            nice -n 10 cargo fmt --manifest-path Cargo.toml --all -- --check
step 02-contract-gen-all-check     nice -n 10 cargo run --locked -p cua-driver-contract --bin cua-contract-gen -- all --check
step 03-contract-crate-tests       nice -n 10 cargo test --locked -p cua-driver-contract
step 04-core-lib-tests             nice -n 10 cargo test --locked -p cua-driver-core --lib
step 05-core-tool-schema-tests     nice -n 10 cargo test --locked -p cua-driver-core --lib tool_schema
step 06-core-contract-parity       nice -n 10 cargo test --locked -p cua-driver-core --test contract_parity
step 07-schema-consistency-linux   env CUA_TEST_REQUIRE_DRIVER_BIN=1 nice -n 10 cargo test --locked -p cua-driver --test schema_consistency_test
step 08-protocol-element-token     nice -n 10 cargo test --locked -p cua-driver --test protocol_element_token_test --test protocol_schema_test
echo "done" | tee -a "$OUT/steps.txt"
