#!/usr/bin/env bash
set -eu
# Supply checked-out exact head or base and an already provisioned venv.
# Example: bash reproduce.sh /path/to/head /path/to/venv 1 /path/to/output
repo_root=$1
venv_root=$2
expect_envelopes=$3
receipt_root=$4
script_root=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$receipt_root"
cp "$script_root/test_4990_reward_paths_evidence.py" "$repo_root/libs/cua-bench/cua_bench/tests/test_4990_reward_paths_evidence.py"
cd "$repo_root"
PYTHONPATH=libs/cua-bench CUA_TELEMETRY=0 EXPECT_ENVELOPES="$expect_envelopes" RECEIPT_DIR="$receipt_root" "$venv_root/bin/python" -m pytest libs/cua-bench/cua_bench/tests/test_4990_reward_paths_evidence.py --basetemp="$receipt_root/pytest-temp" -q
