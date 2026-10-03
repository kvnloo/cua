#!/usr/bin/env python3
"""Cited-file check and privacy scan for an experiment packet (standard library only).

usage: python3 verify_helper.py [packet-dir] [--readme all|files] [--json] [--privacy [--base <sha>]]
       (run it under bin/hostless; set CUA_PRIVACY_NAMES_FILE for the name check, see below)

A packet reproduces from a clean checkout only if every file it cites is committed. The repository
.gitignore drops *.log and build/ outputs, so a packet can look complete in the lane worktree and
still miss evidence once pushed. This check fails when a cited path is not tracked by git, and says
whether git ignores it ("ignored", e.g. a *.log) or not ("untracked", never added or deleted).

Cited paths come from
  - README.md: inline code spans and relative Markdown link targets. With --readme files (the
    default) only the section(s) whose heading starts with "Files" are read; a README with no such
    section is read whole. --readme all always reads the whole README.
  - headline JSON: string values in the packet's top-level *summary*.json and headline*.json files.
A token counts as a packet path when it is relative and its first segment is a top-level entry of
the packet (tracked or on disk) or raw/. Repo citations (libs/..., focus_guard.rs:614) and prose
are skipped. A glob (raw/unit/*.log) must match at least one tracked file, and a cited directory
at least one tracked file under it (so cite the files, not only their directory). Tokens with placeholders
(<id>, {a}, ..., NN, xxx) are skipped; brace lists ({a,b}) are expanded.

From verify_artifacts.py (copy this file next to it):

    from verify_helper import check_cited, check_privacy
    findings = check_cited(HERE)        # [] when every cited file is tracked
    leaks = check_privacy(HERE, base)   # [] when no tracked packet file (and no commit base..HEAD) leaks

Privacy scan (check_privacy). Private names are never committed, not even encoded: they are read at
verify time from the untracked file named by CUA_PRIVACY_NAMES_FILE (one per line), plus the host name
and the local user name, and matched as whole tokens (case-insensitive). Findings carry a kind, where
and a pattern tag such as name#1(user), never the matched value:
  plain-name        a private name in plain text (the host name anywhere; the user name outside raw/)
  user-name-in-raw  the local user name in a raw/ file (gzip and tar.gz members included)
  encoded-name      a private name hex- or base64-encoded, or found after decoding a hex run
                    ([0-9a-f]{8,}, even length) or a base64 run (>= 12 chars, valid padding)
  encoded-list      >= 2 quoted hex/base64 literals in one file that each decode to a name-like token
                    (a committed encoded name list fails even when its names are not in the names file)
  abs-path          /home/<x>/, /mnt/<x>/, /Users/<x>/ or a local root (home, checkout mount, TMPDIR),
                    in plain or decoded text
  secret-like       API-key, token or private-key patterns
gzip and tar.gz blobs are scanned as their members, decompressed in memory (never the compressed bytes);
other binary blobs as their printable runs.
"""

from __future__ import annotations

import base64
import fnmatch
import getpass
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

CODE_SPAN = re.compile(r"`([^`\n]+)`")
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
TRAILING = ".,;:)]}'\""
PLACEHOLDER = re.compile(r"<[^>]*>|\{[^,}]*\}|\.\.\.|…|\$|(?<![A-Z])N{2,}(?![A-Za-z])|[xX]{3,}")
FILE_EXT = re.compile(r"\.[A-Za-z0-9]{1,5}$")
RAW_SUFFIXES = (".log", ".jsonl", ".jsonl.gz", ".out", ".txt", ".csv", ".patch")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def readme_text(packet: Path, scope: str) -> str:
    path = packet / "README.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if scope == "all":
        return text
    keep, level, out = False, 0, []
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            if keep and len(m.group(1)) <= level:
                keep = False
            if m.group(2).strip().lower().startswith("files"):
                keep, level = True, len(m.group(1))
        if keep:
            out.append(line)
    return "\n".join(out) if out else text


def cited_tokens(packet: Path, scope: str) -> list[tuple[str, str]]:
    """(source, token) pairs from README.md and the headline JSON files."""
    text = readme_text(packet, scope)
    found = [("README.md", t) for m in CODE_SPAN.finditer(text) for t in m.group(1).split()]
    found += [("README.md", m.group(1)) for m in MD_LINK.finditer(text)]
    for js in sorted({*packet.glob("*summary*.json"), *packet.glob("headline*.json")}):
        try:
            stack = [json.loads(js.read_text(encoding="utf-8"))]
        except (OSError, ValueError):
            continue
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack += node.values()
            elif isinstance(node, list):
                stack += node
            elif isinstance(node, str) and "/" in node and " " not in node and len(node) < 300:
                found.append((js.name, node))
    return found


