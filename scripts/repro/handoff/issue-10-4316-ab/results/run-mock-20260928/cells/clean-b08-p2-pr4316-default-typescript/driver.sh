#!/bin/bash
# CI-equivalent Driver wrapper: restores the browser test hooks the runners do not forward.
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec "/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-e2e86d704" "$@"
