#!/usr/bin/env python3
"""FRESH-07 Phase 1a: diff inventory of libs/cua-driver between the old line and new main.

usage: inventory.py <repo> <old> <new> <out.json>
Every changed path is classified by an explicit rule; the script fails if any path matches no rule
or more than one, and checks the Linux-relevant set equals the expected set. The per-file commits
(git log old..new -- path) are recorded so each row cites its upstream PR.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

RULES = [
    ("linux:platform-linux", r"^libs/cua-driver/rust/crates/platform-linux/"),
    ("linux:cua-driver-core", r"^libs/cua-driver/rust/crates/cua-driver-core/"),
    ("version:rust-workspace", r"^libs/cua-driver/rust/(Cargo\.lock|Cargo\.toml|VERSION)$"),
    ("fixture:shared-scenarios", r"^libs/cua-driver/tests/fixtures/shared/scenarios\.json$"),
    ("non-linux:platform-macos", r"^libs/cua-driver/rust/crates/platform-macos/"),
    ("non-linux:platform-windows", r"^libs/cua-driver/rust/crates/platform-windows/"),
    ("non-linux:e2e-appkit-winui3-wpf", r"^libs/cua-driver/rust/crates/cua-driver-e2e/tests/(harness_(appkit|winui3|wpf)_test\.rs|support/foreground_text_oracle\.rs)$"),
    ("non-linux:fixture-macos-windows", r"^libs/cua-driver/tests/fixtures/apps/(macos|windows)/"),
    ("docs", r"^libs/cua-driver/(docs/|rust/CHANGELOG\.md$|rust/Skills/)"),
    ("version:bindings-installers", r"^libs/cua-driver/(python/pyproject\.toml|python/src/cua_driver/__init__\.py|typescript/package(-lock)?\.json|scripts/_install-rust\.sh|scripts/install\.ps1)$"),
]
EXPECTED_LINUX = {
    "libs/cua-driver/rust/crates/platform-linux/src/overlay.rs",
    "libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs",
    "libs/cua-driver/rust/Cargo.lock",
    "libs/cua-driver/rust/Cargo.toml",
    "libs/cua-driver/rust/VERSION",
    "libs/cua-driver/tests/fixtures/shared/scenarios.json",
}


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    repo, old, new, out = sys.argv[1:5]
    names = [p for p in git(repo, "diff", "--name-only", old, new, "--", "libs/cua-driver").splitlines() if p]
    numstat = {}
    for line in git(repo, "diff", "--numstat", old, new, "--", "libs/cua-driver").splitlines():
        add, dele, path = line.split("\t", 2)
        numstat[path] = {"added": int(add), "deleted": int(dele)}
    rows, errors = [], []
    for p in names:
        hits = [cls for cls, rx in RULES if re.search(rx, p)]
        if len(hits) != 1:
            errors.append({"path": p, "rule_hits": hits})
        commits = [c for c in git(repo, "log", "--format=%h %s", f"{old}..{new}", "--", p).splitlines() if c]
        rows.append({"path": p, "class": hits[0] if len(hits) == 1 else None, **numstat.get(p, {}), "commits": commits})
    linux = {r["path"] for r in rows if r["class"] and (r["class"].startswith("linux:") or r["class"].startswith("version:rust")
                                                         or r["class"].startswith("fixture:"))}
    result = {
        "old": git(repo, "rev-parse", old).strip(), "new": git(repo, "rev-parse", new).strip(),
        "files_changed": len(names), "rows": rows, "classification_errors": errors,
        "linux_relevant": sorted(linux), "linux_relevant_equals_expected": linux == EXPECTED_LINUX,
        "commits_touching_libs_cua_driver": [c for c in git(repo, "log", "--format=%h %s", f"{old}..{new}", "--", "libs/cua-driver").splitlines() if c],
        "complete": not errors and len(rows) == len(names),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps({k: result[k] for k in ("files_changed", "complete", "linux_relevant_equals_expected", "classification_errors")}))
    return 0 if result["complete"] and result["linux_relevant_equals_expected"] else 2


if __name__ == "__main__":
    sys.exit(main())