def expand_braces(token: str) -> list[str]:
    m = re.search(r"\{([^{}]*,[^{}]*)\}", token)
    if not m:
        return [token]
    return [x for alt in m.group(1).split(",") for x in expand_braces(token[:m.start()] + alt + token[m.end():])]


def normalise(token: str, packet_rel: str) -> str | None:
    token = token.strip().rstrip(TRAILING).split("#", 1)[0]
    token = re.sub(r":\d+(?:-\d+)?$", "", token)  # file.py:12 or file.py:12-30
    if packet_rel and token.startswith(packet_rel + "/"):
        token = token[len(packet_rel) + 1:]
    token = token.removeprefix("./")
    if not token or "://" in token or token.startswith(("/", "~", "-", ".", "$", "@", "!")):
        return None
    return token


def is_packet_path(token: str, top: set[str]) -> bool:
    first, _, rest = token.rstrip("/").partition("/")
    if not rest:  # a bare name: a top-level entry, or a raw-evidence file name (run.log)
        return first in top or token.endswith(RAW_SUFFIXES)
    if first not in top and first != "raw":
        return False
    last = token.rstrip("/").rsplit("/", 1)[-1]
    return token.endswith("/") or first == "raw" or bool(FILE_EXT.search(last)) or any(c in last for c in "*?[")


def check_cited(packet: Path | str, scope: str = "files") -> list[dict]:
    """Every cited packet path that git does not track: {"path", "kind": ignored|untracked, "source"}."""
    packet = Path(packet).resolve()
    top_dir = Path(git(packet, "rev-parse", "--show-toplevel").stdout.strip())
    packet_rel = packet.relative_to(top_dir).as_posix()
    tracked = {p for p in git(packet, "ls-files", "-z", "--", ".").stdout.split("\0") if p}  # packet-relative
    top = {p.split("/", 1)[0] for p in tracked} | {p.name for p in packet.iterdir()}
    findings, seen = [], set()
    for source, raw in cited_tokens(packet, scope):
        token = normalise(raw, packet_rel)
        for path in expand_braces(token) if token else []:
            path = path.rstrip(TRAILING)
            if path in seen or PLACEHOLDER.search(path) or "__pycache__" in path or not is_packet_path(path, top):
                continue
            seen.add(path)
            probe = re.sub(r"\[[^]]*\]|[*?]", "x", path)
            if "/" not in path.rstrip("/") and path.rstrip("/") not in top:  # bare file name cited in context
                if any(fnmatch.fnmatchcase(p.rsplit("/", 1)[-1], path) for p in tracked):
                    continue
                probe = "raw/" + probe
            elif any(c in path for c in "*?["):
                pattern = path + "*" if path.endswith("/") else path
                if any(fnmatch.fnmatchcase(p, pattern) for p in tracked):
                    continue
            elif path.rstrip("/") in tracked or any(p.startswith(path.rstrip("/") + "/") for p in tracked):
                continue
            ignored = git(packet, "check-ignore", "-q", "--no-index", "--", probe).returncode == 0
            findings.append({"path": path, "kind": "ignored" if ignored else "untracked", "source": source})
    return findings


# ---- privacy scan (PUB-02) --------------------------------------------------------------------------
GENERIC_PATH = re.compile(r"/(?:home|mnt|Users)/[A-Za-z0-9_.-]+/")
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
HEXRUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){4,}(?![0-9A-Fa-f])")
B64RUN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{12,}={0,2}(?![A-Za-z0-9+/=])")
LITERAL = re.compile(r"[\"'`]([A-Za-z0-9+/]{8,}={0,2})[\"'`]")
NAMELIKE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{2,62}")
PRINTABLE = re.compile(rb"[\x20-\x7e]{6,}")


def private_names() -> list[tuple[str, str]]:
    """(role, name) for CUA_PRIVACY_NAMES_FILE entries ("file"), the local user ("user") and the host
    ("host"). Read at verify time; never stored in the repository and never printed."""
    found: dict[str, str] = {}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        for line in Path(src).read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                found[line.strip()] = "file"
    try:
        found[getpass.getuser()] = "user"
    except (KeyError, OSError):
        pass
    found[socket.gethostname()] = "host"
    return sorted((role, n) for n, role in found.items() if n and n != "localhost")


