#!/usr/bin/env bash
# Run on the MBP Linux fleet node. This does not start a model or a desktop.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
cd "$ROOT"
[[ -n ${HOBBY_SOURCE_SHA:-} ]] || { echo 'HOBBY_SOURCE_SHA is required' >&2; exit 2; }
printf 'HOBBY_SOURCE_SHA=%s\n' "$HOBBY_SOURCE_SHA"
python3 --version
heartbeat() { while sleep 60; do printf 'HobbyLM exact-head unit gate still running at %s\n' "$(date -u +%FT%TZ)"; done; }
heartbeat & pulse=$!
trap 'kill "$pulse" 2>/dev/null || true' EXIT
VENV=$(mktemp -d /tmp/hobbylm-unit.XXXXXX)
trap 'kill "$pulse" 2>/dev/null || true; rm -rf "$VENV"' EXIT
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet \
    -e libs/python/core -e libs/python/agent \
    'pytest==8.3.5' 'pytest-asyncio==0.25.3' 'torch==2.5.1' 'ruff==0.9.10' \
    'opentelemetry-api' 'opentelemetry-sdk' 'opentelemetry-exporter-otlp-proto-http'
export CUA_TELEMETRY=0 CUA_TELEMETRY_ENABLED=false OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
"$VENV/bin/python" -m pytest libs/python/core/tests libs/python/agent/tests -q --tb=short
"$VENV/bin/python" -m ruff check \
    libs/python/agent/cua_agent/loops/hobbylm.py \
    libs/python/agent/examples/hobbylm_eval \
    libs/python/agent/tests/test_hobbylm*.py
printf 'HOBBY_UNIT_GATE_PASS=%s\n' "$HOBBY_SOURCE_SHA"
