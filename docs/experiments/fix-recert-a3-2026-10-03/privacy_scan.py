#!/usr/bin/env python3
"""RECERT-FIX a3 privacy scan of every commit of one or more branches (stdlib only).

For every commit in <base>..<head> (each branch), scans what the commit ADDED: the commit message, the
author/committer identity, every added or modified path name, and the lines it added (whole content
for a new file and for .gz members) for:
  - absolute local paths (/home/<x>, /mnt/<x>, /root/<x>, /Users/<x>, /media/<x>, /run/user/<n>) and
    /tmp/<x> paths;
  - the machine names listed one per line in the UNTRACKED file named by CUA_PRIVACY_NAMES_FILE
    (for example the output of `hostname` and `id -un`); the names are never printed, only counted;
  - secret patterns (provider/API key shapes, private key blocks, KEY=value assignments);
and repeats the name and path checks on the decoded text of every hex literal (>= 8 hex digits, even
length) and base64 literal (>= 16 chars) in the blob, so an encoded list cannot hide a name.
Prints one line per finding (commit, path, category, count) and exits 1 if any finding.

usage: CUA_PRIVACY_NAMES_FILE=<file> privacy_scan.py <repo> <base> <head> [<head> ...]
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import subprocess
import sys

ABS = re.compile(r"(?<![\w<>.-])/(?:home|mnt|root|Users|media|run/user)/[\w.-]+")
TMP = re.compile(r"(?<![\w<>.-])/tmp/[\w.-]+")
HEX = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-fA-F]{2}){4,}(?![0-9A-Za-z])")
B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])")
SECRET = {
    "api_key_shape": re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "key_assignment": re.compile(r"(?i)\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
}
ALLOWED_IDENTITIES = {"Kevin Rajan <7121943+kvnloo@users.noreply.github.com>"}


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def load_names() -> list[re.Pattern]:
    path = os.environ.get("CUA_PRIVACY_NAMES_FILE")
    if not path or not os.path.exists(path):
        sys.exit("CUA_PRIVACY_NAMES_FILE must name an existing file")
    names = {n.strip() for n in open(path, encoding="utf-8").read().split() if n.strip()}
    names |= {n.split(".")[0] for n in names}
    return [re.compile(r"(?i)(?<![\w-])%s(?![\w-])" % re.escape(n)) for n in sorted(names) if len(n) >= 2]


def decoded(text: str):
    for m in HEX.finditer(text):
        try:
            yield binascii.unhexlify(m.group(0)).decode("utf-8", "ignore")
        except (binascii.Error, ValueError):
            pass
    for m in B64.finditer(text):
        s = m.group(0)
        try:
            yield base64.b64decode(s + "=" * (-len(s) % 4), validate=False).decode("utf-8", "ignore")
        except (binascii.Error, ValueError):
            pass


def hits(text: str, names: list[re.Pattern], deep: bool = True) -> dict[str, int]:
    out: dict[str, int] = {}

    def add(key: str, n: int) -> None:
        if n:
            out[key] = out.get(key, 0) + n

    add("abs_path", len(ABS.findall(text)))
    add("tmp_path", len(TMP.findall(text)))
    add("machine_name", sum(len(p.findall(text)) for p in names))
    for key, pat in SECRET.items():
        add("secret:" + key, len(pat.findall(text)))
    if deep:
        for inner in decoded(text):
            add("decoded:abs_path", len(ABS.findall(inner)))
            add("decoded:machine_name", sum(len(p.findall(inner)) for p in names))
    return out


# Reviewed non-credential values the key-assignment shape matches (a harness row label and the jev-use
# fixture's trial form token); listed so the scan stays strict for everything else.
REVIEWED_NOT_SECRET = ("token:late-retained-early", "fix01-private-token")


def added_text(repo: str, commit: str, path: str) -> str:
    """The lines this commit added to `path` (every line for a new file or a root commit)."""
    out = subprocess.run(["git", "-C", repo, "diff", "--no-color", "--unified=0", "--no-renames",
                          f"{commit}^!", "--", path], capture_output=True).stdout.decode("utf-8", "replace")
    if not out:  # root commit
        out = subprocess.run(["git", "-C", repo, "show", "--no-color", "--format=", commit, "--", path],
                             capture_output=True).stdout.decode("utf-8", "replace")
    return "\n".join(line[1:] for line in out.splitlines() if line.startswith("+") and not line.startswith("+++"))


def scrub_reviewed(text: str) -> str:
    for value in REVIEWED_NOT_SECRET:
        text = text.replace(value, "<reviewed-not-secret>")
    return text


def main(argv: list[str]) -> int:
    """Scans what each commit ADDED: its commit message, identities, path names and added lines."""
    repo, base, heads = argv[0], argv[1], argv[2:]
    names = load_names()
    findings = 0
    scanned = 0
    files = 0
    for head in heads:
        for c in git(repo, "rev-list", "--reverse", f"{base}..{head}").split():
            scanned += 1
            ident = git(repo, "log", "-1", "--format=%an <%ae>%x00%cn <%ce>", c).split("\0")
            for who in ident:
                if who.strip() not in ALLOWED_IDENTITIES:
                    print(f"FINDING {c[:12]} <identity> unexpected_identity 1")
                    findings += 1
            for key, n in hits(git(repo, "log", "-1", "--format=%B", c), names).items():
                print(f"FINDING {c[:12]} <commit message> {key} {n}")
                findings += 1
            raw = git(repo, "diff-tree", "-r", "-z", "--no-commit-id", "--no-renames", "--diff-filter=AM", "--root", c)
            parts = raw.split("\0")
            for meta, path in zip(parts[0::2], parts[1::2]):
                if not meta:
                    continue
                files += 1
                for key, n in hits(path, names, deep=False).items():
                    print(f"FINDING {c[:12]} {path}#name {key} {n}")
                    findings += 1
                if path.endswith(".gz"):
                    sha = meta.split()[3]
                    data = subprocess.run(["git", "-C", repo, "cat-file", "blob", sha], capture_output=True).stdout
                    import gzip
                    text = gzip.decompress(data).decode("utf-8", "replace")
                else:
                    text = added_text(repo, c, path)
                for key, n in hits(scrub_reviewed(text), names).items():
                    print(f"FINDING {c[:12]} {path} {key} {n}")
                    findings += 1
    print(f"{'PASS' if not findings else 'FAIL'} privacy: {scanned} commits, {files} added/modified files, {findings} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