def local_roots(repo: Path | None) -> list[str]:
    """Home, and the first two components of the checkout and of TMPDIR (e.g. a mount root)."""
    roots = {str(Path.home())}
    for p in (repo, os.environ.get("TMPDIR")):
        parts = Path(p).resolve().parts if p else ()
        if len(parts) >= 3:
            roots.add("/" + "/".join(parts[1:3]))
    return sorted(r for r in roots if r.count("/") >= 2)


def _b64(run: str) -> bytes | None:
    body = run.rstrip("=")
    if len(body) % 4 == 1 or (run != body and len(run) % 4):
        return None
    try:
        return base64.b64decode(body + "=" * (-len(body) % 4), validate=True)
    except ValueError:
        return None


def decoded_texts(text: str) -> list[str]:
    """The decoded text of every hex run and base64 run in text (decodings that are mostly printable)."""
    runs = [bytes.fromhex(m.group()) for m in HEXRUN.finditer(text)]
    runs += [b for m in B64RUN.finditer(text) if (b := _b64(m.group())) is not None]
    out = []
    for b in runs:
        s = b.decode("utf-8", errors="replace")
        if s and sum(ch.isprintable() for ch in s) >= 0.9 * len(s):
            out.append(s)
    return out


def encoded_list(text: str) -> bool:
    """True when text holds >= 2 quoted hex/base64 literals that each decode to a name-like token."""
    n = 0
    for m in LITERAL.finditer(text):
        run = m.group(1)
        if HEXRUN.fullmatch(run) and re.search(r"[A-Fa-f]", run):
            b = bytes.fromhex(run)
        else:
            b = _b64(run) if len(run) >= 12 else None
        n += b is not None and bool(NAMELIKE.fullmatch(b.decode("latin-1")))
    return n >= 2


def _as_text(data: bytes) -> str:
    if b"\0" in data[:8000]:  # binary: its printable runs only
        return "\n".join(m.group().decode("ascii") for m in PRINTABLE.finditer(data))
    return data.decode("utf-8", errors="replace")


def blob_texts(path: str, data: bytes) -> list[tuple[str, str]]:
    """(suffix, text) pairs: gzip / tar.gz members decompressed in memory, never the compressed bytes."""
    try:
        if path.endswith((".tar.gz", ".tgz")):
            out = []
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                for m in tar.getmembers():
                    out.append((f"!{m.name}#name", m.name))
                    if m.isfile():
                        raw = tar.extractfile(m).read()
                        out.append((f"!{m.name}", _as_text(gzip.decompress(raw) if m.name.endswith(".gz") else raw)))
            return out
        if path.endswith(".gz"):
            return [("!gunzip", _as_text(gzip.decompress(data)))]
    except (OSError, EOFError, tarfile.TarError):
        return [("!undecompressable", _as_text(data))]
    return [("", _as_text(data))]


