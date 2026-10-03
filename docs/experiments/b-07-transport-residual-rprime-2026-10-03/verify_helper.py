#!/usr/bin/env python3
"""Cited-file check for an experiment packet (standard library only).

usage: python3 verify_helper.py [packet-dir] [--readme all|files] [--json]   (run it under bin/hostless)

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

    from verify_helper import check_cited
    findings = check_cited(HERE)        # [] when every cited file is tracked
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


def main(argv: list[str]) -> int:
    scope = argv[argv.index("--readme") + 1] if "--readme" in argv else "files"
    rest = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--readme")]
    findings = check_cited(Path(rest[0]) if rest else Path.cwd(), scope)
    if "--json" in argv:
        print(json.dumps(findings, indent=1))
    for f in findings:
        print(f"FAIL {f['kind']}: {f['path']} (cited in {f['source']})")
    print(f"{'PASS' if not findings else 'FAIL'} cited files tracked: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
