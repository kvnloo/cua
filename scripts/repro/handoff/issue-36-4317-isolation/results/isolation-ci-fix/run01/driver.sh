#!/bin/bash
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec "/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-e2e86d704" "$@"
