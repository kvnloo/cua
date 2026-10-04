#!/usr/bin/env python3
"""Packet reproducibility check: every cited file must be committed (stdlib only).

usage: python3 verify_helper.py [packet-dir] [--json]     (run it under bin/hostless)

A packet reproduces from a clean checkout only if every file it cites is tracked by git. The
repository-wide .gitignore drops *.log and build/ outputs, so a packet can look complete in its lane
worktree and still be missing evidence once pushed. This helper fails when:

  ignored     a cited path is not tracked and git would ignore it (git check-ignore);
  untracked   a cited path is not tracked and not ignored (never added, or deleted);
  present-but-ignored
              a file exists on disk inside the packet but git ignores it (the lane worktree
              case: fix it before committing, with the packet-local .gitignore or git add -f).

Cited paths come from README.md (inline code spans and relative Markdown link targets, including the
Files section) and from the headline JSON files at the packet top level (*summary*.json,
provenance.json): string values that name a path inside the packet. A token counts as a packet path
when it is relative and its first segment is a top-level entry of the packet or raw/, so repo
source citations (libs/..., focus_guard.rs:614) and prose are not misread as packet files. Globs
(raw/unit/*.log) must match at least one tracked file; brace lists are expanded; tokens with
placeholders (<id>, {a}, NN) are skipped.

Packet verifiers import it:

    from verify_helper import check_packet       # copy this file next to verify_artifacts.py
    findings = check_packet(HERE)                # [] when every cited file is tracked
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

CODE_SPAN = re.compile(r"`([^`\n]+)`")
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")
TRAILING = ".,;:)]}'\""
PLACEHOLDER = re.compile(r"<[^>]*>|[{}]|N{2,}(?![A-Za-z])|x{3,}|X{3,}|\.\.\.|\u2026|\$")
FILE_EXT = re.compile(r"\.[A-Za-z0-9]{1,5}$")
SKIP_PARTS = {"__pycache__"}
RAW_SUFFIXES = (".log", ".jsonl", ".jsonl.gz", ".out", ".txt", ".csv", ".patch")


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)


def tracked_files(packet: Path) -> set[str]:
    out = git(packet, "ls-files", "-z", "--", ".").stdout
    return {p for p in out.split("\0") if p}


def expand_braces(token: str) -> list[str]:
    m = re.search(r"\{([^{}]*,[^{}]*)\}", token)
    if not m:
        return [token]
    return [x for alt in m.group(1).split(",") for x in expand_braces(token[:m.start()] + alt + token[m.end():])]


def normalise(token: str, packet_rel: str) -> str | None:
    token = token.strip().rstrip(TRAILING).split("#", 1)[0]
    token = re.sub(r":\d+(?:-\d+)?$", "", token)  # file.py:12 or file.py:12-30
    if not token or " " in token or "://" in token or token.startswith(("/", "~", "-", ".", "$", "@", "#")):
        return None
    if packet_rel and token.startswith(packet_rel + "/"):
        token = token[len(packet_rel) + 1:]
    if token.startswith("./"):
        token = token[2:]
    return token or None


def is_packet_path(token: str, top_entries: set[str]) -> bool:
    first = token.split("/", 1)[0]
    if "/" not in token.rstrip("/"):
        # a bare name counts if it exists, or if it has a raw-evidence suffix (run.log, trials.jsonl)
        return token.rstrip("/") in top_entries or token.endswith(RAW_SUFFIXES)
    if not (first in top_entries or first == "raw"):
        return False
    # harness/tools/call or module.attr are not files: a cited path ends in a file suffix, a glob or
    # "/", or lies under raw/
    last = token.rstrip("/").rsplit("/", 1)[-1]
    return token.endswith("/") or first == "raw" or bool(FILE_EXT.search(last)) or any(c in last for c in "*?[")


def cited_tokens(packet: Path) -> list[tuple[str, str]]:
    """(source, raw token) pairs from README.md and the headline JSON files."""
    found: list[tuple[str, str]] = []
    readme = packet / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="replace")
        for m in CODE_SPAN.finditer(text):
            found += [("README.md", t) for t in m.group(1).split() if t]
        found += [("README.md", m.group(1)) for m in MD_LINK.finditer(text)]
    for js in sorted(list(packet.glob("*summary*.json")) + list(packet.glob("provenance.json"))):
        try:
            doc = json.loads(js.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stack = [doc]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack += list(node.values())
            elif isinstance(node, list):
                stack += node
            elif isinstance(node, str) and "/" in node and len(node) < 300:
                found.append((js.name, node))
    return found


def check_packet(packet: Path | str, *, include_present: bool = True) -> list[dict]:
    packet = Path(packet).resolve()
    top = Path(git(packet, "rev-parse", "--show-toplevel").stdout.strip())
    packet_rel = packet.relative_to(top).as_posix()
    tracked = tracked_files(packet)
    rel_tracked = {p[len(packet_rel) + 1:] if p.startswith(packet_rel + "/") else p for p in tracked}
    top_entries = {p.split("/", 1)[0] for p in rel_tracked} | {p.name for p in packet.iterdir()}
    findings: list[dict] = []
    seen: set[str] = set()
    for source, raw in cited_tokens(packet):
        token = normalise(raw, packet_rel)
        if token is None:
            continue
        for path in expand_braces(token):
            path = path.rstrip(TRAILING)
            if path in seen or PLACEHOLDER.search(path) or not is_packet_path(path, top_entries):
                continue
            seen.add(path)
            if any(part in SKIP_PARTS for part in path.split("/")):
                continue
            bare = "/" not in path.rstrip("/")
            if bare and path.rstrip("/") not in top_entries:
                # a bare file name cited in context (session.txt of each trial): any tracked file with that name
                if any(fnmatch.fnmatchcase(p.rsplit("/", 1)[-1], path) for p in rel_tracked):
                    continue
                probe = "raw/" + re.sub(r"\[[^]]*\]|[*?]", "x", path)
            elif any(ch in path for ch in "*?["):
                if any(fnmatch.fnmatchcase(p, path) for p in rel_tracked):
                    continue
                probe = re.sub(r"\[[^]]*\]|[*?]", "x", path)
            elif path.endswith("/"):
                if any(p.startswith(path) for p in rel_tracked):
                    continue
                probe = path
            else:
                if path in rel_tracked or any(p.startswith(path + "/") for p in rel_tracked):
                    continue
                probe = path
            ignored = git(packet, "check-ignore", "-q", "--", probe, check=False).returncode == 0
            findings.append({"kind": "ignored" if ignored else "untracked", "path": path, "source": source})
    if include_present:
        out = git(packet, "ls-files", "-z", "-o", "-i", "--exclude-standard", "--", ".").stdout
        for p in sorted(x for x in out.split("\0") if x):
            if not any(part in SKIP_PARTS for part in p.split("/")) and not p.endswith(".pyc"):
                rel = p[len(packet_rel) + 1:] if p.startswith(packet_rel + "/") else p
                findings.append({"kind": "present-but-ignored", "path": rel, "source": "worktree"})
    return findings


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    packet = Path(args[0]) if args else Path.cwd()
    findings = check_packet(packet)
    if "--json" in argv:
        print(json.dumps(findings, indent=1))
    for f in findings:
        print(f"FAIL {f['kind']}: {f['path']} (cited in {f['source']})")
    print(f"{'PASS' if not findings else 'FAIL'} cited files tracked: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
