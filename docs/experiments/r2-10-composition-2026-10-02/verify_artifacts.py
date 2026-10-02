#!/usr/bin/env python3
"""R2-10 packet verifier (standard library only).

1. Recomputes the whole summary from raw/ with analyze_r2_10.analyze and requires it to equal the
   committed r2-10-summary.json (seeded bootstrap: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim in README.md.
3. Privacy-scans EVERY commit of the branch (base..HEAD, merges included): every added/modified
   blob (tar.gz/gz members included), every path name, commit message and author/committer
   identity: no absolute home or mount paths, no lane/host names, no secret-like values.
   Private names are never committed, not even encoded: they come from the untracked file named
   by CUA_PRIVACY_NAMES_FILE plus the verifying host's own name (whole-token match). Hex runs
   (even length >= 8) and base64 runs (>= 12 chars, valid padding) are decoded and scanned too,
   and a committed list of encoded name-like strings fails (PUB-02 rewrite).

usage: verify_artifacts.py [--base 989cc76cec262ff8bcf6968b637820340fb9caaa] [--skip-git]
"""

from __future__ import annotations

import argparse
import base64
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
import analyze_r2_10 as A  # noqa: E402

BASE = "989cc76cec262ff8bcf6968b637820340fb9caaa"
# Generic path patterns first (private#0-2 stay stable for ALLOW); private names follow. They are read at
# verify time and never stored in the repository, not even encoded (PUB-02 rewrite of an encoded list).
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"), re.compile(r"/Users/[A-Za-z0-9_.-]+/")]


def _private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        names |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        return sorted(names), f"private names: {len(names)} (CUA_PRIVACY_NAMES_FILE + host name)"
    return sorted(names), "private names: CUA_PRIVACY_NAMES_FILE not set; the name sub-check covers the host name only"


NAMES, NAMES_NOTE = _private_names()
# whole-token match: a short local user name can be a prefix of a public handle
PRIVATE = GENERIC + [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])") for n in NAMES]
HEXRUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){4,}(?![0-9A-Fa-f])")
B64RUN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{12,}={0,2}(?![A-Za-z0-9+/=])")
LITERAL = re.compile(r"[\"']([A-Za-z0-9+/]{8,}={0,2})[\"']")
NAMELIKE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{2,62}")
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com"), ("kvnloo", "7121943+kvnloo@users.noreply.github.com")}
# Upstream content (trycua/cua PR 4316 head a0bca7440, brought in by the step-2 merge b10cd09f2), already
# public: a GitHub Actions runner path in the CI workflow and a placeholder key literal in a unit test
# (recorded as benign by the wave-1/2 publish scans). Matched by (commit, path, pattern); nothing else.
ALLOW = {
    ("a0bca7440", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("b10cd09f2", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("a0bca7440", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
    ("b10cd09f2", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
}
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True).stdout


def texts_of_blob(path: str, data: bytes) -> list[tuple[str, str]]:
    # compressed bytes are not text (a short name can occur in them by chance): scan the members
    out = [] if path.endswith((".gz", ".tgz")) else [(path, data.decode("utf-8", errors="replace"))]
    if path.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for m in tar.getmembers():
                out.append((f"{path}:{m.name}", m.name))
                if m.isfile():
                    out.append((f"{path}:{m.name}", tar.extractfile(m).read().decode("utf-8", errors="replace")))
    elif path.endswith(".gz"):
        out.append((path + ":gunzip", gzip.decompress(data).decode("utf-8", errors="replace")))
    return out


def _b64(run: str) -> bytes | None:
    body = run.rstrip("=")
    if len(body) % 4 == 1 or (run != body and len(run) % 4):
        return None
    try:
        return base64.b64decode(body + "=" * (-len(body) % 4), validate=True)
    except ValueError:
        return None


def with_decoded(targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """targets plus the decoded text of every hex run and base64 run in them (decodings that are text)."""
    extra = []
    for where, text in targets:
        runs = [bytes.fromhex(r.group()) for r in HEXRUN.finditer(text)]
        runs += [b for r in B64RUN.finditer(text) if (b := _b64(r.group())) is not None]
        for b in runs:
            s = b.decode("utf-8", errors="replace")
            if s and sum(ch.isprintable() for ch in s) >= 0.9 * len(s):
                extra.append((where + ":decoded", s))
    return list(targets) + extra


def encoded_list(text: str) -> bool:
    """True when one text holds >= 2 quoted hex/base64 literals that each decode to a name-like token."""
    n = 0
    for r in LITERAL.finditer(text):
        run = r.group(1)
        if HEXRUN.fullmatch(run) and re.search(r"[A-Fa-f]", run):
            b = bytes.fromhex(run)
        else:
            b = _b64(run) if len(run) >= 12 else None
        n += b is not None and bool(NAMELIKE.fullmatch(b.decode("latin-1")))
    return n >= 2


def privacy_scan(base: str) -> None:
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits: list[str] = []
    secret_hits: list[str] = []
    bad_ident: list[str] = []
    allowed: list[str] = []
    encoded_lists: list[str] = []
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
        encoded_lists += [f"{c[:9]} {w[:120]}" for w, t in targets if w != "path" and encoded_list(t)]
        for where, text in with_decoded(targets):
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
    check("privacy: no committed list of hex/base64-encoded name-like strings in any commit", not encoded_lists,
          f"hits: {encoded_lists[:10]}")
    print(NAMES_NOTE)
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
            for where, text in with_decoded(texts_of_blob(str(f.relative_to(HERE)), f.read_bytes())):
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
