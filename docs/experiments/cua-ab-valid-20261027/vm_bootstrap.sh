#!/usr/bin/env bash
# Fresh Boat VM: fetch this harness at an exact public SHA, install the pinned tools, run one shard.
# Public sources only (GitHub raw/release, npm registry). No credentials. Prints H2H* lines on stdout.
set -euo pipefail
umask 022

harness_sha="${1:?usage: vm_bootstrap.sh <40-hex harness sha> <shard>}"
shard="${2:?shard}"
[[ "$harness_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "BLOCKED: harness sha must be 40 hex" >&2; exit 2; }

# Pins (all verified below; a mismatch stops the shard before any attempt).
DRIVER_TAG="cua-driver-rs-v0.38.0"
DRIVER_TAG_COMMIT="85e2b1318bd77ccf3cfa88ccdf875a4bb7eaed19"   # trycua/cua tag -> commit
DRIVER_TARBALL="cua-driver-rs-0.38.0-linux-x86_64-binary.tar.gz"
DRIVER_TARBALL_SHA256="31ab9709dd91ce73677e49b9f3e75c6f0d3e4d9625c286c9e58262bfbea698dd"  # release SHA256SUMS
DRIVER_BINARY_SHA256="bf57b2f3778a0a7daa9388e241f20ce948b32a7a2f4dd102e497f34e54137934"
OPENCLI_VERSION="2.0.2"
OPENCLI_TAG_COMMIT="deca0fee85016be2e58836eeca974825e09c9076"   # jackwener/opencli v2.0.2
OPENCLI_INTEGRITY="sha512-+O+S+FQikiVunP/alMG//ww9D1lpgA24+C6ifyyzI4rZVT6GEJVqaiGZWbyI2i/Hcocs4l1K6gnNt+3Yaf2wtw=="

W="$HOME/h2h"
rm -rf "$W"; mkdir -p "$W"; cd "$W"
raw="https://raw.githubusercontent.com/kvnloo/cua/$harness_sha"
for f in libs/cua-driver/examples/jev-use/fixture_server.py \
         docs/experiments/pomerado-cua-2026-10-25/audit_fixture.py \
         docs/experiments/pomerado-cua-2026-10-25/arm_common.py \
         docs/experiments/pomerado-cua-2026-10-25/mcp_stdio.py \
         docs/experiments/cua-ab-valid-20261027/h2h_run.py \
         docs/experiments/cua-ab-valid-20261027/adapters/jev/read-status.js \
         docs/experiments/cua-ab-valid-20261027/adapters/jev/submit-value.js; do
  mkdir -p "$(dirname "$f")"
  curl -fsSL --retry 3 "$raw/$f" -o "$f"
done

# Boat image ships /opt and /opt/google user-owned; Chrome itself is root-owned and the
# driver refuses a non-root-owned ancestor. Repair only those two directories.
opt_fix="none"
for d in /opt /opt/google; do
  if [[ -d "$d" && "$(stat -c %u "$d")" != "0" ]]; then
    sudo -n chown root:root "$d" && opt_fix="chowned"
  fi
done

# Pinned CUA Driver release binary (not the image's preinstalled one).
curl -fsSL --retry 3 -o "$DRIVER_TARBALL" \
  "https://github.com/trycua/cua/releases/download/$DRIVER_TAG/$DRIVER_TARBALL"
echo "$DRIVER_TARBALL_SHA256  $DRIVER_TARBALL" | sha256sum -c - >&2
mkdir -p driver && tar xzf "$DRIVER_TARBALL" -C driver
driver="$W/driver/cua-driver"
echo "$DRIVER_BINARY_SHA256  $driver" | sha256sum -c - >&2
driver_version="$("$driver" --version)"
[[ "$driver_version" == "cua-driver 0.38.0" ]] || { echo "BLOCKED: driver version $driver_version" >&2; exit 2; }
doctor_exe="$("$driver" doctor --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["build"]["exe_sha256"])' || echo unknown)"
preinstalled="$(command -v cua-driver || true)"
preinstalled_version="$([[ -n "$preinstalled" ]] && cua-driver --version 2>/dev/null || echo none)"

# Pinned opencli from the npm registry, integrity-checked before install.
npm pack "@jackwener/opencli@$OPENCLI_VERSION" --silent >/dev/null 2>&1
tgz="jackwener-opencli-$OPENCLI_VERSION.tgz"
got="sha512-$(openssl dgst -sha512 -binary "$tgz" | base64 -w0)"
[[ "$got" == "$OPENCLI_INTEGRITY" ]] || { echo "BLOCKED: opencli integrity $got" >&2; exit 2; }
npm install --prefix "$W/oc" --no-audit --no-fund --silent "./$tgz" >/dev/null 2>&1
opencli="$W/oc/node_modules/.bin/opencli"
mkdir -p "$HOME/.opencli/clis/jev"
cp docs/experiments/cua-ab-valid-20261027/adapters/jev/*.js "$HOME/.opencli/clis/jev/"
opencli_version="$("$opencli" --version 2>/dev/null | tail -n1)"

chrome="/opt/google/chrome/google-chrome"
chrome_version="$("$chrome" --version 2>/dev/null || echo unknown)"
python3 - "$W/pins.json" <<PY
import hashlib, json, platform, sys
from pathlib import Path
def h(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins = {
  "harness_sha": "$harness_sha",
  "driver_version": "$driver_version", "driver_release_tag": "$DRIVER_TAG",
  "driver_tag_commit": "$DRIVER_TAG_COMMIT", "driver_tarball_sha256": "$DRIVER_TARBALL_SHA256",
  "driver_binary_sha256": "$DRIVER_BINARY_SHA256", "driver_doctor_exe_sha256": "$doctor_exe",
  "image_preinstalled_driver_not_used": "$preinstalled_version",
  "opencli_version": "$opencli_version", "opencli_tag_commit": "$OPENCLI_TAG_COMMIT",
  "opencli_npm_integrity": "$OPENCLI_INTEGRITY",
  "opencli_adapter_read_sha256": h("docs/experiments/cua-ab-valid-20261027/adapters/jev/read-status.js"),
  "opencli_adapter_write_sha256": h("docs/experiments/cua-ab-valid-20261027/adapters/jev/submit-value.js"),
  "fixture_sha256": h("libs/cua-driver/examples/jev-use/fixture_server.py"),
  "audit_fixture_sha256": h("docs/experiments/pomerado-cua-2026-10-25/audit_fixture.py"),
  "chrome_version": "$chrome_version", "node_version": "$(node --version)",
  "python_version": platform.python_version(), "nproc": "$(nproc)",
  "mem_kb": "$(awk '/MemTotal/{print $2}' /proc/meminfo)", "opt_ownership_fix": "$opt_fix",
}
Path(sys.argv[1]).write_text(json.dumps(pins, sort_keys=True))
print("H2HPINS " + json.dumps(pins, sort_keys=True))
PY

export DISPLAY="${DISPLAY:-:0}"
python3 -I docs/experiments/cua-ab-valid-20261027/h2h_run.py --shard "$shard" \
  --driver "$driver" --opencli "$opencli" --chrome "$chrome" --pins "$W/pins.json" \
  --deadline-s "${H2H_DEADLINE_S:-360}" --max-blocks "${H2H_MAX_BLOCKS:-99}"
