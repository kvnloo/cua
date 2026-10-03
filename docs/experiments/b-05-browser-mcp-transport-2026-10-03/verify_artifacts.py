#!/usr/bin/env python3
"""B-05 packet verifier (standard library only).

1. Recomputes the whole summary from raw/ with analyze_b05.analyse and requires it to equal the
   committed b05-summary.json (seeded bootstrap: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim in README.md.
3. Requires every file the packet cites (README.md, PREREG*.json, provenance.json, headline file)
   by a packet-relative path to exist and to be tracked by git (not ignored); fails on any
   ignored-but-cited file. Works from a clean clone.
4. Wave-5 fix pass (derived_checks): recomputes the reworded instrumentation shares, every full E2-sensitivity
   sentence and grid row, the terminal BELOW_GATE / UNTESTED lists, the amends-SHA note, the lane record
   (RESULT.json) and the unreachability of the pre-rewrite commits.
5. Privacy-scans EVERY commit of the branch (base..HEAD): every added/modified blob (tar.gz/gz
   members included), every path, commit message and author/committer identity: no absolute home or
   mount paths, no lane/host names, no secret-like values; hex and base64 literals are decoded and scanned too. Private names are never committed (not even
   encoded): they come from the untracked file named by CUA_PRIVACY_NAMES_FILE, plus the verifying
   host's own name; without that file the name sub-check covers the host name only (a note says so).

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The summary recompute imports the cited harness; never let it write __pycache__ into cited directories
# (a plain `python3 verify_artifacts.py` from a clean clone must pass).
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import analyze_b05 as A  # noqa: E402

BASE = "989cc76cec262ff8bcf6968b637820340fb9caaa"
# Generic patterns first (indices 0-2 are stable for ALLOW); private names follow and are read at verify
# time, never stored in the repository.
GENERIC = [re.compile(r"/home/[A-Za-z0-9_.-]+/"), re.compile(r"/mnt/[A-Za-z0-9_.-]+/"), re.compile(r"/Users/[A-Za-z0-9_.-]+/")]


def _private_names() -> tuple[list[str], str]:
    names = {socket.gethostname()} - {"", "localhost"}
    src = os.environ.get("CUA_PRIVACY_NAMES_FILE", "")
    if src and Path(src).is_file():
        names |= {x.strip() for x in Path(src).read_text().splitlines() if x.strip() and not x.startswith("#")}
        return sorted(names), f"private names: {len(names)} (CUA_PRIVACY_NAMES_FILE + host name)"
    return sorted(names), "private names: CUA_PRIVACY_NAMES_FILE not set; name sub-check covers the host name only"


NAMES, NAMES_NOTE = _private_names()
PRIVATE = GENERIC + [re.compile(re.escape(n)) for n in NAMES]
SECRET = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                                  r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
                                  r"TYPESAFE_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{24,}")]
IDENTITY = {("Kevin Rajan", "7121943+kvnloo@users.noreply.github.com"), ("kvnloo", "7121943+kvnloo@users.noreply.github.com")}
# Upstream content already public (trycua/cua PR 4316 head a0bca7440, merged into R by b10cd09f2):
# a GitHub Actions runner path in a CI workflow and a placeholder key literal in a unit test.
ALLOW = {
    ("a0bca7440", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("b10cd09f2", ".github/workflows/ci-jev-use.yml", "private#0"),
    ("a0bca7440", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
    ("b10cd09f2", "libs/cua-driver/examples/jev-use/typescript/run_guarded_completion.test.ts", "secret#5"),
}
CITE = re.compile(r"(?<![A-Za-z0-9_./-])((?:raw|harness)/[A-Za-z0-9_./-]+[A-Za-z0-9_-])")
FILE_EXT = (".py", ".rs", ".sh", ".json", ".jsonl", ".gz", ".txt", ".md")
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, check=True).stdout


HEX_LIT = re.compile(r"(?<![0-9A-Za-z])(?:[0-9a-fA-F]{2}){3,}(?![0-9A-Za-z])")
B64_LIT = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])")


def decoded_literals(text: str) -> str:
    """Hex and base64 literals decoded to text, so an encoded private name is still found."""
    out: list[str] = []
    for m in HEX_LIT.finditer(text):
        try:
            out.append(bytes.fromhex(m.group(0)).decode("utf-8", errors="ignore"))
        except ValueError:
            pass
    for m in B64_LIT.finditer(text):
        s = m.group(0)
        try:
            out.append(base64.b64decode(s + "=" * (-len(s) % 4), validate=True).decode("utf-8", errors="ignore"))
        except (ValueError, binascii.Error):
            pass
    return "\n".join(out)


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
    return out + [(f"{w}:decoded", decoded_literals(x)) for w, x in out]


def privacy_scan(base: str) -> None:
    commits = git("rev-list", f"{base}..HEAD").decode().split()
    hits: list[str] = []
    secret_hits: list[str] = []
    bad_ident: list[str] = []
    allowed: list[str] = []
    blobs = 0
    for c in commits:
        meta = git("show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", c).decode(errors="replace").split("\x00")
        if (meta[0], meta[1]) not in IDENTITY or (meta[2], meta[3]) not in IDENTITY:
            bad_ident.append(f"{c[:9]} {meta[0]} / {meta[2]}")
        targets = [("commit-message", meta[4]), ("commit-message:decoded", decoded_literals(meta[4]))]
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
            for i, pat in enumerate(PRIVATE):
                if pat.search(text):
                    (allowed if (c[:9], where.removesuffix(":decoded"), f"private#{i}") in ALLOW else hits).append(f"{c[:9]} {where[:120]} private#{i}")
            for i, pat in enumerate(SECRET):
                if pat.search(text):
                    (allowed if (c[:9], where.removesuffix(":decoded"), f"secret#{i}") in ALLOW else secret_hits).append(f"{c[:9]} {where[:120]} secret#{i}")
    check("privacy: no absolute local paths / lane or host names in any commit", not hits,
          f"{len(commits)} commits, {blobs} blobs; hits: {hits[:10]}")
    check("privacy: no secret-like values in any commit", not secret_hits, f"hits: {secret_hits[:10]}")
    check("privacy: author/committer identity", not bad_ident, f"bad: {bad_ident[:10]}")
    print(f"privacy: {len(commits)} commits, {blobs} blobs scanned; allowlisted upstream content: {sorted(set(allowed))}")


def cited_files_tracked() -> None:
    texts = [p for p in ("README.md", "PREREG.json", "PREREG-AMENDMENT-1.json", "provenance.json",
                         "headline-numbers.json", "RESULT.json") if (HERE / p).exists()]
    cited: set[str] = set()
    for name in texts:
        for m in CITE.findall((HERE / name).read_text()):
            m = m.rstrip(".")
            # a file path has a known extension; an extension-less token counts only as a directory
            if m.endswith(FILE_EXT) or (HERE / m).is_dir() or "." not in Path(m).name and m.count("/") > 1:
                cited.add(m)
    try:
        tracked = set(git("ls-files", "--", ".").decode().split())
        ignored = set(git("ls-files", "--others", "--ignored", "--exclude-standard", "--", ".").decode().split())
    except subprocess.CalledProcessError:
        tracked, ignored = None, set()
    missing, untracked, ign = [], [], []
    for c in sorted(cited):
        p = HERE / c
        if not p.exists():
            missing.append(c)
            continue
        # interpreter bytecode caches are build output, not cited content
        files = [p] if p.is_file() else [q for q in p.rglob("*") if q.is_file() and "__pycache__" not in q.parts]
        for q in files:
            rel = str(q.relative_to(HERE))
            if rel in ignored:
                ign.append(rel)
            elif tracked is not None and rel not in tracked:
                untracked.append(rel)
    check("cited files exist", not missing, f"missing: {missing[:10]}")
    check("no cited file is git-ignored", not ign, f"ignored: {ign[:10]}")
    check("every cited file is tracked", not untracked, f"untracked: {untracked[:10]}")
    print(f"cited paths checked: {len(cited)}")


CLS = ("fill", "toggle", "modal")
PRE_REWRITE = ("d1b42db63", "3cced771f", "92cab8900")


def flat(s: str) -> str:
    return " ".join(s.split())


def need(name: str, text: str, readme_flat: str) -> None:
    check(name, flat(text) in readme_flat, f"not in README: {text!r}")


def derived_checks(s: dict, readme: str, skip_git: bool) -> None:
    """Wave-5 fix pass: every reworded number and every full E2-sensitivity row is recomputed here."""
    rf = flat(readme)
    sc = s["e2_sensitivity"]["scales"]
    pa = s["phase_A"]["by_class"]

    def shares(group: str, scale: float) -> list[float]:
        out = []
        for c in CLS:
            g = pa[c]["groups"][group]
            out.append(100 * (g["raw"]["mean"] - g["corr"]["mean"]) * scale / g["raw"]["mean"])
        return out

    j = lambda xs, f="{:.0f}": " / ".join(f.format(x) for x in xs)  # noqa: E731
    rows = {"transport_in_out": None, "admission_residual": None, "resolution": None}
    for g in rows:
        a, b = shares(g, 1.0), shares(g, sc["x_pooled"])
        need(f"instrumentation share row {g}", f"| {g} | {j(a)}% | {j(b)}% | BENCHMARK+REAL |", rf)
        rows[g] = (a, b)
    ta, tb = rows["transport_in_out"]
    aa, ab = rows["admission_residual"]
    need("disposition: transport share at c_m", f"transport in/out is {j(ta)}% instrumentation", rf)
    need("disposition: transport share at measured scale", f"about {j(tb)}% when the correction is scaled", rf)
    need("disposition: admission share", f"{j(aa)}% at c_m, about {j(ab)}% at the measured scale", rf)
    check("disposition: transport is not mostly instrumentation (all classes < 50% at c_m)", max(ta) < 50, str(ta))
    check("disposition: admission is mostly instrumentation (all classes > 50% at both scales)",
          min(aa) > 50 and min(ab) > 50, f"{aa} {ab}")
    check("disposition: the c_m/x_pooled ranges quoted match (81-88%, ~55-60%)",
          round(min(aa)) == 81 and round(max(aa)) == 88 and 55 <= round(min(ab)) and round(max(ab)) <= 60, f"{aa} {ab}")
    ovh_m = s["overhead_control"]["by_class"]["modal"]["T_runner_ms"]["mean_diff"]
    raw_m = pa["modal"]["groups"]["transport_in_out"]["raw"]["mean"]
    check("modal ruled out by the overhead control (whole penalty < half of raw transport)", ovh_m / raw_m < 0.5,
          f"{ovh_m}/{raw_m}")
    need("modal overhead sentence", f"({ovh_m:.2f} ms) is {100 * ovh_m / raw_m:.0f}% of raw modal transport ({raw_m:.2f} ms)", rf)
    check("README no longer says most of transport was instrumentation",
          "time was the phase-trace instrumentation itself" not in rf and "Most of R2-10's" not in rf)
    need("cross-binary statement", "any comparison with R2-10's numbers is cross-binary", rf)
    # E2 sensitivity: full sentences and every full grid row (replaces the wave-4 loose fragments)
    es = s["e2_sensitivity"]
    pred = [s["overhead_control"]["by_class"][c]["predicted_overhead_ms"] for c in CLS]
    meas = [s["overhead_control"]["by_class"][c]["T_runner_ms"]["mean_diff"] for c in CLS]
    ratio = [es["measured_over_predicted"][c] for c in CLS]
    need("sensitivity: predicted/measured/ratio sentence",
         f"The predicted instrumentation cost (marks × c_m) is {j(pred, '{:.2f}')} ms, but the overhead control "
         f"measured {j(meas, '{:.2f}')} ms, i.e. {j(ratio, '{:.3f}')} of the prediction.", rf)
    need("sensitivity: scale sentence",
         f'"x_pooled" scales c_m by the pooled ratio {sc["x_pooled"]:.3f} (c_m {es["by_scale"]["x_pooled"]["c_m_us"]:.1f} us) '
         f'and "x_min" by {sc["x_min"]:.3f} (c_m {es["by_scale"]["x_min"]["c_m_us"]:.1f} us).', rf)
    T = es["by_scale"]["x1"]["T_runner_corr_mean_ms"]
    la = es["loadavg_1m_mean"]
    need("sensitivity: load sentence",
         f"(O1, same binary and arm, loadavg {la['O1']:.1f}) have corrected T_runner {j([T['O1_COMP'][c] for c in CLS], '{:.1f}')} ms "
         f"against Phase A's {j([T['phase_A'][c] for c in CLS], '{:.1f}')} ms", rf)
    labels = {"lane_rules": "lane", "below_gate_untested": "no BG", "invariant_rule_off": "no inv", "both_lane_rules_off": "neither"}
    for rs, first in (("phase_A", f"Phase A (load {la['phase_A']:.1f})"), ("O1_COMP", f"O1 COMP (load {la['O1']:.1f})")):
        for k, (rule, lab) in enumerate(labels.items()):
            name = first if k == 0 else ("Phase A" if rs == "phase_A" else "O1 COMP")
            cells = [j([es["by_scale"][x]["untested_share"][f"{rs}:{rule}"][c] for c in CLS], "{:.1%}").replace("%", "") + "%"
                     for x in ("x1", "x_pooled", "x_min")]
            need(f"sensitivity grid row {rs}:{rule}", f"| {name} | {lab} | " + " | ".join(cells) + " |", rf)
    # terminal verdicts: the BELOW_GATE list is exactly the summary's BELOW_GATE rows
    bg = sorted({k.removeprefix("f.") + ("" if all(v == "BELOW_GATE" for v in vs.values()) else " (" + ", ".join(c for c in CLS if vs[c] == "BELOW_GATE") + ")")
                 for k, vs in s["verdicts"].items() if any(v == "BELOW_GATE" for v in vs.values())})
    line = next((l for l in readme.splitlines() if l.startswith("| adm.inner (fill, modal), adm.outer")), "")
    listed = sorted(x.strip() for x in re.split(r",\s+(?![^()]*\))", line.split("|")[1])) if line else []
    check("terminal table: BELOW_GATE list equals the summary's BELOW_GATE rows", listed == bg, f"listed {listed} vs {bg}")
    unt = sorted(f"{k.removeprefix('f.')}:{c}" for k, vs in s["verdicts"].items() for c in CLS if vs[c].startswith("UNTESTED"))
    want = sorted([f"{x}:{c}" for x in ("c_in.prep", "c_out.route", "d_out.post") for c in CLS] + ["adm.inner:toggle"])
    check("terminal table: UNTESTED rows are exactly c_in.prep, c_out.route, d_out.post, toggle adm.inner", unt == want, str(unt))
    for x in ("PARSE_FAST", "VALIDATE_FAST"):
        means = [s["phase_B"][x]["by_class"][c]["caller_ms"]["mean_diff"] for c in CLS] if "mean_diff" in s["phase_B"][x]["by_class"]["fill"]["caller_ms"] else []
        check(f"{x}: KILL (every class mean work deleted < 0.5 ms)", means and max(means) < 0.5, str(means))
    need("terminal table: candidates KILL", '| PARSE_FAST (c_out.parse candidate) | KILL ("reducible, below gate")', rf)
    need("c_in.prep F1 floor cited", "Its F1 floor (the same mcp client stack replaying recorded frames) is 0.33 ms per task", rf)
    need("Phase A load stated as a limit", "**Phase A load is a limit.** Phase A (the attribution chunk A1) ran at a mean 1-minute loadavg of 13.8", rf)
    need("malformed-frame scope stated", "Scope: this control exercises the frame parser only", rf)
    # amends note, lane record, unreachable pre-rewrite commits
    am = json.loads((HERE / "PREREG-AMENDMENT-1.json").read_text())["amends"]
    prov = json.loads((HERE / "provenance.json").read_text())
    check("amends SHA note: amendment cites 3cced771f, mapped to 03f52d7eb in provenance and README",
          "3cced771f" in am and prov["shas"]["amends_sha_map"]["3cced771f"].startswith("03f52d7eb")
          and "it maps to 03f52d7eb" in rf)
    res = json.loads((HERE / "RESULT.json").read_text())
    check("lane record: REVISE, E2 borderline / not established, no pre-rewrite SHA as a lane commit",
          res["disposition"] == "REVISE" and "borderline / not established" in res["e2"]
          and not any(p in json.dumps(res["lane_commits"]) for p in PRE_REWRITE)
          and "met for fill" not in json.dumps(res), "")
    check("lane record: 5 near misses (4 attempt 2 + 1 fix pass), matching README deviation 6",
          len(res["near_misses"]) == 5 and "adds a fifth one" in rf, str(len(res["near_misses"])))
    check("lane record: provider 0/0", res["provider"] == {"attempts": 0, "reached": 0})
    if not skip_git:
        reach = git("rev-list", "HEAD").decode().split()
        check("pre-rewrite commits d1b42db63 / 3cced771f / 92cab8900 are not reachable from HEAD",
              not [r for r in reach if r.startswith(PRE_REWRITE)], "")


def walk(obj, path):  # noqa: ANN001, ANN201
    for key in path.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--skip-git", action="store_true")
    args = p.parse_args()
    recomputed = json.loads(json.dumps(A.analyse(HERE / "raw"), sort_keys=True, default=str))
    committed = json.loads((HERE / "b05-summary.json").read_text())
    check("summary recomputes identically from raw/", recomputed == committed, "" if recomputed == committed else "differs")
    hp = HERE / "headline-numbers.json"
    if hp.exists():
        readme = (HERE / "README.md").read_text()
        for h in json.loads(hp.read_text())["numbers"]:
            val = walk(recomputed, h["path"])
            shown = h["format"].format(*val) if isinstance(val, list) else h["format"].format(val)
            check(f"headline {h['id']} = {shown}", shown == h["text"] and h["text"] in readme,
                  f"recomputed {shown!r}, listed {h['text']!r}, in README {h['text'] in readme}")
    derived_checks(recomputed, (HERE / "README.md").read_text(), args.skip_git)
    for f in sorted((HERE / "raw").rglob("*")):
        if f.is_file():
            for where, text in texts_of_blob(str(f.relative_to(HERE)), f.read_bytes()):
                if any(pat.search(text) for pat in PRIVATE):
                    check(f"raw privacy {where[:100]}", False, "private string in raw file")
    print(NAMES_NOTE)
    if not args.skip_git:
        cited_files_tracked()
        privacy_scan(args.base)
    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
