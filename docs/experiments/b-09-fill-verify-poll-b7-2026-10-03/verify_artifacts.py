#!/usr/bin/env python3
"""B-09 packet verifier (standard library only; run it under bin/hostless, from a clean clone if you like).
Derived from B-08's verify_artifacts.py (blob-identical copy in this lane's first commit).

1. Recomputes the whole summary (every gate, the poll verdict, S and Part E') from raw/ with analyze_b09 and
   requires it to equal the committed b09-summary.json (every bootstrap is seeded: deterministic).
2. Every headline number in headline-numbers.json equals its recomputed value (by JSON path) and its README
   text appears verbatim in README.md.
3. Harness identity: the first lane commit holds B-08's files with exactly the blob ids in provenance.json;
   every harness file except harness/b04/harness/compiled_routine.py still has its B-08 blob; compiled_routine.py
   has the blob of the harness commit (unchanged since, i.e. since before PREREG); tests/test_compiled_routine_r207.py
   keeps R2-07's blob; the COMP arm line of harness/b04/run_b04.py equals R2-10R's; the routine artifact equals B-04's.
4. B-07 carry: every BELOW_GATE / IRREDUCIBLE unit label in PREREG part_E_prime equals b07-summary.json's label on
   the same binary (c_in.prep on fill is UNTESTED here by rule).
5. Receipts: every trial and control record carries the PREREG binary name, sha256 and version and no lane variable
   in the Driver environment; every measured / control manifest says hostless=1, lock exclusive, provider mock and
   the sha256, and lies inside an EXCLUSIVE quiet-timed ledger window of its own label (raw/lock-ledger.jsonl);
   every round started at 1-min loadavg <= 4.0; the SHARED receipts of the pilot and the final analysis exist;
   versions logs (start, end) show cua-driver 0.32.0 and the sha256; unit logs red (errors) and green (OK).
6. Cited files are tracked (verify_helper + every raw/ harness/ lane-scripts/ tests/ path in README/PREREG/provenance).
7. PREREG.json was committed before the first measured trial and only once.
8. Privacy scan of EVERY lane commit (base..HEAD): blobs (tar.gz members included), paths, messages, identity
   and trailer; hex and base64 literals decoded. Private names come from the untracked file named by
   CUA_PRIVACY_NAMES_FILE plus the host name (word-boundary match); extra patterns (session-bus paths and the
   like) from the untracked file named by CUA_PRIVACY_PATTERNS_FILE.

When raw/main-trials.tar.gz is absent (the measured run is NOT_RUN / BLOCKED) checks 1-2 are replaced by the
blocked checks: no measured data or summary is claimed, this lane has no EXCLUSIVE ledger line, the lock-blocker
record exists, the 12 excluded pilot records carry the binary identity; PREREG committed once.

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
import analyze_b09 as A  # noqa: E402
import b09_rows as R  # noqa: E402
from verify_helper import check_cited  # noqa: E402

BASE = "49ae94590f3b7e25cf7bf5fbfbbf67d51aaadff3"
FIRST_COMMIT_SUBJECT = "exp(b-09): copy B-08 harness and lane code blob-identical from 49ae94590"
HARNESS_COMMIT_PREFIX = "exp(b-09): harness - "
CHANGED = "harness/b04/harness/compiled_routine.py"
R207_TEST = ("tests/test_compiled_routine_r207.py", "e9c7ff81e6ea39fb493a328d38b920d56165141d")
B07_SUMMARY = HERE.parent / "b-07-transport-residual-rprime-2026-10-03" / "b07-summary.json"
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"),
           re.compile(r"/Users/[A-Za-z0-9_.-]+/"), re.compile(r"/tmp/claude-[0-9]")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com")}
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
HEXLIT = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-fA-F]{2}){4,}(?![0-9A-Za-z])")
B64LIT = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])")
CITE = re.compile(r"(?<![A-Za-z0-9_./-])((?:raw|harness|lane-scripts|tests)/[A-Za-z0-9_./*-]+[A-Za-z0-9_*-])")
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


def hash_object(rel: str) -> str:
    return subprocess.run(["git", "hash-object", str(HERE / rel)], capture_output=True, text=True, check=True).stdout.strip()


# ── 1-2 summary and headlines ───────────────────────────────────────────────
def summary_and_headlines() -> dict:
    trials, mans = A.load(HERE / "raw")
    doc = json.loads(json.dumps(A.analyse_trials(trials, mans), sort_keys=True))
    committed = json.loads((HERE / "b09-summary.json").read_text())
    check("summary: recomputed from raw/ equals b09-summary.json (gates, verdict, S, Part E')", doc == committed,
          f"{len(trials)} trial records")
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
def tree_at(commit: str, pre: str) -> dict[str, str]:
    tree = {}
    for line in git("ls-tree", "-r", "--full-tree", commit).decode().splitlines():
        meta, path = line.split("\t", 1)
        if path.startswith(pre + "/"):
            tree[path[len(pre) + 1:]] = meta.split()[2]
    return tree


def harness_identity() -> None:
    prov = json.loads((HERE / "provenance.json").read_text())
    blobs = prov["copied_from_b08"]["blobs"]
    pre = rel_prefix()
    log = [c.split(" ", 1) for c in git("log", "--format=%H %s", f"{BASE}..HEAD", "--", ".").decode().splitlines()]
    first = [h for h, s in log if s == FIRST_COMMIT_SUBJECT]
    harn = [h for h, s in log if s.startswith(HARNESS_COMMIT_PREFIX)]
    bad = []
    if len(first) != 1:
        bad.append(f"first copy commit found {len(first)} times")
    else:
        tree = tree_at(first[0], pre)
        for rel, blob in blobs.items():
            if tree.get(rel) != blob:
                bad.append(f"first commit {rel}")
        extra = set(tree) - set(blobs)
        if extra:
            bad.append(f"first commit extra files {sorted(extra)}")
    for rel, blob in blobs.items():
        if rel.startswith("harness/") and rel != CHANGED and hash_object(rel) != blob:
            bad.append(f"{rel} changed")
    if len(harn) != 1:
        bad.append(f"harness commit found {len(harn)} times")
    else:
        if tree_at(harn[0], pre).get(CHANGED) != hash_object(CHANGED):
            bad.append(f"{CHANGED} changed after the harness commit")
        if hash_object(CHANGED) == blobs.get(CHANGED):
            bad.append(f"{CHANGED} equals the B-08 blob (no harness change?)")
    if hash_object(R207_TEST[0]) != R207_TEST[1]:
        bad.append(f"{R207_TEST[0]} is not R2-07's blob")
    check("harness: first commit = B-08 blobs; untouched harness files keep them; compiled_routine.py fixed since the "
          "harness commit; R2-07 test blob", not bad, f"{bad}")

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
    units = prereg["part_E_prime"]["verdict_map"]["units"]
    bad = []
    for u, (v, _src) in units.items():
        if u == "any other lane-scope label":
            continue
        src7 = s7["units"].get(u) or s7["resolution"].get(u)
        mine = v["fill"] if isinstance(v, dict) else v
        theirs = src7["fill"]
        if u == "c_in.prep":
            if mine != "UNTESTED":
                bad.append("c_in.prep/fill must be UNTESTED")
            continue
        if theirs == "ABSENT":
            continue
        if not theirs.startswith(mine):
            bad.append(f"{u}/fill: {mine} vs B-07 {theirs}")
    check("B-07 carry: PREREG unit labels equal b07-summary.json labels on fill (same binary B7)", not bad, f"{bad}")


# ── 5 receipts ──────────────────────────────────────────────────────────────
def receipts(prereg: dict) -> None:
    sha, ver, name = prereg["binary"]["sha256"], prereg["binary"]["version"], prereg["binary"]["name"]
    trials, mans = A.load(HERE / "raw")
    bad_t = [t["summary"]["trial"] for t in trials
             if (t["summary"].get("driver_sha256"), t["summary"].get("driver_version"), t["summary"].get("driver_name"))
             != (sha, ver, name)]
    kinds = {}
    for t in trials:
        kinds[t["summary"].get("kind")] = kinds.get(t["summary"].get("kind"), 0) + 1
    check("receipts: every trial and control record carries the binary name, sha256 and version", trials and not bad_t,
          f"{len(trials)} records {kinds}; bad {bad_t[:5]}")
    lane_leak = [t["summary"]["trial"] for t in trials if t["summary"].get("driver_env_lane")]
    check("receipts: no CUA_LANE_EXP_* variable in any Driver environment", not lane_leak, f"{lane_leak[:5]}")
    ledger = [json.loads(x) for x in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines() if x.strip()]
    bad, load_bad = [], []
    for p in sorted((HERE / "raw/main").glob("run-manifest-*.json")):
        d = json.loads(p.read_text())
        if d.get("hostless") != "1" or d.get("lock_mode") != "exclusive" or d.get("provider") != "mock" \
                or d.get("driver_sha256") != sha or d.get("driver_version") != ver or d.get("driver_name") != name:
            bad.append(f"{p.name}: fields")
        lab = d.get("lock_label")
        win = [x for x in ledger if x.get("label") == lab and "cmd_sha256" in x and "mode" not in x]
        if not win or not any(utc(x["acquired"]) <= utc(d["started_utc"]) and utc(d["ended_utc"]) <= utc(x["released"])
                              for x in win):
            bad.append(f"{p.name}: not inside an EXCLUSIVE quiet-timed window of {lab}")
        started = {}
        for c in d.get("load_checks", []):
            started[c["round"]] = c["load1"]  # last check before the round = the one it started on
        for r in d.get("rounds_completed", []):
            if started.get(r, 99) > 4.0:
                load_bad.append(f"{p.name}: round {r} load1 {started.get(r)}")
    n = len(list((HERE / "raw/main").glob("run-manifest-*.json")))
    check("receipts: measured / control manifests hostless/exclusive/mock/name/sha/version and inside their EXCLUSIVE "
          "ledger window", n > 0 and not bad, f"{n} manifests; {bad[:5]}")
    check("receipts: every completed round started at 1-min loadavg <= 4.0", not load_bad, f"{load_bad[:5]}")
    shared = {x["label"] for x in ledger if x.get("mode") == "shared"}
    need = {"b09-pilot-r00-01", "b09-analyze-final", "b09-versions-start", "b09-versions-end"}
    check("receipts: SHARED-lock receipts for the pilot, the version reads and the final analysis", need <= shared,
          f"missing {sorted(need - shared)}")
    common_receipts(sha, ver)


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
            if m not in tracked and "." in m.rsplit("/", 1)[-1] and m.rsplit(".", 1)[0] + ".py" in tracked:
                m = m.rsplit(".", 1)[0] + ".py"  # module.function citation -> module file
            if "*" in m:
                if not any(fnmatch.fnmatchcase(t, m) for t in tracked):
                    bad.append(m)
            elif m not in tracked and not any(t.startswith(m.rstrip("/") + "/") for t in tracked):
                bad.append(m)
    check("cited raw/harness/lane-scripts/tests paths are tracked", not bad, f"{sorted(set(bad))[:10]}")


def prereg_first() -> None:
    t_pre = git("log", "--diff-filter=A", "--format=%cI", "--", "PREREG.json").decode().split()
    starts = [utc(json.loads(m.read_text())["started_utc"]) for m in sorted((HERE / "raw/main").glob("run-manifest-*.json"))]
    ok = bool(t_pre and starts and datetime.fromisoformat(t_pre[-1]) < min(starts))
    check("PREREG.json committed before the first measured trial", ok,
          f"prereg {t_pre[-1] if t_pre else None}, first measured chunk {min(starts).isoformat() if starts else None}")
    ch = git("log", "--format=%H", "--", "PREREG.json").decode().split()
    check("PREREG.json never amended after its first commit", len(ch) == 1, f"{len(ch)} commits touch it")


# ── 8 privacy ────────────────────────────────────────────────────────────────
def patterns() -> tuple[list[re.Pattern], str]:
    ns = {socket.gethostname()} - {"", "localhost"}
    note = []
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        ns |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        note.append(f"names {len(ns)} (CUA_PRIVACY_NAMES_FILE + host name)")
    else:
        note.append("CUA_PRIVACY_NAMES_FILE not set: host name only")
    pats = [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", re.I) for n in sorted(ns)]
    pf = os.environ.get("CUA_PRIVACY_PATTERNS_FILE", "")
    if pf and Path(pf).is_file():
        extra = [re.compile(x.strip()) for x in Path(pf).read_text().splitlines() if x.strip() and not x.startswith("#")]
        pats += extra
        note.append(f"extra patterns {len(extra)} (CUA_PRIVACY_PATTERNS_FILE)")
    else:
        note.append("CUA_PRIVACY_PATTERNS_FILE not set")
    return pats, "; ".join(note)


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
    private, note = patterns()
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


def blocked_receipts(prereg: dict) -> None:
    """Measured run NOT_RUN (BLOCKED): what exists must be consistent and nothing measured may be claimed."""
    sha, ver, name = prereg["binary"]["sha256"], prereg["binary"]["version"], prereg["binary"]["name"]
    check("blocked: no measured trials, manifests or summary in the packet",
          not (HERE / "raw/main-trials.tar.gz").exists() and not list((HERE / "raw").glob("main/run-manifest-*.json"))
          and not (HERE / "b09-summary.json").exists(), "")
    ledger = [json.loads(x) for x in (HERE / "raw/lock-ledger.jsonl").read_text().splitlines() if x.strip()]
    excl = [x for x in ledger if "mode" not in x]
    check("blocked: no EXCLUSIVE quiet-timed acquisition by this lane in the ledger", not excl, f"{[x.get('label') for x in excl]}")
    blk = json.loads((HERE / "raw/lock-blocker.json").read_text())
    check("blocked: lock-blocker record present (holder, effect, unblock)", all(k in blk for k in ("holder", "effect", "unblock")), "")
    pilot = R.load_tar(HERE / "raw/pilot-trials.tar.gz")
    bad = [t["summary"]["trial"] for t in pilot
           if (t["summary"].get("driver_sha256"), t["summary"].get("driver_version"), t["summary"].get("driver_name")) != (sha, ver, name)
           or t["summary"].get("driver_env_lane")]
    check("pilot (excluded): 12 records carry the binary identity and no lane variable reached the Driver",
          len(pilot) == 12 and not bad, f"{len(pilot)} records; bad {bad[:5]}")
    shared = {x["label"] for x in ledger if x.get("mode") == "shared"}
    need = {"b09-pilot-r00-01", "b09-versions-start", "b09-versions-end"}
    check("receipts: SHARED-lock receipts for the pilot and the version reads", need <= shared, f"missing {sorted(need - shared)}")
    common_receipts(sha, ver)


def common_receipts(sha: str, ver: str) -> None:
    vb = []
    logs = sorted((HERE / "raw/logs").glob("versions-*.log"))
    for log in logs:
        t = log.read_text()
        if f"driver_version: {ver}" not in t or f"driver_sha256: {sha}" not in t:
            vb.append(log.name)
    check("receipts: versions logs (start, end) show the version and sha256", len(logs) >= 2 and not vb,
          f"{[x.name for x in logs]} {vb}")
    red = (HERE / "raw/unit/unit-red.log").read_text()
    green = (HERE / "raw/unit/unit-green.log").read_text()
    check("unit: red log fails (new tests vs the unmodified routine) and green log passes 32/32",
          "FAILED (errors=9, skipped=6)" in red and "Ran 32 tests" in green and green.rstrip().endswith("OK"), "")


def prereg_once() -> None:
    ch = git("log", "--format=%H", "--", "PREREG.json").decode().split()
    check("PREREG.json committed once and never amended", len(ch) == 1, f"{len(ch)} commits touch it")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-git", action="store_true")
    a = ap.parse_args()
    prereg = json.loads((HERE / "PREREG.json").read_text())
    measured = (HERE / "raw/main-trials.tar.gz").exists()
    if measured:
        summary_and_headlines()
    harness_identity()
    b07_carry(prereg)
    if measured:
        receipts(prereg)
    else:
        blocked_receipts(prereg)
    if not a.skip_git:
        cited()
        prereg_first() if measured else prereg_once()
        privacy_scan(a.base)
    width = max(len(n) for n, _, _ in CHECKS)
    for n, ok, d in CHECKS:
        print(f"{'PASS' if ok else 'FAIL'}  {n.ljust(width)}  {d[:300]}")
    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
