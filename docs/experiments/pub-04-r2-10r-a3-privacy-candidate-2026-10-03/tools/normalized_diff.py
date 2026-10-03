#!/usr/bin/env python3
"""PUB-04 normalized diff: a rewritten tree equals its published original except for redactions (stdlib only).

usage: normalized_diff.py <repo> <out.json> <published>:<candidate>[:<allowed added path>,...] ...
       (run under bin/hostless; CUA_REDACT_PATTERNS_FILE optional, see check 1)

For each pair the full trees are compared path by path (ls-tree -r):
  - a path only in the published tree fails; a path only in the candidate fails unless it is listed as an
    allowed addition (the rewrite note);
  - a path with the same blob id is byte-identical;
  - a path with different blobs must pass both checks below.
Check 1 (masked equality, needs CUA_REDACT_PATTERNS_FILE): the published bytes with every redaction pattern
  applied equal the candidate bytes exactly, the candidate bytes have 0 pattern hits, and (completeness)
  no path name or blob under docs/experiments/ (CUA_DIFF_SCOPE) in the candidate tree has a pattern hit,
  read with the scanner's text rules (gzip/tar.gz members decompressed, binary blobs as printable runs).
  Images and other binary assets elsewhere in the repository are upstream content and out of scope.
Check 2 (pattern-free, needs no private input): the candidate text is cut at each placeholder token
  (<session-bus>, <home>, <mount>, <user>, <host>, <name>); the published text must equal the candidate
  outside those spans (each span: one or more characters, no newline). It reports how many spans hold a
  value different from the placeholder (= redactions). It proves "no other change" but not completeness:
  a file left unredacted is byte-identical to the published one and passes it (the scanner covers that).
Manifest entries are ordinary paths here: a changed manifest must pass the same checks only if its change
is a redaction; any other change fails (this candidate changes no manifest).
For a rewritten commit pair it also checks author name, email and date are equal and that the published
message body (Co-Authored-By trailer removed) is a prefix of the candidate message.
Writes JSON with per-path rows (blob ids, counts; never a redacted value) and per-pair gates.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_helper import blob_texts  # noqa: E402

SCOPE = os.environ.get("CUA_DIFF_SCOPE", "docs/experiments/")
PLACEHOLDERS = ["<session-bus>", "<home>", "<mount>", "<user>", "<host>", "<name>"]
PH = re.compile("|".join(re.escape(p) for p in PLACEHOLDERS))


def git(repo: str, *args: str, text: bool = True):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True, text=text).stdout


def tree(repo: str, rev: str) -> dict[str, str]:
    out = {}
    for entry in filter(None, git(repo, "ls-tree", "-r", "-z", rev).split("\0")):
        meta, path = entry.split("\t", 1)
        out[path] = meta.split()[2]
    return out


def load_patterns() -> list[tuple[re.Pattern, str]] | None:
    src = os.environ.get("CUA_REDACT_PATTERNS_FILE", "")
    if not src or not Path(src).is_file():
        return None
    rows = []
    for line in Path(src).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            rows.append((re.compile(r["regex"], re.I if "i" in r.get("flags", "") else 0), r["placeholder"]))
    return rows


def split_check(old: str, new: str) -> tuple[bool, int, int]:
    """(published equals candidate outside placeholder spans, spans, spans whose value differs)."""
    parts = PH.split(new)
    if len(parts) == 1:
        return old == new, 0, 0
    rx = re.compile("".join(re.escape(p) + ("([^\n]+?)" if i < len(parts) - 1 else "") for i, p in enumerate(parts)), re.S)
    m = rx.fullmatch(old)
    if not m:
        return False, len(parts) - 1, -1
    spans = list(m.groups())
    placeholders = PH.findall(new)
    return True, len(spans), sum(1 for s, p in zip(spans, placeholders) if s != p)


def compare(repo: str, a: str, b: str, allowed: list[str], pats) -> dict:
    ta, tb = tree(repo, a), tree(repo, b)
    rows, identical = [], 0
    removed = sorted(set(ta) - set(tb))
    added = sorted(set(tb) - set(ta))
    for path in sorted(set(ta) & set(tb)):
        if ta[path] == tb[path]:
            identical += 1
            continue
        old = git(repo, "cat-file", "blob", ta[path], text=False).decode("utf-8")
        new = git(repo, "cat-file", "blob", tb[path], text=False).decode("utf-8")
        row = {"path": path, "old_blob": ta[path], "new_blob": tb[path]}
        ok2, spans, differing = split_check(old, new)
        row.update(split_equal=ok2, placeholder_spans=spans, redactions_by_split=differing)
        if pats is not None:
            masked = old
            for pat, ph in pats:
                masked = pat.sub(ph, masked)
            row["masked_equal"] = masked == new
            row["candidate_pattern_hits"] = sum(len(p.findall(new)) for p, _ in pats)
        rows.append(row)
    tree_hits, res_scope = None, None
    if pats is not None:  # completeness: no pattern hit left in the experiment packets of the candidate tree
        scope = sorted((p, s) for p, s in tb.items() if p.startswith(SCOPE))
        blobs = sorted({s for _, s in scope})
        batch = subprocess.run(["git", "-C", repo, "cat-file", "--batch"], input=("\n".join(blobs) + "\n").encode(),
                               capture_output=True, check=True).stdout
        pos, data_of = 0, {}
        for sha in blobs:
            header_end = batch.index(b"\n", pos)
            size = int(batch[pos:header_end].split()[2])
            data_of[sha] = batch[header_end + 1:header_end + 1 + size]
            pos = header_end + 1 + size + 1
        tree_hits = []
        for path, sha in scope:  # the scanner's text rules: gzip/tar members decompressed, binary = printable runs
            n = sum(len(p.findall(t)) for _, t in blob_texts(path, data_of[sha]) for p, _ in pats)
            n += sum(len(p.findall(path)) for p, _ in pats)
            if n:
                tree_hits.append({"path": path, "hits": n})
        res_scope = {"prefix": SCOPE, "paths": len(scope)}
    bad_added = [p for p in added if p not in allowed]
    gates = {
        "no_path_removed": not removed,
        "only_allowed_paths_added": not bad_added,
        "every_differing_path_split_equal": all(r["split_equal"] for r in rows),
    }
    if pats is not None:
        gates["every_differing_path_masked_equal"] = all(r["masked_equal"] for r in rows)
        gates["candidate_has_0_pattern_hits_in_differing_paths"] = all(r["candidate_pattern_hits"] == 0 for r in rows)
        gates["candidate_tree_has_0_pattern_hits"] = not tree_hits
    res = {"published": git(repo, "rev-parse", a).strip(), "candidate": git(repo, "rev-parse", b).strip(),
           "paths_published": len(ta), "paths_candidate": len(tb), "identical_paths": identical,
           "differing_paths": len(rows), "redactions": sum(max(r["redactions_by_split"], 0) for r in rows),
           "added": added, "removed": removed, "completeness_scope": res_scope, "candidate_tree_pattern_hits": tree_hits, "rows": rows}
    meta_a = git(repo, "log", "-1", "--format=%an%x00%ae%x00%aI%x00%B", a).split("\0")
    meta_b = git(repo, "log", "-1", "--format=%an%x00%ae%x00%aI%x00%B", b).split("\0")
    body_a = "\n".join(x for x in meta_a[3].rstrip("\n").splitlines() if not x.startswith("Co-Authored-By: ")).rstrip()
    if not allowed:  # a rewritten commit pair (not the note layer)
        gates["author_name_email_date_equal"] = meta_a[:3] == meta_b[:3]
        gates["published_message_is_prefix"] = meta_b[3].startswith(body_a + "\n\n")
    res["gates"] = gates
    res["pass"] = all(gates.values())
    return res


def main() -> None:
    repo, out = sys.argv[1], Path(sys.argv[2])
    pats = load_patterns()
    pairs = []
    for spec in sys.argv[3:]:
        a, b, *rest = spec.split(":")
        allowed = rest[0].split(",") if rest and rest[0] else []
        pairs.append(compare(repo, a, b, allowed, pats))
    doc = {"tool": "normalized_diff.py", "masked_check": pats is not None, "placeholders": PLACEHOLDERS,
           "pairs": pairs, "pass": all(p["pass"] for p in pairs)}
    out.write_text(json.dumps(doc, indent=1) + "\n")
    for p in pairs:
        print(p["published"][:12], "->", p["candidate"][:12], f"paths={p['paths_published']}/{p['paths_candidate']}",
              f"identical={p['identical_paths']} differing={p['differing_paths']} redactions={p['redactions']}",
              f"added={len(p['added'])} removed={len(p['removed'])}", "PASS" if p["pass"] else f"FAIL {p['gates']}")
    print("normalized diff:", "PASS" if doc["pass"] else "FAIL", f"(masked check {'run' if pats else 'not run'})")
    sys.exit(0 if doc["pass"] else 1)


if __name__ == "__main__":
    main()
