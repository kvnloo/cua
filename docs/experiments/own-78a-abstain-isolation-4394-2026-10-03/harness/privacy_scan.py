#!/usr/bin/env python3
"""Privacy scan of every commit in <base>..HEAD (standard library only).

For each commit: every added/modified blob, every path, the message and the author/committer
identity. Fails on absolute home/mount paths, private names, or secret-like values. Hex and base64
literals are decoded and scanned too. Private names are never stored in the repository: they come
from the untracked file named by CUA_PRIVACY_NAMES_FILE (one per line) plus the verifying host's
own name, matched on word boundaries. Without the file a note says the name check is host-only.

usage: privacy_scan.py [--base <sha>] [--repo <dir>]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import re
import socket
import subprocess
import sys

GENERIC = [
    re.compile(r"/home/[A-Za-z0-9_.-]+"),
    re.compile(r"/mnt/[A-Za-z0-9_.-]+"),
    re.compile(r"/Users/[A-Za-z0-9_.-]+"),
    re.compile("cua-lane" + "-tmp"),
    re.compile("cua-lanes" + "/"),
]
SECRET = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bts_[A-Za-z0-9_-]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"(?:TYPESAFE_API_KEY|api[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9._-]{12,}", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
IDENTITY = "Kevin Rajan <7121943+kvnloo@users.noreply.github.com>"
HEX = re.compile(r"\b(?:[0-9a-fA-F]{2}){4,}\b")
B64 = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")


def private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and os.path.isfile(src):
        with open(src, encoding="utf-8") as stream:
            names |= {line.strip() for line in stream if line.strip()}
        note = f"private names: {len(names)} (CUA_PRIVACY_NAMES_FILE + host name)"
    else:
        note = "private names: CUA_PRIVACY_NAMES_FILE not set; name check covers the host name only"
    return sorted(n for n in names if n), note


def decoded_variants(text: str) -> list[str]:
    out = []
    for match in HEX.findall(text):
        try:
            out.append(bytes.fromhex(match).decode("utf-8", "ignore"))
        except ValueError:
            pass
    for match in B64.findall(text):
        try:
            out.append(base64.b64decode(match + "=" * (-len(match) % 4), validate=False).decode("utf-8", "ignore"))
        except (binascii.Error, ValueError):
            pass
    return out


def scan(base: str, repo: str) -> tuple[bool, list[str], str]:
    def git(*args: str) -> bytes:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True).stdout

    names, note = private_names()
    name_pats = [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I) for n in names]
    commits = git("rev-list", "--reverse", f"{base}..HEAD").decode().split()
    problems: list[str] = []
    blobs = 0
    for c in commits:
        ident = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>", c).decode().splitlines()
        if any(line != IDENTITY for line in ident):
            problems.append(f"{c[:9]} identity")
        targets = [("message", git("show", "-s", "--format=%B", c).decode("utf-8", "replace"))]
        for line in git("diff-tree", "--root", "-r", "--no-commit-id", "--no-renames", c).decode().splitlines():
            meta, _, path = line.partition("\t")
            fields = meta.split()
            targets.append(("path:" + path, path))
            if fields[4] == "D":
                continue
            blobs += 1
            targets.append((path, git("cat-file", "blob", fields[3]).decode("utf-8", "replace")))
        for where, text in targets:
            variants = [text, *decoded_variants(text)]
            for v in variants:
                for i, pat in enumerate(GENERIC):
                    if pat.search(v):
                        problems.append(f"{c[:9]} {where[:100]} generic#{i}")
                for i, pat in enumerate(name_pats):
                    if pat.search(v):
                        problems.append(f"{c[:9]} {where[:100]} name#{i}")
                for i, pat in enumerate(SECRET):
                    if pat.search(v):
                        problems.append(f"{c[:9]} {where[:100]} secret#{i}")
    summary = f"{len(commits)} commits, {blobs} blobs scanned; {note}"
    return not problems, sorted(set(problems)), summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="5107f3ccaef38f9f5c66708f1a633f6288bc5dc8")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    ok, problems, summary = scan(args.base, args.repo)
    print(("PASS " if ok else "FAIL ") + summary)
    for p in problems[:40]:
        print("  " + p)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
