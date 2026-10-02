#!/usr/bin/env python3
"""R2-10 packet verifier (standard library only).

1. Recomputes the whole summary from raw/ with analyze_r2_10.analyze and requires it to equal the
   committed r2-10-summary.json (seeded bootstrap: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim in README.md.
3. Privacy-scans EVERY commit of the branch (base..HEAD, merges included): every added/modified
   blob (tar.gz/gz members included), every path name, commit message and author/committer
   identity: no absolute home or mount paths, no lane/host names, no secret-like values.
   Private names are stored hex-encoded so this file does not contain them.

usage: verify_artifacts.py [--base 989cc76cec262ff8bcf6968b637820340fb9caaa] [--skip-git]
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_r2_10 as A  # noqa: E402

BASE = "989cc76cec262ff8bcf6968b637820340fb9caaa"
_H = ["67726f6f74", "7a6572306d6f64656c73", "6375612d6c616e6573", "2f746d702f636c61756465", "6b766e40"]
PRIVATE = [re.compile(re.escape(bytes.fromhex(h).decode())) for h in _H] + [
    re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"), re.compile(r"/Users/[A-Za-z0-9_.-]+/")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com"), ("kvnloo", "7121943+kvnloo@users.noreply.github.com")}
# Upstream content (trycua/cua PR 4316 head a0bca7440, brought in by the step-2 merge b10cd09f2), already
# public: a GitHub Actions runner path in the CI workflow and a placeholder key literal in a unit test
# (recorded as benign by the wave-1/2 publish scans). Matched by (commit, path, pattern); nothing else.
ALLOW = {
    ("a0bca7440", ".github/workflows/ci-jev-use.yml", "private#5"),
    ("b10cd09f2", ".github/workflows/ci-jev-use.yml", "private#5"),
    ("a0bca7440", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
    ("b10cd09f2", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
}
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
                    out.append((f"{path}:{m.name}", tar.extractfile(m).read().decode("utf-8", errors="replace")))
    elif path.endswith(".gz"):
        out.append((path + ":gunzip", gzip.decompress(data).decode("utf-8", errors="replace")))
    return out


def privacy_scan(base: str) -> None:
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits: list[str] = []
    secret_hits: list[str] = []
    bad_ident: list[str] = []
    allowed: list[str] = []
    blobs_scanned = 0
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
            data = git("cat-file", "blob", fields[3])
            blobs_scanned += 1
            targets.extend(texts_of_blob(path, data))
        for where, text in targets:
            for i, pat in enumerate(PRIVATE):
                if pat.search(text):
                    if (c[:9], where, f"private#{i}") in ALLOW:
                        allowed.append(f"{c[:9]} {where} private#{i}")
                    else:
                        hits.append(f"{c[:9]} {where[:120]} private#{i}")
            for i, pat in enumerate(SECRET):
                if pat.search(text):
                    if (c[:9], where, f"secret#{i}") in ALLOW:
                        allowed.append(f"{c[:9]} {where} secret#{i}")
                    else:
                        secret_hits.append(f"{c[:9]} {where[:120]} secret#{i}")
    check("privacy: no absolute local paths / lane or host names in any commit", not hits,
          f"{len(commits)} commits, {blobs_scanned} blobs; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: author/committer identity", not bad_ident, f"bad: {bad_ident[:10]}")
    print(f"privacy allowlisted (upstream PR 4316 content): {sorted(set(allowed))}")


def walk(obj, path):  # noqa: ANN001, ANN201
    for key in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(key)]
        else:
            obj = obj[key]
    return obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--skip-git", action="store_true")
    args = p.parse_args()
    summary_path = HERE / "r2-10-summary.json"
    recomputed = json.loads(json.dumps(A.analyze(HERE / "raw"), sort_keys=True, default=str))
    committed = json.loads(summary_path.read_text())
    check("summary recomputes identically from raw/", recomputed == committed,
          "" if recomputed == committed else "differs")
    readme = (HERE / "README.md").read_text()
    heads = json.loads((HERE / "headline-numbers.json").read_text())
    for h in heads["numbers"]:
        val = walk(recomputed, h["path"])
        shown = h["format"].format(val) if not isinstance(val, list) else h["format"].format(*val)
        check(f"headline {h['id']} = {shown}", shown == h["text"] and h["text"] in readme,
              f"recomputed {shown!r}, listed {h['text']!r}, in README {h['text'] in readme}")
    for f in sorted((HERE / "raw").rglob("*")):
        if f.is_file():
            for where, text in texts_of_blob(str(f.relative_to(HERE)), f.read_bytes()):
                if any(pat.search(text) for pat in PRIVATE):
                    check(f"raw privacy {where[:100]}", False, "private string in raw file")
    if not args.skip_git:
        privacy_scan(args.base)
    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
