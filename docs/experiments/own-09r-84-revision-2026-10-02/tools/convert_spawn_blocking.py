#!/usr/bin/env python3
"""OWN-09R revision step (4): route production native work through
`spawn_blocking_owned` (stdlib only, deterministic, idempotent).

Rule (reviewable, mechanical): every production `tokio::task::spawn_blocking(`
call in the target files becomes `spawn_blocking_owned(`, a drop-in that
returns the same `JoinHandle` and additionally moves the current call's
admission holds into the closure. Each converted site is classified for the
listing: `awaited` (`spawn_blocking(..).await`), `timeout_budget` (inner future
of `tokio::time::timeout(budget, spawn_blocking(..)).await`) or `handle` (the
JoinHandle is bound and awaited/joined later; each such site is reviewed by
hand and listed in the packet README). Outside a dispatch scope the holds are
empty and behaviour is identical to `spawn_blocking`. Code inside
`#[cfg(test)]`, `#[test]` and `#[tokio::test]` items is never touched.

usage: convert_spawn_blocking.py <libs/cua-driver/rust/crates dir> [--check] [--list out.json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NEEDLE = "tokio::task::spawn_blocking("
TARGETS = {
    # crate-relative file globs -> replacement path
    "platform-linux/src": "cua_driver_core::tool::spawn_blocking_owned(",
    "cua-driver-core/src/clipboard.rs": "crate::tool::spawn_blocking_owned(",
    "cua-driver-core/src/window_target.rs": "crate::tool::spawn_blocking_owned(",
    "cua-driver-core/src/recording_tools.rs": "crate::tool::spawn_blocking_owned(",
}


def code_mask(text: str) -> list[bool]:
    """True for characters that are Rust code (not comment, string or char literal)."""
    mask = [True] * len(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                mask[k] = False
            i = j
            continue
        if text.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            for k in range(i, j):
                mask[k] = False
            i = j
            continue
        m = re.match(r'b?r(#*)"', text[i:])
        if m and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            close = '"' + m.group(1)
            j = text.find(close, i + len(m.group(0)))
            j = n if j < 0 else j + len(close)
            for k in range(i, j):
                mask[k] = False
            i = j
            continue
        if c == '"' or (c == "b" and text.startswith('b"', i)):
            j = i + (2 if c == "b" else 1)
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j += 1
            for k in range(i, min(j, n)):
                mask[k] = False
            i = j
            continue
        if c == "'":
            m = re.match(r"'(\\(x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]+\}|.)|[^\\'])'", text[i:])
            if m:
                for k in range(i, i + len(m.group(0))):
                    mask[k] = False
                i += len(m.group(0))
                continue
        i += 1
    return mask


def match_close(text: str, mask: list[bool], open_at: int, pair: str = "()") -> int:
    depth = 0
    for k in range(open_at, len(text)):
        if not mask[k]:
            continue
        if text[k] == pair[0]:
            depth += 1
        elif text[k] == pair[1]:
            depth -= 1
            if depth == 0:
                return k
    raise ValueError(f"unbalanced {pair} at {open_at}")


def test_spans(text: str, mask: list[bool]) -> list[tuple[int, int]]:
    spans = []
    for m in re.finditer(r"#\[(cfg\(test\)|test|tokio::test[^\]]*)\]", text):
        if not mask[m.start()]:
            continue
        j = m.end()
        while j < len(text) and not (mask[j] and text[j] in "{;"):
            j += 1
        if j >= len(text):
            continue
        end = match_close(text, mask, j, "{}") if text[j] == "{" else j
        spans.append((m.start(), end))
    return spans


def skip_ws(text: str, k: int) -> int:
    while k < len(text) and text[k].isspace():
        k += 1
    return k


def enclosing_fn(text: str, pos: int) -> str:
    names = re.findall(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", text[:pos])
    return names[-1] if names else "?"


def classify(text: str, mask: list[bool], at: int, needle: str = NEEDLE) -> str:
    close = match_close(text, mask, at + len(needle) - 1)
    k = skip_ws(text, close + 1)
    if text.startswith(".await", k):
        return "awaited"
    t = text.rfind("tokio::time::timeout(", max(0, at - 400), at)
    if t >= 0 and mask[t]:
        tclose = match_close(text, mask, t + len("tokio::time::timeout(") - 1)
        after = skip_ws(text, k + 1) if text.startswith(",", k) else k
        if tclose == after and text.startswith(".await", skip_ws(text, tclose + 1)):
            return "timeout_budget"
    return "handle"


def files(crates: Path) -> list[tuple[Path, str]]:
    out = []
    for rel, repl in TARGETS.items():
        p = crates / rel
        if p.is_dir():
            out += [(f, repl) for f in sorted(p.rglob("*.rs"))]
        else:
            out.append((p, repl))
    return out


def main() -> int:
    crates = Path(sys.argv[1])
    check = "--check" in sys.argv
    list_out = sys.argv[sys.argv.index("--list") + 1] if "--list" in sys.argv else None
    converted, skipped, already = [], [], []
    for path, repl in files(crates):
        text = path.read_text(encoding="utf-8")
        mask = code_mask(text)
        spans = test_spans(text, mask)
        rel = str(path.relative_to(crates))
        for m in re.finditer(re.escape(repl), text):
            if mask[m.start()] and not any(a <= m.start() <= b for a, b in spans):
                already.append({"file": rel, "line": text.count("\n", 0, m.start()) + 1,
                                "fn": enclosing_fn(text, m.start()),
                                "shape": classify(text, mask, m.start(), repl)})
        edits = []
        for m in re.finditer(re.escape(NEEDLE), text):
            at = m.start()
            if not mask[at] or any(a <= at <= b for a, b in spans):
                continue
            row = {"file": rel, "line": text.count("\n", 0, at) + 1, "fn": enclosing_fn(text, at)}
            shape = classify(text, mask, at)
            converted.append({**row, "shape": shape})
            edits.append(at)
        if edits and not check:
            for at in reversed(edits):
                text = text[:at] + repl + text[at + len(NEEDLE):]
            path.write_text(text, encoding="utf-8")
    report = {
        "rule": "every production tokio::task::spawn_blocking( in the target files -> spawn_blocking_owned( (drop-in JoinHandle)",
        "converted_now": converted,
        "already_owned": already,
        "skipped_production": skipped,
    }
    if list_out:
        Path(list_out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"converted_now={len(converted)} already_owned={len(already)} skipped={len(skipped)}"
          + (" (check only)" if check else ""))
    return 1 if (check and converted) else 0


if __name__ == "__main__":
    sys.exit(main())
