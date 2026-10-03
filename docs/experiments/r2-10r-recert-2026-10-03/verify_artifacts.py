#!/usr/bin/env python3
"""R2-10R packet verifier (standard library only).

1. Recomputes r2-10r-summary.json (analyze_r2_10.analyze), d1-summary.json (analyze_d1.analyze),
   recert-summary.json (recert_gates.gates against reference/r2-10-reference.json) and
   nm2-sensitivity.json (sensitivity_nm2.analyze, PREREG-AMENDMENT-2) from raw/ and requires each to
   equal the committed file (seeded bootstrap: deterministic) and the nm2 sensitivity rows to pass.
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim in README.md.
3. Requires every file this packet cites (every file under raw/, reference/, harness/, the top-level
   packet files, and every packet-relative path named in README.md) to exist, to be tracked by git
   and not to be git-ignored; fails on untracked files under raw/.
4. Requires the reference to be the accepted R2-10 summary blob (git blob sha1 recorded in it, read
   from exp/r2-10-composition-20261002 030f6bdbf when that commit is available).
5. Privacy-scans EVERY commit of the branch (base..HEAD, merges included): every added/modified
   blob (tar.gz/gz members included), every path name, commit message and author/committer
   identity: no absolute home or mount paths, no lane/host names, no secret-like values.
   Private names are stored hex-encoded so this file does not contain them.

usage: verify_artifacts.py [--base 0f1955d2f1ee2b01b40775aa53ea2af0b5544218] [--skip-git]
(R2-10R edit of the R2-10 verify_artifacts.py: three recomputed summaries, the tracked/ignored-file
check, the reference check, base 0f1955d2f and the step-2 merge 6f438492b in the allowlist.)
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_d1 as D  # noqa: E402
import analyze_r2_10 as A  # noqa: E402
import recert_gates as G  # noqa: E402
import sensitivity_nm2 as N2  # noqa: E402

BASE = "0f1955d2f1ee2b01b40775aa53ea2af0b5544218"
R2_10_COMMIT = "030f6bdbf"
R2_10_SUMMARY = "docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json"
_H = ["67726f6f74", "7a6572306d6f64656c73", "6375612d6c616e6573", "2f746d702f636c61756465", "6b766e40"]
PRIVATE = [re.compile(re.escape(bytes.fromhex(h).decode())) for h in _H] + [
    re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"), re.compile(r"/Users/[A-Za-z0-9_.-]+/")]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com"), ("kvnloo", "7121943+kvnloo@users.noreply.github.com")}
# Upstream content (trycua/cua PR 4316 head a0bca7440, brought in by the step-2 merge 6f438492b), already
# public: a GitHub Actions runner path in the CI workflow and a placeholder key literal in a unit test
# (the same two hits R2-10 allowlisted for a0bca7440 / b10cd09f2). Matched by (commit, path, pattern).
ALLOW = {
    ("a0bca7440", ".github/workflows/ci-jev-use.yml", "private#5"),
    ("6f438492b", ".github/workflows/ci-jev-use.yml", "private#5"),
    ("a0bca7440", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
    ("6f438492b", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
}
TOP = ["README.md", "PREREG.json", "PREREG-AMENDMENT-1.json", "PREREG-AMENDMENT-2.json", "nm2-sensitivity.json",
       "sensitivity_nm2.py", "provenance.json", "r2-10r-summary.json", "d1-summary.json", "recert-summary.json",
       "headline-numbers.json", "analyze_r2_10.py", "analyze_d1.py", "recert_gates.py", "make_headlines.py",
       "verify_artifacts.py", ".gitignore", "reference/r2-10-reference.json"]
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str, ok: bool = True) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=ok).stdout


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


def privacy_scan(base: str) -> None:
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits: list[str] = []
    secret_hits: list[str] = []
    bad_ident: list[str] = []
    allowed: list[str] = []
    blobs_scanned = 0
    for c in commits:
        meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            bad_ident.append(f"{c[:9]} {meta[0]} / {meta[2]}")
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
            blobs_scanned += 1
            targets.extend(texts_of_blob(path, data))
        for where, text in targets:
            for i, pat in enumerate(PRIVATE):
                if pat.search(text):
                    if (c[:9], where, f"private#{i}") in ALLOW:
                        allowed.append(f"{c[:9]} {where} private#{i}")
                    else:
                        hits.append(f"{c[:9]} {where[:120]} private#{i}")
            for i, pat in enumerate(SECRET):
                if pat.search(text):
                    if (c[:9], where, f"secret#{i}") in ALLOW:
                        allowed.append(f"{c[:9]} {where} secret#{i}")
                    else:
                        secret_hits.append(f"{c[:9]} {where[:120]} secret#{i}")
    check("privacy: no absolute local paths / lane or host names in any commit", not hits,
          f"{len(commits)} commits, {blobs_scanned} blobs; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: author/committer identity", not bad_ident, f"bad: {bad_ident[:10]}")
    print(f"privacy: {len(commits)} commits, {blobs_scanned} blobs; allowlisted (upstream PR 4316 content): {sorted(set(allowed))}")


def tracked_check() -> None:
    cited = set(TOP)
    for sub in ("raw", "reference", "harness"):
        for f in sorted((HERE / sub).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                cited.add(str(f.relative_to(HERE)))
    readme = (HERE / "README.md").read_text()
    for m in re.finditer(r"`((?:raw|harness|reference)/[^`\s*]+)`", readme):
        p = m.group(1).rstrip("/")
        if (HERE / p).is_dir():
            continue
        cited.add(p)
    tracked = set(git("ls-files", "--", ".").decode().splitlines())
    missing, untracked, ignored = [], [], []
    for p in sorted(cited):
        if not (HERE / p).exists():
            missing.append(p)
            continue
        if p not in tracked:
            untracked.append(p)
        if subprocess.run(["git", "-C", str(HERE), "check-ignore", "-q", "--no-index", p]).returncode == 0:
            ignored.append(p)
    check(f"cited files exist ({len(cited)})", not missing, f"missing: {missing[:10]}")
    check("cited files are tracked by git", not untracked, f"untracked: {untracked[:10]}")
    check("cited files are not git-ignored", not ignored, f"ignored: {ignored[:10]}")


def reference_check() -> None:
    ref = json.loads((HERE / "reference" / "r2-10-reference.json").read_text())
    want = ref.get("source", {}).get("summary_git_blob_sha1")
    # --verify -q: a clone without 030f6bdbf (e.g. --single-branch) prints nothing instead of echoing the argument
    got = git("rev-parse", "--verify", "-q", f"{R2_10_COMMIT}:{R2_10_SUMMARY}", ok=False).decode().strip()
    if got:
        blob = git("cat-file", "blob", got)
        same = G.extract(json.loads(blob))
        same_ok = all(same[k] == ref[k] for k in ("S", "decomposition", "work_deleted", "validity", "e4"))
        check("reference = verdicts extracted from the accepted R2-10 summary blob", got == want and same_ok,
              f"blob {got} vs recorded {want}; extract equal {same_ok}")
    else:
        check("reference blob available (R2-10 commit not in this clone; recorded sha1 only)", bool(want), "")


def walk(docs, path):  # noqa: ANN001, ANN201
    doc, _, rest = path.partition(":")
    obj = docs[doc]
    for key in rest.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--skip-git", action="store_true")
    args = p.parse_args()
    S = json.loads(json.dumps(A.analyze(HERE / "raw"), sort_keys=True, default=str))
    Dd = json.loads(json.dumps(D.analyze(HERE / "raw"), sort_keys=True))
    Gg = json.loads(json.dumps(G.gates(S, Dd, json.loads((HERE / "reference" / "r2-10-reference.json").read_text())),
                               sort_keys=True))
    for name, rec in (("r2-10r-summary.json", S), ("d1-summary.json", Dd), ("recert-summary.json", Gg)):
        committed = json.loads((HERE / name).read_text())
        check(f"{name} recomputes identically from raw/", rec == committed, "" if rec == committed else "differs")
    Nn = json.loads(json.dumps(N2.analyze(HERE / "raw"), sort_keys=True))
    committed = json.loads((HERE / "nm2-sensitivity.json").read_text())
    check("nm2-sensitivity.json recomputes identically from raw/", Nn == committed, "" if Nn == committed else "differs")
    check("nm2 sensitivity: nm1-only and drop-window native S keep the R2-10 direction (8/8 rows)",
          Nn["pass"] and Nn["rows_n"] == 8, f"rows {Nn['rows_n']}")
    docs = {"S": S, "D": Dd, "G": Gg, "N": Nn}
    readme = (HERE / "README.md").read_text()
    heads = json.loads((HERE / "headline-numbers.json").read_text())
    for h in heads["numbers"]:
        val = walk(docs, h["path"])
        shown = h["format"].format(*val) if isinstance(val, list) else h["format"].format(val)
        check(f"headline {h['id']} = {shown}", shown == h["text"] and h["text"] in readme,
              f"recomputed {shown!r}, listed {h['text']!r}, in README {h['text'] in readme}")
    for f in sorted((HERE / "raw").rglob("*")):
        if f.is_file():
            for where, text in texts_of_blob(str(f.relative_to(HERE)), f.read_bytes()):
                if any(pat.search(text) for pat in PRIVATE):
                    check(f"raw privacy {where[:100]}", False, "private string in raw file")
    if not args.skip_git:
        tracked_check()
        reference_check()
        privacy_scan(args.base)
    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
