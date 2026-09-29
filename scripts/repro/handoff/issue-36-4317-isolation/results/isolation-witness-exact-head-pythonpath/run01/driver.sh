#!/bin/bash
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec /usr/bin/python3 "/mnt/zer0models/github/cua-lanes/evidence/scripts/repro/handoff/issue-36-4317-isolation/../issue-10-4316-ab/mcp_trace_proxy.py" --real "/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-e2e86d704" --trace "/mnt/zer0models/github/cua-lanes/artifacts/p0-4317/isolation-witness-exact-head-pythonpath/run01/mcp-trace.jsonl" -- "$@"
