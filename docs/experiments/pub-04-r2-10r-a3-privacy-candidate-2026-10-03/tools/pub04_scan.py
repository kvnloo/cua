#!/usr/bin/env python3
"""PUB-04 per-commit privacy scan (the PUB-03 scanner, committed). Run under bin/hostless.

Extends the template PrivacyScanner (verify_helper.py, PUB-02 copy) with:
  tmp-dbus      a /tmp/dbus-<id> session-bus socket path (plain, url-decoded, hex/base64-decoded)
  url-encoded   percent-encoded private names and url-encoded absolute local roots / home paths
Every commit: its message and author/committer identity, every added/modified path name (plain and
hex/base64-decoded) and blob (gzip and tar.gz members decompressed in memory, tar member names included).
Every finding records class, commit, file (where), a tag and an occurrence count; never a matched value.

usage:
  pub04_scan.py range  <out.json> <label> <rev-list args...>
  pub04_scan.py census <out.json> <heads-file: "branch tip" per line>
Set CUA_PRIVACY_NAMES_FILE to the untracked names file and CUA_SCAN_REPO to the repository (default:
the repository of the current directory). PUB-04 import changes from PUB-03: the repository comes from
the environment (no committed local path) and the commit identity is scanned with the message.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_helper import GENERIC_PATH, PrivacyScanner, SECRET, decoded_texts, encoded_list  # noqa: E402

DBUS = re.compile(r"/tmp/dbus-[A-Za-z0-9_]+")
PRIVATE = {"plain-name", "user-name-in-raw", "encoded-name", "encoded-list", "abs-path", "tmp-dbus", "url-encoded"}
CLASSES = ["plain-name", "user-name-in-raw", "encoded-name", "url-encoded", "encoded-list", "abs-path",
           "tmp-dbus", "abs-path-generic", "secret-like"]


class Scanner(PrivacyScanner):
    def __init__(self, repo: Path) -> None:
        super().__init__(repo)
        self.url = []
        for i, (role, name) in enumerate(self.names):
            raw = name.encode()
            for fmt in ("%{:02x}", "%{:02X}"):
                enc = "".join(fmt.format(b) for b in raw)
                self.url.append((f"name#{i}({role})", re.compile(re.escape(enc), re.I)))

    def _abs_n(self, text: str) -> tuple[str | None, int]:
        n = sum(len(p.findall(text)) for p in self.roots)
        if n:
            return "local-root", n
        g = len(GENERIC_PATH.findall(text))
        return ("generic", g) if g else (None, 0)

    def scan_text(self, where: str, text: str, in_raw: bool = False) -> list[dict]:
        hits: dict[tuple[str, str], int] = {}

        def add(kind: str, tag: str, n: int = 1) -> None:
            hits[(kind, tag)] = hits.get((kind, tag), 0) + n

        for tag, role, pat in self.plain:
            n = len(pat.findall(text))
            if n:
                add("user-name-in-raw" if role == "user" and in_raw else "plain-name", tag, n)
        kind, n = self._abs_n(text)
        if kind:
            add("abs-path" if kind == "local-root" else "abs-path-generic", kind, n)
        n = len(DBUS.findall(text))
        if n:
            add("tmp-dbus", "plain", n)
        for i, pat in enumerate(SECRET):
            n = len(pat.findall(text))
            if n:
                add("secret-like", f"secret#{i}", n)
        for tag, pat in self.encoded:
            n = len(pat.findall(text))
            if n:
                add("encoded-name", f"{tag} encoded", n)
        for tag, pat in self.url:
            n = len(pat.findall(text))
            if n:
                add("url-encoded", f"{tag} percent", n)
        if "%" in text:
            dec = unquote(text)
            if dec != text:
                for tag, _, pat in self.plain:
                    extra = len(pat.findall(dec)) - len(pat.findall(text))
                    if extra > 0:
                        add("url-encoded", f"{tag} url-decoded", extra)
                kd, nd = self._abs_n(dec)
                ka, na = self._abs_n(text)
                if kd == "local-root" and nd > (na if ka == "local-root" else 0):
                    add("url-encoded", "local-root url-decoded", nd - (na if ka == "local-root" else 0))
                extra = len(DBUS.findall(dec)) - len(DBUS.findall(text))
                if extra > 0:
                    add("tmp-dbus", "url-decoded", extra)
        for dec in decoded_texts(text):
            for tag, _, pat in self.plain:
                n = len(pat.findall(dec))
                if n:
                    add("encoded-name", f"{tag} decoded", n)
            kd, nd = self._abs_n(dec)
            if kd == "local-root":
                add("abs-path", "local-root decoded", nd)
            n = len(DBUS.findall(dec))
            if n:
                add("tmp-dbus", "decoded", n)
        if encoded_list(text):
            add("encoded-list", ">=2 encoded name-like literals")
        safe = self.redact(where)
        return [{"kind": k, "where": safe, "detail": d, "n": n} for (k, d), n in sorted(hits.items())]


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def scan_commits(repo: str, args: list[str], sc: Scanner, cache: dict) -> tuple[list[str], list[dict]]:
    commits = git(repo, "rev-list", "--reverse", *args).split()
    out = []
    for c in commits:
        found = sc.scan_text("<commit message>", git(repo, "log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B", c))
        parents = git(repo, "rev-list", "--parents", "-n", "1", c).split()[1:]
        diff = git(repo, "diff-tree", "-r", "-z", "--no-commit-id", "--no-renames", "--diff-filter=AM",
                   parents[0] if parents else "--root", c).split("\0")
        for meta, path in zip(diff[0::2], diff[1::2]):
            if not meta:
                continue
            sha = meta.split()[3]
            if (sha, path) not in cache:
                data = subprocess.run(["git", "-C", repo, "cat-file", "blob", sha], capture_output=True).stdout
                cache[(sha, path)] = sc.scan_blob(path, data)
            found += cache[(sha, path)]
        out += [dict(f, commit=c[:12]) for f in found]
    return commits, out


def row_for(label: str, args: list[str], repo: str, sc: Scanner, cache: dict, upstream: str) -> dict:
    commits, findings = scan_commits(repo, args, sc, cache)
    counts: dict[str, dict] = {}
    for f in findings:
        c = counts.setdefault(f["kind"], {"findings": 0, "occurrences": 0})
        c["findings"] += 1
        c["occurrences"] += f["n"]
    first: dict[str, str] = {}
    for f in findings:  # findings are in commit order (oldest first)
        if f["kind"] in PRIVATE:
            first.setdefault(f["kind"], f["commit"])
    priv = [f for f in findings if f["kind"] in PRIVATE]
    per_commit = []
    for c in commits:
        k: dict[str, int] = {}
        for f in findings:
            if f["commit"] == c[:12]:
                k[f["kind"]] = k.get(f["kind"], 0) + 1
        per_commit.append({"commit": c, "private": sum(v for kk, v in k.items() if kk in PRIVATE), "counts": k})
    return {"per_commit": per_commit, "branch": label, "rev_list": " ".join(args).replace(upstream, "upstream/main"),
            "commits_scanned": len(commits), "tip": git(repo, "rev-parse", args[0]).strip(),
            "counts": counts, "private_findings": len(priv), "first_offending_commit": first,
            "private_detail": [{k: f[k] for k in ("kind", "commit", "where", "detail", "n")} for f in priv]}


def main() -> None:
    mode, out = sys.argv[1], Path(sys.argv[2])
    repo = os.environ.get("CUA_SCAN_REPO") or git(".", "rev-parse", "--show-toplevel").strip()
    upstream = git(repo, "rev-parse", "upstream/main").strip()
    sc = Scanner(Path(repo))
    cache: dict = {}
    meta = {"scanner": "PUB-04 pub04_scan.py (PUB-03 extension of verify_helper.PrivacyScanner)", "names_note": sc.note(),
            "upstream_main_local_ref": upstream, "classes": CLASSES,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rows = []
    if mode == "range":
        rows.append(row_for(sys.argv[3], sys.argv[4:], repo, sc, cache, upstream))
    else:
        for line in Path(sys.argv[3]).read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            name, tip = line.split()[:2]
            rows.append(row_for(name, [tip, "--not", upstream], repo, sc, cache, upstream))
            r = rows[-1]
            print(f"{name} commits={r['commits_scanned']} private={r['private_findings']} "
                  f"{ {k: v['findings'] for k, v in r['counts'].items()} }", flush=True)
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out.write_text(json.dumps(dict(meta, rows=rows), indent=1) + "\n")
    if mode == "range":
        r = rows[0]
        print(f"{r['branch']} commits={r['commits_scanned']} private={r['private_findings']} "
              f"{ {k: (v['findings'], v['occurrences']) for k, v in r['counts'].items()} }")


if __name__ == "__main__":
    main()
