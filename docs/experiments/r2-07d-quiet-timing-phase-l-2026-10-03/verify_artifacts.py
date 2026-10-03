#!/usr/bin/env python3
"""R2-07d packet verifier.

1. Harness identity: the R2-07c harness directory and the reused R2-07c analysis are tree/blob
   identical at HEAD and at every commit of this branch to 7f46edd16 (PREREG harness_identity).
2. PREREG.json was committed before the first measured trial (commit time < earliest Q/L trial start).
3. Recomputes r2-07d-summary.json (analyze_r2_07d.analyze) from raw/ and requires it to equal the
   committed file (seeded bootstrap: deterministic).
4. Every number in headline-numbers.json equals its recomputed value and appears verbatim in README.md.
5. Every compiled artifact in raw/artifacts/ passes compiled_routine_tm.check_artifact_authority_tm.
6. Every file the packet cites (top-level files, driver/, raw/, and packet-relative paths in README.md)
   is tracked and not git-ignored; no untracked file under raw/.
7. Privacy over EVERY commit of the branch (7f46edd16..HEAD): every added/modified blob (tar.gz members
   included), path, commit message and author/committer identity: no absolute home/mount paths, no
   host or user names (from the untracked CUA_PRIVACY_NAMES_FILE plus the host name), no secret-like
   values; hex and base64 runs are decoded and scanned too; a committed list of encoded name-like
   strings fails.

usage (under hostless, jev-use venv python or any python3 >= 3.10):
  verify_artifacts.py [--skip-git] [--privacy-only]
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
PKT = "docs/experiments/r2-07d-quiet-timing-phase-l-2026-10-03"
R207C = "docs/experiments/r2-07c-toggle-modal-compiled-2026-10-03"
BASE = "7f46edd1681fbf58586f8b4972636c3da56e3be6"
IDENTITY_PATHS = {f"{R207C}/harness": "66bad345b1736b97b66884bbf40a1505c16083bf",
                  f"{R207C}/analyze_r2_07c.py": "dab482887210fc68ab13a325aae55bd09388ac4d",
                  f"{R207C}/harness/src/r2-10-composition-2026-10-02": None}
TOP = ["README.md", "PREREG.json", "provenance.json", "r2-07d-summary.json", "headline-numbers.json",
       "analyze_r2_07d.py", "verify_artifacts.py", ".gitignore", "driver/r2_07d.py", "driver/run_chunk_d.sh",
       "driver/probe_then.sh", "driver/test_r2_07d.py", "driver/package_d.py"]
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"),
           re.compile(r"/Users/[A-Za-z0-9_.-]+/"), re.compile(r"/tmp/[A-Za-z0-9_.-]+")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}",
                                  r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
HEXRUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){4,}(?![0-9A-Fa-f])")
B64RUN = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{12,}={0,2}(?![A-Za-z0-9+/=])")
LITERAL = re.compile(r"[\"']([A-Za-z0-9+/]{8,}={0,2})[\"']")
NAMELIKE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{2,62}")
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com")}
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str, ok: bool = True) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=ok).stdout


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


def encoded_list(text: str) -> bool:
    n = 0
    for r in LITERAL.finditer(text):
        run = r.group(1)
        if HEXRUN.fullmatch(run) and re.search(r"[A-Fa-f]", run):
            b = bytes.fromhex(run)
        else:
            b = _b64(run) if len(run) >= 12 else None
        n += b is not None and bool(NAMELIKE.fullmatch(b.decode("latin-1")))
    return n >= 2


def privacy_scan() -> None:
    names, note = private_names()
    private = GENERIC + [re.compile(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])") for n in names]
    commits = git("rev-list", f"{BASE}..HEAD").decode().split()
    hits, secret_hits, bad_ident, encoded, blobs = [], [], [], [], 0
    for c in commits:
        meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            bad_ident.append(c[:9])
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
            data = git("cat-file", "blob", fields[3])
            blobs += 1
            targets.extend(texts_of_blob(path, data))
        encoded += [f"{c[:9]} {w[:100]}" for w, t in targets if w != "path" and encoded_list(t)]
        for where, text in with_decoded(targets):
            for i, pat in enumerate(private):
                if pat.search(text):
                    hits.append(f"{c[:9]} {where[:100]} private#{i}")
            for i, pat in enumerate(SECRET):
                if pat.search(text):
                    secret_hits.append(f"{c[:9]} {where[:100]} secret#{i}")
    check("privacy: no absolute local paths / host or user names in any commit", not hits,
          f"{len(commits)} commits, {blobs} blobs; {note}; hits: {hits[:8]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:8]}")
    check("privacy: no committed list of encoded name-like strings", not encoded, f"hits: {encoded[:8]}")
    check("privacy: author/committer identity + Co-Authored-By trailer on every commit", not bad_ident,
          f"bad: {bad_ident[:8]}")


def identity_check() -> None:
    commits = git("rev-list", f"{BASE}..HEAD").decode().split() + [BASE]
    want = {p: (v or git("rev-parse", f"{BASE}:{p}").decode().strip()) for p, v in IDENTITY_PATHS.items()}
    bad = []
    for c in commits:
        for p, v in want.items():
            got = git("rev-parse", f"{c}:{p}", ok=False).decode().strip()
            if got != v:
                bad.append(f"{c[:9]} {p} {got[:12]}")
    check("harness identity: R2-07c harness/ tree, harness/src and analyze_r2_07c.py unchanged at every commit",
          not bad, f"{len(commits)} commits; tree {want[f'{R207C}/harness'][:12]}; bad: {bad[:6]}")


def prereg_before_trials(summary: dict) -> None:
    out = git("log", "--diff-filter=A", "--format=%H %cI", "--", f":(top){PKT}/PREREG.json").decode().split()
    if not out:
        check("PREREG committed before the first measured trial", False, "PREREG.json not committed")
        return
    sha, when = out[-2], out[-1]
    first = summary.get("first_measured_trial_utc")
    from datetime import datetime
    t_pre = datetime.fromisoformat(when)
    ok = first is None or t_pre < datetime.fromisoformat(first.replace("Z", "+00:00"))
    check("PREREG committed before the first measured trial", ok, f"PREREG {sha[:9]} {when}; first measured trial {first}")


def tracked_check() -> None:
    cited = set(TOP)
    for sub in ("raw", "driver"):
        for f in sorted((HERE / sub).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                cited.add(str(f.relative_to(HERE)))
    readme = (HERE / "README.md").read_text()
    for m in re.finditer(r"`((?:raw|driver)/[^`\s*]+)`", readme):
        p = m.group(1).rstrip("/")
        if not (HERE / p).is_dir():
            cited.add(p)
    tracked = set(git("ls-files", ".").decode().split())
    missing = sorted(p for p in cited if p not in tracked)
    untracked = git("ls-files", "--others", "--exclude-standard", "raw").decode().split()
    check("every cited file exists, is tracked and not ignored; no untracked file under raw/",
          not missing and not untracked, f"{len(cited)} cited; missing/untracked: {missing[:8]} {untracked[:5]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-git", action="store_true")
    ap.add_argument("--privacy-only", action="store_true")
    a = ap.parse_args()
    if a.privacy_only:
        identity_check()
        privacy_scan()
    else:
        sys.path.insert(0, str(HERE))
        import analyze_r2_07d as AD  # noqa: E402

        summary = json.loads((HERE / "r2-07d-summary.json").read_text())
        fresh = json.loads(json.dumps(AD.analyze(HERE / "raw"), sort_keys=True, default=AD.default))
        check("r2-07d-summary.json recomputes from raw/", fresh == summary,
              "" if fresh == summary else f"differs in keys: {[k for k in summary if summary.get(k) != fresh.get(k)][:8]}")
        heads = json.loads((HERE / "headline-numbers.json").read_text())
        readme = (HERE / "README.md").read_text()
        recomputed = AD.headlines(fresh)
        bad = [k for k, v in heads.items() if recomputed.get(k) != v]
        absent = [k for k, v in heads.items() if v["text"] not in readme]
        check("headline numbers equal their recomputed values", not bad, f"{len(heads)} numbers; bad: {bad[:8]}")
        check("headline numbers appear verbatim in README.md", not absent, f"absent: {absent[:8]}")
        import compiled_routine_tm as crt  # noqa: E402  (put on sys.path by analyze_r2_07d)

        arts = sorted((HERE / "raw" / "artifacts").glob("*.json"))
        probs = {p.name: crt.check_artifact_authority_tm(json.loads(p.read_text())) for p in arts}
        check("every compiled artifact passes the authority scan", bool(arts) and not any(probs.values()),
              f"{len(arts)} artifacts; problems: {[k for k, v in probs.items() if v]}")
        if not a.skip_git:
            identity_check()
            prereg_before_trials(summary)
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
