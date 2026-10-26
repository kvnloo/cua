#!/usr/bin/env bash
# Isolated Boat VM prerequisite probe. No Pomerado mint or A/B trial is run.
set -euo pipefail
umask 077

die() {
  printf 'BLOCKED_BOAT_SETUP: %s\n' "$*" >&2
  exit 2
}

usage() {
  cat <<'EOF'
Usage: bash docs/experiments/pomerado-cua-2026-10-25/boat_setup.sh \
  --expected-head <40-character-reviewed-PR-head-SHA> [--fix-ownership]

Runs a fresh-source CUA Driver mock/fixture setup check, NOT Pomerado A/B.
Chrome paths are checked before Cargo/uv or browser execution. The optional
--fix-ownership explicitly repairs safe existing Chrome path components;
the default only prints exact sudo chown/chmod remediation and refuses.
Never supply credentials or an authenticated browser profile.
EOF
}

expected_head=""
fix_ownership=()
while (( $# )); do
  case "$1" in
    --expected-head)
      (( $# >= 2 )) || die "--expected-head requires a value"
      expected_head="$2"
      shift 2
      ;;
    --fix-ownership)
      fix_ownership=(--fix-ownership)
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unsupported argument: $1"
      ;;
  esac
done
[[ "$expected_head" =~ ^[0-9a-f]{40}$ ]] || die "explicit reviewed --expected-head SHA required"
for tool in git python3 cargo uv sha256sum grep sed; do
  command -v "$tool" >/dev/null 2>&1 || die "required executable missing: $tool"
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
branch="exp/pomerado-site-procedure-20261025"
head="$(git -C "$repo_root" rev-parse --verify HEAD)" || die "not a Git checkout"
checked_branch="$(git -C "$repo_root" symbolic-ref -q --short HEAD || true)"
[[ "$checked_branch" == "$branch" ]] || die "wrong branch: ${checked_branch:-detached}; expected $branch"
[[ "$head" == "$expected_head" ]] || die "HEAD drift: observed $head, expected $expected_head"
[[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=all)" ]] ||
  die "source tree has tracked or untracked files; refuse unverifiable build"
[[ -f "$repo_root/libs/cua-driver/rust/Cargo.toml" ]] ||
  die "full source checkout required; Boat's fixture-only bundle cannot build Driver"

# Real /opt checks have no test-root override. Do not change ownership unless
# an operator deliberately opted into non-recursive root/mode repairs.
python3 "$script_dir/boat_preflight.py" browser "${fix_ownership[@]}"

installed_driver="$(command -v cua-driver || true)"
if [[ -n "$installed_driver" ]]; then
  installed_version="$("$installed_driver" --version 2>&1 || true)"
  printf 'BOAT_PREINSTALLED_DRIVER_NOT_SELECTED: %s: %s\n' "$installed_driver" "$installed_version"
fi

rust_dir="$repo_root/libs/cua-driver/rust"
branch_binary="$rust_dir/target/release/cua-driver"
if [[ -n "${CUA_DRIVER_BIN:-}" && "$CUA_DRIVER_BIN" != "$branch_binary" ]]; then
  die "CUA_DRIVER_BIN points outside the branch build: $CUA_DRIVER_BIN"
fi

# Always build from the exact, clean, reviewed checkout. Cargo's incremental
# cache is safe to reuse; an old PATH release or a stale target binary is not.
(
  cd "$rust_dir"
  CUA_DRIVER_GIT_SHA="$head" CARGO_TARGET_DIR="$rust_dir/target" \
    cargo build --locked --release -p cua-driver --bin cua-driver
) || die "branch source Driver build failed"
[[ -f "$branch_binary" && -x "$branch_binary" && ! -L "$branch_binary" ]] ||
  die "missing/non-executable/symlinked branch Driver artifact: $branch_binary"
expected_version="$(python3 - "$rust_dir/Cargo.toml" <<'PY'
import pathlib
import sys
import tomllib
with pathlib.Path(sys.argv[1]).open("rb") as source:
    print(tomllib.load(source)["workspace"]["package"]["version"])
PY
)"
export CUA_DRIVER_BIN="$branch_binary"
export PATH="$(dirname "$branch_binary"):$PATH"
[[ "$(command -v cua-driver)" == "$branch_binary" ]] ||
  die "PATH resolves cua-driver outside the branch build"
driver_version="$(cua-driver --version)" || die "branch Driver --version failed"
python3 "$script_dir/boat_preflight.py" version \
  --observed "$driver_version" --expected "$expected_version"
binary_sha256="$(sha256sum "$branch_binary" | cut -d ' ' -f 1)"
printf 'BOAT_BRANCH_DRIVER: ref=%s head=%s version=%s sha256=%s\n' \
  "$branch" "$head" "$driver_version" "$binary_sha256"

evidence_root="$(mktemp -d "${TMPDIR:-/tmp}/cua-boat-jev.XXXXXXXX")"
[[ -d "$evidence_root" && ! -L "$evidence_root" ]] || die "cannot create fresh evidence directory"
# Matching semver alone cannot prove the executable is from this commit.
# Doctor reports the running /proc/self/exe digest and embedded source SHA.
# Unrelated Doctor environment probes can fail; require its exact build block.
doctor_exit=0
cua-driver doctor --json > "$evidence_root/driver-doctor.json" || doctor_exit=$?
python3 "$script_dir/boat_preflight.py" attest \
  --doctor-file "$evidence_root/driver-doctor.json" \
  --expected-version "$expected_version" \
  --expected-head "$head" \
  --expected-sha256 "$binary_sha256"
printf 'BOAT_BRANCH_DRIVER_DOCTOR_EXIT: %s (separate from build identity)\n' "$doctor_exit"
python3 - "$evidence_root/preflight.json" "$head" "$driver_version" "$binary_sha256" "$doctor_exit" <<'PY'
import json
from pathlib import Path
import sys
out = {
    "schema": "cua.pomerado.boat_preflight.v1",
    "evidence_class": "CUA_DRIVER_MOCK_SETUP_ONLY",
    "source_ref": "exp/pomerado-site-procedure-20261025",
    "source_head": sys.argv[2],
    "driver_version": sys.argv[3],
    "driver_binary_sha256": sys.argv[4],
    "doctor_exit_code": int(sys.argv[5]),
    "doctor_build_identity_verified": True,
    "chromium_path": "/opt/google/chrome/google-chrome",
    "pomerado_mints": "NOT_RUN",
    "pomerado_trials": "NOT_RUN",
    "cua_vs_pomerado_ab": "NOT_RUN",
}
Path(sys.argv[1]).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
PY

fixture_dir="$repo_root/libs/cua-driver/examples/jev-use"
fixture_pid=""
stop_fixture() {
  if [[ -n "$fixture_pid" ]]; then
    kill "$fixture_pid" 2>/dev/null || true
    wait "$fixture_pid" 2>/dev/null || true
    fixture_pid=""
  fi
}
trap stop_fixture EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Smoke the actual repository-owned fixture independently on an ephemeral
# loopback port. verify_setup.py later manages a *separate* owned fixture.
(
  cd "$fixture_dir"
  exec python3 fixture_server.py --port 0
) >"$evidence_root/fixture.log" 2>&1 &
fixture_pid=$!
fixture_url=""
for (( attempt=0; attempt<60; attempt++ )); do
  fixture_url="$(sed -nE 's@^Fixture ready at (http://127[.]0[.]0[.]1:[0-9]+/)$@\1@p' \
    "$evidence_root/fixture.log")"
  if [[ -n "$fixture_url" ]]; then
    break
  fi
  kill -0 "$fixture_pid" 2>/dev/null || die "fixture_server.py exited before readiness; see $evidence_root/fixture.log"
  sleep 0.1
done
[[ -n "$fixture_url" ]] || die "fixture_server.py readiness timeout; see $evidence_root/fixture.log"
python3 - "$fixture_url" <<'PY'
import json
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen
origin = sys.argv[1]
parsed = urlsplit(origin)
if (parsed.scheme, parsed.hostname, parsed.path) != ("http", "127.0.0.1", "/"):
    raise SystemExit("BLOCKED: fixture origin not trusted loopback")
with urlopen(origin + "state", timeout=3) as response:
    if response.status != 200 or json.load(response) != {"submitted": None}:
        raise SystemExit("BLOCKED: fixture independent oracle not clean")
PY
stop_fixture

[[ ! -e "$evidence_root/verify" ]] || die "verify output path already exists"
(
  cd "$fixture_dir"
  uv sync --frozen --python 3.12
  uv run --frozen --python 3.12 python verify_setup.py \
    --output-dir "$evidence_root/verify"
) 2>&1 | tee "$evidence_root/verify.stdout"
printf 'BOAT_SETUP_VERIFIED: %s (CUA mock Driver only; all A/B NOT_RUN)\n' "$evidence_root"
