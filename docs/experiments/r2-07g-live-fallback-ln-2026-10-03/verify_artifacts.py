#!/usr/bin/env python3
"""R2-07g packet verifier.

1. Identity: the R2-07c, R2-07d and R2-07e packet directories (harness, runners, analyses, raw/) are
   tree-identical at every commit of this branch to the base (PREREG source.identity); the
   pre-registered gate functions in analyze_r2_07g.py (t_gate, lf_gate, false_success, e2_mapping and
   their constants) are unchanged since the PREREG commit.
2. PREREG.json was committed before the first measured trial (commit time < earliest Q/L trial start).
3. Recomputes r2-07g-summary.json (analyze_r2_07g.analyze) from raw/ and requires it to equal the
   committed file (seeded bootstrap: deterministic).
4. Every number in headline-numbers.json equals its recomputed value and appears verbatim in README.md.
5. Every compiled artifact in raw/artifacts/ passes compiled_routine_tm.check_artifact_authority_tm.
6. Every file the packet cites (top-level files, driver/, raw/, and packet-relative paths in README.md)
   is tracked and not git-ignored; no untracked file under raw/.
7. Privacy over EVERY commit of the branch (67b99ddc6..HEAD): every added/modified blob (tar.gz members
   included), path, commit message and author/committer identity: no absolute home/mount paths, no
   host or user names (from the untracked CUA_PRIVACY_NAMES_FILE plus the host name), no secret-like
   values; names are matched on word boundaries; hex and base64 runs are decoded and scanned too; a
   committed list of encoded name-like strings fails.
8. Provider: raw/provider-ledger.jsonl attempts/reached within the lane cap (16 reached / 20 attempts),
   no blocked_by_cap line, the summary's counts equal the ledger, every attempt is attributed to an L2
   live invocation (LF/LN), and per-trial ledger lines equal the trial's counted requests.
9. Gates: the H_T, H_LF and E2 verdicts in the summary equal the pre-registered functions applied to
   the recomputed rows, and Binary R identity (name/sha256/version) is in every trial record and manifest.

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
PKT = "docs/experiments/r2-07g-live-fallback-ln-2026-10-03"
R207E = "docs/experiments/r2-07e-modal-gate-phase-l-2026-10-03"
R207D = "docs/experiments/r2-07d-quiet-timing-phase-l-2026-10-03"
R207C = "docs/experiments/r2-07c-toggle-modal-compiled-2026-10-03"
BASE = "67b99ddc6a66a217c76dc491977de78180434751"
PREREG_SHA = "721b461db1d69b4346bf29d2b863f3a3991fe539"
IDENTITY_PATHS = {R207C: "77b5128e435a24282f76238ac0558fc590659276",
                  f"{R207C}/harness": "66bad345b1736b97b66884bbf40a1505c16083bf",
                  R207D: "90e0c0d875e12f592c7099ed5bc3570c11b8339e",
                  f"{R207D}/driver/r2_07d.py": "0989b68bc57d8fc16de3c0ab2cf80c61cd6bd334",
                  R207E: "8c3901b1d660a760a1d0e34281cd43d1e26d2dcb",
                  f"{R207E}/driver/r2_07e.py": "27d850be87d83189cbe0c02f77c6746af72e4a4f"}
DRIVER_SHA256 = "12b9045aafddd208c7aeb7e49d5a2e5ab7e776c07ec6d7bd62322807291458a9"
CAP = (16, 20)
GATE_FNS = ("t_gate", "lf_gate", "false_success", "e2_mapping")
GATE_CONSTS = ("T_ROUNDS", "GATE_MS", "LF_PLANNED", "LANE_CAP")
TOP = ["README.md", "PREREG.json", "provenance.json", "r2-07g-summary.json", "headline-numbers.json",
       "analyze_r2_07g.py", "verify_artifacts.py", ".gitignore", "driver/r2_07g.py", "driver/run_chunk_g.sh",
       "driver/test_r2_07g.py", "driver/package_g.py"]
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
    want = dict(IDENTITY_PATHS)
    bad = []
    for c in commits:
        for p, v in want.items():
            got = git("rev-parse", f"{c}:{p}", ok=False).decode().strip()
            if got != v:
                bad.append(f"{c[:9]} {p} {got[:12]}")
    check("identity: R2-07c (harness tree 66bad345), R2-07d and R2-07e packet trees unchanged at every commit",
          not bad, f"{len(commits)} commits; {len(want)} paths; bad: {bad[:6]}")
    import ast
    def gate_src(blob: bytes) -> str:
        tree = ast.parse(blob.decode())
        fns = [ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in GATE_FNS]
        consts = {t.id: ast.dump(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  for t in n.targets if isinstance(t, ast.Name) and t.id in GATE_CONSTS}
        return json.dumps([fns, consts], sort_keys=True) if len(fns) == len(GATE_FNS) else "missing"
    pre = gate_src(git("show", f"{PREREG_SHA}:{PKT}/analyze_r2_07g.py"))
    now = gate_src((HERE / "analyze_r2_07g.py").read_bytes())
    check("pre-registered gate functions and constants unchanged since the PREREG commit",
          pre == now and pre != "missing", f"{PREREG_SHA[:9]}: {', '.join(GATE_FNS)}")


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


def gate_checks(S: dict, att: list) -> None:
    """Recompute the pre-registered verdicts from the recomputed rows; provider attribution; Driver identity."""
    import analyze_r2_07g as AG  # noqa: E402

    T, L = S["part_T"], S["part_L2"]
    tg = T["timing"]
    ci = (tg.get("diff_COMP_CR_minus_COMP_ms") or {}).get("ci95")
    h_t = bool(ci and ci[1] <= AG.GATE_MS and not tg["failed_pairs"] and not tg["not_run_rounds"]
               and tg["valid_pairs"] == AG.T_ROUNDS)
    check("H_T recomputed: 95% CI upper <= +2.0 ms, 40/40 pairs valid", (S["disposition"]["H_T"] == "PASS") == h_t,
          f"H_T {S['disposition']['H_T']}; ci95 {ci}; valid {tg['valid_pairs']}/40")
    lf = L["LF"] + [None] * len(L["LF_not_run"])
    g = AG.lf_gate(lf)
    e2 = AG.e2_mapping(g["pass"])
    check("H_LF and the E2 mapping recomputed from the LF rows",
          g == L["LF_gate"] and (S["disposition"]["H_LF"] == "PASS") == g["pass"]
          and S["e2"] == e2 and S["disposition"]["modal_lineage"] == e2["modal_lineage"],
          f"LF {g['verified']}/{g['planned']} verified; E2 {e2['live_modal_provider_decision_component']}")
    live_trials = {r["trial"] for r in L["LF"] + ([L["LN"]] if L["LN"] else [])}
    per_trial = {}
    for x in att:
        per_trial[x.get("trial")] = per_trial.get(x.get("trial"), 0) + 1
    rows = L["LF"] + ([L["LN"]] if L["LN"] else [])
    ok = set(per_trial) <= live_trials and all(per_trial.get(r["trial"], 0) == (r["requests"] or {}).get("attempts")
                                                for r in rows)
    check("every provider attempt belongs to an L2 live invocation; per-trial lines equal counted requests", ok,
          f"ledger trials {sorted(per_trial.items())}")
    import tarfile
    bad, n, n_cr, listed, all_names = [], 0, 0, set(), set()
    for tgz in sorted((HERE / "raw").glob("*-trials.tar.gz")):
        if tgz.name.startswith("shake"):
            continue
        with tarfile.open(tgz, "r:gz") as tar:
            for m in tar.getmembers():
                if not m.isfile() or not m.name.endswith(".jsonl") or m.name.endswith(".driver-trace.jsonl"):
                    continue
                all_names.add(Path(m.name).name[:-6])
                lines = [json.loads(x) for x in tar.extractfile(m).read().decode().splitlines() if x.strip()]
                n += 1
                if "-COMP_CR-" not in m.name:
                    continue  # rb10.one (COMP, smoke) records carry no identity field: covered by the manifest below
                n_cr += 1
                summ = next((x for x in lines if x.get("driver_sha256")), None)
                if not summ or summ.get("driver_sha256") != DRIVER_SHA256 or summ.get("driver_version") != "cua-driver 0.32.0":
                    bad.append(m.name)
                listed.add(Path(m.name).name[:-6])
    mans = [p for p in (HERE / "raw").glob("*-manifests/*.json") if not p.parent.name.startswith("shake")]
    in_manifest = set()
    for p in mans:
        man = json.loads(p.read_text())
        if man.get("driver_sha256") != DRIVER_SHA256 or man.get("driver_version") != "cua-driver 0.32.0":
            bad.append(p.name)
        in_manifest |= {u for x in man.get("units_run", []) for u in x.get("trials", [])}
        in_manifest |= set(man.get("trials", []))
    check("binary R identity: every COMP_CR record carries sha256 + version; every manifest does; every trial is "
          "listed by a manifest", n > 0 and not bad and not (all_names - in_manifest - listed),
          f"{n} records ({n_cr} COMP_CR), {len(mans)} manifests; bad: {bad[:6]}; unlisted: "
          f"{sorted(all_names - in_manifest - listed)[:6]}")


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
        import analyze_r2_07g as AG  # noqa: E402

        summary = json.loads((HERE / "r2-07g-summary.json").read_text())
        fresh = json.loads(json.dumps(AG.analyze(HERE / "raw"), sort_keys=True, default=AG.default))
        check("r2-07g-summary.json recomputes from raw/", fresh == summary,
              "" if fresh == summary else f"differs in keys: {[k for k in summary if summary.get(k) != fresh.get(k)][:8]}")
        heads = json.loads((HERE / "headline-numbers.json").read_text())
        readme = (HERE / "README.md").read_text()
        recomputed = AG.headlines(fresh)
        bad = [k for k, v in heads.items() if recomputed.get(k) != v]
        absent = [k for k, v in heads.items() if v["text"] not in readme]
        check("headline numbers equal their recomputed values", not bad, f"{len(heads)} numbers; bad: {bad[:8]}")
        check("headline numbers appear verbatim in README.md", not absent, f"absent: {absent[:8]}")
        import compiled_routine_tm as crt  # noqa: E402  (put on sys.path by the R2-07d/R2-07c analysis)

        arts = sorted((HERE / "raw" / "artifacts").glob("*.json"))
        probs = {p.name: crt.check_artifact_authority_tm(json.loads(p.read_text())) for p in arts}
        check("every compiled artifact passes the authority scan", bool(arts) and not any(probs.values()),
              f"{len(arts)} artifacts; problems: {[k for k, v in probs.items() if v]}")
        led = [json.loads(x) for x in (HERE / "raw" / "provider-ledger.jsonl").read_text().splitlines() if x.strip()] \
            if (HERE / "raw" / "provider-ledger.jsonl").exists() else []
        att = [x for x in led if x.get("kind") == "attempt"]
        reached = sum(1 for x in att if x.get("reached"))
        blocked = sum(1 for x in led if x.get("kind") == "blocked_by_cap")
        check("provider ledger within the lane cap (16 reached / 20 attempts), no blocked send, summary equals ledger",
              len(att) <= CAP[1] and reached <= CAP[0] and blocked == 0
              and (summary["provider"]["attempts"], summary["provider"]["reached"]) == (len(att), reached),
              f"{len(att)} attempts / {reached} reached / {blocked} blocked_by_cap")
        gate_checks(fresh, att)
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
