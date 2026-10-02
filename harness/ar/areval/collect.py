"""Impure collectors: git, itemcheck and file hashing. Everything the pure gates consume is
produced here and written to JSON first, so an evaluation can be re-run from its inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

HARNESS_REL = "harness/ar"
FIXTURES_REL = "docs/experiments/ar-harness-2026-10-02/fixtures"
CANDIDATE_FROZEN_GLOBS = (
    "libs/cua-driver/rust/Cargo.toml",
    "libs/cua-driver/rust/Cargo.lock",
    "libs/cua-driver/rust/crates/*/Cargo.toml",
    "libs/cua-driver/rust/crates/cua-driver-core/src/phase_trace.rs",
    "libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py",
    "libs/cua-driver/examples/jev-use/python/driver_env.py",
    "libs/cua-driver/examples/jev-use/python/native.py",
    "libs/cua-driver/examples/jev-use/python/run.py",
)
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def git_bytes(repo: Path, rev: str, path: str) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def frozen_paths(repo: Path, rev: str) -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", rev, "--", *CANDIDATE_FROZEN_GLOBS).split()
    # git ls-tree pathspecs do not glob crates/*; expand that one by listing.
    crates = [p for p in git(repo, "ls-tree", "-r", "--name-only", rev, "--", "libs/cua-driver/rust/crates").split()
              if p.endswith("/Cargo.toml") and p.count("/") == 5]
    return sorted(set(out) | set(crates))


def hunks_by_file(diff: str) -> dict[str, list[list[int]]]:
    out: dict[str, list[list[int]]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/")
            out.setdefault(current, [])
        elif current and (m := HUNK.match(line)):
            bs, bl, cs, cl = m.groups()
            out[current].append([int(bs), int(bl if bl is not None else 1), int(cs), int(cl if cl is not None else 1)])
    return out


def run_itemcheck(itemcheck: Path, repo: Path, base: str, cand: str, paths: list[str],
                  hunks: dict[str, list[list[int]]], allowlist: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:  # honours TMPDIR (the lane temp root)
        files = []
        for i, path in enumerate(paths):
            entry: dict[str, Any] = {"key": path, "hunks": hunks.get(path, [])}
            for side, rev in (("base", base), ("cand", cand)):
                data = git_bytes(repo, rev, path)
                if data is None:
                    entry[side] = None
                else:
                    p = Path(tmp) / f"{i}-{side}.rs"
                    p.write_bytes(data)
                    entry[side] = str(p)
            files.append(entry)
        req = Path(tmp) / "request.json"
        req.write_text(json.dumps({"allowlist": allowlist["items"], "files": files}))
        proc = subprocess.run([str(itemcheck), "--request", str(req)], capture_output=True, text=True)
        if proc.returncode not in (0, 1):
            raise RuntimeError(f"itemcheck failed: {proc.stderr}")
        return json.loads(proc.stdout)


def collect_g0_inputs(repo: Path, champion: str, candidate: str, itemcheck: Path,
                      allowlist: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    diff = git(repo, "diff", "--no-renames", "--no-color", "-U0", f"{champion}..{candidate}")
    full = git(repo, "diff", "--no-renames", "--no-color", f"{champion}..{candidate}")
    names = git(repo, "diff", "--no-renames", "--name-only", f"{champion}..{candidate}").split()
    rs = [p for p in names if p.endswith(".rs")]
    report = run_itemcheck(itemcheck, repo, champion, candidate, rs, hunks_by_file(diff), allowlist)
    frozen = {}
    for path in manifest.get("candidate_frozen", {}):
        data = git_bytes(repo, candidate, path)
        frozen[path] = sha256_bytes(data) if data is not None else None
    base = git(repo, "merge-base", champion, candidate).strip()
    return {"diff": full, "itemcheck": report, "frozen_sha256": frozen,
            "lineage_ok": base == git(repo, "rev-parse", champion).strip(),
            "champion": git(repo, "rev-parse", champion).strip(),
            "candidate": git(repo, "rev-parse", candidate).strip()}


def harness_files(wt: Path) -> list[Path]:
    """Evaluator-owned files: harness/ar plus the fixtures package the runner imports."""
    skip = {"manifest.json"}
    out = []
    for rel in (HARNESS_REL, FIXTURES_REL):
        root = wt / rel
        out += [p for p in root.rglob("*") if p.is_file() and p.name not in skip
                and "__pycache__" not in p.parts and "target" not in p.parts]
    return sorted(out)


def build_manifest(wt: Path, champion: str, itemcheck: Path, allowlist: dict[str, Any]) -> dict[str, Any]:
    repo = wt
    frozen = {p: sha256_bytes(git_bytes(repo, champion, p) or b"") for p in frozen_paths(repo, champion)}
    segment = sorted(allowlist["items"])
    report = run_itemcheck(itemcheck, repo, champion, champion, segment, {}, allowlist)
    if not report["ok"]:
        raise RuntimeError(f"champion does not pass itemcheck against itself: {report['violations']}")
    tests = {k: v["test_items_cand"] for k, v in report["files"].items()}
    harness = {str(p.relative_to(wt)): sha256_bytes(p.read_bytes()) for p in harness_files(wt)}
    return {"schema": "ar.manifest.v1", "champion_commit": git(repo, "rev-parse", champion).strip(),
            "candidate_frozen": frozen, "test_items": tests,
            "segment_files_sha256": {p: sha256_bytes(git_bytes(repo, champion, p) or b"") for p in segment},
            "harness": harness}


def harness_selfcheck(wt: Path, manifest: dict[str, Any]) -> list[str]:
    now = {str(p.relative_to(wt)): sha256_bytes(p.read_bytes()) for p in harness_files(wt)}
    errors = [f"changed:{p}" for p, s in manifest["harness"].items() if now.get(p) != s]
    errors += [f"added:{p}" for p in now if p not in manifest["harness"]]
    return errors
