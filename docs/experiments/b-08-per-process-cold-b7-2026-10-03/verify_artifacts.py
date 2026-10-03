#!/usr/bin/env python3
"""B-08 packet verifier (standard library only; run it under bin/hostless, from a clean clone if you like).
Derived from B-06's verify_artifacts.py (31bc98a95).

1. Recomputes the whole summary from raw/ with analyze_b08 and requires it to equal the committed
   b08-summary.json (every bootstrap is seeded: deterministic).
2. Every headline number in headline-numbers.json equals its recomputed value (by JSON path) and its README
   text appears verbatim in README.md.
3. Harness identity: the first lane commit holds B-06's files with exactly the blob ids in provenance.json;
   the files that are still unchanged copies (harness/b04/**, harness/r2-10r/r2_10_browser.py,
   harness/r2-10r/scripted-COMP.json, r10r_observation.py) keep those blobs; the B-07 copies keep the blobs in
   PREREG.json; the COMP arm line of harness/b04/run_b04.py equals R2-10R's; the routine artifact equals B-04's.
4. B-07 carry: every BELOW_GATE / IRREDUCIBLE unit label in PREREG part_E equals b07-summary.json's label on the
   same binary (c_in.prep on fill is UNTESTED here by rule).
5. Receipts: every trial record carries the PREREG binary name, sha256 and version; every measured manifest
   says hostless=1, lock exclusive, provider mock and the sha256, and lies inside an EXCLUSIVE quiet-timed ledger
   window of its own label (raw/lock-ledger.jsonl); the SHARED receipts of the pilot and the analyzer exist;
   versions logs (start, end) show cua-driver 0.32.0 and the sha256.
6. Cited files are tracked (verify_helper + every raw/ harness/ lane-scripts/ path in README/PREREG/provenance).
7. PREREG.json was committed before the first measured trial.
8. Privacy scan of EVERY lane commit (base..HEAD): blobs (tar.gz members included), paths, messages, identity
   and trailer; hex and base64 literals decoded. Private names come from the untracked file named by
   CUA_PRIVACY_NAMES_FILE plus the host name, word-boundary match.

usage: verify_artifacts.py [--base <sha>] [--skip-git]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import fnmatch
import gzip
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import analyze_b08 as A  # noqa: E402
from verify_helper import check_cited  # noqa: E402

BASE = "eab1e87a3fb35a300a5d434cd10f2cddbf9a3bb1"
FIRST_COMMIT_SUBJECT = "exp(b-08): copy B-06 harness blob-identical from 31bc98a95"
B07_SUMMARY = HERE.parent / "b-07-transport-residual-rprime-2026-10-03" / "b07-summary.json"
UNCHANGED_COPIES = ("harness/b04/", "harness/r2-10r/r2_10_browser.py", "harness/r2-10r/scripted-COMP.json",
                    "r10r_observation.py")
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"),
           re.compile(r"/Users/[A-Za-z0-9_.-]+/"), re.compile(r"/tmp/claude-[0-9]"), re.compile("/tmp/" + "dbus-")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com")}
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
HEXLIT = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-fA-F]{2}){4,}(?![0-9A-Za-z])")
B64LIT = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])")
CITE = re.compile(r"(?<![A-Za-z0-9_./-])((?:raw|harness|lane-scripts)/[A-Za-z0-9_./*-]+[A-Za-z0-9_*-])")
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True).stdout


def rel_prefix() -> str:
    top = Path(git("rev-parse", "--show-toplevel").decode().strip())
    return HERE.relative_to(top).as_posix()


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ── 1-2 summary and headlines ───────────────────────────────────────────────
def summary_and_headlines() -> dict:
    trials, mans = A.load(HERE / "raw")
    doc = json.loads(json.dumps(A.analyse_trials(trials, mans), sort_keys=True))
    committed = json.loads((HERE / "b08-summary.json").read_text())
    check("summary: recomputed from raw/ equals b08-summary.json", doc == committed, f"{len(trials)} trial records")
    readme = (HERE / "README.md").read_text()
    heads = json.loads((HERE / "headline-numbers.json").read_text())
    bad = []
    for h in heads["numbers"]:
        node = doc
        for k in h["path"]:
            node = node[k]
        if node != h["value"] or h["readme_text"] not in readme:
            bad.append(h["name"])
    check("headline numbers equal the recomputed values and appear verbatim in README.md", not bad,
          f"{len(heads['numbers'])} numbers; bad: {bad[:10]}")
    return doc


# ── 3-4 harness identity and B-07 carry ─────────────────────────────────────
def harness_identity(prereg: dict) -> None:
    prov = json.loads((HERE / "provenance.json").read_text())
    blobs = prov["copied_from_b06"]["blobs"]
    pre = rel_prefix()
    first = [c for c in git("log", "--format=%H %s", f"{BASE}..HEAD", "--", ".").decode().splitlines()
             if c.split(" ", 1)[1] == FIRST_COMMIT_SUBJECT]
    bad = []
    if len(first) != 1:
        bad.append(f"first copy commit found {len(first)} times")
    else:
        c = first[0].split()[0]
        tree = {}
        for line in git("ls-tree", "-r", "--full-tree", c).decode().splitlines():
            meta, path = line.split("\t", 1)
            if path.startswith(pre + "/"):
                tree[path[len(pre) + 1:]] = meta.split()[2]
        for rel, blob in blobs.items():
            if tree.get(rel) != blob:
                bad.append(f"first commit {rel}")
        extra = set(tree) - set(blobs) - {"provenance.json"}
        if extra:
            bad.append(f"first commit extra files {sorted(extra)}")
    for rel, blob in blobs.items():
        if not rel.startswith(UNCHANGED_COPIES):
            continue
        h = subprocess.run(["git", "hash-object", str(HERE / rel)], capture_output=True, text=True, check=True).stdout.strip()
        if h != blob:
            bad.append(f"{rel} changed")
    for rel, blob in prereg["harness"]["copied_from_b07"].items():
        h = subprocess.run(["git", "hash-object", str(HERE / rel)], capture_output=True, text=True, check=True).stdout.strip()
        if h != blob:
            bad.append(f"{rel} (B-07 copy) changed")
    check("harness: first commit = B-06 blobs; unchanged copies and B-07 copies keep their blob ids", not bad, f"{bad}")

    def comp_line(path: Path) -> str:
        lines = path.read_text().splitlines()
        i = next(k for k, x in enumerate(lines) if x.strip().startswith('"COMP": {'))
        return lines[i].strip() + " " + lines[i + 1].strip()
    a, b = comp_line(HERE / "harness/b04/run_b04.py"), comp_line(HERE / "harness/r2-10r/r2_10_browser.py")
    check("harness: run_b04 COMP arm == R2-10R r2_10_browser COMP arm", a == b, a)
    r1 = json.loads((HERE / "harness/r2-10r/scripted-COMP.json").read_text())["artifact"]
    r2 = json.loads((HERE / "harness/b04/harness/r2-10-scripted-COMP-routine.json").read_text())["artifact"]
    check("harness: R2-10R scripted COMP artifact == B-04 copy", r1 == r2, r1.get("routine_id", ""))


def b07_carry(prereg: dict) -> None:
    s7 = json.loads(B07_SUMMARY.read_text())["verdicts"]
    units = prereg["part_E"]["verdict_map"]["units"]
    bad = []
    for u, (v, _src) in units.items():
        if u == "any other lane-scope label":
            continue
        src7 = s7["units"].get(u) or s7["resolution"].get(u)
        for cls in A.CLASSES:
            mine = v[cls] if isinstance(v, dict) else v
            theirs = src7[cls]
            if u == "c_in.prep" and cls == "fill":
                if mine != "UNTESTED":
                    bad.append("c_in.prep/fill must be UNTESTED")
                continue
            if theirs == "ABSENT":
                continue
            if not theirs.startswith(mine):
                bad.append(f"{u}/{cls}: {mine} vs B-07 {theirs}")
    check("B-07 carry: PREREG unit labels equal b07-summary.json labels (same binary B7)", not bad, f"{bad}")


# ── 5 receipts ──────────────────────────────────────────────────────────────
def receipts(prereg: dict) -> None:
    sha, ver, name = prereg["binary"]["sha256"], prereg["binary"]["version"], prereg["binary"]["name"]
    trials, mans = A.load(HERE / "raw")
    bad_t = [t["summary"]["trial"] for t in trials
             if (t["summary"].get("driver_sha256"), t["summary"].get("driver_version"), t["summary"].get("driver_name"))
             != (sha, ver, name)]
    check("receipts: every trial record carries the binary name, sha256 and version", trials and not bad_t,
          f"{len(trials)} trials; bad {bad_t[:5]}")
    ledger = [json.loads(x) for x in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines() if x.strip()]
    bad = []
    for p in sorted((HERE / "raw/main").glob("run-manifest-*.json")):
        d = json.loads(p.read_text())
        if d.get("hostless") != "1" or d.get("lock_mode") != "exclusive" or d.get("provider") != "mock" \
                or d.get("driver_sha256") != sha or d.get("driver_version") != ver:
            bad.append(f"{p.name}: fields")
        lab = d.get("lock_label")
        win = [x for x in ledger if x.get("label") == lab and "cmd_sha256" in x and "mode" not in x]
        if not win or not any(utc(x["acquired"]) <= utc(d["started_utc"]) and utc(d["ended_utc"]) <= utc(x["released"])
                              for x in win):
            bad.append(f"{p.name}: not inside an EXCLUSIVE quiet-timed window of {lab}")
    n = len(list((HERE / "raw/main").glob("run-manifest-*.json")))
    check("receipts: measured manifests hostless/exclusive/mock/sha/version and inside their EXCLUSIVE ledger window",
          n > 0 and not bad, f"{n} manifests; {bad[:5]}")
    shared = {x["label"] for x in ledger if x.get("mode") == "shared"}
    need = {"b08-pilot-r00-05", "b08-analyze-final"}
    check("receipts: SHARED-lock receipts for the pilot and the final analysis", need <= shared, f"missing {sorted(need - shared)}")
    vb = []
    logs = sorted((HERE / "raw/logs").glob("versions-*.log"))
    for log in logs:
        t = log.read_text()
        if f"driver_version: {ver}" not in t or f"driver_sha256: {sha}" not in t:
            vb.append(log.name)
    check("receipts: versions logs (start, end) show the version and sha256", len(logs) >= 2 and not vb, f"{[x.name for x in logs]} {vb}")


# ── 6-7 cited files and PREREG order ────────────────────────────────────────
def cited() -> None:
    f = check_cited(HERE)
    check("cited files tracked (verify_helper: README Files + summary/headline JSON)", not f, f"{f[:10]}")
    tracked = set(git("ls-files", "--", ".").decode().split())
    bad = []
    for nm in ("README.md", "PREREG.json", "provenance.json"):
        p = HERE / nm
        if not p.exists():
            continue
        for m in CITE.findall(p.read_text()):
            m = m.rstrip(".")
            if "*" in m:
                if not any(fnmatch.fnmatchcase(t, m) for t in tracked):
                    bad.append(m)
            elif m not in tracked and not any(t.startswith(m.rstrip("/") + "/") for t in tracked):
                bad.append(m)
    check("cited raw/harness/lane-scripts paths are tracked", not bad, f"{sorted(set(bad))[:10]}")


def prereg_first() -> None:
    t_pre = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json").decode().split()
    starts = [utc(json.loads(m.read_text())["started_utc"]) for m in sorted((HERE / "raw/main").glob("run-manifest-*.json"))]
    ok = bool(t_pre and starts and datetime.fromisoformat(t_pre[-1]) < min(starts))
    check("PREREG.json committed before the first measured trial", ok,
          f"prereg {t_pre[-1] if t_pre else None}, first measured chunk {min(starts).isoformat() if starts else None}")
    ch = git("log", "--format=%H", "--", "PREREG.json").decode().split()
    check("PREREG.json never amended after its first commit (no amendment permitted)", len(ch) == 1, f"{len(ch)} commits touch it")


# ── 8 privacy ────────────────────────────────────────────────────────────────
def names() -> tuple[list[re.Pattern], str]:
    ns = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    note = "private names: CUA_PRIVACY_NAMES_FILE not set; name sub-check covers the host name only"
    if src and Path(src).is_file():
        ns |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        note = f"private names: {len(ns)} (CUA_PRIVACY_NAMES_FILE + host name), word-boundary match"
    return [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I) for n in sorted(ns)], note


def decoded_variants(text: str) -> list[str]:
    out = []
    for m in HEXLIT.finditer(text):
        try:
            s = bytes.fromhex(m.group(0)).decode("utf-8", errors="ignore")
        except ValueError:
            continue
        if sum(c.isprintable() for c in s) >= 4:
            out.append(s)
    for m in B64LIT.finditer(text):
        tok = m.group(0)
        if len(tok) % 4:
            continue
        try:
            s = base64.b64decode(tok, validate=True).decode("utf-8", errors="ignore")
        except (binascii.Error, ValueError):
            continue
        if sum(c.isprintable() for c in s) >= 4:
            out.append(s)
    return out


def texts_of_blob(path: str, data: bytes) -> list[tuple[str, str]]:
    out = [(path, data.decode("utf-8", errors="replace"))]
    if path.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for m in tar.getmembers():
                out.append((f"{path}:{m.name}", m.name))
                if m.isfile():
                    raw = tar.extractfile(m).read()
                    if m.name.endswith(".gz"):
                        raw = gzip.decompress(raw)
                    out.append((f"{path}:{m.name}", raw.decode("utf-8", errors="replace")))
    elif path.endswith(".gz"):
        out.append((path + ":gunzip", gzip.decompress(data).decode("utf-8", errors="replace")))
    return out


def privacy_scan(base: str) -> None:
    private, note = names()
    pats = GENERIC + private
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits, secret_hits, bad_ident, blobs = [], [], [], 0
    for c in commits:
        meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            bad_ident.append(c[:9])
        if TRAILER not in meta[4]:
            bad_ident.append(f"{c[:9]} trailer")
        targets = [("commit-message", meta[4])]
        parents = git("show", "-s", "--format=%P", c).decode().split()
        diff = git("diff-tree", "-r", "--no-commit-id", "--no-renames", parents[0] if parents else "--root", c).decode()
        for line in diff.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            fields, path = parts[0].split(), parts[1]
            targets.append(("path", path))
            if fields[4] == "D":
                continue
            blobs += 1
            targets.extend(texts_of_blob(path, git("cat-file", "blob", fields[3])))
        for where, text in targets:
            variants = [text] + decoded_variants(text)
            for i, pat in enumerate(pats):
                if any(pat.search(v) for v in variants):
                    hits.append(f"{c[:9]} {where[:120]} private#{i}")
            for i, pat in enumerate(SECRET):
                if any(pat.search(v) for v in variants):
                    secret_hits.append(f"{c[:9]} {where[:120]} secret#{i}")
    check("privacy: no absolute local paths / session-bus paths / host or user names in any commit (hex/base64 decoded)",
          not hits, f"{len(commits)} commits, {blobs} blobs; {note}; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: author/committer identity and trailer", not bad_ident, f"bad: {bad_ident[:10]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-git", action="store_true")
    a = ap.parse_args()
    prereg = json.loads((HERE / "PREREG.json").read_text())
    summary_and_headlines()
    harness_identity(prereg)
    b07_carry(prereg)
    receipts(prereg)
    if not a.skip_git:
        cited()
        prereg_first()
        privacy_scan(a.base)
    width = max(len(n) for n, _, _ in CHECKS)
    for n, ok, d in CHECKS:
        print(f"{'PASS' if ok else 'FAIL'}  {n.ljust(width)}  {d[:300]}")
    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
