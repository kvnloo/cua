#!/usr/bin/env python3
"""PUB-02 boolean privacy audit (SOURCE; standard library only; run under bin/hostless).

Uses the upgraded template scanner (verify_helper.PrivacyScanner, a copy of
docs/experiments/_template/verify_helper.py) and records counts, tags and commit SHAs only, never a
matched value. Set CUA_PRIVACY_NAMES_FILE to the untracked private-names file.

  tips      every origin exp/* and docs/* branch head in raw/audit/origin-heads-at-start.txt: the files
            the branch changes against its merge-base with upstream main (git diff --diff-filter=AM;
            against the upstream main tree when the shallow clone holds no merge-base), read at the tip
            (gzip / tar.gz members in memory, path names included). For a branch with
            a finding, its commits (rev-list tip --not upstream/main, oldest first) are scanned to name
            the first commit that carries each finding class.
  commits   every commit of each branch in raw/audit/unpublished-at-start.txt that is not on origin
            (rev-list tip --not upstream/main --remotes=origin): message, path names, added/modified
            blobs against the first parent.
  ranges    the explicit ranges in raw/audit/ranges.txt (the PUB-02 output branches).

usage: audit_privacy.py <repo> <packet-dir> [--only tips|commits|ranges]
writes <packet-dir>/raw/audit/audit-<part>.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from verify_helper import PrivacyScanner, scan_commits  # noqa: E402

CLASSES = ["encoded-name", "encoded-list", "plain-name", "user-name-in-raw", "abs-path", "secret-like"]
PRIVATE_CLASSES = {"encoded-name", "encoded-list", "plain-name", "user-name-in-raw", "abs-path"}


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def blob(repo: str, sha: str) -> bytes:
    return subprocess.run(["git", "-C", repo, "cat-file", "blob", sha], capture_output=True, check=True).stdout


def classify(f: dict) -> str:
    """Audit class of one finding; abs-path splits into local-root and generic (public paths included)."""
    if f["kind"] == "abs-path":
        return "abs-path" if f["detail"].startswith("local-root") else "abs-path-generic"
    return f["kind"]


def summarize(findings: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for f in findings:
        counts[classify(f)] = counts.get(classify(f), 0) + 1
    return counts


def first_commits(findings: list[dict], order: list[str]) -> dict[str, str]:
    rank = {c[:12]: i for i, c in enumerate(order)}
    out: dict[str, str] = {}
    for f in sorted(findings, key=lambda f: rank.get(f["commit"], 1 << 30)):
        out.setdefault(classify(f), f["commit"])
    return out


def scan_tip(repo: str, tip: str, upstream: str, scanner: PrivacyScanner, cache: dict) -> tuple[list[dict], int, str]:
    mb = subprocess.run(["git", "-C", repo, "merge-base", tip, upstream], capture_output=True, text=True)
    # shallow clone: an old branch may share no local commit with upstream main; then diff the two trees
    base, scope = (mb.stdout.strip(), "merge-base") if mb.returncode == 0 else (upstream, "tree-vs-upstream-main")
    raw = git(repo, "diff", "-z", "--no-renames", "--diff-filter=AM", "--raw", base, tip).split("\0")
    findings, n = [], 0
    for meta, path in zip(raw[0::2], raw[1::2]):
        if not meta:
            continue
        sha = meta.split()[3]
        n += 1
        if (sha, path) not in cache:
            cache[(sha, path)] = scanner.scan_blob(path, blob(repo, sha))
        findings += cache[(sha, path)]
    return findings, n, scope


def main() -> None:
    repo, packet = sys.argv[1], Path(sys.argv[2]).resolve()
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    audit = packet / "raw" / "audit"
    scanner = PrivacyScanner(Path(repo))
    upstream = git(repo, "rev-parse", "upstream/main").strip()
    cache: dict = {}
    ccache: dict = {}
    meta = {"scanner": "verify_helper.PrivacyScanner (template copy)", "names_note": scanner.note(),
            "upstream_main_local_ref": upstream, "classes": CLASSES + ["abs-path-generic"],
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if only in (None, "tips"):
        rows = []
        for line in (audit / "origin-heads-at-start.txt").read_text().splitlines():
            name, tip = line.split()
            findings, nfiles, scope = scan_tip(repo, tip, upstream, scanner, cache)
            row = {"branch": name.removeprefix("origin/"), "tip": tip, "scope": scope, "files_scanned": nfiles,
                   "counts": summarize(findings)}
            if any(classify(f) in PRIVATE_CLASSES for f in findings):  # where/tag listed for private classes only
                row["findings"] = sorted({(classify(f), f["where"], f["detail"]) for f in findings
                                          if classify(f) in PRIVATE_CLASSES})
            # first offending commit only for the private classes (generic paths and secret-like
            # patterns in public upstream content are counted, not traced)
            if any(classify(f) in PRIVATE_CLASSES for f in findings):
                order = git(repo, "rev-list", "--reverse", tip, "--not", upstream).split()
                row["commits_scanned_for_first"] = len(order)
                row["first_offending_commit"] = first_commits(
                    scan_commits(Path(repo), [tip, "--not", upstream], scanner, ccache), order)
            rows.append(row)
            print(f"tip {row['branch']} {tip} files={nfiles} {row['counts']}", flush=True)
        (audit / "audit-tips.json").write_text(json.dumps(dict(meta, rows=rows), indent=1) + "\n")
    for part, src, rng in (("commits", "unpublished-at-start.txt", None), ("ranges", "ranges.txt", True)):
        if only not in (None, part):
            continue
        rows = []
        for line in (audit / src).read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            name, spec = line.split(None, 1)
            args = spec.split() if rng else [spec.strip(), "--not", upstream, "--remotes=origin"]
            order = git(repo, "rev-list", "--reverse", *args).split()
            findings = scan_commits(Path(repo), args, scanner, ccache)
            row = {"branch": name, "rev_list": " ".join(args).replace(upstream, "upstream/main"),
                   "commits_scanned": len(order), "counts": summarize(findings),
                   "first_offending_commit": first_commits(findings, order)}
            if findings:
                row["findings"] = sorted({(classify(f), f["commit"], f["where"], f["detail"]) for f in findings})
            rows.append(row)
            print(f"{part} {name} commits={len(order)} {row['counts']}", flush=True)
        (audit / f"audit-{part}.json").write_text(json.dumps(dict(meta, rows=rows), indent=1) + "\n")


if __name__ == "__main__":
    main()
