#!/usr/bin/env python3
"""FRESH-07R Part 1: classify every libs/cua-driver path changed between two upstream commits (git only).

usage: freshness_inventory.py <repo> <from> <to> <out.json>
Classes (explicit path rules, first match wins; a path that matches none is UNCLASSIFIED and counts as STOP):
  STOP            platform-linux, cua-driver-core, cua-driver (binary crate), cua-driver-contract / contract/,
                  cua-driver-sdk, examples/jev-use, cursor-overlay, tests/, rust/tests/, rust/examples/
  version_string  VERSION, Cargo.toml, Cargo.lock, Skills/cua-driver/SKILL.md, python/pyproject.toml,
                  python/src/cua_driver/__init__.py, typescript/package.json, typescript/package-lock.json
                  (every changed line must be a version line; otherwise STOP)
  changelog       rust/CHANGELOG.md
  macos           rust/crates/platform-macos/, rust/Skills/cua-driver/MACOS.md
  windows         rust/crates/platform-windows/, rust/crates/cua-driver-uia/
  uninstall       scripts/ (installer/uninstaller and their pytest suite; not compiled into the Driver)
Verdict: AFFECTED (with the STOP paths) if any STOP/UNCLASSIFIED path, else VERSION_ONLY_FOR_LINUX.
Also records whether any packet harness (orig/, harness/) names a changed non-STOP file.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
B = "libs/cua-driver/"
STOP = ("rust/crates/platform-linux/", "rust/crates/cua-driver-core/", "rust/crates/cua-driver/",
        "rust/crates/cua-driver-contract/", "contract/", "rust/crates/cua-driver-sdk/", "examples/jev-use/",
        "rust/crates/cursor-overlay/", "tests/", "rust/tests/", "rust/examples/")
VERSION_FILES = ("rust/VERSION", "rust/Cargo.toml", "rust/Cargo.lock", "rust/Skills/cua-driver/SKILL.md",
                 "python/pyproject.toml", "python/src/cua_driver/__init__.py", "typescript/package.json",
                 "typescript/package-lock.json")
RULES = [("changelog", ("rust/CHANGELOG.md",)),
         ("macos", ("rust/crates/platform-macos/", "rust/Skills/cua-driver/MACOS.md")),
         ("windows", ("rust/crates/platform-windows/", "rust/crates/cua-driver-uia/")),
         ("uninstall", ("scripts/",))]
VLINE = re.compile(r'^[-+]\s*(?:version\s*=\s*"[0-9.]+"|"version":\s*"[0-9.]+",?|__version__\s*=\s*"[0-9.]+".*'
                   r'|version:\s*[0-9.]+.*|[0-9]+\.[0-9]+\.[0-9]+)\s*$')


def git(repo: str, *a: str) -> str:
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True).stdout


def main() -> int:
    repo, a, b, out = sys.argv[1:5]
    a_full, b_full = git(repo, "rev-parse", a).strip(), git(repo, "rev-parse", b).strip()
    rows = []
    for line in git(repo, "diff", "--numstat", a_full, b_full, "--", B).splitlines():
        add, rem, path = line.split("\t")
        rel = path[len(B):]
        cls = "UNCLASSIFIED"
        if rel.startswith(STOP):
            cls = "STOP"
        elif rel in VERSION_FILES:
            body = [x for x in git(repo, "diff", "-U0", a_full, b_full, "--", path).splitlines()
                    if x[:1] in "+-" and not x.startswith(("+++", "---"))]
            cls = "version_string" if body and all(VLINE.match(x) for x in body) else "STOP"
        else:
            for name, prefixes in RULES:
                if rel.startswith(prefixes) or rel in prefixes:
                    cls = name
                    break
        rows.append({"path": path, "added": int(add), "removed": int(rem), "class": cls})
    stop = [r["path"] for r in rows if r["class"] in ("STOP", "UNCLASSIFIED")]
    names = {Path(r["path"]).name for r in rows if r["class"] not in ("STOP", "UNCLASSIFIED")}
    harness_refs = []
    for d in ("orig", "harness"):
        for f in sorted((HERE / d).rglob("*")) if (HERE / d).exists() else []:
            if f.is_file() and "__pycache__" not in f.parts and f.suffix in (".py", ".sh", ".ts", ".js", ".json"):
                t = f.read_text(errors="replace")
                harness_refs += [f"{f.relative_to(HERE)}:{n}" for n in names
                                 if n not in ("VERSION", "Cargo.toml", "Cargo.lock", "package.json", "conftest.py")
                                 and re.search(rf"\b{re.escape(n)}\b", t)]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    res = {"from": a_full, "to": b_full, "commits": int(git(repo, "rev-list", "--count", f"{a_full}..{b_full}").strip()),
           "files_changed": len(rows), "counts": counts, "stop_paths": stop,
           "verdict": "AFFECTED" if stop else "VERSION_ONLY_FOR_LINUX",
           "harness_refs_to_changed_nonstop_files": harness_refs, "files": rows}
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("from", "to", "commits", "files_changed", "counts", "verdict", "stop_paths",
                                          "harness_refs_to_changed_nonstop_files")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
