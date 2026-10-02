#!/usr/bin/env python3
"""R2-10R recertification gates (standard library only).

Compares VERDICTS only (never numbers) between the accepted R2-10 packet (reference extracted from
exp/r2-10-composition-20261002 030f6bdbf, docs/experiments/r2-10-composition-2026-10-02/r2-10-summary.json)
and this packet's r2-10r-summary.json + d1-summary.json. Gate rules are PREREG.json ``gates``.

usage:
  recert_gates.py --make-reference <r2-10-summary.json> --source <text>   (writes reference/r2-10-reference.json)
  recert_gates.py [--summary r2-10r-summary.json] [--d1 d1-summary.json] [--out recert-summary.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REF = HERE / "reference" / "r2-10-reference.json"
CLASSES = ["fill", "toggle", "modal"]
TASKS = ["checkbox", "text"]
SIGN_MIN_MS = 5.0  # work-deleted sign check applies to components whose R2-10 |deleted| >= 5 ms


def get(d: Any, path: str) -> Any:
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def s_paths() -> list[str]:
    out = []
    for arm in ("COMP", "COMP_E", "COMP_K"):
        for cls in CLASSES:
            out.append(f"browser.scripted.S.{arm}.{cls}.all")
    out += ["browser.scripted.S.COMP.fill.amortized_mean_ratio", "browser.scripted.S.COMP.fill.warm_only"]
    for arm in ("S0", "X"):
        for t in TASKS:
            out.append(f"native.S.{arm}.{t}.all")
    return out


def decomp_units() -> list[tuple[str, str]]:
    units = [(f"browser.scripted.decomposition.{cls}/{arm}", f"scripted/{cls}/{arm}")
             for cls in CLASSES for arm in ("BASE", "COMP", "COMP_E", "COMP_K")]
    units += [(f"native.decomposition.{t}/{arm}", f"native/{t}/{arm}") for t in TASKS for arm in ("BASE", "S0", "X")]
    return units


def wd_units() -> list[tuple[str, str]]:
    units = [(f"browser.scripted.work_deleted_vs_wall_clock.{cls}.component_mean_ms_deleted", f"scripted/{cls}/COMP")
             for cls in CLASSES]
    units += [(f"native.work_deleted_vs_wall_clock.{t}/{arm}.component_mean_ms_deleted", f"native/{t}/{arm}")
              for t in TASKS for arm in ("S0", "X")]
    return units


def extract(summary: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {"S": {}, "decomposition": {}, "work_deleted": {}}
    for p in s_paths():
        blk = get(summary, p) or {}
        ref["S"][p] = {"S": blk.get("S"), "ci95": blk.get("ci95"), "n": blk.get("n")}
    for p, name in decomp_units():
        d = get(summary, p) or {}
        ref["decomposition"][name] = {
            "components": {c: {"verdict": v.get("verdict"), "above_threshold": v.get("above_threshold")}
                           for c, v in (d.get("components") or {}).items()},
            "untested_share": d.get("untested_share"),
            "e2_target_met": (d.get("untested_share") is not None and d["untested_share"] < 0.05)}
    for p, name in wd_units():
        ref["work_deleted"][name] = get(summary, p) or {}
    ref["validity"] = get(summary, "gates.validity.shares")
    ref["e4"] = get(summary, "gates.e4.totals")
    return ref


def side(ci: list[float] | None) -> str | None:
    if not ci:
        return None
    if ci[0] > 1:
        return "above_1"
    if ci[1] < 1:
        return "below_1"
    return "includes_1"


def gates(summary: dict[str, Any], d1: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    g: dict[str, Any] = {}
    g["phase0"] = {"pass": bool(get(summary, "phase0.pass")),
                   "rows": {k: get(summary, f"phase0.{k}.pass") for k in ("a_unit", "b_c1", "c_nw2", "d_default_off", "e_r2_07b")}}
    shares = get(summary, "gates.validity.shares") or {}
    expected_units = ([f"browser/scripted/{c}/{a}" for c in CLASSES for a in ("BASE", "COMP", "COMP_E", "COMP_K")]
                      + [f"native/{t}/{a}" for t in TASKS for a in ("BASE", "S0", "X")])
    g["validity_100"] = {"shares": {u: shares.get(u) for u in expected_units},
                         "pass": all(shares.get(u) == 1.0 for u in expected_units)}
    e4 = get(summary, "gates.e4.totals") or {}
    g["e4_zero"] = {"totals": e4, "pass": bool(e4) and all(v == 0 for v in e4.values())}
    srows = {}
    for p, r in ref["S"].items():
        cur = get(summary, p) or {}
        rs, cs = side(r.get("ci95")), side(cur.get("ci95"))
        gated = rs in ("above_1", "below_1")
        srows[p] = {"R2_10_side": rs, "R_prime_side": cs, "R_prime_S": cur.get("S"), "R_prime_ci95": cur.get("ci95"),
                    "R_prime_n": cur.get("n"), "gated": gated, "pass": (cs == rs) if gated else None}
    g["S_direction"] = {"rows": srows, "pass": all(v["pass"] for v in srows.values() if v["gated"]),
                        "changed": [p for p, v in srows.items() if v["gated"] and not v["pass"]],
                        "not_gated_changed": [p for p, v in srows.items() if not v["gated"] and v["R_prime_side"] != v["R2_10_side"]]}
    drows, crossings, e2_changes, mismatches = {}, [], [], []
    for p, name in decomp_units():
        cur = get(summary, p) or {}
        rref = ref["decomposition"].get(name) or {}
        comps = {}
        for c, rv in (rref.get("components") or {}).items():
            cv = (cur.get("components") or {}).get(c) or {}
            same = cv.get("verdict") == rv.get("verdict")
            crossed = cv.get("above_threshold") != rv.get("above_threshold")
            comps[c] = {"verdict": cv.get("verdict"), "verdict_same": same, "above_threshold_R2_10": rv.get("above_threshold"),
                        "above_threshold_R_prime": cv.get("above_threshold"), "crossed_threshold": crossed,
                        "R_prime_mean_ms": cv.get("mean_ms"), "R_prime_share": cv.get("share")}
            if not same:
                mismatches.append(f"{name}:{c}")
            if crossed:
                crossings.append(f"{name}:{c} ({'now above' if cv.get('above_threshold') else 'now below'} 5% / 50 ms)")
        met = cur.get("untested_share") is not None and cur["untested_share"] < 0.05
        if met != rref.get("e2_target_met"):
            e2_changes.append(f"{name}: E2 untested<5% {'now met' if met else 'no longer met'}")
        drows[name] = {"components": comps, "R_prime_untested_share": cur.get("untested_share"),
                       "e2_target_met_R2_10": rref.get("e2_target_met"), "e2_target_met_R_prime": met,
                       "R_prime_floor_ratio_mean": cur.get("floor_ratio_mean"), "R_prime_T_irreducible_ms": cur.get("T_irreducible_ms")}
    sign_rows, sign_flips = {}, []
    for p, name in wd_units():
        cur = get(summary, p) or {}
        for c, rv in (ref["work_deleted"].get(name) or {}).items():
            if rv is None or abs(rv) < SIGN_MIN_MS:
                continue
            cv = cur.get(c)
            ok = cv is not None and (cv > 0) == (rv > 0)
            sign_rows[f"{name}:{c}"] = {"R2_10_sign": "deleted" if rv > 0 else "added",
                                        "R_prime_ms": cv, "pass": ok}
            if not ok:
                sign_flips.append(f"{name}:{c}")
    g["verdict_mapping"] = {"decomposition": drows, "work_deleted_sign": sign_rows, "verdict_mismatches": mismatches,
                            "work_deleted_sign_flips": sign_flips, "flagged_threshold_crossings": crossings,
                            "flagged_e2_status_changes": e2_changes, "pass": not mismatches and not sign_flips}
    dg = (d1 or {}).get("gate") or {}
    g["d1_digests"] = {"digests_identical_40_of_40": dg.get("digests_identical_40_of_40"),
                       "truncated_false_40_of_40": dg.get("truncated_false_40_of_40"), "row_pass": dg.get("pass"),
                       "pass": bool(dg.get("digests_identical_40_of_40"))}
    order = ["phase0", "validity_100", "e4_zero", "S_direction", "verdict_mapping", "d1_digests"]
    failed = [k for k in order if not g[k]["pass"]]
    claims = []
    if "S_direction" in failed:
        claims += [f"S direction changed: {p}" for p in g["S_direction"]["changed"]]
    if "verdict_mapping" in failed:
        claims += [f"verdict changed: {x}" for x in mismatches] + [f"deletion sign flipped: {x}" for x in sign_flips]
    for k in ("phase0", "validity_100", "e4_zero", "d1_digests"):
        if k in failed:
            claims.append(f"gate failed: {k}")
    g["failed"] = failed
    g["changed_claims"] = claims
    g["disposition"] = "RECERTIFIED" if not failed else "RECERT_FAIL"
    return g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make-reference")
    ap.add_argument("--source", default="")
    ap.add_argument("--summary", default=str(HERE / "r2-10r-summary.json"))
    ap.add_argument("--d1", default=str(HERE / "d1-summary.json"))
    ap.add_argument("--out", default=str(HERE / "recert-summary.json"))
    args = ap.parse_args()
    if args.make_reference:
        raw = Path(args.make_reference).read_bytes()
        ref = extract(json.loads(raw))
        ref["source"] = {"text": args.source, "summary_sha256": hashlib.sha256(raw).hexdigest(),
                         "summary_git_blob_sha1": hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()}
        REF.parent.mkdir(parents=True, exist_ok=True)
        REF.write_text(json.dumps(ref, indent=1, sort_keys=True) + "\n")
        print(json.dumps({"written": "reference/r2-10-reference.json", **ref["source"]}))
        return
    summary = json.loads(Path(args.summary).read_text())
    d1 = json.loads(Path(args.d1).read_text()) if Path(args.d1).exists() else {}
    ref = json.loads(REF.read_text())
    g = gates(summary, d1, ref)
    Path(args.out).write_text(json.dumps(g, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: g[k] for k in ("disposition", "failed", "changed_claims")} | {
        "flagged_threshold_crossings": g["verdict_mapping"]["flagged_threshold_crossings"],
        "flagged_e2_status_changes": g["verdict_mapping"]["flagged_e2_status_changes"],
        "S_not_gated_changed": g["S_direction"]["not_gated_changed"]}, indent=1))


if __name__ == "__main__":
    main()
