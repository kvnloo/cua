#!/usr/bin/env python3
"""B-06 packet verifier (standard library only; run it under bin/hostless).

1. Recomputes the whole summary from raw/ with analyze_b06.analyse and requires it to equal the committed
   b06-summary.json (every bootstrap is seeded: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value (by its JSON path
   in the summary) and its README text to appear verbatim in README.md.
3. Harness identity: every copied harness file has the git blob hash PREREG.json records; the COMP arm line
   of harness/b04/run_b04.py equals the COMP line of R2-10R's harness/r2-10r/r2_10_browser.py; the R2-10R
   routine artifact equals B-04's copy.
4. Receipts: every trial record carries the PREREG binary sha256; every measured manifest says
   hostless=1, lock exclusive, provider mock; every measured manifest lies inside an EXCLUSIVE quiet-timed
   ledger window of its own label (raw/lock-ledger.jsonl); versions logs show cua-driver 0.32.0 and the sha256.
5. Cited files: verify_helper.check_cited (README Files section + summary/headline JSON) and every raw/ or
   harness/ path in README.md, PREREG.json and provenance.json must be tracked by git.
6. PREREG.json was committed before the first measured trial (first commit time < first manifest start).
7. Privacy-scans EVERY commit of the branch (base..HEAD): every added/modified blob (tar.gz members
   included), path, commit message and identity: no absolute home/mount/tmp paths, no host or user name,
   no secret-like values; hex and base64 literals are decoded and scanned too. Private names are never
   committed: they come from the untracked file named by CUA_PRIVACY_NAMES_FILE plus the host name, and
   match on word boundaries (the public fork handle that merely starts with a short user name is not a hit).

usage: verify_artifacts.py [--base <sha>] [--skip-git]
"""

from __future__ import annotations

import argparse
import base64
import binascii
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
import analyze_b06 as A  # noqa: E402
from verify_helper import check_cited  # noqa: E402

BASE = "45dff8f3227a21ff8bef1af4bf4c2bcbd9449b2a"
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"),
           re.compile(r"/Users/[A-Za-z0-9_.-]+/"), re.compile(r"/tmp/claude-[0-9]")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com")}
HEXLIT = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-fA-F]{2}){4,}(?![0-9A-Za-z])")
B64LIT = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])")
CITE = re.compile(r"(?<![A-Za-z0-9_./-])((?:raw|harness|lane-scripts)/[A-Za-z0-9_./*-]+[A-Za-z0-9_*-])")
# Paths of OTHER packets that PREREG/README/provenance quote by their packet-relative name (never this packet's files).
EXTERNAL_CITES = {
    "harness/r2_10_browser.py": "R2-10R packet (c183b95e3); copied here as harness/r2-10r/r2_10_browser.py",
    "raw/browser/scripted-routines": "R2-10R packet (c183b95e3); routine copied here as harness/r2-10r/scripted-COMP.json",
    "raw/browser/scripted-trials.tar.gz": "R2-10R packet (c183b95e3); re-analysed, not copied (sha256 in raw/r10r-observation-rows.json)",
}
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True).stdout


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
            b = bytes.fromhex(m.group(0))
        except ValueError:
            continue
        s = b.decode("utf-8", errors="ignore")
        if sum(c.isprintable() for c in s) >= 4:
            out.append(s)
    for m in B64LIT.finditer(text):
        tok = m.group(0)
        if len(tok) % 4:
            continue
        try:
            b = base64.b64decode(tok, validate=True)
        except (binascii.Error, ValueError):
            continue
        s = b.decode("utf-8", errors="ignore")
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
            bad_ident.append(f"{c[:9]}")
        if "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" not in meta[4]:
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
    check("privacy: no absolute local paths / host or user names in any commit (hex/base64 decoded)", not hits,
          f"{len(commits)} commits, {blobs} blobs; {note}; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: author/committer identity and trailer", not bad_ident, f"bad: {bad_ident[:10]}")


