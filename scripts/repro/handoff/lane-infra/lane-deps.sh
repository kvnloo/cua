#!/usr/bin/env bash
# usage: lane-deps.sh <worktree>   (installs the locked jev-use example deps exactly like CI: uv sync --frozen, npm ci --ignore-scripts)
set -euo pipefail
export PATH=/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin:/home/kvn/.local/bin:$PATH
export TMPDIR=/mnt/zer0models/cua-lane-tmp
cd "$1/libs/cua-driver/examples/jev-use"
echo "[$(date -u +%FT%TZ)] deps start $1 node=$(node --version) uv=$(uv --version)"
uv sync --frozen --python 3.12
npm ci --ignore-scripts
echo "[$(date -u +%FT%TZ)] deps done $1"
