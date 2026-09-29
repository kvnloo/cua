#!/bin/bash
# CI-equivalent Driver wrapper: restores the browser test hooks the runners do not forward.
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec /usr/bin/python3 "/mnt/zer0models/github/cua-lanes/evidence/scripts/repro/handoff/issue-10-4316-ab/mcp_trace_proxy.py" --real "/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-e2e86d704" --trace "/mnt/zer0models/github/cua-lanes/artifacts/p0-4316/ab/run-mock-20260928/cells/traced-b03-p4-main-default-python/mcp-trace.jsonl" -- "$@"
