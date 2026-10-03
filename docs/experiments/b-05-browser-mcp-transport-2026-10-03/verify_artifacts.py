#!/usr/bin/env python3
"""B-05 packet verifier (standard library only).

1. Recomputes the whole summary from raw/ with analyze_b05.analyse and requires it to equal the
   committed b05-summary.json (seeded bootstrap: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim in README.md.
3. Requires every file the packet cites (README.md, PREREG*.json, provenance.json, headline file)
   by a packet-relative path to exist and to be tracked by git (not ignored); fails on any
   ignored-but-cited file. Works from a clean clone.
4. Privacy-scans EVERY commit of the branch (base..HEAD): every added/modified blob (tar.gz/gz
   members included), every path, commit message and author/committer identity: no absolute home or
   mount paths, no lane/host names, no secret-like values. Private names are never committed (not even
   encoded): they come from the untracked file named by CUA_PRIVACY_NAMES_FILE, plus the verifying
   host's own name; without that file the name sub-check covers the host name only (a note says so).

usage: verify_artifacts.py [--base <sha>] [--skip-git]
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_b05 as A  # noqa: E402

BASE = "989cc76cec262ff8bcf6968b637820340fb9caaa"
# Generic patterns first (indices 0-2 are stable for ALLOW); private names follow and are read at verify
# time, never stored in the repository.
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"), re.compile(r"/Users/[A-Za-z0-9_.-]+/")]


def _private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        names |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        return sorted(names), f"private names: {len(names)} (CUA_PRIVACY_NAMES_FILE + host name)"
    return sorted(names), "private names: CUA_PRIVACY_NAMES_FILE not set; name sub-check covers the host name only"


NAMES, NAMES_NOTE = _private_names()
PRIVATE = GENERIC + [re.compile(re.escape(n)) for n in NAMES]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com"), ("kvnloo", "7121943+kvnloo@users.noreply.github.com")}
# Upstream content already public (trycua/cua PR 4316 head a0bca7440, merged into R by b10cd09f2):
# a GitHub Actions runner path in a CI workflow and a placeholder key literal in a unit test.
ALLOW = {
    ("a0bca7440", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("b10cd09f2", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("a0bca7440", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
    ("b10cd09f2", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
}
CITE = re.compile(r"(?<![A-Za-z0-9_./-])((?:raw|harness)/[A-Za-z0-9_./-]+[A-Za-z0-9_-])")
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True).stdout


def texts_of_blob(path: str, data: bytes) -> list[tuple[str, str]]:
    out = [(path, data.decode("utf-8", errors="replace"))]
    if path.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for m in tar.getmembers():
                out.append((f"{path}:{m.name}", m.name))
                if m.isfile():
                    raw = tar.extractfile(m).read()
                    if m.name.endswith(".gz"):
                        raw = gzip.decompress(raw)
                    out.append((f"{path}:{m.name}", raw.decode("utf-8", errors="replace")))
    elif path.endswith(".gz"):
        out.append((path + ":gunzip", gzip.decompress(data).decode("utf-8", errors="replace")))
    return out


def privacy_scan(base: str) -> None:
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits: list[str] = []
    secret_hits: list[str] = []
    bad_ident: list[str] = []
    allowed: list[str] = []
    blobs = 0
    for c in commits:
        meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            bad_ident.append(f"{c[:9]} {meta[0]} / {meta[2]}")
        targets = [("commit-message", meta[4])]
        parents = git("show", "-s", "--format=%P", c).decode().split()
        diff = git("diff-tree", "-r", "--no-commit-id", "--no-renames", parents[0] if parents else "--root", c).decode()
        for line in diff.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            fields, path = parts[0].split(), parts[1]
            targets.append(("path", path))
            if fields[4] == "D":
                continue
            blobs += 1
            targets.extend(texts_of_blob(path, git("cat-file", "blob", fields[3])))
        for where, text in targets:
            for i, pat in enumerate(PRIVATE):
                if pat.search(text):
                    (allowed if (c[:9], where, f"private#{i}") in ALLOW else hits).append(f"{c[:9]} {where[:120]} private#{i}")
            for i, pat in enumerate(SECRET):
                if pat.search(text):
                    (allowed if (c[:9], where, f"secret#{i}") in ALLOW else secret_hits).append(f"{c[:9]} {where[:120]} secret#{i}")
    check("privacy: no absolute local paths / lane or host names in any commit", not hits,
          f"{len(commits)} commits, {blobs} blobs; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: author/committer identity", not bad_ident, f"bad: {bad_ident[:10]}")
    print(f"privacy: {len(commits)} commits, {blobs} blobs scanned; allowlisted upstream content: {sorted(set(allowed))}")


def cited_files_tracked() -> None:
    texts = [p for p in ("README.md", "PREREG.json", "PREREG-AMENDMENT-1.json", "provenance.json",
                         "headline-numbers.json") if (HERE / p).exists()]
    cited: set[str] = set()
    for name in texts:
        cited |= {m.rstrip(".") for m in CITE.findall((HERE / name).read_text())}
    try:
        tracked = set(git("ls-files", "--", ".").decode().split())
        ignored = set(git("ls-files", "--others", "--ignored", "--exclude-standard", "--", ".").decode().split())
    except subprocess.CalledProcessError:
        tracked, ignored = None, set()
    missing, untracked, ign = [], [], []
    for c in sorted(cited):
        p = HERE / c
        if not p.exists():
            missing.append(c)
            continue
        files = [p] if p.is_file() else [q for q in p.rglob("*") if q.is_file()]
        for q in files:
            rel = str(q.relative_to(HERE))
            if rel in ignored:
                ign.append(rel)
            elif tracked is not None and rel not in tracked:
                untracked.append(rel)
    check("cited files exist", not missing, f"missing: {missing[:10]}")
    check("no cited file is git-ignored", not ign, f"ignored: {ign[:10]}")
    check("every cited file is tracked", not untracked, f"untracked: {untracked[:10]}")
    print(f"cited paths checked: {len(cited)}")


def walk(obj, path):  # noqa: ANN001, ANN201
    for key in path.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--skip-git", action="store_true")
    args = p.parse_args()
    recomputed = json.loads(json.dumps(A.analyse(HERE / "raw"), sort_keys=True, default=str))
    committed = json.loads((HERE / "b05-summary.json").read_text())
    check("summary recomputes identically from raw/", recomputed == committed, "" if recomputed == committed else "differs")
    hp = HERE / "headline-numbers.json"
    if hp.exists():
        readme = (HERE / "README.md").read_text()
        for h in json.loads(hp.read_text())["numbers"]:
            val = walk(recomputed, h["path"])
            shown = h["format"].format(*val) if isinstance(val, list) else h["format"].format(val)
            check(f"headline {h['id']} = {shown}", shown == h["text"] and h["text"] in readme,
                  f"recomputed {shown!r}, listed {h['text']!r}, in README {h['text'] in readme}")
    for f in sorted((HERE / "raw").rglob("*")):
        if f.is_file():
            for where, text in texts_of_blob(str(f.relative_to(HERE)), f.read_bytes()):
                if any(pat.search(text) for pat in PRIVATE):
                    check(f"raw privacy {where[:100]}", False, "private string in raw file")
    print(NAMES_NOTE)
    if not args.skip_git:
        cited_files_tracked()
        privacy_scan(args.base)
    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
