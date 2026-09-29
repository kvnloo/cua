#!/usr/bin/env bash
# The Linux-runnable "CI: cua-driver contract clients" steps that exercise the live tool registry
# (ci-cua-driver-contract-clients.yml lines ~160-190), run on any worktree so a head can be compared with main.
# usage: validate-contract-gates.sh <worktree> <out-dir> [target-dir-name]
set -uo pipefail
WT="$1"; OUT="$2"; TGT="${3:-cua-test}"
mkdir -p "$OUT"
export CARGO_HOME=/mnt/zer0models/cargo-home-cua
export CARGO_TARGET_DIR=/mnt/zer0models/cargo-targets/$TGT
export TMPDIR=/mnt/zer0models/cua-lane-tmp
export PATH=/home/kvn/.cargo/bin:$PATH
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT/libs/cua-driver/rust"
echo "head=$(git rev-parse HEAD) rustc=$(rustc --version)" | tee "$OUT/env.txt"
: > "$OUT/steps.txt"
step() {
  local name="$1"; shift
  local t0=$(date +%s%N)
  "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  local t1=$(date +%s%N)
  printf '%-52s rc=%d  %d ms\n' "$name" "$rc" "$(( (t1 - t0) / 1000000 ))" | tee -a "$OUT/steps.txt"
}
find . -path ./target -prune -o -type f -exec touch {} +
export CUA_TEST_REQUIRE_DRIVER_BIN=1
step 07a-schema-consistency-portable-gate  nice -n 10 cargo test --locked -p cua-driver --test schema_consistency_test portable_desktop_contracts_are_accepted_by_active_backend
step 07b-schema-consistency-all            nice -n 10 cargo test --locked -p cua-driver --test schema_consistency_test
step 09-compatibility-contract-test        nice -n 10 cargo test --locked -p cua-driver --test compatibility_contract_test
step 10-embedded-host-sdk-mcp-test         nice -n 10 cargo test --locked -p cua-driver --test embedded_host_sdk_mcp_test
echo done | tee -a "$OUT/steps.txt"
