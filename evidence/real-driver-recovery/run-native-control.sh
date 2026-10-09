#!/usr/bin/env bash
# Existing native control lane only. This deliberately never certifies recovery.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
if [[ ${1:-} == --preflight ]]; then exec python3 "$here/preflight.py"; fi
: "${CUA_DISPOSABLE_DESKTOP:?Set to 1 only inside an owned disposable desktop}"
[[ $CUA_DISPOSABLE_DESKTOP == 1 ]]
: "${SOURCE_ROOT:?Absolute path to a clean exact-head checkout}"
: "${EXPECTED_SHA:?Exact full source SHA}"
: "${EVIDENCE_DIR:?New absolute output directory outside checkout}"
[[ $SOURCE_ROOT == /* && $EVIDENCE_DIR == /* ]]
[[ ! -e $EVIDENCE_DIR ]]
[[ $(git -C "$SOURCE_ROOT" rev-parse HEAD) == "$EXPECTED_SHA" ]]
# Reject tracked edits; binary is built below, never taken from PATH.
git -C "$SOURCE_ROOT" diff --quiet
git -C "$SOURCE_ROOT" diff --cached --quiet
mkdir -p "$EVIDENCE_DIR"
python3 "$here/preflight.py" > "$EVIDENCE_DIR/preflight.json"
cd "$SOURCE_ROOT"
git rev-parse HEAD > "$EVIDENCE_DIR/source-sha.txt"
git rev-parse HEAD:libs/cua-driver/rust > "$EVIDENCE_DIR/driver-tree.txt"
export CARGO_TARGET_DIR="$EVIDENCE_DIR/target"
cargo build --locked --release -p cua-driver --features portal-input \
  --manifest-path libs/cua-driver/rust/Cargo.toml 2>&1 | tee "$EVIDENCE_DIR/build.log"
export CUA_DRIVER_BIN="$CARGO_TARGET_DIR/release/cua-driver"
sha256sum "$CUA_DRIVER_BIN" > "$EVIDENCE_DIR/binary-sha256.txt"
"$CUA_DRIVER_BIN" --version > "$EVIDENCE_DIR/binary-version.txt"
bash libs/cua-driver/tests/fixtures/build/linux.sh --only gtk3
cd libs/cua-driver/examples/jev-use
uv sync --frozen
npm ci --ignore-scripts
uv run --frozen python verify_native.py --harness gtk3 --typescript \
  --output-dir "$EVIDENCE_DIR/native-control" 2>&1 | tee "$EVIDENCE_DIR/native-control.log"
printf '%s\n' 'CONTROL_FINISHED: required forced recovery/refusal fault matrix remains NOT_RUN.' \
  | tee "$EVIDENCE_DIR/ACCEPTANCE_BLOCKED.txt"
# Never allow a happy-path control to become a recovery-E2E PASS.
exit 2
