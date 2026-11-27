#!/usr/bin/env python3
"""Fail-closed ownership and binary-version checks for the isolated Boat lane.

The CLI always checks the real /opt path. Fake-root support exists only in the
pure inspection function for unprivileged unit tests; it cannot launch Driver.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Callable

CHROME = Path("/opt/google/chrome/google-chrome")
CHAIN = (Path("/"), Path("/opt"), Path("/opt/google"),
         Path("/opt/google/chrome"), CHROME)


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    detail: str
    remedy: str


def inspect_chrome(
    *, root: Path = Path("/"), lstat_fn: Callable = os.lstat
) -> list[Finding]:
    """Inspect each component without trusting symlinks or the caller's uid.

    The alternate root and lstat function are callable-only test seams. They
    are deliberately not exposed as CLI flags.
    """
    findings: list[Finding] = []
    for logical in CHAIN:
        physical = root if logical == Path("/") else root / logical.relative_to("/")
        try:
            info = lstat_fn(physical)
        except FileNotFoundError:
            findings.append(Finding("MISSING", str(logical), "path absent",
                                    "Install the trusted Chrome image; do not create a placeholder"))
            break
        except OSError as error:
            findings.append(Finding("STAT", str(logical), str(error),
                                    "Inspect the path without following symlinks"))
            break
        if stat.S_ISLNK(info.st_mode):
            findings.append(Finding("SYMLINK", str(logical), "symlink not trusted",
                                    "Replace with a verified non-symlink path"))
            break
        valid_type = stat.S_ISREG(info.st_mode) if logical == CHROME else stat.S_ISDIR(info.st_mode)
        if not valid_type:
            findings.append(Finding("TYPE", str(logical), "not a regular executable or directory",
                                    "Restore a trusted Chrome installation"))
            break
        if info.st_uid != 0 or info.st_gid != 0:
            findings.append(Finding(
                "OWNER", str(logical), f"uid={info.st_uid}, gid={info.st_gid}",
                f"sudo chown root:root {logical}",
            ))
        if info.st_mode & 0o022:
            findings.append(Finding(
                "MODE", str(logical), f"mode={info.st_mode & 0o7777:04o} is group/other-writable",
                f"sudo chmod go-w {logical}",
            ))
        if logical == CHROME and not info.st_mode & 0o111:
            findings.append(Finding("EXEC", str(logical), "Chrome is not executable",
                                    "Restore the trusted executable; do not chmod an unknown file"))
    return findings


def validate_driver_version(observed: str, expected_version: str) -> None:
    expected = f"cua-driver {expected_version}"
    if observed != expected:
        raise ValueError(
            f"BRANCH_DRIVER_MISMATCH: got {observed!r}; expected {expected!r}. "
            "Do not use Boat's preinstalled cua-driver; rebuild from this checkout."
        )


def validate_driver_build(
    build: object, expected_version: str, expected_head: str, expected_sha256: str
) -> None:
    """Doctor must report the identity of its *executing* image, not a label."""
    if not isinstance(build, dict):
        raise ValueError("BRANCH_DRIVER_IDENTITY_MISMATCH: missing doctor.build")
    expected = {
        "version": expected_version,
        "git_sha": expected_head,
        "exe_sha256": expected_sha256,
    }
    for key, value in expected.items():
        if build.get(key) != value:
            raise ValueError(
                f"BRANCH_DRIVER_IDENTITY_MISMATCH: doctor.build.{key} "
                f"got {build.get(key)!r}, expected {value!r}"
            )


def browser_preflight(*, fix_ownership: bool = False) -> int:
    findings = inspect_chrome()
    if not findings:
        print(f"CHROME_OWNERSHIP_OK: {CHROME}")
        return 0
    for finding in findings:
        print(f"BLOCKED_CHROME_{finding.code}: {finding.path}: "
              f"{finding.detail}; remediation: {finding.remedy}", file=sys.stderr)
    if not fix_ownership:
        return 2
    # Never repair a missing, symlinked, or type-confused tree, nor the / mount.
    # Repairs are non-recursive and only to the fixed, explicitly checked paths.
    if any(f.code not in {"OWNER", "MODE"} or f.path == "/" for f in findings):
        print("FIX_REFUSED: repair only verified existing Chrome paths; "
              "resolve other findings manually", file=sys.stderr)
        return 2
    for finding in findings:
        arguments = (["chown", "root:root", finding.path] if finding.code == "OWNER"
                     else ["chmod", "go-w", finding.path])
        print(f"OPT_IN_REPAIR: {finding.remedy}", file=sys.stderr)
        try:
            command = arguments if os.geteuid() == 0 else ["sudo", "-n", *arguments]
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"FIX_FAILED: {error}", file=sys.stderr)
            return 2
    remaining = inspect_chrome()
    if remaining:
        for finding in remaining:
            print(f"STILL_BLOCKED: {finding.code} {finding.path}", file=sys.stderr)
        return 2
    print(f"CHROME_OWNERSHIP_OK: {CHROME}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_subparsers(dest="command", required=True)
    browser = choices.add_parser("browser", help="inspect real Chrome ancestors")
    browser.add_argument("--fix-ownership", action="store_true",
                         help="explicitly repair owner/mode on existing non-symlink Chrome paths")
    version = choices.add_parser("version", help="refuse any unexpected Driver version")
    version.add_argument("--observed", required=True)
    version.add_argument("--expected", required=True)
    attest = choices.add_parser("attest", help="reject a stale executable SHA/source")
    attest.add_argument("--doctor-file", type=Path, required=True)
    attest.add_argument("--expected-version", required=True)
    attest.add_argument("--expected-head", required=True)
    attest.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    if args.command == "attest":
        try:
            with args.doctor_file.open(encoding="utf-8") as stream:
                details = json.load(stream)
            validate_driver_build(
                details.get("build") if isinstance(details, dict) else None,
                args.expected_version, args.expected_head, args.expected_sha256,
            )
        except (ValueError, OSError) as error:
            print(f"BLOCKED: {error}", file=sys.stderr)
            return 2
        print("BRANCH_DRIVER_BINARY_IDENTITY_OK")
        return 0
    if args.command == "browser":
        return browser_preflight(fix_ownership=args.fix_ownership)
    try:
        validate_driver_version(args.observed, args.expected)
    except ValueError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    print(f"BRANCH_DRIVER_VERSION_OK: {args.observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
