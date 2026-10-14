#!/usr/bin/env python3
"""Run only bounded, offline attribution evidence. No production edits."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

PACKET = Path(__file__).resolve().parent
SOURCE_SHA = "22c99c02ff119344e746e19bf8ecc782dbd1f679"
COMMIT = "c8edda06be53e13a759c69de125ce37189023954"
PARENT = "1553a3f360ea12155be3bc77e27c427ca62f967a"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phase", choices=["characterize", "proposed-parity"], required=True)
    args = parser.parse_args()
    root = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PACKET / "source-manifest.json").read_text())
    for item in manifest["files"]:
        data = (root / item["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    metadata_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((PACKET / "metadata").glob("*.json"))
    }
    registry = json.loads((root / ".github/releases/components.json").read_text())
    component = registry["components"]["cua-driver-rs"]
    paths = sorted(set(component["changeDetectionPaths"] + registry["sharedChangePaths"]))
    excludes = sorted(set(component["changeDetectionExcludePaths"]))
    allowed = {
        ("git", "rev-parse", "HEAD"),
        ("git", "log", "--reverse", "--format=%H", PARENT + ".." + COMMIT,
         "--", *paths, *[f":(exclude){p}" for p in excludes]),
        ("git", "show", "--format=", "--name-only", COMMIT),
        ("git", "show", "-s", "--format=%s%x00%B", COMMIT),
    }
    assert os.environ.get("GIT_NO_LAZY_FETCH") == "1"
    assert os.environ.get("GIT_CONFIG_NOSYSTEM") == "1"
    assert os.environ.get("GIT_CONFIG_GLOBAL") == "/dev/null"
    assert os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"
    forbidden_env = {"GH_TOKEN", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
    assert not (forbidden_env & set(os.environ)), "credential-bearing environment"
    calls = []
    denied = []
    real_popen = subprocess.Popen

    def guarded_popen(command, *pargs, **kwargs):
        key = tuple(command) if isinstance(command, (list, tuple)) else ()
        if key not in allowed or kwargs.get("shell") or Path(kwargs.get("cwd", ".")).resolve() != root:
            denied.append({"kind": "process", "command": str(command)})
            raise RuntimeError("offline guard: process refused")
        calls.append(list(key))
        return real_popen(command, *pargs, **kwargs)

    subprocess.Popen = guarded_popen

    def audit(event, details):
        if event.startswith("socket.") or event in {"os.system", "os.exec", "os.posix_spawn"}:
            denied.append({"kind": event})
            raise RuntimeError("offline guard: network or direct process refused")

    sys.addaudithook(audit)
    # Self-tests fail before creating a socket or launching a process.
    for action in (lambda: socket.socket(), lambda: subprocess.run(["false"], cwd=root)):
        try:
            action()
        except RuntimeError:
            pass
        else:
            raise AssertionError("offline guard self-test failed")
    self_test_denials = list(denied)
    denied.clear()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()
    assert head == SOURCE_SHA, head
    sys.path.insert(0, str(root / ".github/scripts"))
    sys.path.insert(0, str(PACKET))
    os.environ["CUA_ATTRIBUTION_SOURCE"] = str(root)
    os.environ["CUA_ATTRIBUTION_OUTPUT"] = str(output)
    import pytest

    selectors = [str(PACKET / "test_pair.py") + "::test_current_paired_behavior"]
    if args.phase == "characterize":
        selectors += [
            str(root / ".github/scripts/tests/test_release_attribution.py")
            + "::test_pr_4500_squash_trailer_resolves_with_the_checked_in_config",
            str(root / ".github/scripts/tests/test_release_attribution.py")
            + "::test_squash_trailer_without_maintainer_provenance_fails_closed",
            str(root / ".github/scripts/tests/test_pr_attribution.py")
            + "::test_unresolved_coauthor_identity_helper_reports_squash_risk",
        ]
    else:
        selectors = [str(PACKET / "test_pair.py") + "::test_PROPOSED_consistency_expectation"]
    code = pytest.main(["-q", "-s", "--tb=short", "-c", "/dev/null", "-p", "no:cacheprovider",
                        *selectors])
    receipt = {
        "phase": args.phase,
        "tested_source_sha": head,
        "source_files_sha256_verified": len(manifest["files"]),
        "metadata_sha256": metadata_hashes,
        "pytest_exit": int(code),
        "allowed_git_calls": calls,
        "guard_self_test_denials": self_test_denials,
        "unexpected_guard_denials": denied,
        "isolation_limit": "Python audit/process allowlist and minimal environment; no OS network namespace",
        "scope": "Actual local Python functions, real local historical git range, recorded API responses only",
    }
    (output / "run-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("RUN_RECEIPT", json.dumps(receipt, sort_keys=True))
    if denied:
        raise AssertionError("unexpected prohibited operation attempted")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())