def harness_identity(prereg: dict) -> None:
    bad = []
    for rel, meta in prereg["harness"]["copied_blob_identical"].items():
        p = HERE / rel
        if not p.is_file():
            bad.append(f"missing {rel}")
            continue
        h = subprocess.run(["git", "hash-object", str(p)], capture_output=True, text=True, check=True).stdout.strip()
        if h != meta["blob"]:
            bad.append(f"{rel} {h[:9]} != {meta['blob'][:9]}")
    check("harness: copied files are blob-identical to their sources (PREREG blobs)", not bad, f"{bad}")

    def comp_line(path: Path) -> str:
        lines = path.read_text().splitlines()
        i = next(k for k, x in enumerate(lines) if x.strip().startswith('"COMP": {'))
        return (lines[i].strip() + " " + lines[i + 1].strip())
    a, b = comp_line(HERE / "harness/b04/run_b04.py"), comp_line(HERE / "harness/r2-10r/r2_10_browser.py")
    check("harness: run_b04 COMP arm == R2-10R r2_10_browser COMP arm", a == b, a)
    r1 = json.loads((HERE / "harness/r2-10r/scripted-COMP.json").read_text())["artifact"]
    r2 = json.loads((HERE / "harness/b04/harness/r2-10-scripted-COMP-routine.json").read_text())["artifact"]
    check("harness: R2-10R scripted COMP artifact == B-04 copy", r1 == r2, r1.get("routine_id", ""))


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def receipts(prereg: dict) -> None:
    sha = prereg["binary"]["sha256"]
    rows = A.load(HERE / "raw/main-trials.tar.gz") + A.load(HERE / "raw/wn-trials.tar.gz") + A.load(HERE / "raw/x-trials.tar.gz")
    check("receipts: every trial record carries the PREREG binary sha256",
          all(r["driver_sha256"] == sha for r in rows), f"{len(rows)} trials")
    ledger = [json.loads(x) for x in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines() if x.strip()]
    mans = sorted((HERE / "raw").glob("*/run-manifest-*.json"))
    measured = [m for m in mans if not m.parent.name.startswith("pilot")]
    bad = []
    for m in measured:
        d = json.loads(m.read_text())
        if d.get("hostless") != "1" or d.get("lock_mode") != "exclusive" or d.get("provider") != "mock" \
                or d.get("driver_sha256") != sha:
            bad.append(f"{m.name}: fields")
        lab = d.get("lock_label")
        win = [x for x in ledger if x.get("label") == lab and "cmd_sha256" in x and "mode" not in x]
        if not win or not any(utc(x["acquired"]) <= utc(d["started_utc"]) and utc(d["ended_utc"]) <= utc(x["released"])
                              for x in win):
            bad.append(f"{m.name}: not inside an EXCLUSIVE quiet-timed window of {lab}")
    check("receipts: measured manifests hostless/exclusive/mock/sha and inside their EXCLUSIVE ledger window",
          measured and not bad, f"{len(measured)} manifests; {bad}")
    vb = []
    for log in sorted((HERE / "raw/logs").glob("versions-*.log")):
        t = log.read_text()
        if "driver_version: cua-driver 0.32.0" not in t or f"driver_sha256: {sha}" not in t:
            vb.append(log.name)
    check("receipts: versions logs show cua-driver 0.32.0 and the binary sha256 (start and end)",
          len(list((HERE / "raw/logs").glob("versions-*.log"))) >= 2 and not vb, f"{vb}")


def cited() -> None:
    f = check_cited(HERE)
    check("cited files tracked (verify_helper: README Files + summary/headline JSON)", not f, f"{f[:10]}")
    tracked = set(git("ls-files", "--", ".").decode().split())
    bad = []
    for name in ("README.md", "PREREG.json", "PREREG-AMENDMENT-1.json", "provenance.json"):
        p = HERE / name
        if not p.exists():
            continue
        for m in CITE.findall(p.read_text()):
            m = m.rstrip(".")
            if m.rstrip("/") in EXTERNAL_CITES:
                continue
            if "*" in m:
                import fnmatch
                if not any(fnmatch.fnmatchcase(t, m) for t in tracked):
                    bad.append(m)
            elif m not in tracked and not any(t.startswith(m.rstrip("/") + "/") for t in tracked):
                bad.append(m)
    check("cited raw/harness/lane-scripts paths are tracked", not bad,
          f"{sorted(set(bad))[:10]}; other-packet paths skipped: {sorted(EXTERNAL_CITES)}")


def amendment_first() -> None:
    t_am = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG-AMENDMENT-1.json").decode().split()
    starts = [utc(json.loads(m.read_text())["started_utc"]) for m in sorted((HERE / "raw/x").glob("run-manifest-*.json"))]
    ok = bool(t_am and starts and datetime.fromisoformat(t_am[-1]) < min(starts))
    check("PREREG-AMENDMENT-1.json committed before the first block-x trial", ok,
          f"amendment {t_am[-1] if t_am else None}, first block-x trial {min(starts).isoformat() if starts else None}")


def prereg_first() -> None:
    t_pre = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json").decode().split()
    starts = []
    for m in sorted((HERE / "raw").glob("*/run-manifest-*.json")):
        if not m.parent.name.startswith("pilot"):
            starts.append(utc(json.loads(m.read_text())["started_utc"]))
    ok = bool(t_pre and starts and datetime.fromisoformat(t_pre[-1]) < min(starts))
    check("PREREG.json committed before the first measured trial", ok,
          f"prereg {t_pre[-1] if t_pre else None}, first trial {min(starts).isoformat() if starts else None}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-git", action="store_true")
    a = ap.parse_args()
    prereg = json.loads((HERE / "PREREG.json").read_text())
    doc = A.analyse(HERE / "raw/main-trials.tar.gz", HERE / "raw/wn-trials.tar.gz", HERE / "raw/x-trials.tar.gz")
    committed = json.loads((HERE / "b06-summary.json").read_text())
    check("summary: recomputed from raw/ equals b06-summary.json", json.loads(json.dumps(doc, sort_keys=True)) == committed)
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
          f"{len(heads['numbers'])} numbers; bad: {bad}")
    harness_identity(prereg)
    receipts(prereg)
    if not a.skip_git:
        cited()
        prereg_first()
        amendment_first()
        privacy_scan(a.base)
    width = max(len(n) for n, _, _ in CHECKS)
    for n, ok, d in CHECKS:
        print(f"{'PASS' if ok else 'FAIL'}  {n.ljust(width)}  {d[:300]}")
    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
