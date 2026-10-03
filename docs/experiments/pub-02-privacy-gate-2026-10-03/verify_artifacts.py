#!/usr/bin/env python3
"""PUB-02 packet verifier (standard library only; run under bin/hostless from a clean clone).

1. Recomputes pub02-summary.json from raw/ (audit JSON, control logs, rewrite evidence) and requires it to
   equal the committed file.
2. Requires the audit tables in README.md to equal the tables rendered from raw/audit/*.json, row for row.
3. Controls: the template plant controls (green 3/3 dummy, 1/1 abs-path, 1/1 encoded list, clean passes;
   red-before 0/3 with the old template), template unit tests 11/11 twice, the R2-10 mutation control
   (129/129 unmutated, exactly 2 FAIL mutated), the rewrite verifiers (A 189/189 and B 133/133, with and
   without CUA_PRIVACY_NAMES_FILE; red-before 187/189 and 131/133 on the original histories).
4. When this clone holds the objects: each rewritten commit differs from its original only in
   verify_artifacts.py and keeps the author date; the head tree diffs are exactly the stated files;
   2cedaa9a4 is reused. Otherwise these checks are reported as skipped (counted, never as passed).
5. Cited files are tracked (verify_helper.check_cited) and the packet, and every commit of the branch
   past --base (default: the branch base cca59642d), pass verify_helper.check_privacy.

usage: verify_artifacts.py [--base <sha>] [--skip-git]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from verify_helper import check_cited, check_privacy  # noqa: E402

BASE = "cca59642dce3cd1a9c8e17b9f578eb94fc4b1f6e"
RAW = HERE / "raw"
COLS = ["encoded-name", "encoded-list", "plain-name", "user-name-in-raw", "abs-path", "abs-path-generic", "secret-like"]
CHECKS: list[tuple[str, bool | None, str]] = []


def check(name: str, ok: bool | None, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True)


def load(name: str) -> dict:
    return json.loads((RAW / "audit" / name).read_text())


def cell(counts: dict, col: str) -> str:
    return str(counts.get(col, 0))


def first(row: dict) -> str:
    fo = row.get("first_offending_commit") or {}
    keys = [k for k in COLS if k in fo and k not in ("abs-path-generic", "secret-like")]
    return ", ".join(f"{k} {fo[k][:9]}" for k in keys) or "-"


def tables() -> dict[str, list[str]]:
    """Markdown rows rendered from raw/audit/*.json (never values: counts, tags and SHAs only)."""
    head = "| Branch | Scope | Scanned | " + " | ".join(COLS) + " | First offending commit (private classes) | Evidence class |"
    out: dict[str, list[str]] = {}
    tips = load("audit-tips.json")["rows"]
    rows, clean = [], []
    for r in tips:
        if any(r["counts"].get(c) for c in COLS[:5]):
            rows.append(f"| `{r['branch']}` | tip {r['tip'][:9]} ({r['scope']}) | {r['files_scanned']} files | "
                        + " | ".join(cell(r["counts"], c) for c in COLS) + f" | {first(r)} | SOURCE |")
        else:
            clean.append(r)
    gen = sum(r["counts"].get("abs-path-generic", 0) for r in clean)
    sec = sum(r["counts"].get("secret-like", 0) for r in clean)
    rows.append(f"| {len(clean)} other origin exp/* and docs/* tips | tips | "
                f"{sum(r['files_scanned'] for r in clean)} files | 0 | 0 | 0 | 0 | 0 | {gen} | {sec} | - | SOURCE |")
    out["tips"] = [head, "|" + "---|" * (len(COLS) + 5)] + rows
    for part in ("commits", "ranges"):
        rows = []
        for r in load(f"audit-{part}.json")["rows"]:
            scope = re.sub(r"\b([0-9a-f]{9})[0-9a-f]{31}\b", r"\1", r["rev_list"])
            rows.append(f"| `{r['branch']}` | {scope} | {r['commits_scanned']} commits | "
                        + " | ".join(cell(r["counts"], c) for c in COLS) + f" | {first(r)} | SOURCE |")
        out[part] = [head, "|" + "---|" * (len(COLS) + 5)] + rows
    return out


def grab(path: str, pattern: str) -> str | None:
    m = re.search(pattern, (HERE / path).read_text())
    return m.group(1) if m else None


def summary() -> dict:
    s: dict = {"audit": {}}
    for part in ("tips", "commits", "ranges"):
        rows = load(f"audit-{part}.json")["rows"]
        s["audit"][part] = {
            "branches": len(rows),
            "with_private_finding": sorted(r["branch"] for r in rows if any(r["counts"].get(c) for c in COLS[:5])),
            "totals": {c: sum(r["counts"].get(c, 0) for r in rows) for c in COLS},
        }
    own = next(r for r in load("audit-tips.json")["rows"] if r["branch"] == "exp/own-20g-guard-final-diff-a2-20261003")
    s["own_20g_user_name_in_raw"] = {"tip": own["tip"], "count": own["counts"].get("user-name-in-raw", 0),
                                      "first_commit": (own.get("first_offending_commit") or {}).get("user-name-in-raw")}
    c = "raw/controls/"
    s["controls"] = {
        "plants_green": grab(c + "plants-green-49301c1a2.txt", r"(dummy name caught: .*)"),
        "plants_red_before": grab(c + "plants-red-before-cca59642d.txt", r"(dummy name caught: .*)"),
        "template_unit_runs_ok": (HERE / c / "template-unit.txt").read_text().count("Ran 11 tests"),
        "mutation_unmutated": grab(c + "r2-10-mutation-control.txt", r"unmutated: (rc=\d+ \d+/\d+ checks passed)"),
        "mutation_mutated": grab(c + "r2-10-mutation-control.txt", r"\nmutated: (rc=\d+ \d+/\d+ checks passed; FAIL lines: \d+)"),
    }
    w = "raw/rewrite/"
    s["rewrite"] = {
        "r2_10r_a3": {
            "without_names_file": grab(w + "r2-10r-a3/r2-10r-a3-no-names-file.txt", r"(\d+/\d+) checks passed"),
            "with_names_file": grab(w + "r2-10r-a3/r2-10r-a3-with-names-file.txt", r"(\d+/\d+) checks passed"),
            "red_before_original": grab(w + "r2-10r-a3/r2-10r-red-before-original-c183b95e3.txt", r"(\d+/\d+) checks passed"),
            "privacy_commits_scanned": grab(w + "r2-10r-a3/r2-10r-a3-with-names-file.txt", r"privacy: (\d+) commits"),
        },
        "r2_10_r1c": {
            "without_names_file": grab(w + "r2-10-r1c/r2-10-r1c-no-names-file.txt", r"(\d+/\d+) checks passed"),
            "with_names_file": grab(w + "r2-10-r1c/r2-10-r1c-with-names-file.txt", r"(\d+/\d+) checks passed"),
            "red_before_original": grab(w + "r2-10-r1c/r2-10-red-before-original-36ccdd766.txt", r"(\d+/\d+) checks passed"),
            "ancestor_commits_with_list_or_encoding": sum(
                int(x) for x in re.findall(r"= (\d+)", (HERE / w / "r2-10-r1c/ancestor-check-8f3a646b4.txt").read_text())[1:]),
        },
    }
    return s


def git_checks() -> None:
    for sub, files in (("r2-10r-a3", None), ("r2-10-r1c", None)):
        for line in (RAW / "rewrite" / sub / "sha-map.txt").read_text().splitlines():
            old, new = line.split()
            have = git("cat-file", "-e", f"{old}^{{commit}}").returncode == 0 and git("cat-file", "-e", f"{new}^{{commit}}").returncode == 0
            if not have:
                check(f"rewrite {sub} {old[:9]} -> {new[:9]} (objects not in this clone)", None)
                continue
            diff = git("diff", "--name-only", old, new).stdout.split()
            dates = {git("log", "-1", "--format=%aI", x).stdout.strip() for x in (old, new)}
            ok = (diff == [] if old == new else len(diff) == 1 and diff[0].endswith("/verify_artifacts.py")) and len(dates) == 1
            check(f"rewrite {sub} {old[:9]} -> {new[:9]}: only verify_artifacts.py differs, author date kept", ok, f"{diff} {dates}")
    for sub, orig, head, want in (
            ("r2-10r-a3", "c183b95e35f5af7f2548dec3720b58a65214d9da", "d22eeb2ecf8a679d1425c21120a599775aa0817d",
             ["README.md", "raw/provenance/builds.log", "verify_artifacts.py"]),
            ("r2-10-r1c", "36ccdd766fca9ac2971218245f3539a6c30cf842", "eaca68df9d7f4757028ba787f2e2fa82c92bafe7",
             ["verify_artifacts.py"])):
        if git("cat-file", "-e", f"{orig}^{{commit}}").returncode or git("cat-file", "-e", f"{head}^{{commit}}").returncode:
            check(f"{sub} head tree diff vs {orig[:9]} (objects not in this clone)", None)
            continue
        got = sorted(p.split("/", 3)[3] for p in git("diff", "--name-only", orig, head).stdout.split())
        check(f"{sub} head {head[:9]} vs {orig[:9]}: tree diff is exactly {want}", got == want, f"{got}")
        stat = git("diff", "--stat", orig, head).stdout
        committed = (RAW / "rewrite" / sub / f"diff-stat-vs-{orig[:9]}.txt").read_text()
        check(f"{sub} committed diff --stat equals git diff --stat {orig[:9]} {head[:9]}", stat == committed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-git", action="store_true")
    args = ap.parse_args()
    s = summary()
    committed = json.loads((HERE / "pub02-summary.json").read_text())
    check("pub02-summary.json recomputes identically from raw/", s == committed)
    readme = (HERE / "README.md").read_text()
    for part, rows in tables().items():
        missing = [r[:80] for r in rows if r not in readme]
        check(f"README {part} audit table equals raw/audit/audit-{part}.json ({len(rows) - 2} rows)", not missing, f"{missing[:3]}")
    k = s["controls"]
    check("plant controls (new template): dummy 3/3, abs-path 1/1, encoded list 1/1, clean passes",
          k["plants_green"] == "dummy name caught: 3/3; abs-path plant caught: 1/1; encoded-list plant caught: 1/1; clean template passes: yes")
    check("plant controls red-before (template cca59642d, no privacy scan): 0/3, 0/1, 0/1",
          k["plants_red_before"] == "dummy name caught: 0/3; abs-path plant caught: 0/1; encoded-list plant caught: 0/1; clean template passes: yes")
    check("template unit tests 11/11 OK with and without CUA_PRIVACY_NAMES_FILE", k["template_unit_runs_ok"] == 2
          and (RAW / "controls" / "template-unit.txt").read_text().count("\nOK\n") == 2)
    check("R2-10 mutation control: unmutated 129/129, mutated exactly 2 FAIL (127/129)",
          k["mutation_unmutated"] == "rc=0 129/129 checks passed" and k["mutation_mutated"] == "rc=1 127/129 checks passed; FAIL lines: 2")
    a, b = s["rewrite"]["r2_10r_a3"], s["rewrite"]["r2_10_r1c"]
    check("R2-10R a3 clean-clone verifier 189/189 without and with CUA_PRIVACY_NAMES_FILE (188 + 1 privacy check)",
          a["without_names_file"] == a["with_names_file"] == "189/189" and a["privacy_commits_scanned"] == "16")
    check("R2-10R red-before: the rewritten verifier on the original history fails 2 privacy checks (187/189)",
          a["red_before_original"] == "187/189")
    check("R2-10 r1c clean-clone verifier 133/133 without and with CUA_PRIVACY_NAMES_FILE (132 + 1 privacy check)",
          b["without_names_file"] == b["with_names_file"] == "133/133")
    check("R2-10 red-before: the rewritten verifier on the original r1b history fails 2 privacy checks (131/133)",
          b["red_before_original"] == "131/133")
    check("8f3a646b4 and its local ancestors: 0 commits add or remove the list or any name encoding",
          b["ancestor_commits_with_list_or_encoding"] == 0)
    check("ranges: the three PUB-02 branches carry 0 private findings in every scanned commit",
          not s["audit"]["ranges"]["with_private_finding"])
    if not args.skip_git:
        git_checks()
        cited = check_cited(HERE, "all")
        check("cited files are tracked (verify_helper.check_cited, whole README)", not cited, f"{cited[:5]}")
        leaks = check_privacy(HERE, args.base)
        check(f"privacy: packet files and every commit {args.base[:9]}..HEAD (verify_helper.check_privacy)", not leaks,
              f"{[(f['kind'], f.get('commit', 'checkout'), f['where'], f['detail']) for f in leaks[:10]]}")
    bad = [c for c in CHECKS if c[1] is False]
    skipped = [c for c in CHECKS if c[1] is None]
    for name, ok, detail in CHECKS:
        tag = "SKIP" if ok is None else "PASS" if ok else "FAIL"
        print(f"[{tag}] {name}" + (f"  ({detail})" if detail and ok is False else ""))
    run = len(CHECKS) - len(skipped)
    print(f"{run - len(bad)}/{run} checks passed, {len(skipped)} skipped")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
