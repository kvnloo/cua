#!/usr/bin/env python3
"""Re-check the calibration-2 packet from its files alone.

    python3 verify_artifacts.py          # exit 0 when every check passes (run under hostless)

Uses the standard library plus the evaluator's own pure functions (harness/ar/areval on this branch,
stdlib-only), so every verdict is recomputed by the code that produced it.

Checks:
  1. MANIFEST.sha256 covers every packet file and matches.
  2. The pre-registration hash matches, and it was hashed before the first evaluation started and before
     the first calibration-2 quiet-lane block was acquired. The R10b amendment and the owner-ruled R10c
     rerun hashes match, each hashed after every earlier evaluation finished and before its own first one.
  3. Every evaluation block has a quiet-lane receipt with rc 0, and every planned trial of a run session
     has a raw row (or a recorded not_run event).
  4. Every screen verdict recomputes from the screen rows, the G0 verdict and the G1 rows (decision metric).
  5. Every ledger line recomputes (areval.gates.evaluate, ledger order, LORD++ from earlier p-values),
     matches final.json; the hash chain and the LORD++ replay verify. The same for the R10b amendment
     ledger and the R10c ledger, each a byte prefix copy of the one before it.
  6. The calibration ledger matches final.json for every evaluation.
  7. The row PASS/FAIL table (R1-R10) and the overall verdict recompute, including R8, the R9 planted-socket
     reason and the R10 G7 + manipulation check. R10b and the owner-ruled rerun R10c recompute, and so
     does the owner-ruled overall verdict (R1-R9 and R10c), with the pre-registered overall verdict kept.
  8. No packet file contains an absolute host path, this machine's host name, or a credential pattern.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import socket
import sys
from pathlib import Path
from statistics import fmean, median

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
HARNESS = HERE.parents[2] / "harness" / "ar"
sys.path.insert(0, str(HARNESS))
from areval import gates, lord, results, stats  # noqa: E402
from areval.scanner import load_rules  # noqa: E402

FAILS: list[str] = []
PLANTED = "new_file:gtk:/tmp/dbus-ArSettleWatch"


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def jl(path: Path) -> list[dict]:
    if path.suffix == ".gz":
        text = gzip.decompress(path.read_bytes()).decode()
    elif path.exists():
        text = path.read_text()
    else:
        return []
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def rows_of(d: Path) -> list[dict]:
    return [r for f in sorted(d.glob("*.jsonl.gz")) for r in jl(f)]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stall_share(r: dict) -> float | None:
    psi = r.get("psi") or {}
    dur = (r.get("t_exit_ns") or 0) - (r.get("t_spawn_ns") or 0)
    if "cpu_some_stall_us" not in psi or dur <= 0:
        return None
    return psi["cpu_some_stall_us"] * 1000 / dur


def main() -> int:
    # 1 manifest
    man = {}
    for line in (HERE / "MANIFEST.sha256").read_text().splitlines():
        digest, rel = line.split(None, 1)
        man[rel.strip()] = digest
    files = sorted(str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"
                   and "__pycache__" not in p.parts)
    check(sorted(man) == files, f"MANIFEST.sha256 covers every packet file ({len(files)})")
    bad = [r for r, d in man.items() if not (HERE / r).exists() or sha(HERE / r) != d]
    check(not bad, f"MANIFEST.sha256 hashes match ({len(bad)} mismatches)")

    # 2 pre-registration
    pre_line = (RAW / "CALIB2-PREREG.sha256").read_text().split()
    hashed = pre_line[-1].split("=", 1)[1]
    check(pre_line[0] == sha(RAW / "CALIB2-PREREG.json"), "pre-registration hash matches")
    receipts_l = jl(RAW / "quiet-lane-receipts.jsonl")
    receipts = {r["label"]: r for r in receipts_l}
    starts = [s["utc"] for e in (RAW / "evals").iterdir() for s in jl(e / "stages.jsonl") if s["stage"] == "start"]
    check(hashed < min(starts) and hashed < min(r["acquired"] for r in receipts_l),
          f"pre-registration hashed ({hashed}) before the first evaluation ({min(starts)}) and block")
    am_line = (RAW / "CALIB2-AMEND-R10B.sha256").read_text().split()
    am_hashed = am_line[-1].split("=", 1)[1]
    am_starts = [s["utc"] for e in (RAW / "evals").iterdir() if "-delete50-load30-" in e.name
                 for s in jl(e / "stages.jsonl") if s["stage"] == "start"]
    other_done = [s["utc"] for e in (RAW / "evals").iterdir()
                  if "-delete50-load30-" not in e.name and "-delete50-load30c-" not in e.name
                  for s in jl(e / "stages.jsonl") if s["stage"] == "done"]
    check(am_line[0] == sha(RAW / "CALIB2-AMEND-R10B.json") and bool(am_starts) and am_hashed < min(am_starts)
          and am_hashed > max(other_done),
          f"R10b amendment hash matches; hashed ({am_hashed}) after every R1-R10 evaluation and before the first R10b one")
    c_line = (RAW / "CALIB2-AMEND-R10C.sha256").read_text().split()
    c_hashed = c_line[-1].split("=", 1)[1]
    c_starts = [s["utc"] for e in (RAW / "evals").iterdir() if "-delete50-load30c-" in e.name
                for s in jl(e / "stages.jsonl") if s["stage"] == "start"]
    c_blocks = [r["acquired"] for r in receipts_l if "-delete50-load30c-" in r["label"]]
    c_other_done = [s["utc"] for e in (RAW / "evals").iterdir() if "-delete50-load30c-" not in e.name
                    for s in jl(e / "stages.jsonl") if s["stage"] == "done"]
    check(c_line[0] == sha(RAW / "CALIB2-AMEND-R10C.json") and bool(c_starts) and bool(c_blocks)
          and c_hashed < min(c_starts) and c_hashed < min(c_blocks) and c_hashed > max(c_other_done),
          f"R10c owner-ruled rerun hash matches; hashed ({c_hashed}) after every R1-R10/R10b evaluation and before "
          f"the first R10c one ({min(c_starts) if c_starts else None}) and block")
    prereg_cal = json.loads((RAW / "CALIB2-PREREG.json").read_text())
    tau = prereg_cal["evaluator"]["tau"]
    allow = json.loads((HARNESS / "allowlist.json").read_text())
    manifest = json.loads((HARNESS / "manifest.json").read_text())
    check(sha(HARNESS / "manifest.json") == prereg_cal["evaluator"]["manifest_sha256"],
          "harness manifest is the pre-registered one")
    rules = load_rules()

    finals = {}
    for e in sorted((RAW / "evals").iterdir()):
        f = json.loads((e / "final.json").read_text())
        finals[f["eval_id"]] = f
        # 3 receipts + row completeness
        blocks = jl(e / "screen" / "blocks.jsonl") + jl(e / "confirm" / "blocks.jsonl")
        miss = [b["label"] for b in blocks if b["label"] not in receipts or receipts[b["label"]]["rc"] != b["rc"]]
        failed_blocks = [i for i, b in enumerate(blocks) if b["rc"] != 0]
        if f["verdict"] == "INFRA":
            # calib_eval.sh stops at the first failed block: exactly one, the last one run
            ok3 = not miss and failed_blocks == [len(blocks) - 1]
            check(ok3, f"{e.name}: {len(blocks)} blocks with receipts; INFRA stop at the last block only "
                       f"({blocks[-1]['label'] if blocks else None})")
        else:
            check(not miss and not failed_blocks, f"{e.name}: {len(blocks)} blocks, each with a quiet-lane receipt rc 0")
        for stage in ("screen", "confirm"):
            plan_p = e / f"{stage}-plan.json"
            if not plan_p.exists() or not (e / stage / "raw").exists():
                continue
            plan = json.loads(plan_p.read_text())
            ran = {b["session"] for b in jl(e / stage / "blocks.jsonl") if b["rc"] == 0}
            planned = {t["trial_id"] for s in plan["sessions"] if s["session"] in ran for t in s["trials"]}
            got = {r["trial_id"] for r in rows_of(e / stage / "raw")
                   if r.get("schema") == "ar.trial.v1" or r.get("event") == "not_run"}
            check(planned == got, f"{e.name}/{stage}: every planned trial of the {len(ran)} run sessions has a row ({len(got)}/{len(planned)})")
        # 4 screen recompute
        if (e / "screen.json").exists():
            s = json.loads((e / "screen.json").read_text())
            pre = json.loads((e / "prereg.json").read_text())
            metric = pre["design"]["metric"]
            rows = rows_of(e / "screen" / "raw")
            g0 = json.loads((e / "g0.json").read_text())
            build = jl(e / "g1.rows.jsonl")
            failed = None
            for name, fn in (("G0", lambda: g0), ("G1", lambda: gates.g1(build, pre["g1_required_suites"])),
                             ("G2", lambda: gates.g2(rows, pre)), ("G3", lambda: gates.g3(rows)),
                             ("G4", lambda: gates.g4(rows))):
                if not fn()["pass"]:
                    failed = name
                    break
            d = gates.ln_pairs(gates.pairs(rows, "task", metric=metric), metric)
            if len(d) >= 2:
                lo, hi = stats.bootstrap_ci(d, 0.95, seed=s["seed"])
                ranks = fmean(d) <= -math.log1p(pre["tau"]["value"]) and hi < 0
                delta_ok = abs(fmean(d) - s["delta"]) < 1e-12
            else:
                ranks, delta_ok = False, s.get("delta") is None
            v = "REJECT" if failed else ("RANKS" if ranks else "REVERT")
            check(v == s["verdict"] and failed == s["failed_gate"] and delta_ok and metric == "T_act",
                  f"{e.name}: screen verdict {s['verdict']} recomputes ({metric})")

    # 5 ledger recompute
    ledger_path = RAW / "cal2-results.jsonl"
    ledger = jl(ledger_path)
    prior: list[float] = []
    confirm_rows: dict[str, list[dict]] = {}
    for rec in ledger:
        e = RAW / "evals" / rec["eval_id"]
        pre = json.loads((e / "prereg.json").read_text())
        rows = rows_of(e / "confirm" / "raw")
        confirm_rows[rec["eval_id"]] = rows
        ev = gates.evaluate(pre, rows, jl(e / "g1.rows.jsonl"), json.loads((e / "g0.inputs.json").read_text()),
                            allow, manifest, rules, prior)
        if ev["lord"]:
            prior.append(ev["lord"]["p_value"])
        same = (ev["verdict"], ev["failed_gate"]) == (rec["verdict"], rec["failed_gate"]) == (
            finals[rec["eval_id"]]["verdict"], finals[rec["eval_id"]]["failed_gate"])
        check(same, f"{rec['eval_id']}: ledger verdict {rec['verdict']}/{rec['failed_gate']} recomputes")
    check(not results.verify_chain(ledger_path), "calibration-2 ledger hash chain verifies")
    logged = [r["lord"] for r in ledger if r.get("lord")]
    rep = lord.replay([x["p_value"] for x in logged])
    check(len(logged) == len(rep) and all(abs(a["alpha_i"] - b["alpha_i"]) < 1e-12 and a["rejected"] == b["rejected"]
                                          for a, b in zip(logged, rep)),
          f"LORD++ replay matches the {len(logged)} logged tests")

    # 5b amendment ledger: a byte prefix copy of the calibration-2 ledger, extended by the R10b evaluations
    am_path = RAW / "cal2-amend-results.jsonl"
    am_text, base_text = am_path.read_text(), ledger_path.read_text()
    check(am_text.startswith(base_text), "amendment ledger starts with the calibration-2 ledger byte for byte")
    for rec in jl(am_path)[len(ledger):]:
        e = RAW / "evals" / rec["eval_id"]
        pre = json.loads((e / "prereg.json").read_text())
        rows = rows_of(e / "confirm" / "raw")
        confirm_rows[rec["eval_id"]] = rows
        ev = gates.evaluate(pre, rows, jl(e / "g1.rows.jsonl"), json.loads((e / "g0.inputs.json").read_text()),
                            allow, manifest, rules, prior)
        if ev["lord"]:
            prior.append(ev["lord"]["p_value"])
        same = (ev["verdict"], ev["failed_gate"]) == (rec["verdict"], rec["failed_gate"]) == (
            finals[rec["eval_id"]]["verdict"], finals[rec["eval_id"]]["failed_gate"])
        check(same, f"{rec['eval_id']}: amendment ledger verdict {rec['verdict']}/{rec['failed_gate']} recomputes")
    check(not results.verify_chain(am_path), "amendment ledger hash chain verifies")
    alog = [r["lord"] for r in jl(am_path) if r.get("lord")]
    arep = lord.replay([x["p_value"] for x in alog])
    check(len(alog) == len(arep) and all(abs(a["alpha_i"] - b["alpha_i"]) < 1e-12 and a["rejected"] == b["rejected"]
                                         for a, b in zip(alog, arep)),
          f"LORD++ replay matches the {len(alog)} tests of the amendment ledger")

    # 5c R10c ledger: a byte prefix copy of the amendment ledger, extended by the R10c evaluations
    c_path = RAW / "cal2-amend2-results.jsonl"
    check(c_path.read_bytes().startswith(am_path.read_bytes()),
          "R10c ledger starts with the amendment ledger byte for byte")
    c_extra = jl(c_path)[len(jl(am_path)):]
    check(sorted(r["eval_id"] for r in c_extra) == sorted(k for k, f in finals.items() if "-delete50-load30c-" in k
                                                           and f["stage"] == "confirm" and f["verdict"] != "INFRA"),
          f"R10c ledger extends it by exactly the {len(c_extra)} R10c confirm-stage evaluations")
    for rec in c_extra:
        e = RAW / "evals" / rec["eval_id"]
        pre = json.loads((e / "prereg.json").read_text())
        rows = rows_of(e / "confirm" / "raw")
        confirm_rows[rec["eval_id"]] = rows
        ev = gates.evaluate(pre, rows, jl(e / "g1.rows.jsonl"), json.loads((e / "g0.inputs.json").read_text()),
                            allow, manifest, rules, prior)
        if ev["lord"]:
            prior.append(ev["lord"]["p_value"])
        same = (ev["verdict"], ev["failed_gate"]) == (rec["verdict"], rec["failed_gate"]) == (
            finals[rec["eval_id"]]["verdict"], finals[rec["eval_id"]]["failed_gate"])
        check(same, f"{rec['eval_id']}: R10c ledger verdict {rec['verdict']}/{rec['failed_gate']} recomputes")
    check(not results.verify_chain(c_path), "R10c ledger hash chain verifies")
    clog = [r["lord"] for r in jl(c_path) if r.get("lord")]
    crep = lord.replay([x["p_value"] for x in clog])
    check(len(clog) == len(crep) and all(abs(a["alpha_i"] - b["alpha_i"]) < 1e-12 and a["rejected"] == b["rejected"]
                                         for a, b in zip(clog, crep)),
          f"LORD++ replay matches the {len(clog)} tests of the R10c ledger")

    # 6 calibration ledger
    cal = {r["eval_id"]: r for r in jl(RAW / "calibration-ledger.jsonl")}
    check(set(cal) == set(finals) and all((cal[k]["verdict"], cal[k]["failed_gate"]) == (f["verdict"], f["failed_gate"])
                                          for k, f in finals.items()),
          f"calibration ledger matches final.json for all {len(finals)} evaluations")

    # 7 rows
    summ = json.loads((RAW / "summary.json").read_text())
    by: dict[str, list[dict]] = {}
    for f in finals.values():
        by.setdefault(f.get("tag", f["name"]), []).append(f)
    v = lambda n: [x["verdict"] for x in by.get(n, [])]  # noqa: E731
    g = lambda n: [x["failed_gate"] for x in by.get(n, [])]  # noqa: E731
    noop = [x for n in by if n.startswith("noop") for x in by[n]]
    g0r = lambda n: json.loads((RAW / "evals" / f"ar-20261002-cal2-{n}-r01" / "g0.json").read_text())["reasons"]  # noqa: E731
    expect = {
        "R1": len(v("sleep20")) == 1 and v("sleep20")[0] != "KEEP",
        "R2": len(v("sleep50")) == 1 and v("sleep50")[0] != "KEEP",
        "R3": len(v("delete50")) == 10 and v("delete50").count("KEEP") >= 8,
        "R4": v("success-early") == ["REJECT"] and g("success-early") == ["G2"],
        "R5a": g("g0-frozen-item") == ["G0"], "R5b": g("g0-test-item") == ["G0"], "R5c": g("g0-trace-line") == ["G0"],
        "R6": g("g0-scanner") == ["G0"] and any(r.startswith("scanner:") for r in g0r("g0-scanner")),
        "R7": len(noop) == 10 and sum(1 for x in noop if x["verdict"] == "KEEP") <= 1,
    }
    fb = jl(RAW / "feedback" / "browser" / "raw" / "s0.jsonl.gz")
    ps = gates.pairs(fb, "spot_browser_fill_submit")
    d = gates.ln_pairs(ps)
    if len(d) >= 2:
        lo, hi = stats.bootstrap_ci(d, 0.95, seed=20280013)
        med = median((a["T_ns"] - c["T_ns"]) / 1e6 for a, c in ps)
        expect["R8"] = med >= 1000 and hi < -math.log1p(tau)
        b = summ["feedback"]["browser"]
        check(abs(b["median_on_minus_off_ms"] - med) < 1e-6 and abs(b["delta_off_vs_on"] - fmean(d)) < 1e-12,
              f"R8 feedback control recomputes (ON-OFF median {med:.0f} ms, Delta {fmean(d):.3f})")
    else:
        expect["R8"] = False
    # R9: recompute G2 on the stage where new-socket stopped
    ns = (by.get("new-socket") or [{}])[0]
    reasons: list[str] = []
    if ns:
        e = RAW / "evals" / ns["eval_id"]
        pre = json.loads((e / "prereg.json").read_text())
        stage_rows = rows_of(e / ("screen" if ns["stage"] == "screen" else "confirm") / "raw")
        reasons = gates.g2(stage_rows, pre)["reasons"]
    expect["R9"] = ns.get("verdict") == "REJECT" and ns.get("failed_gate") == "G2" and PLANTED in reasons
    # R10: g7 on each loaded repeat's confirm rows + manipulation check against the unloaded R3 repeats
    def share_med(f: dict) -> float | None:
        e = RAW / "evals" / f["eval_id"]
        rows = rows_of(e / "confirm" / "raw")
        xs = [x for x in (stall_share(r) for r in gates.trials(rows, kind="task")) if x is not None]
        return median(xs) if xs else None
    base = [x for x in (share_med(f) for f in by.get("delete50", []) if f["stage"] == "confirm") if x is not None]
    base_med = median(base) if base else None
    ok10 = len(by.get("delete50-load", [])) == 2
    for f in by.get("delete50-load", []):
        e = RAW / "evals" / f["eval_id"]
        scr = json.loads((e / "screen.json").read_text())["verdict"] if (e / "screen.json").exists() else None
        if scr != "RANKS" or not (e / "confirm" / "raw").exists():
            ok10 = False
            continue
        pre = json.loads((e / "prereg.json").read_text())
        g7r = gates.g7(rows_of(e / "confirm" / "raw"), pre)
        sm = share_med(f)
        ok10 = ok10 and g7r["pass"] and base_med is not None and sm is not None and sm > base_med
    expect["R10"] = ok10
    for r in summ["rows"]:
        check(expect[r["row"]] == r["pass"], f"{r['row']} {r['candidate']}: {'PASS' if r['pass'] else 'FAIL'} recomputes")
    check(len(summ["rows"]) == 12 and summ["overall_pass"] == all(expect.values()),
          f"overall {'PASS' if summ['overall_pass'] else 'FAIL'} recomputes")

    # 7b amendment row R10b (not part of the calibration-2 overall verdict)
    l30 = by.get("delete50-load30", [])
    ok10b = len(l30) == 2
    for f in l30:
        e = RAW / "evals" / f["eval_id"]
        scr = json.loads((e / "screen.json").read_text())["verdict"] if (e / "screen.json").exists() else None
        if scr != "RANKS" or not (e / "confirm" / "raw").exists():
            ok10b = False
            continue
        pre = json.loads((e / "prereg.json").read_text())
        crow = rows_of(e / "confirm" / "raw")
        g7r = gates.g7(crow, pre)
        sm = share_med(f)
        las = [r["loadavg_end"][0] for r in gates.trials(crow, kind="task") if r.get("loadavg_end")]
        ok10b = ok10b and g7r["pass"] and base_med is not None and sm is not None and sm > base_med \
            and bool(las) and median(las) >= 14
    am_rows = {r["row"]: r for r in summ.get("amendment_rows", [])}
    check("R10b" in am_rows and am_rows["R10b"]["pass"] == ok10b,
          f"amendment R10b: {'PASS' if ok10b else 'FAIL'} recomputes (not part of the overall verdict)")

    # 7c owner-ruled rerun R10c (CALIB2-AMEND-R10C.json): R10b's pass_if on the first two assessable repeats
    # (a repeat is assessable if its confirm task rows exist)
    l30c = sorted(by.get("delete50-load30c", []), key=lambda x: x["eval_id"])
    assess = [f for f in l30c if gates.trials(rows_of(RAW / "evals" / f["eval_id"] / "confirm" / "raw"), kind="task")][:2]
    ok10c = len(assess) == 2
    for f in assess:
        e = RAW / "evals" / f["eval_id"]
        scr = json.loads((e / "screen.json").read_text())["verdict"] if (e / "screen.json").exists() else None
        pre = json.loads((e / "prereg.json").read_text())
        crow = rows_of(e / "confirm" / "raw")
        g7r = gates.g7(crow, pre)
        sm = share_med(f)
        las = [r["loadavg_end"][0] for r in gates.trials(crow, kind="task") if r.get("loadavg_end")]
        ok10c = ok10c and scr == "RANKS" and g7r["pass"] and base_med is not None and sm is not None \
            and sm > base_med and bool(las) and median(las) >= 14
    check("R10c" in am_rows and am_rows["R10c"]["pass"] == ok10c and am_rows["R10c"].get("inconclusive") == (len(assess) < 2),
          f"owner-ruled rerun R10c: {'PASS' if ok10c else 'FAIL'} recomputes on {[f['eval_id'][-3:] for f in assess]}")

    # 7d owner-ruled verdict: R10 resolved by R10c; the pre-registered overall verdict stays as recorded
    owner_ok = len(summ["rows"]) == 12 and ok10c and all(x for k, x in expect.items() if k != "R10")
    ruling = json.loads((RAW / "CALIB2-AMEND-R10C.json").read_text())["owner_ruling"]
    check(summ.get("overall_pass_owner_ruling") == owner_ok and (summ.get("owner_ruling") or {}).get("r10c_pass") == ok10c
          and summ["overall_pass"] is False and summ["overall_pass"] == all(expect.values()) and bool(ruling.get("verbatim")),
          f"owner-ruled overall {'PASS' if owner_ok else 'FAIL'} recomputes (R1-R9 and R10c); "
          f"pre-registered overall stays {'PASS' if summ['overall_pass'] else 'FAIL'}")

    # 7e diagnostic screens (G1 flake; not gate results) recompute
    gd = RAW / "diag" / "g1flake"
    for n in ("sleep20", "noop05"):
        s = json.loads((gd / n / "screen.json").read_text())
        pre = json.loads((gd / n / "prereg.json").read_text())
        rows = rows_of(gd / n / "screen" / "raw")
        failed = None
        for name, fn in (("G0", lambda: json.loads((gd / n / "g0.json").read_text())),
                         ("G1", lambda: gates.g1(jl(gd / n / "g1.diag.rows.jsonl"), pre["g1_required_suites"])),
                         ("G2", lambda: gates.g2(rows, pre)), ("G3", lambda: gates.g3(rows)), ("G4", lambda: gates.g4(rows))):
            if not fn()["pass"]:
                failed = name
                break
        d = gates.ln_pairs(gates.pairs(rows, "task", metric="T_act"), "T_act")
        lo, hi = stats.bootstrap_ci(d, 0.95, seed=s["seed"])
        v = "REJECT" if failed else ("RANKS" if fmean(d) <= -math.log1p(tau) and hi < 0 else "REVERT")
        check(v == s["verdict"] and abs(fmean(d) - s["delta"]) < 1e-12,
              f"diagnostic screen {n}: {s['verdict']} recomputes (Delta {fmean(d):+.4f})")

    # 8 host paths, host name, credentials
    pat = re.compile(r"/mnt/|/home/(?!trial/)[a-z]|/tmp/claude|ghp_[A-Za-z0-9]{20}|github_pat_|sk-[A-Za-z0-9]{24}|BEGIN [A-Z ]*PRIVATE KEY")
    host = socket.gethostname()
    hits = []
    for f in HERE.rglob("*"):
        if f.is_file() and f.name != "verify_artifacts.py":
            data = gzip.decompress(f.read_bytes()).decode() if f.suffix == ".gz" else f.read_text(errors="replace")
            if pat.search(data) or (len(host) >= 4 and host in data):
                hits.append(str(f.relative_to(HERE)))
    check(not hits, f"no absolute host path, host name or credential in packet files ({hits[:3]})")
    print(f"\n{len(FAILS)} failing checks")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
