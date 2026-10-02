#!/usr/bin/env bash
# kvnloo/cua#107 lane AB: run the experiment-local acquisition-equality UNIT test.
#   usage (under the lane's hostless wrapper and the cargo-build lock):
#     run_unit_acquisition.sh <worktree> <scratch-dir> <cargo-target-dir> [extra cargo test args]
# Exports the committed libs/cua-driver tree of <worktree> HEAD into <scratch-dir> (git archive,
# so the tested tree is exactly the committed one), appends i107ab_acquisition_equality.rs to the
# COPY of v2_tests.rs, and runs only the i107ab tests plus the existing semantic query/scope test.
# The worktree itself is never modified.
set -euo pipefail
WT="$1"; SCRATCH="$2"; TGT="$3"; shift 3
HERE="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
git -C "$WT" archive --format=tar HEAD libs/cua-driver/rust libs/cua | tar -x -C "$SCRATCH"
TREE="$(git -C "$WT" rev-parse HEAD:libs/cua-driver)"
V2="$SCRATCH/libs/cua-driver/rust/crates/cua-driver-core/src/browser/v2_tests.rs"
printf '\n// ---- appended by run_unit_acquisition.sh (experiment-local) ----\n' >> "$V2"
cat "$HERE/i107ab_acquisition_equality.rs" >> "$V2"
export CARGO_TARGET_DIR="$TGT"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$SCRATCH/libs/cua-driver/rust"
echo "[$(date -u +%FT%TZ)] i107ab unit start libs_cua_driver_tree=$TREE test_sha256=$(sha256sum "$HERE/i107ab_acquisition_equality.rs" | cut -d' ' -f1)"
set +e
nice -n 10 cargo test --locked -p cua-driver-core --lib -j 8 "$@" -- --nocapture --test-threads 1 \
  i107ab_ semantic_query_and_content_scope_are_read_only_and_precise
rc=$?
set -e
echo "[$(date -u +%FT%TZ)] i107ab unit done rc=$rc"
exit $rc
