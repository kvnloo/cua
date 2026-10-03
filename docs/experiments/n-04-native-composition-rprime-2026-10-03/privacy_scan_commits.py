#!/usr/bin/env python3
"""Privacy scan of EVERY commit in a git range (standard library + git).

For each commit in <base>..<head>: the author/committer identity, the commit message, every changed
path and every added or modified blob (gzip members and tar.gz members included) are scanned for
  * absolute local paths (home, mount, macOS user and root directories) and lane-directory names;
  * private names: every non-empty line of the untracked file named by CUA_PRIVACY_NAMES_FILE plus the
    verifying host's own name, matched as whole words, case-insensitive (a name never matches inside a
    longer public handle). The names are never printed and never committed;
  * secret-like values (API-key, token and private-key shapes);
Binary blobs are scanned as their printable ASCII runs (>= 8 bytes, like strings(1)), so random compressed
bytes cannot fake a short-name match. The same patterns are also applied to the DECODED form of every hex literal (>= 8 bytes) and base64 /
base64url literal (>= 6 chars before padding) in the text whose decoded bytes are at least 90% printable ASCII, so a
name or path cannot hide in an encoded string. Without CUA_PRIVACY_NAMES_FILE the name sub-check covers
the host name only and the output says so.

usage: privacy_scan_commits.py --repo <dir> --range <base>..<head> [--allow <sha9>:<path>:<pattern-id> ...]
exit 0 = clean, 1 = findings (printed as commit / where / pattern id, never the matched text).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import io
import os
import re
import socket
import subprocess
import sys
import tarfile
from pathlib import Path

IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com")}
# fragments, so this file does not match itself
GENERIC = [re.compile("/" + p + r"[A-Za-z0-9_.-]+/") for p in ("home/", "mnt/", "Users/")] + [
    re.compile("/" + "root/"), re.compile("cua-lane" + "-tmp"), re.compile("cua-" + "lanes/")]
SECRET = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}", r"xox[abprs]-[A-Za-z0-9-]{10,}",
    r"(?i)(api|secret|access)[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
HEX = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){8,}(?![0-9A-Fa-f])")
B64 = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{6,}={0,2}")


def private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        names |= {x.strip() for x in Path(src).read_text(encoding="utf-8").splitlines()
                  if x.strip() and not x.startswith("#")}
        return sorted(names), f"CUA_PRIVACY_NAMES_FILE set: {len(names)} private names (file + host name)"
    return sorted(names), "CUA_PRIVACY_NAMES_FILE not set: the name sub-check covers the host name only"


def git(repo: str, *args: str) -> bytes:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True).stdout


def printable(b: bytes) -> bool:
    return len(b) >= 4 and sum(1 for c in b if 32 <= c < 127 or c in (9, 10, 13)) >= 0.9 * len(b)


def decoded_forms(text: str) -> list[str]:
    out = []
    for m in HEX.finditer(text):
        try:
            b = bytes.fromhex(m.group(0))
        except ValueError:
            continue
        if printable(b):
            out.append(b.decode("ascii", errors="replace"))
    for m in B64.finditer(text):
        s = m.group(0)
        for dec in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                b = dec(s + "=" * (-len(s) % 4))
            except (binascii.Error, ValueError):
                continue
            if printable(b):
                out.append(b.decode("ascii", errors="replace"))
                break
    return out


PRINTABLE_RUN = re.compile(rb"[\x20-\x7e\t]{8,}")


def as_text(data: bytes) -> str:
    """UTF-8 text as is; a binary blob (compressed members, images) as its printable ASCII runs of
    >= 8 bytes, like strings(1), so random compressed bytes cannot fake a short name match."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return "\n".join(m.group(0).decode("ascii") for m in PRINTABLE_RUN.finditer(data))


def texts_of_blob(path: str, data: bytes) -> list[tuple[str, str]]:
    out = [(path, as_text(data))]
    try:
        if path.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for m in tar.getmembers():
                    out.append((f"{path}:{m.name}", m.name))
                    if m.isfile():
                        raw = tar.extractfile(m).read()
                        if m.name.endswith(".gz"):
                            raw = gzip.decompress(raw)
                        out.append((f"{path}:{m.name}", as_text(raw)))
        elif path.endswith(".gz"):
            out.append((path + ":gunzip", as_text(gzip.decompress(data))))
    except (OSError, EOFError, tarfile.TarError) as exc:
        out.append((path + ":undecodable", f"{type(exc).__name__}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--range", required=True)
    ap.add_argument("--allow", action="append", default=[])
    args = ap.parse_args()
    names, note = private_names()
    pats = [(f"path#{i}", p) for i, p in enumerate(GENERIC)]
    pats += [(f"name#{i}", re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I))
             for i, n in enumerate(names)]
    pats += [(f"secret#{i}", p) for i, p in enumerate(SECRET)]
    allow = set(args.allow)
    commits = git(args.repo, "rev-list", "--reverse", args.range).decode().split()
    hits: list[str] = []
    blobs = decoded = 0
    for c in commits:
        meta = git(args.repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            hits.append(f"{c[:9]} identity")
        targets = [("commit-message", meta[4])]
        parents = git(args.repo, "show", "-s", "--format=%P", c).decode().split()
        diff = git(args.repo, "diff-tree", "-r", "--no-commit-id", "--no-renames",
                   parents[0] if parents else "--root", c).decode()
        for line in diff.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            fields, path = parts[0].split(), parts[1]
            targets.append(("path:" + path, path))
            if fields[4] == "D" or fields[1] == "160000":
                continue
            blobs += 1
            targets.extend(texts_of_blob(path, git(args.repo, "cat-file", "blob", fields[3])))
        for where, text in targets:
            forms = [("plain", text)] + [("decoded", d) for d in decoded_forms(text)]
            decoded += len(forms) - 1
            for kind, t in forms:
                for pid, p in pats:
                    if p.search(t):
                        key = f"{c[:9]}:{where.split(':', 1)[-1] if where.startswith('path:') else where}:{pid}"
                        if key not in allow:
                            hits.append(f"{c[:9]} {where[:140]} {pid} ({kind})")
    print(f"privacy scan {args.range}: {len(commits)} commits, {blobs} blobs, {decoded} decoded literals; {note}")
    for h in sorted(set(hits)):
        print("  HIT", h)
    print("PRIVACY", "FAILED" if hits else "OK", f"({len(set(hits))} findings)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
