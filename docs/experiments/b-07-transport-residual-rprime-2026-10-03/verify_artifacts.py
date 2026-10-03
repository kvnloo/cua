#!/usr/bin/env python3
"""B-07 packet verifier (standard library only; run it under the lane's hostless wrapper).

1. Recomputes the whole summary from raw/ with analyze_b07.analyse and requires it to equal the
   committed b07-summary.json (seeded bootstrap: deterministic).
2. Requires every headline number in headline-numbers.json to equal its recomputed value and to
   appear verbatim (whitespace-normalised) in README.md; derived checks recompute the verdict tables,
   the E2 rows and the claims the README states.
3. Requires every file the packet cites to exist and be tracked by git (not ignored), and runs the
   PKT-01 template's verify_helper.py (cca59642d) over the packet.
4. Privacy-scans EVERY commit of the branch after R' (45dff8f32..HEAD): every added/modified blob
   (tar.gz/gz members included, hex and base64 literals decoded), every path, commit message and
   author/committer identity: no absolute home or mount paths, no host/user names, no secret-like
   values. Private names are never committed: they come from the untracked file named by
   CUA_PRIVACY_NAMES_FILE, plus the verifying host's own name. Only the fork owner's public GitHub
   handle is removed before the name patterns run.

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
import analyze_b07 as A  # noqa: E402

BASE = "45dff8f3227a21ff8bef1af4bf4c2bcbd9449b2a"  # R'; every lane commit after it is scanned
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
# The public GitHub handle of the fork owner (kvnloo/cua#N references, commit identity) can contain a
# private name as a substring. Only that exact handle is removed before the NAME patterns run; the
# generic home/mount path patterns always see the full text.
PUBLIC_HANDLE = re.compile(r"kvnloo")


def private_hit(i: int, pat: re.Pattern, text: str) -> bool:
    return bool(pat.search(text if i < len(GENERIC) else PUBLIC_HANDLE.sub("", text)))
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
B64_LIT = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{4,}={0,2}(?![A-Za-z0-9+/=])")


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
                if private_hit(i, pat, text):
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
                         "headline-numbers.json", "RESULT.json", "PREREG-AMENDMENT-1.json") if (HERE / p).exists()]
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


# ── B-07 table rendering (README tables are generated from the summary by this function) ──
CLS = ("fill", "toggle", "modal")
PRE_REWRITE = ()


def flat(s: str) -> str:
    return " ".join(s.split())


def f2(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def ci(c: list | None) -> str:
    return "n/a" if not c else f"[{c[0]:.2f}, {c[1]:.2f}]"


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render_rows(S: dict) -> dict[str, list[str]]:
    """Every README table row that carries a number or a verdict."""
    out: dict[str, list[str]] = {}
    pa = S["phase_A"]["by_class"]
    rows = []
    for g in ("transport_in_out", "admission_residual", "resolution", "client_validation"):
        cells = [f"{f2(pa[c]['groups'][g]['raw']['mean'])} / {f2(pa[c]['groups'][g]['corr']['mean'])} {ci(pa[c]['groups'][g]['corr']['ci95'])}" for c in CLS]
        rows.append(f"| {g} | " + " | ".join(cells) + " | BENCHMARK+REAL |")
    out["groups"] = rows
    rows = []
    V = S["verdicts"]
    for u in ("c_in.prep", "c_out.route", "d_out.post", "adm.inner", "adm.outer", "c_in.serialize", "write_pipe_in",
              "pipe_out_frame", "c_out.parse", "c_out.result_model", "c_out.validate", "c_out.return", "d_in.parse",
              "d_in.invoke", "d_out.serialize", "d_out.write_flush"):
        cells = [f"{f2(pa[c]['units'][u]['raw']['mean'])} / {f2(pa[c]['units'][u]['corr']['mean'])} {ci(pa[c]['units'][u]['corr']['ci95'])}" for c in CLS]
        vs = [V["units"][u][c] for c in CLS]
        vtxt = vs[0] if len(set(vs)) == 1 else " / ".join(vs)
        rows.append(f"| {u} | " + " | ".join(cells) + f" | {vtxt} | BENCHMARK+REAL (A1) |")
    out["units"] = rows
    rows = []
    for k in ("res.dispatch", "res.ref_parse", "res.store_lookup", "res.frame_proof", "res.type_focus",
              "res.cdp_node_resolve", "res.editable_check", "res.post_check"):
        cells = []
        for c in CLS:
            t = pa[c]["subspans"].get(k)
            cells.append("absent" if t is None else f"{f2(t['corr']['mean'])} {ci(t['corr']['ci95'])}")
        vs = [V["resolution"][k][c] for c in CLS if V["resolution"][k][c] != "ABSENT"]
        vtxt = vs[0] if len(set(vs)) == 1 else " / ".join(vs)
        cls_ = "BENCHMARK+REAL (A1); invariant SOURCE" if vtxt.startswith("IRREDUCIBLE") else "BENCHMARK+REAL (A1)"
        rows.append(f"| {k} | " + " | ".join(cells) + f" | {vtxt} | {cls_} |")
    out["resolution"] = rows
    rows = []
    for arm, pb in sorted(S["phase_B"].items()):
        for c in CLS:
            b = pb["by_class"][c]
            to, tr, w = b["T_oracle_ms"], b["T_runner_ms"], b[pb["work_metric"]]
            v = V["candidates"][arm][c]
            rows.append(f"| {arm} | {c} | {to['n_pairs']} | {f2(to['mean_diff'])} {ci(to['ci95'])} | "
                        f"{f2(tr['mean_diff'])} {ci(tr['ci95'])} | {f2(w['mean_diff'])} {ci(w['ci95'])} | "
                        f"{v['candidate']} | {v['target_verdict']} | BENCHMARK+REAL |")
    out["phase_B"] = rows
    rows = []
    for c in CLS:
        e = S["e2"][c]
        cells = []
        for k in ("corr:below_gate_as_irreducible", "corr:below_gate_as_untested", "raw:below_gate_as_irreducible",
                  "raw:below_gate_as_untested"):
            cells.append(f"{pct(e[k]['a_r2_10_carry_over']['untested_share'])} / {pct(e[k]['b_b04_cold_excess_untested']['untested_share'])}")
        rows.append(f"| {c} | " + " | ".join(cells) + f" | {f2(e['corr:below_gate_as_irreducible']['a_r2_10_carry_over']['mean_T_ms'])} | BENCHMARK+REAL (A1) |")
    out["e2"] = rows
    oc = S["overhead_control"]["by_class"]
    out["overhead"] = [f"| {c} | {oc[c]['T_runner_ms']['n_pairs']} | {f2(oc[c]['T_runner_ms']['mean_diff'])} {ci(oc[c]['T_runner_ms']['ci95'])} | "
                       f"{f2(oc[c]['T_oracle_ms']['mean_diff'])} {ci(oc[c]['T_oracle_ms']['ci95'])} | {f2(oc[c]['predicted_overhead_ms'])} | "
                       f"{f2(oc[c]['measured_over_predicted'])} | BENCHMARK+REAL |" for c in CLS]
    return out


def derived_checks(S: dict, readme: str, skip_git: bool) -> None:
    rf = flat(readme)
    for name, rows in render_rows(S).items():
        for i, row in enumerate(rows):
            check(f"README table {name} row {i + 1}", flat(row) in rf, row)
    amend = json.loads((HERE / "PREREG-AMENDMENT-1.json").read_text())
    pa = S["phase_A"]["by_class"]
    sel = sorted(a for a, t in A.CANDIDATE_TARGET.items()
                 if any(pa[c]["units"][t]["corr"]["mean"] >= 0.5 for c in CLS))
    check("selection rule reproduces PREREG-AMENDMENT-1 'selected'", sel == sorted(amend["selected"]), f"{sel} vs {amend['selected']}")
    check("Phase A: 96 valid, coverage >= 0.98 on every trial", S["phase_A"]["valid"] == 96 and not S["phase_A"]["coverage_below_0_98"]
          and S["phase_A"]["coverage_b05_min"] >= 0.98)
    sm = S["smoke"]
    ok = all(sm[k]["n"] == 15 and sm[k]["verified"] == 15 and sm[k]["exp_env"] == ["{}"] for k in ("D-B7", "D-Rp")) and all(
        sm["D-B7"]["by_class_shapes"][c] == sm["D-Rp"]["by_class_shapes"][c] and sm["D-B7"]["by_class_routes"][c] == sm["D-Rp"]["by_class_routes"][c]
        for c in CLS)
    check("default-off smoke: B7 and R' 15/15 each, identical receipt shapes and routes per class, no EXP env", ok)
    for arm in amend["selected"]:
        eq = S["equivalence"][arm]
        check(f"{arm}: N4a 15/15 in the arm", A.n4a_ok(S, arm))
        check(f"{arm}: requests byte-identical and responses decoded-identical in every trial",
              eq["requests_different"] == 0 and eq["trials_responses_decoded_identical"] == eq["trials"])
        check(f"{arm}: negative/fallback control passes", S["negative"][arm]["all_rejected"] is True)
    q = S["equivalence"]["POST_FAST"]
    check("as stated (Deviation 3): PREP_FAST equivalence 100%; POST_FAST structure 89 of 90, so its equivalence is not 100%",
          S["equivalence"]["PREP_FAST"]["all_equal"] is True and q["all_equal"] is False
          and (q["structure_pairs_identical"], q["structure_pairs"]) == (89, 90)
          and "89 of 90" in rf)
    for arm in amend["selected"]:
        for c in CLS:
            v = S["verdicts"]["candidates"][arm][c]["candidate"]
            s0 = S["phase_B"][arm]["by_class"][c]["sensitivity_without_round0_T_oracle_ms"]["gate_pass"]
            check(f"{arm}/{c}: round-0 sensitivity fails the gate (as stated)", s0 is False)
            if v.startswith("DELETED"):
                check(f"{arm}/{c}: DELETED is reported as fragile", "DELETED (fragile)" in rf)
    check("COMP_OFF: N4a 15/15", A.n4a_ok(S, "COMP_OFF"))
    e4 = [v for v in S["e4"].values()]
    check("E4: 0 stale dispatch / duplicate / unverified success / refusal-as-success in every arm",
          all(all(not x for k, x in d.items() if isinstance(x, (int, float)) and k != "n") for d in e4), json.dumps(S["e4"])[:300])
    # timing order and lock evidence
    led = [json.loads(x) for x in (HERE / "raw" / "locks" / "quiet-lane-ledger-b07.jsonl").read_text().splitlines() if x.strip()]
    labels = {x["label"] for x in led if x.get("mode") != "shared"}  # quiet-timed receipts = EXCLUSIVE
    measured = [k for k in S["chunks"] if k[0] in "AOPQN"]
    check("every measured chunk has an EXCLUSIVE quiet-timed receipt", all(k in labels for k in measured), str(sorted(set(measured) - labels)))
    if not skip_git:
        def ctime(path: str) -> str:
            return git("log", "--diff-filter=A", "--format=%cI", "--", str(HERE / path)).decode().split()[-1]
        from datetime import datetime
        t_pre = datetime.fromisoformat(ctime("PREREG.json"))
        t_am = datetime.fromisoformat(ctime("PREREG-AMENDMENT-1.json"))
        starts = {x["label"]: datetime.fromisoformat(x["acquired"].replace("Z", "+00:00")) for x in led}
        check("PREREG committed before the first measured chunk", all(starts[k] > t_pre for k in measured if k in starts))
        check("PREREG-AMENDMENT-1 committed before every Phase B / N4a chunk",
              all(starts[k] > t_am for k in measured if k in starts and k[0] in "PQN"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    p.add_argument("--skip-git", action="store_true")
    args = p.parse_args()
    recomputed = json.loads(json.dumps(A.analyse(HERE / "raw"), sort_keys=True, default=str))
    committed = json.loads((HERE / "b07-summary.json").read_text())
    check("summary recomputes identically from raw/", recomputed == committed, "" if recomputed == committed else "differs")
    readme = (HERE / "README.md").read_text()
    hp = HERE / "headline-numbers.json"
    if hp.exists():
        for h in json.loads(hp.read_text())["numbers"]:
            val = walk(recomputed, h["path"])
            shown = h["format"].format(*val) if isinstance(val, list) else h["format"].format(val)
            check(f"headline {h['id']} = {shown}", shown == h["text"] and flat(h["text"]) in flat(readme),
                  f"recomputed {shown!r}, listed {h['text']!r}")
    derived_checks(recomputed, readme, args.skip_git)
    for f in sorted((HERE / "raw").rglob("*")):
        if f.is_file():
            for where, text in texts_of_blob(str(f.relative_to(HERE)), f.read_bytes()):
                if any(private_hit(i, pat, text) for i, pat in enumerate(PRIVATE)):
                    check(f"raw privacy {where[:100]}", False, "private string in raw file")
    print(NAMES_NOTE)
    if not args.skip_git:
        cited_files_tracked()
        import verify_helper
        bad = verify_helper.check_cited(HERE)
        check("PKT-01 verify_helper: no ignored or untracked cited path", not bad, str(bad[:5]))
        privacy_scan(args.base)
    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


def walk(obj, path):  # noqa: ANN001, ANN201
    for key in path.split("."):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


if __name__ == "__main__":
    main()