class PrivacyScanner:
    """Scans text and blobs for the finding kinds in the module docstring; reports tags, never values."""

    def __init__(self, repo: Path | None = None) -> None:
        self.names = private_names()
        self.plain = []
        self.encoded = []
        for i, (role, name) in enumerate(self.names):
            tag = f"name#{i}({role})"
            self.plain.append((tag, role, re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", re.I)))
            raw = name.encode()
            for enc in {raw.hex(), raw.hex().upper()}:
                self.encoded.append((tag, re.compile(r"(?<![0-9A-Fa-f])" + enc + r"(?![0-9A-Fa-f])")))
            b64 = base64.b64encode(raw).decode()
            self.encoded.append((tag, re.compile(r"(?<![A-Za-z0-9+/])" + re.escape(b64) + r"(?![A-Za-z0-9+/=])")))
        self.roots = [re.compile(re.escape(r) + r"(?![A-Za-z0-9_.-])") for r in local_roots(repo)]

    def note(self) -> str:
        roles = [r for r, _ in self.names]
        return (f"private names: {len(self.names)} (file {roles.count('file')}, host {roles.count('host')}, "
                f"user {roles.count('user')}); CUA_PRIVACY_NAMES_FILE "
                f"{'read' if os.environ.get('CUA_PRIVACY_NAMES_FILE') else 'not set'}; local roots: {len(self.roots)}")

    def redact(self, where: str) -> str:
        for tag, _, pat in self.plain:
            where = pat.sub(f"<{tag}>", where)
        for i, pat in enumerate(self.roots):
            where = pat.sub(f"<root#{i}>", where)
        return where

    def _abs(self, text: str) -> str | None:
        if any(p.search(text) for p in self.roots):
            return "local-root"
        return "generic" if GENERIC_PATH.search(text) else None

    def scan_text(self, where: str, text: str, in_raw: bool = False) -> list[dict]:
        hits: set[tuple[str, str]] = set()
        for tag, role, pat in self.plain:
            if pat.search(text):
                hits.add(("user-name-in-raw" if role == "user" and in_raw else "plain-name", tag))
        if (kind := self._abs(text)):
            hits.add(("abs-path", kind))
        hits |= {("secret-like", f"secret#{i}") for i, pat in enumerate(SECRET) if pat.search(text)}
        hits |= {("encoded-name", f"{tag} encoded") for tag, pat in self.encoded if pat.search(text)}
        for dec in decoded_texts(text):
            hits |= {("encoded-name", f"{tag} decoded") for tag, _, pat in self.plain if pat.search(dec)}
            if (kind := self._abs(dec)):
                hits.add(("abs-path", f"{kind} decoded"))
        if encoded_list(text):
            hits.add(("encoded-list", ">=2 encoded name-like literals"))
        safe = self.redact(where)
        return [{"kind": k, "where": safe, "detail": d} for k, d in sorted(hits)]

    def scan_blob(self, path: str, data: bytes) -> list[dict]:
        in_raw = path.startswith("raw/") or "/raw/" in path
        out = self.scan_text(path + "#name", path)
        for suffix, text in blob_texts(path, data):
            out += self.scan_text(path + suffix, text, in_raw)
        return out


def scan_commits(repo: Path, rev_range: list[str], scanner: PrivacyScanner, cache: dict | None = None) -> list[dict]:
    """Every commit of rev_range (git rev-list arguments): message, changed paths and added/modified blobs
    against the first parent. Each finding gets a "commit" field."""
    cache = {} if cache is None else cache
    commits = git(repo, "rev-list", *rev_range).stdout.split()
    out = []
    for c in commits:
        msg = git(repo, "log", "-1", "--format=%B", c).stdout
        found = scanner.scan_text("<commit message>", msg)
        parents = git(repo, "rev-list", "--parents", "-n", "1", c).stdout.split()[1:]
        diff = git(repo, "diff-tree", "-r", "-z", "--no-commit-id", "--no-renames", "--diff-filter=AM",
                   parents[0] if parents else "--root", c).stdout.split("\0")
        for meta, path in zip(diff[0::2], diff[1::2]):
            if not meta:
                continue
            sha = meta.split()[3]
            if (sha, path) not in cache:
                data = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", sha], capture_output=True).stdout
                cache[(sha, path)] = scanner.scan_blob(path, data)
            found += cache[(sha, path)]
        out += [dict(f, commit=c[:12]) for f in found]
    return out


def check_privacy(packet: Path | str, base: str | None = None) -> list[dict]:
    """Privacy findings for every tracked packet file (from the checkout) and, with base, for every
    commit base..HEAD of the repository. [] when clean."""
    packet = Path(packet).resolve()
    top = Path(git(packet, "rev-parse", "--show-toplevel").stdout.strip())
    scanner = PrivacyScanner(top)
    findings = []
    for rel in (p for p in git(packet, "ls-files", "-z", "--", ".").stdout.split("\0") if p):
        f = packet / rel
        if f.is_file():
            findings += scanner.scan_blob(rel, f.read_bytes())
    if base:
        findings += scan_commits(top, [f"{base}..HEAD"], scanner)
    return findings


def main(argv: list[str]) -> int:
    scope = argv[argv.index("--readme") + 1] if "--readme" in argv else "files"
    base = argv[argv.index("--base") + 1] if "--base" in argv else None
    rest = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--readme", "--base"))]
    packet = Path(rest[0]) if rest else Path.cwd()
    findings = check_cited(packet, scope)
    if "--json" in argv:
        print(json.dumps(findings, indent=1))
    for f in findings:
        print(f"FAIL {f['kind']}: {f['path']} (cited in {f['source']})")
    print(f"{'PASS' if not findings else 'FAIL'} cited files tracked: {len(findings)} finding(s)")
    leaks = []
    if "--privacy" in argv:
        top = Path(git(packet.resolve(), "rev-parse", "--show-toplevel").stdout.strip())
        print(PrivacyScanner(top).note())
        leaks = check_privacy(packet, base)
        for f in leaks:
            print(f"FAIL privacy {f['kind']}: {f.get('commit', 'checkout')} {f['where']} ({f['detail']})")
        print(f"{'PASS' if not leaks else 'FAIL'} privacy ({'tracked files' + (f' + commits {base}..HEAD' if base else '')}):"
              f" {len(leaks)} finding(s)")
    return 1 if findings or leaks else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
