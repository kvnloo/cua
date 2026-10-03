#!/usr/bin/env python3
"""PUB-04 scripted redaction rewrite of an unpublished branch's own commits (standard library only).

usage: pub04_redact.py <repo> <packet-rel> <map-out.json> <orig commit>...      (oldest first; under bin/hostless)

The patterns come from the untracked file named by CUA_REDACT_PATTERNS_FILE, one JSON object per line
{"class", "regex", "placeholder", "flags"}; this file holds no pattern literal and never prints a matched value.
Each commit is rebuilt with git plumbing (read-tree into a private index, update-index --cacheinfo,
write-tree, commit-tree) onto the rebuilt parent:
  - every blob under <packet-rel> in the commit's full tree is redacted (text blobs; a .gz single member
    is rewritten with the packet writer settings after a byte-identical round trip; a hit inside a
    tar.gz member or a binary blob aborts);
  - a changed blob outside <packet-rel> with a hit aborts (the lane only rewrites its own packet);
  - manifests: every blob under <packet-rel> is searched for the old sha256 and old git blob id (full and
    12-char prefix) of each redacted file; a raw/MANIFEST.json entry is updated in place, any other
    reference aborts. The references found are recorded per file (an empty list = no manifest entry);
  - the commit message is redacted with the same patterns (count recorded).
Per commit, "files" lists every redacted blob of its tree; "introduced_here" marks the ones the commit
adds or changes (the others are inherited from the rewritten parent).
Author name/email/date are kept; the committer is Kevin Rajan; a rewrite note goes before the
Co-Authored-By trailer. A commit whose tree, parent and message are unchanged is reused.
Writes JSON per commit: {orig, new, files: [{path, count, by_class, old_blob, new_blob, old_sha256,
new_sha256, manifest_refs}], message_count, manifest}.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

COAUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PRINTABLE = re.compile(rb"[\x20-\x7e]{6,}")


def git(repo: str, *args: str, inp=None, env=None, text=True):
    r = subprocess.run(["git", "-C", repo, *args], input=inp, capture_output=True, check=True, env=env, text=text)
    return r.stdout


def blob(repo: str, sha: str) -> bytes:
    return subprocess.run(["git", "-C", repo, "cat-file", "blob", sha], capture_output=True, check=True).stdout


def gz_write(member_path: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename=Path(member_path).name, mode="wb", compresslevel=9, fileobj=buf, mtime=0) as s:
        s.write(data)
    return buf.getvalue()


class Patterns:
    def __init__(self, path: str) -> None:
        self.rows = []
        for line in Path(path).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                flags = re.I if "i" in r.get("flags", "") else 0
                self.rows.append((r["class"], re.compile(r["regex"], flags), r["placeholder"]))
        if not self.rows:
            raise SystemExit("abort: empty pattern file")

    def classes(self) -> list[str]:
        return [c for c, _, _ in self.rows]

    def sub(self, text: str) -> tuple[str, dict[str, int]]:
        by: dict[str, int] = {}
        for cls, pat, ph in self.rows:
            text, n = pat.subn(ph, text)
            if n:
                by[cls] = by.get(cls, 0) + n
        return text, by

    def hits(self, text: str) -> int:
        return sum(len(p.findall(text)) for _, p, _ in self.rows)


def redact_blob(pats: Patterns, path: str, data: bytes) -> tuple[bytes, dict[str, int]]:
    if path.endswith(".gz"):
        plain = gzip.decompress(data)
        if path.endswith((".tar.gz", ".tgz")):
            if pats.hits(plain.decode("latin-1")):
                raise SystemExit(f"abort: tar.gz member redaction is not implemented ({path})")
            return data, {}
        text = plain.decode("utf-8", errors="replace")
        if not pats.hits(text):
            return data, {}
        if gz_write(path, plain) != data:
            raise SystemExit(f"abort: gzip writer is not byte-identical on the original {path}")
        new, by = pats.sub(plain.decode("utf-8"))
        return gz_write(path, new.encode("utf-8")), by
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if any(pats.hits(m.group().decode("ascii")) for m in PRINTABLE.finditer(data)):
            raise SystemExit(f"abort: hit in a binary blob ({path})")
        return data, {}
    new, by = pats.sub(text)
    return (new.encode("utf-8") if by else data), by


def update_manifest(text: str, changes: dict[str, bytes]) -> tuple[str, list[str]]:
    want = json.loads(text)
    done = []
    for key, data in sorted(changes.items()):
        if key not in want:
            continue
        old = want[key]
        sha, size = hashlib.sha256(data).hexdigest(), len(data)
        block = re.compile(r'("' + re.escape(key) + r'": \{\s*"bytes": )' + str(old["bytes"]) +
                           r'(,\s*"sha256": ")' + old["sha256"] + '"')
        text, n = block.subn(lambda m: m.group(1) + str(size) + m.group(2) + sha + '"', text)
        if n != 1:
            raise SystemExit(f"abort: manifest entry layout for {key} not found exactly once")
        want[key] = dict(old, bytes=size, sha256=sha)
        done.append(key)
    if json.loads(text) != want:
        raise SystemExit("abort: manifest text update does not equal the intended JSON")
    return text, done


def fold(s: str, w: int = 100) -> str:
    lines, cur = [], ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > w:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return "\n".join(lines + ([cur] if cur else []))


def main() -> None:
    repo, packet, mapout = sys.argv[1:4]
    pats = Patterns(os.environ["CUA_REDACT_PATTERNS_FILE"])
    commits = [git(repo, "rev-parse", c + "^{commit}").strip() for c in sys.argv[4:]]
    cache: dict[tuple[str, str], tuple[str, dict]] = {}
    out = []
    parent = git(repo, "rev-parse", commits[0] + "^").strip()
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as work:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(work) / "index"))
        for orig in commits:
            oparent = git(repo, "rev-parse", orig + "^").strip()
            changed = git(repo, "diff-tree", "-r", "-z", "--no-commit-id", "--no-renames", "--diff-filter=AM",
                          oparent, orig).split("\0")
            introduced = {path for meta, path in zip(changed[0::2], changed[1::2]) if meta}
            for meta, path in zip(changed[0::2], changed[1::2]):
                if meta and not path.startswith(packet + "/"):
                    if redact_blob(pats, path, blob(repo, meta.split()[3]))[1] or pats.hits(path):
                        raise SystemExit(f"abort: hit outside the packet ({path})")
            git(repo, "read-tree", orig, env=env)
            files, ptree = [], {}
            for entry in filter(None, git(repo, "ls-tree", "-r", "-z", orig, "--", packet).split("\0")):
                meta, path = entry.split("\t", 1)
                mode, typ, sha = meta.split()
                if typ != "blob":
                    continue
                if pats.hits(path):
                    raise SystemExit(f"abort: hit in a path name ({path})")
                ptree[path] = sha
                if (sha, path) not in cache:
                    data = blob(repo, sha)
                    new, by = redact_blob(pats, path, data)
                    nsha = git(repo, "hash-object", "-w", "--stdin", inp=new, text=False).decode().strip() if by else sha
                    cache[(sha, path)] = (nsha, by)
                nsha, by = cache[(sha, path)]
                if by:
                    git(repo, "update-index", "--cacheinfo", f"{mode},{nsha},{path}", env=env)
                    old_data, new_data = blob(repo, sha), blob(repo, nsha)
                    files.append({"path": path[len(packet) + 1:], "count": sum(by.values()), "by_class": by,
                                  "old_blob": sha, "new_blob": nsha,
                                  "old_sha256": hashlib.sha256(old_data).hexdigest(),
                                  "new_sha256": hashlib.sha256(new_data).hexdigest(), "manifest_refs": [],
                                  "introduced_here": path in introduced})
            # manifest references to the old content of each redacted file
            needles = {f["path"]: [f["old_sha256"], f["old_blob"], f["old_sha256"][:12], f["old_blob"][:12]]
                       for f in files}
            for path, sha in ptree.items():
                if not files or path.endswith((".gz", ".tgz")):
                    continue
                text = blob(repo, sha).decode("utf-8", errors="replace")
                for f in files:
                    if any(n in text for n in needles[f["path"]]):
                        f["manifest_refs"].append(path[len(packet) + 1:])
            manifest = None
            mpath = f"{packet}/raw/MANIFEST.json"
            other = sorted({r for f in files for r in f["manifest_refs"]} - {"raw/MANIFEST.json"})
            if other:
                raise SystemExit(f"abort: redacted content referenced by a non-manifest file: {other}")
            if any(f["manifest_refs"] for f in files):
                mold = ptree[mpath]
                rel = {f["path"][4:]: blob(repo, f["new_blob"]) for f in files if f["path"].startswith("raw/")}
                mnew_text, done = update_manifest(blob(repo, mold).decode(), rel)
                mnew = git(repo, "hash-object", "-w", "--stdin", inp=mnew_text).strip()
                git(repo, "update-index", "--cacheinfo", f"100644,{mnew},{mpath}", env=env)
                manifest = {"path": "raw/MANIFEST.json", "entries_updated": len(done), "old_blob": mold, "new_blob": mnew}
            tree = git(repo, "write-tree", env=env).strip()
            otree = git(repo, "rev-parse", orig + "^{tree}").strip()
            msg = git(repo, "log", "-1", "--format=%B", orig)
            body = "\n".join(x for x in msg.rstrip("\n").splitlines() if not x.startswith("Co-Authored-By: ")).rstrip()
            body, mby = pats.sub(body)
            if tree == otree and parent == oparent and not mby:
                out.append({"orig": orig, "new": orig, "files": [], "message_count": 0, "manifest": None, "reused": True})
                parent = orig
                continue
            own = [f for f in files if f["introduced_here"]]
            classes = sorted({c for f in own for c in f["by_class"]} | set(mby))
            if own or mby:
                note = (f"PUB-04 privacy rewrite (2026-10-03) of {orig[:9]}: {sum(f['count'] for f in own)} "
                        f"redaction(s) ({', '.join(classes)}) in {len(own)} packet file(s) this commit adds or changes"
                        f"{' and the commit message' if mby else ''}"
                        f"{' and the matching raw/MANIFEST.json entries' if manifest else ''}, each replaced by a "
                        f"placeholder token. Author date kept; every other byte of the tree is identical to {orig[:9]}.")
            else:
                note = (f"PUB-04 privacy rewrite (2026-10-03) of {orig[:9]}: re-parented onto the redacted history. "
                        f"Author date kept; the tree differs from {orig[:9]} only by the redaction it inherits.")
            newmsg = f"{body}\n\n{fold(note)}\n\n{COAUTHOR}\n"
            fmt = git(repo, "log", "-1", "--format=%an%x00%ae%x00%aI", orig).rstrip("\n").split("\0")
            cenv = dict(os.environ, GIT_AUTHOR_NAME=fmt[0], GIT_AUTHOR_EMAIL=fmt[1], GIT_AUTHOR_DATE=fmt[2],
                        GIT_COMMITTER_NAME="Kevin Rajan", GIT_COMMITTER_EMAIL="7121943+kvnloo@users.noreply.github.com")
            new = git(repo, "commit-tree", tree, "-p", parent, "-F", "-", inp=newmsg, env=cenv).strip()
            out.append({"orig": orig, "new": new, "files": files, "message_count": sum(mby.values()),
                        "manifest": manifest, "reused": False, "author_date": fmt[2]})
            parent = new
    Path(mapout).write_text(json.dumps({"tool": "pub04_redact.py", "pattern_classes": sorted(set(pats.classes())),
                                        "packet": packet, "commits": out}, indent=1) + "\n")
    for r in out:
        print(r["orig"][:12], r["new"][:12], f"files={len(r['files'])} count={sum(f['count'] for f in r['files'])}"
              f" message={r['message_count']} manifest={'yes' if r['manifest'] else 'no'}"
              f" manifest_refs={sum(len(f['manifest_refs']) for f in r['files'])}")


if __name__ == "__main__":
    main()
