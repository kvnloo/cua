#!/usr/bin/env python3
"""R2-07f packet verifier (standard library only; run under bin/hostless).

1. Identity: the R2-07c, R2-07d and R2-07e packet trees are unchanged at every commit of this branch (equal to
   the base 67b99ddc6); the six b08/ files equal their B-08 blobs at 49ae94590 at every commit.
2. PREREG.json was committed before the first measured trial (training, main and fallback blocks) and is unchanged
   since that commit.
3. Recomputes r2-07f-summary.json (analyze_r2_07f.analyze: every gate, S_E3, the amortized cost and the
   decomposition) from raw/ and requires it to equal the committed file (seeded bootstrap: deterministic).
4. Every number in headline-numbers.json equals its recomputed value and its text appears verbatim in README.md.
5. Every compiled artifact in raw/artifacts/ passes compiled_routine_tm.check_artifact_authority_tm.
6. Provider: TypeSafe cap 0 -> no provider ledger in raw/, every manifest ran with provider_mode mock, every trial
   record has 0 provider attempts.
7. Lock evidence: every measured chunk (blocks t, m, f) ran with lock_mode exclusive and has a quiet-lane ledger
   receipt labelled r207f-<chunk> (raw/lock-receipts-global.jsonl, written by bin/quiet-timed); controls ran with
   the SHARED lock and a receipt.
8. Driver identity: every trial record carries B7's name, sha256 and version.
9. Every file the packet cites is tracked and not ignored; no untracked file under raw/.
10. Privacy over EVERY commit of the branch (67b99ddc6..HEAD): every added/modified blob (tar.gz members included),
    path, commit message and author/committer identity: no absolute home/mount/tmp paths, no host or user names
    (word-boundary match; host name plus the untracked CUA_PRIVACY_NAMES_FILE), no secret-like values; hex and
    base64 runs are decoded and scanned too.

usage: verify_artifacts.py [--skip-git] [--privacy-only]
"""

from __future__ import annotations

import argparse
import base64
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

HERE = Path(__file__).resolve().parent
PKT = "docs/experiments/r2-07f-compiled-replay-b7-decomp-2026-10-03"
BASE = "67b99ddc6a66a217c76dc491977de78180434751"
B08_SHA = "49ae94590"
B08_PKT = "docs/experiments/b-08-per-process-cold-b7-2026-10-03"
IDENTITY_PATHS = {"docs/experiments/r2-07c-toggle-modal-compiled-2026-10-03": "77b5128e435a24282f76238ac0558fc590659276",
                  "docs/experiments/r2-07d-quiet-timing-phase-l-2026-10-03": "90e0c0d875e12f592c7099ed5bc3570c11b8339e",
                  "docs/experiments/r2-07e-modal-gate-phase-l-2026-10-03": "8c3901b1d660a760a1d0e34281cd43d1e26d2dcb"}
B08_FILES = {"harness/b07/b07_stdio.py": "da6f2bd45735319a153972bb68f5f75845e8caf4",
             "harness/b05/b05_spans.py": "bf1f90f830eda8cb7e36d9e6e3af91bc5a9c1969",
             "harness/b04/b04_rows.py": "129bfb74c030e9904078e847a5374caeb034f040",
             "harness/r2-10r/analyze_r2_10.py": "af3a691c3b4e6f1681fdfa4df107a560ff9c612b",
             "harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/b01_analysis.py": "6632de0f9814e547f2aa8f70ee678aa31d1eac12",
             "harness/r2-10r/src/b-02-browser-driver-sites-2026-10-02/analyze_browser.py": "43f4e8db0076c03f71879084a91b99f9785b0b9d"}
B7 = ("cua-driver-b07-231f6e8bb", "6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa", "cua-driver 0.32.0")
TOP = ["README.md", "PREREG.json", "provenance.json", "r2-07f-summary.json", "headline-numbers.json",
       "analyze_r2_07f.py", "verify_artifacts.py", ".gitignore", "driver/r2_07f.py", "driver/run_chunk_f.sh",
       "driver/loop_f.sh", "driver/test_r2_07f.py", "driver/package_f.py"]
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"),
           re.compile(r"/Users/[A-Za-z0-9_.-]+/"), re.compile(r"/tmp/[A-Za-z0-9_.-]+")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}",
                                  r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
HEXRUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){4,}(?![0-9A-Fa-f])")
B64RUN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{12,}={0,2}(?![A-Za-z0-9+/=])")
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com")}
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str, ok: bool = True) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=ok).stdout


def word(name: str) -> re.Pattern[str]:
    """Word-boundary matcher: the name not embedded in a longer alphanumeric token."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])")


def private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        names |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        return sorted(names), f"private names: {len(names)} (CUA_PRIVACY_NAMES_FILE + host name)"
    return sorted(names), "private names: CUA_PRIVACY_NAMES_FILE not set; host name only"


def texts_of_blob(path: str, data: bytes) -> list[tuple[str, str]]:
    out = [(path, data.decode("utf-8", errors="replace"))]
    if path.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for m in tar.getmembers():
                out.append((f"{path}:{m.name}", m.name))
                if m.isfile():
                    out.append((f"{path}:{m.name}", tar.extractfile(m).read().decode("utf-8", errors="replace")))
    elif path.endswith(".gz"):
        out.append((path + ":gunzip", gzip.decompress(data).decode("utf-8", errors="replace")))
    return out


def _b64(run: str) -> bytes | None:
    body = run.rstrip("=")
    if len(body) % 4 == 1 or (run != body and len(run) % 4):
        return None
    try:
        return base64.b64decode(body + "=" * (-len(body) % 4), validate=True)
    except ValueError:
        return None


def with_decoded(targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
    extra = []
    for where, text in targets:
        runs = [bytes.fromhex(r.group()) for r in HEXRUN.finditer(text)]
        runs += [b for r in B64RUN.finditer(text) if (b := _b64(r.group())) is not None]
        for b in runs:
            s = b.decode("utf-8", errors="replace")
            if s and sum(ch.isprintable() for ch in s) >= 0.9 * len(s):
                extra.append((where + ":decoded", s))
    return list(targets) + extra


def privacy_scan() -> None:
    names, note = private_names()
    private = GENERIC + [word(n) for n in names]
    commits = git("rev-list", f"{BASE}..HEAD").decode().split()
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
            data = git("cat-file", "blob", fields[3])
            blobs += 1
            targets.extend(texts_of_blob(path, data))
        for where, text in with_decoded(targets):
            for i, pat in enumerate(private):
                if pat.search(text):
                    hits.append(f"{c[:9]} {where[:100]} private#{i}")
            for i, pat in enumerate(SECRET):
                if where.endswith("verify_artifacts.py") and pat.pattern in text:
                    continue  # this file's own pattern literals
                if pat.search(text):
                    secret_hits.append(f"{c[:9]} {where[:100]} secret#{i}")
    check("privacy: no absolute local paths / host or user names in any commit", not hits,
          f"{len(commits)} commits, {blobs} blobs; {note}; hits: {hits[:8]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:8]}")
    check("privacy: author/committer identity + Co-Authored-By trailer on every commit", not bad_ident,
          f"bad: {bad_ident[:8]}")


def identity_check() -> None:
    commits = git("rev-list", f"{BASE}..HEAD").decode().split()
    bad = []
    for c in commits + [BASE]:
        for p, v in IDENTITY_PATHS.items():
            got = git("rev-parse", f"{c}:{p}", ok=False).decode().strip()
            if got != v:
                bad.append(f"{c[:9]} {p.rsplit('/', 1)[-1]} {got[:12]}")
    check("identity: R2-07c / R2-07d / R2-07e packet trees unchanged at every commit", not bad,
          f"{len(commits) + 1} commits; bad: {bad[:6]}")
    bad2 = []
    for f, blob in B08_FILES.items():
        src = git("rev-parse", f"{B08_SHA}:{B08_PKT}/{f}", ok=False).decode().strip()
        if src != blob:
            bad2.append(f"source {f}")
        for c in commits:
            got = git("rev-parse", f"{c}:{PKT}/b08/{f}", ok=False).decode().strip()
            if got != blob:
                bad2.append(f"{c[:9]} {f}")
    check("identity: b08/ copies equal B-08's blobs at 49ae94590 at every commit", not bad2,
          f"{len(B08_FILES)} files x {len(commits)} commits; bad: {bad2[:6]}")


def prereg_check(summary: dict) -> None:
    out = git("log", "--diff-filter=A", "--format=%H %cI", "--", f":(top){PKT}/PREREG.json").decode().split()
    if not out:
        check("PREREG committed before the first measured trial", False, "PREREG.json not committed")
        return
    sha, when = out[-2], out[-1]
    from datetime import datetime
    first = summary.get("first_measured_trial_utc")
    if summary["disposition"]["value"] == "BLOCKED":
        # no measured trial exists; the pilot must predate the PREREG commit
        import analyze_r2_07f as AN  # noqa: E402
        pilot = [t["summary"].get("utc_start") for t in AN.load_block(HERE / "raw", "pilot")]
        ok = first is None and bool(pilot) and all(
            datetime.fromisoformat(p.replace("Z", "+00:00")) < datetime.fromisoformat(when) for p in pilot if p)
        check("PREREG committed after the pilot; no measured trial exists (BLOCKED)", ok,
              f"PREREG {sha[:9]} {when}; last pilot trial start {max(p for p in pilot if p) if pilot else None}")
    else:
        ok = first is not None and datetime.fromisoformat(when) < datetime.fromisoformat(first.replace("Z", "+00:00"))
        check("PREREG committed before the first measured trial", ok, f"PREREG {sha[:9]} {when}; first measured trial {first}")
    changed = git("log", "--format=%H", f"{sha}..HEAD", "--", f":(top){PKT}/PREREG.json").decode().split()
    check("PREREG.json unchanged since its commit", not changed, f"later commits touching it: {changed[:3]}")


def tracked_check() -> None:
    cited = set(TOP)
    for sub in ("raw", "driver", "b08"):
        for f in sorted((HERE / sub).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                cited.add(str(f.relative_to(HERE)))
    readme = (HERE / "README.md").read_text()
    for m in re.finditer(r"`((?:raw|driver|b08)/[^`\s*]+)`", readme):
        p = m.group(1).rstrip("/")
        if not (HERE / p).is_dir():
            cited.add(p)
    tracked = set(git("ls-files", ".").decode().split())
    missing = sorted(p for p in cited if p not in tracked)
    untracked = git("ls-files", "--others", "--exclude-standard", "raw").decode().split()
    check("every cited file exists, is tracked and not ignored; no untracked file under raw/",
          not missing and not untracked, f"{len(cited)} cited; missing/untracked: {missing[:8]} {untracked[:5]}")


def lock_check(raw: Path) -> None:
    led = [json.loads(x) for x in (raw / "lock-receipts-global.jsonl").read_text().splitlines() if x.strip()] \
        if (raw / "lock-receipts-global.jsonl").exists() else []
    excl = {x["label"] for x in led if "mode" not in x and x.get("rc") is not None}  # bin/quiet-timed receipts
    shared = {x["label"] for x in led if x.get("mode") == "shared"}
    bad = []
    n = 0
    for b, mode, labels in (("t", "exclusive", excl), ("m", "exclusive", excl), ("f", "exclusive", excl),
                            ("c", "shared", shared)):
        for p in sorted((raw / f"{b}-manifests").glob("*.json")):
            m = json.loads(p.read_text())
            n += 1
            if m.get("lock_mode") != mode or f"r207f-{m.get('chunk')}" not in labels:
                bad.append(f"{b}:{m.get('chunk')}:{m.get('lock_mode')}")
    check("lock evidence: measured chunks EXCLUSIVE with a quiet-timed receipt, controls SHARED with a receipt",
          n > 0 and not bad, f"{n} manifests; bad: {bad[:6]}")


def blocked_check(raw: Path) -> None:
    """BLOCKED packet: no measured bundle exists, the lane holds no EXCLUSIVE receipt, every pilot manifest ran
    SHARED with a shared receipt (manual pilot chunks p<n> carry the label r207f-pilot-<n>), and the lock-wedge
    evidence shows exclusive waiters with shared locks held and no exclusive receipt after the last one listed."""
    led = [json.loads(x) for x in (raw / "lock-receipts-global.jsonl").read_text().splitlines() if x.strip()]
    shared = {x["label"] for x in led if x.get("mode") == "shared"}
    excl = [x for x in led if "mode" not in x]
    measured = [b for b in ("t", "m", "f", "c") if (raw / f"{b}-trials.tar.gz").exists()]
    bad = []
    for p in sorted((raw / "pilot-manifests").glob("*.json")):
        m = json.loads(p.read_text())
        ch = str(m.get("chunk"))
        label = f"r207f-pilot-{ch[1:]}" if re.fullmatch(r"p\d+", ch) else f"r207f-{ch}"
        if m.get("lock_mode") != "shared" or label not in shared:
            bad.append(ch)
    wedge = [json.loads(x) for x in (raw / "lock-wedge.jsonl").read_text().splitlines() if x.strip()]
    wedged = (bool(wedge) and all(w["exclusive_waiters"] >= 1 for w in wedge)
              and all(w["quiet_lane_lock_read_locks"] >= 1 for w in wedge[1:]))  # line 1: faulty READ-count pattern (README)
    check("BLOCKED: no measured bundle, no EXCLUSIVE receipt, pilot SHARED with receipts, lock-wedge evidence",
          not measured and not excl and not bad and wedged,
          f"measured={measured} exclusive={len(excl)} bad_pilot={bad} wedge_lines={len(wedge)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-git", action="store_true")
    ap.add_argument("--privacy-only", action="store_true")
    a = ap.parse_args()
    raw = HERE / "raw"
    if a.privacy_only:
        identity_check()
        privacy_scan()
    else:
        sys.path.insert(0, str(HERE))
        import analyze_r2_07f as AN  # noqa: E402

        summary = json.loads((HERE / "r2-07f-summary.json").read_text())
        fresh = json.loads(json.dumps(AN.analyze(raw), sort_keys=True, default=AN.default))
        check("r2-07f-summary.json recomputes from raw/ (every gate, S_E3, amortized, decomposition)", fresh == summary,
              "" if fresh == summary else f"differs in keys: {[k for k in summary if summary.get(k) != fresh.get(k)][:8]}")
        heads = json.loads((HERE / "headline-numbers.json").read_text())
        readme = (HERE / "README.md").read_text()
        recomputed = AN.headlines(fresh)
        bad = [k for k, v in heads.items() if recomputed.get(k) != v]
        absent = [k for k, v in heads.items() if v["text"] not in readme]
        check("headline numbers equal their recomputed values", not bad and bool(heads), f"{len(heads)} numbers; bad: {bad[:8]}")
        check("headline numbers appear verbatim in README.md", not absent, f"absent: {absent[:8]}")
        import compiled_routine_tm as crt  # noqa: E402  (on sys.path through analyze_r2_07c)

        arts = sorted((raw / "artifacts").glob("*.json"))
        probs = {p.name: crt.check_artifact_authority_tm(json.loads(p.read_text())) for p in arts}
        check("every compiled artifact passes the authority scan", bool(arts) and not any(probs.values()),
              f"{len(arts)} artifacts; problems: {[k for k, v in probs.items() if v]}")
        blocks = ("pilot",) if summary["disposition"]["value"] == "BLOCKED" else ("t", "m", "f", "c")
        recs = [t for b in blocks for t in AN.load_block(raw, b)]
        mans = [json.loads(p.read_text()) for b in blocks for p in sorted((raw / f"{b}-manifests").glob("*.json"))]
        prov = sum(int((t["summary"].get("provider_requests") or {}).get("attempts", 0) or 0) for t in recs)
        check("provider: TypeSafe cap 0 -> no ledger, provider_mode mock everywhere, 0 attempts in every record",
              not (raw / "provider-ledger.jsonl").exists() and all(m.get("provider_mode") == "mock" for m in mans)
              and prov == 0, f"{len(recs)} records, {len(mans)} manifests, attempts {prov}")
        ids = {(t["summary"].get("driver_name"), t["summary"].get("driver_sha256"), t["summary"].get("driver_version"))
               for t in recs}
        idm = {(m.get("driver_name"), m.get("driver_sha256"), m.get("driver_version")) for m in mans}
        check("Driver identity (B7 name/sha256/version) in every trial record and manifest", ids == {B7} and idm == {B7},
              f"{len(recs)} records: {sorted(map(str, ids))[:3]}")
        if summary["disposition"]["value"] == "BLOCKED":
            blocked_check(raw)
        else:
            lock_check(raw)
        if not a.skip_git:
            identity_check()
            prereg_check(summary)
            tracked_check()
            privacy_scan()
    width = max(len(n) for n, _, _ in CHECKS)
    for name, ok, detail in CHECKS:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
