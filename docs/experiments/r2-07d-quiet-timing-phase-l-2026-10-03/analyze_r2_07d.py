"""R2-07d analysis: quiet-window Phase S timing (block q), carry-over controls (block ctl), Phase L live.

Reads only the packet's raw/ and writes r2-07d-summary.json. Reuses, by import and unchanged, the
R2-07c analysis (../r2-07c-toggle-modal-compiled-2026-10-03/analyze_r2_07c.py: load_block, row_of,
g4_pass, nw2_row, decomposition, e4_total) and through it the R2-10 per-trial row
(analyze_r2_10.browser_row: T_oracle, decomposition, forced-path and arm-configuration checks, E4) and
b01_analysis.paired_diff (seed 20261002, 10000 resamples).

usage (under hostless): python analyze_r2_07d.py [--raw raw] [--out r2-07d-summary.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
R207C_PKT = HERE.parent / "r2-07c-toggle-modal-compiled-2026-10-03"
sys.path.insert(0, str(R207C_PKT))
import analyze_r2_07c as AC  # noqa: E402

A, B = AC.A, AC.B
CLASSES = AC.CLASSES
ROUNDS = 40
GATE_MS = 2.0
LOAD_CEILING = 3.0
WARM_PLANNED = 29
LIVE_PLANNED = 30
ATTEMPT = re.compile(r"-a(\d+)$")


def default(o: Any) -> Any:
    return dict(o) if isinstance(o, Counter) else str(o)


def med(xs):
    return A.med(xs)


def mean(xs):
    return A.mean(xs)


def rows_of(raw: Path, block: str) -> list[dict[str, Any]]:
    out = []
    for t in AC.load_block(raw, block):
        if t["summary"].get("kind") in ("nw2", "smoke"):
            continue
        r = AC.row_of(t)
        r["utc_start"] = t["summary"].get("utc_start")
        m = ATTEMPT.search(t["name"])
        r["attempt"] = int(m.group(1)) if m else 1
        out.append(r)
    return out


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def e4_clean(e4: dict[str, int]) -> bool:
    return all(v == 0 for v in e4.values())


def g3_of(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cr = [r for r in rows if r["arm"] == "COMP_CR"]
    acc = sum(r["g3"]["accepted"] for r in cr)
    fresh = sum(r["g3"]["accepted_fresh"] for r in cr)
    nfa = sum(r["g3"]["nonfresh_attempts"] for r in cr)
    nfr = sum(r["g3"]["nonfresh_refused"] for r in cr)
    return {"cells": len(cr), "accepted_mutations": acc, "accepted_fresh": fresh, "nonfresh_attempts": nfa,
            "nonfresh_attempts_refused_effect_refused": nfr, "pass": acc > 0 and acc == fresh and nfa == nfr}


def g1_g2(rows: list[dict[str, Any]], cls: str) -> dict[str, Any]:
    tr = [r for r in rows if r["cls"] == cls and r["kind"] == "train"]
    ad = [r for r in rows if r["cls"] == cls and r["kind"] == "admission"]
    g1 = [r for r in tr if r["verified"] and (r["training"] or {}).get("compile_error") is None
          and (r["training"] or {}).get("authority_problems") == []]
    g2 = [r for r in ad if r["verified"] and r["valid"] and not r["fallback"] and r["provider_decisions"] == 0
          and r["g3"]["accepted_fresh"] == r["g3"]["accepted"]]
    return {"G1": {"n": len(tr), "pass_n": len(g1), "pass": bool(tr) and len(g1) == len(tr)},
            "G2": {"n": len(ad), "pass_n": len(g2), "pass": bool(ad) and len(g2) == len(ad)},
            "training": [{"trial": r["trial"], "T_oracle_ms": r["T_oracle_ms"], "decisions": r["provider_decisions"],
                          "compile_ms": (r["training"] or {}).get("compile_ms"),
                          "admitted": (r["training"] or {}).get("admitted")} for r in tr],
            "admission": [{"trial": r["trial"], "T_oracle_ms": r["T_oracle_ms"], "valid": r["valid"]} for r in ad]}


def pair_stats(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    diff = B.paired_diff([p[1] for p in pairs], [p[0] for p in pairs])  # COMP_CR - COMP
    return {"n": len(pairs), "median_T_COMP_ms": med([p[0] for p in pairs]),
            "median_T_COMP_CR_ms": med([p[1] for p in pairs]), "diff_COMP_CR_minus_COMP_ms": diff,
            "S_COMP_over_COMP_CR": A.ratio_stat(pairs)}


def phase_s(raw: Path) -> dict[str, Any]:
    rows = rows_of(raw, "q")
    gate_log = jsonl(raw / "q-load-gate.jsonl")
    progress = json.loads((raw / "q-progress.json").read_text()) if (raw / "q-progress.json").exists() else {}
    interrupted = {(x["unit"], x["attempt"]) for x in progress.get("interrupted", [])}
    S: dict[str, Any] = {"cells": len(rows), "interrupted_units": sorted(f"{u}#a{a}" for u, a in interrupted)}
    S["load_gate"] = {"attempts": len(gate_log), "starts": sum(1 for g in gate_log if g["start"]),
                      "end_chunk": sum(1 for g in gate_log if not g["start"]),
                      "started_after_wait": sum(1 for g in gate_log if g["start"] and g["waited_s"] > 0),
                      "load_at_start_max": max((g["load_at_start"] for g in gate_log if g["start"]), default=None),
                      "load_at_start_median": med([g["load_at_start"] for g in gate_log if g["start"]]),
                      "chunks": sorted({g["chunk"] for g in gate_log}, key=lambda x: int(x))}
    remaining = progress.get("done")
    units_done = set(remaining or [])
    for cls in CLASSES:
        crows = [r for r in rows if r["cls"] == cls]
        latest: dict[tuple[int, str], dict[str, Any]] = {}
        for r in crows:
            if r["kind"] not in ("measured", "warm") or r.get("round") is None or r["round"] < 0:
                continue
            key = (r["round"], r["arm"])
            if key not in latest or r["attempt"] > latest[key]["attempt"]:
                latest[key] = r
        pairs, pairs_q, failed, loads, not_run = [], [], [], [], []
        for rnd in range(ROUNDS):
            a, b = latest.get((rnd, "COMP")), latest.get((rnd, "COMP_CR"))
            if a is None and b is None:
                not_run.append(rnd)
                continue
            if not (a and b and a["valid"] and b["valid"] and a["T_oracle_ms"] is not None and b["T_oracle_ms"] is not None):
                failed.append({"round": rnd, "COMP": None if a is None else a["reasons"],
                               "COMP_CR": None if b is None else b["reasons"]})
                continue
            pairs.append((a["T_oracle_ms"], b["T_oracle_ms"]))
            loads += [a["loadavg_1m"], b["loadavg_1m"]]
            if max(a["loadavg_1m"], b["loadavg_1m"]) <= LOAD_CEILING:
                pairs_q.append((a["T_oracle_ms"], b["T_oracle_ms"]))
        st = pair_stats(pairs)
        ci = st["diff_COMP_CR_minus_COMP_ms"].get("ci95")
        gate_ok = bool(ci and ci[1] <= GATE_MS and not failed and not not_run and len(pairs) == ROUNDS)
        gg = g1_g2(crows, cls)
        g3 = g3_of(crows)
        e4 = AC.e4_total(crows)
        trows = [r for r in crows if r["kind"] in ("measured", "warm") and r["valid"]]
        wm = [r for r in crows if r["kind"] == "warm"]
        S[cls] = {"timing": {**st, "valid_pairs": len(pairs), "failed_pairs": failed, "not_run_rounds": not_run,
                             "loadavg_1m": {"min": min(loads) if loads else None, "median": med(loads),
                                            "max": max(loads) if loads else None},
                             "gate_ci_upper_le_2ms": gate_ok},
                  "sensitivity_load_le_3": pair_stats(pairs_q),
                  "G1": gg["G1"], "G2": gg["G2"], "training": gg["training"], "admission": gg["admission"],
                  "G3": g3, "E4": e4, "E4_clean": e4_clean(e4),
                  "warm": {"n": len(wm), "valid": sum(1 for r in wm if r["valid"]), "fallbacks": sum(1 for r in wm if r["fallback"]),
                           "decisions": sum(r["provider_decisions"] for r in wm)},
                  "decomposition": {arm: AC.decomposition([r for r in trows if r["arm"] == arm]) for arm in ("COMP", "COMP_CR")}}
        S[cls]["phase_S_pass"] = bool(gate_ok and gg["G1"]["pass"] and gg["G2"]["pass"] and g3["pass"] and e4_clean(e4))
    S["units_done"] = len(units_done)
    S["phase_S_pass_both"] = all(S[c]["phase_S_pass"] for c in CLASSES)
    S["first_trial_utc"] = min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)
    return S


def controls(raw: Path) -> dict[str, Any]:
    blocks = AC.load_block(raw, "ctl")
    rows = [AC.row_of(t) for t in blocks if t["summary"].get("kind") not in ("nw2", "smoke")]
    C: dict[str, Any] = {"cells": len(blocks)}
    g4: dict[str, Any] = {}
    for r in rows:
        if r["kind"] in ("train", "admission"):
            continue
        key = r["kind"] if r["kind"] != "n8" else f"n8:{r['cls']}-on-{r['page_cls']}"
        if r["kind"] == "g5":
            key = f"g5:{r['g5_row']}"
        ok, note = AC.g4_pass(r)
        cell = g4.setdefault(key, {}).setdefault(r["cls"], {"n": 0, "pass": 0, "notes": []})
        cell["n"] += 1
        cell["pass"] += int(ok)
        cell["notes"].append(f"{r['trial']}: {'PASS' if ok else 'FAIL'} {note}")
    nw2 = [AC.nw2_row(t) for t in blocks if t["summary"].get("kind") == "nw2"]
    g4["nw2"] = {cls: {"n": sum(1 for x in nw2 if x["cls"] == cls), "pass": sum(1 for x in nw2 if x["cls"] == cls and x["pass"])}
                 for cls in CLASSES}
    smoke = []
    for t in blocks:
        s = t["summary"]
        if s.get("kind") != "smoke":
            continue
        ok = (s.get("outcome") == "verified" and s.get("oracle_exact_match") is True and s.get("completion_mutations") == 1
              and s.get("driver_env_exp") == {} and s.get("driver_env_trace_set") is False and s.get("arm") == "BASE")
        smoke.append({"trial": t["name"], "cls": s.get("cls"), "pass": ok, "outcome": s.get("outcome"),
                      "driver_env_exp": s.get("driver_env_exp"), "trace": s.get("driver_env_trace_set")})
    g4["default_smoke"] = {cls: {"n": sum(1 for x in smoke if x["cls"] == cls), "pass": sum(1 for x in smoke if x["cls"] == cls and x["pass"])}
                           for cls in CLASSES}
    C["rows"] = g4
    expected = {**{k: (CLASSES, 1) for k in ("n1", "n2", "n3", "n4a", "n4b", "n5", "n6", "n7", "nw2",
                                               "g5:applied_ack_lost", "g5:withheld_unresolved")},
                "n8:toggle-on-fill": (["toggle"], 1), "n8:toggle-on-modal": (["toggle"], 1),
                "n8:modal-on-toggle": (["modal"], 1), "default_smoke": (CLASSES, 5)}
    C["expected_cells"] = sum(len(cl) * n for cl, n in expected.values())
    C["pass_cells"] = sum(g4.get(k, {}).get(c, {}).get("pass", 0) for k, (cl, n) in expected.items() for c in cl)
    C["pass"] = all(c in g4.get(k, {}) and g4[k][c]["n"] == n and g4[k][c]["pass"] == n
                    for k, (cl, n) in expected.items() for c in cl)
    gg = {cls: g1_g2(rows, cls) for cls in CLASSES}
    C["G1_G2"] = {cls: {"G1": gg[cls]["G1"], "G2": gg[cls]["G2"]} for cls in CLASSES}
    C["G3"] = g3_of(rows)
    C["E4"] = AC.e4_total(rows)
    C["E4_clean"] = e4_clean(C["E4"])
    C["first_trial_utc"] = min((t["summary"].get("utc_start") for t in blocks if t["summary"].get("utc_start")), default=None)
    return C


def phase_l(raw: Path) -> dict[str, Any]:
    rows = rows_of(raw, "live")
    man = AC.manifests(raw, "live")
    L: dict[str, Any] = {"run": bool(rows), "manifests": len(man), "not_run": [x for m in man for x in m.get("not_run", [])],
                         "stopped_for_budget": [m.get("stopped_for_budget") for m in man if m.get("stopped_for_budget")],
                         "kind_changes": [x for m in man for x in m.get("kind_changes", [])], "provider_models": {}}
    for m in man:
        for k, v in (m.get("provider_models") or {}).items():
            L["provider_models"][k] = L["provider_models"].get(k, 0) + v
    for cls in CLASSES:
        inv = [r for r in rows if r["cls"] == cls and r["kind"] in ("train", "warm")]
        tr = [r for r in inv if r["kind"] == "train"]
        wm = [r for r in inv if r["kind"] == "warm"]
        ad = [r for r in rows if r["cls"] == cls and r["kind"] == "admission"]
        valid = sum(1 for r in wm if r["valid"])
        t_all = [r["T_oracle_ms"] for r in inv if r["T_oracle_ms"] is not None]
        compile_ms = sum((r["training"] or {}).get("compile_ms") or 0 for r in tr)
        adm_T = sum(r["T_oracle_ms"] or 0 for r in ad)
        mean_warm = mean([r["T_oracle_ms"] for r in wm])
        mean_all = (sum(t_all) + compile_ms + adm_T) / LIVE_PLANNED if inv else None
        e4 = AC.e4_total([r for r in rows if r["cls"] == cls])
        decomp_all = AC.decomposition([r for r in inv if r["verified"]])
        L[cls] = {"invocations_run": len(inv), "planned": LIVE_PLANNED,
                  "training": [{"trial": r["trial"], "verified": r["verified"], "T_oracle_ms": r["T_oracle_ms"],
                                "decisions": r["provider_decisions"], "requests": r["provider_requests"],
                                "compile_ms": (r["training"] or {}).get("compile_ms"),
                                "admitted": (r["training"] or {}).get("admitted")} for r in tr],
                  "admission": [{"trial": r["trial"], "verified": r["verified"], "valid": r["valid"], "T_oracle_ms": r["T_oracle_ms"],
                                 "decisions": r["provider_decisions"]} for r in ad],
                  "warm": {"n_run": len(wm), "planned": WARM_PLANNED, "valid": valid, "validity": valid / WARM_PLANNED,
                           "fallbacks": sum(1 for r in wm if r["fallback"]), "decisions": sum(r["provider_decisions"] for r in wm),
                           "provider_requests": sum((r["provider_requests"] or {}).get("attempts", 0) for r in wm),
                           "median_T_oracle_ms": med([r["T_oracle_ms"] for r in wm]), "mean_T_oracle_ms": mean_warm,
                           "invalid": [{"trial": r["trial"], "reasons": r["reasons"]} for r in wm if not r["valid"]]},
                  "T_training_ms": [r["T_oracle_ms"] for r in tr],
                  "mean_all_ms": mean_all, "ratio_of_means": (mean_all / mean_warm) if (mean_all and mean_warm) else None,
                  "decisions_total": sum(r["provider_decisions"] for r in inv),
                  "decisions_per_invocation": sum(r["provider_decisions"] for r in inv) / LIVE_PLANNED,
                  "decomposition_warm": AC.decomposition([r for r in wm if r["valid"]]),
                  "decomposition_all": decomp_all,
                  "decomposition_training": AC.decomposition([r for r in tr if r["verified"]]),
                  "provider_decision_share_all": (decomp_all.get("share") or {}).get("provider_decision"),
                  "G3": g3_of([r for r in rows if r["cls"] == cls]), "E4": e4, "E4_clean": e4_clean(e4),
                  "loadavg_1m": {"min": min((r["loadavg_1m"] for r in inv), default=None), "median": med([r["loadavg_1m"] for r in inv]),
                                 "max": max((r["loadavg_1m"] for r in inv), default=None)}}
        L[cls]["verdict"] = ("DELETED" if (valid == WARM_PLANNED and L[cls]["warm"]["decisions"] == 0 and L[cls]["E4_clean"]
                                           and L[cls]["G3"]["pass"]) else "REVISE")
    L["first_trial_utc"] = min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)
    L["shakedown"] = [{"trial": r["trial"], "kind": r["kind"], "verified": r["verified"], "decisions": r["provider_decisions"],
                       "requests": r["provider_requests"]} for r in rows_of(raw, "lshake")]
    return L


def provider(raw: Path) -> dict[str, Any]:
    led = jsonl(raw / "provider-ledger.jsonl")
    att = [x for x in led if x.get("kind") == "attempt"]
    return {"attempts": len(att), "reached": sum(1 for x in att if x.get("reached")),
            "blocked_by_cap": sum(1 for x in led if x.get("kind") == "blocked_by_cap"),
            "by_layer": dict(Counter(x.get("layer") for x in att)),
            "reached_by_layer": dict(Counter(x.get("layer") for x in att if x.get("reached"))),
            "status": dict(Counter(str(x.get("status")) for x in att)),
            "request_id_present": sum(1 for x in att if x.get("request_id_present")),
            "hosts": sorted({str(x.get("host")) for x in att}), "lane_cap": {"reached": 18, "attempts": 22}}


def analyze(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "r2-07d.summary.v1"}
    S["phase_S"] = phase_s(raw)
    S["controls"] = controls(raw)
    S["phase_L"] = phase_l(raw)
    S["provider"] = provider(raw)
    arts = {}
    for p in sorted((raw / "artifacts").glob("*.json")) if (raw / "artifacts").exists() else []:
        art = json.loads(p.read_text())
        arts[p.name] = {"problems": AC.crt.check_artifact_authority_tm(art), "task_class": art.get("task_class"),
                        "steps": [s["logical_target"] for s in art.get("steps", [])]}
    S["artifacts"] = arts
    S["authority_clean"] = bool(arts) and all(not v["problems"] for v in arts.values())
    starts = [x for x in (S["phase_S"]["first_trial_utc"], S["controls"]["first_trial_utc"], S["phase_L"]["first_trial_utc"]) if x]
    S["first_measured_trial_utc"] = min(starts) if starts else None
    PS, L, C = S["phase_S"], S["phase_L"], S["controls"]
    failing = [f"timing:{c}" for c in CLASSES if not PS[c]["timing"]["gate_ci_upper_le_2ms"]]
    failing += [f"{g}:{c}" for c in CLASSES for g in ("G1", "G2", "G3") if not PS[c][g]["pass"]]
    failing += [f"E4:{c}" for c in CLASSES if not PS[c]["E4_clean"]]
    if not C["pass"] or not C["E4_clean"] or not C["G3"]["pass"]:
        failing.append("controls")
    if not S["authority_clean"]:
        failing.append("authority")
    if not PS["phase_S_pass_both"]:
        l_status = "NOT_RUN (pre-registered precondition: Phase S passes in both classes)"
        if L["run"]:
            l_status = "RUN_DESPITE_PRECONDITION"
    else:
        l_status = "RUN" if L["run"] else "NOT_RUN"
        for c in CLASSES:
            if L["run"] and L[c]["verdict"] != "DELETED":
                failing.append(f"phase_L:{c}:warm_valid={L[c]['warm']['valid']}/29,decisions={L[c]['warm']['decisions']},"
                               f"E4_clean={L[c]['E4_clean']}")
        if not L["run"]:
            failing.append("phase_L:not_run")
    keep = PS["phase_S_pass_both"] and L["run"] and all(L[c]["verdict"] == "DELETED" for c in CLASSES) and not failing
    S["disposition"] = {"disposition": "KEEP" if keep else "REVISE", "failing_gates": failing, "phase_L_status": l_status,
                        "provider_decision_component": ("DELETED" if keep else
                                                        ("REVISE (measured rate)" if L["run"] else "UNTESTED (Phase L NOT_RUN)")),
                        "e4_kill_candidate": any(not PS[c]["E4_clean"] for c in CLASSES) or not C["E4_clean"]
                        or (L["run"] and any(not L[c]["E4_clean"] for c in CLASSES))}
    return S


def fmt(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x:+.{nd}f}" if nd >= 0 else str(x)


def headlines(S: dict[str, Any]) -> dict[str, Any]:
    """Every number the README headline cites, with the exact text that must appear in README.md."""
    H: dict[str, Any] = {}
    PS = S["phase_S"]
    for c in CLASSES:
        t = PS[c]["timing"]
        d = t["diff_COMP_CR_minus_COMP_ms"]
        if d.get("median") is not None:
            ci = d["ci95"]
            text = f"{d['median']:+.1f} ms [{ci[0]:+.1f}, {ci[1]:+.1f}]"
            H[f"S_{c}_diff"] = {"value": [round(d["median"], 3), round(ci[0], 3), round(ci[1], 3)], "text": text}
            H[f"S_{c}_medians"] = {"value": [round(t["median_T_COMP_ms"], 3), round(t["median_T_COMP_CR_ms"], 3)],
                                   "text": f"{t['median_T_COMP_ms']:.1f} -> {t['median_T_COMP_CR_ms']:.1f} ms"}
        H[f"S_{c}_pairs"] = {"value": t["valid_pairs"], "text": f"{t['valid_pairs']}/{ROUNDS} pairs valid"}
        H[f"S_{c}_gate"] = {"value": t["gate_ci_upper_le_2ms"], "text": f"{c} gate {'PASS' if t['gate_ci_upper_le_2ms'] else 'FAIL'}"}
    g = PS["load_gate"]
    H["load_gate"] = {"value": [g["attempts"], g["starts"], g["end_chunk"]],
                      "text": f"{g['attempts']} gate attempts, {g['starts']} starts, {g['end_chunk']} chunk ends"}
    C = S["controls"]
    H["controls"] = {"value": [C["pass_cells"], C["expected_cells"]], "text": f"controls {C['pass_cells']}/{C['expected_cells']} pass"}
    P = S["provider"]
    H["provider"] = {"value": [P["attempts"], P["reached"]], "text": f"{P['attempts']} attempts / {P['reached']} reached"}
    L = S["phase_L"]
    if L["run"]:
        for c in CLASSES:
            w = L[c]["warm"]
            H[f"L_{c}_warm_valid"] = {"value": w["valid"], "text": f"{c} warm valid {w['valid']}/29"}
            H[f"L_{c}_warm_decisions"] = {"value": w["decisions"], "text": f"{c} warm decisions {w['decisions']}"}
            if w["median_T_oracle_ms"] is not None:
                H[f"L_{c}_warm_median"] = {"value": round(w["median_T_oracle_ms"], 3), "text": f"{w['median_T_oracle_ms']:.1f} ms"}
    H["disposition"] = {"value": S["disposition"]["disposition"], "text": f"Disposition: {S['disposition']['disposition']}"}
    return H


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "r2-07d-summary.json"))
    p.add_argument("--headlines", default=str(HERE / "headline-numbers.json"))
    a = p.parse_args()
    S = json.loads(json.dumps(analyze(Path(a.raw)), sort_keys=True, default=default))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    Path(a.headlines).write_text(json.dumps(headlines(S), indent=1, sort_keys=True) + "\n")
    print(json.dumps({"disposition": S["disposition"], "provider": S["provider"],
                      **{c: {"timing": {k: S["phase_S"][c]["timing"][k] for k in ("valid_pairs", "gate_ci_upper_le_2ms",
                                                                                  "median_T_COMP_ms", "median_T_COMP_CR_ms")},
                             "diff": S["phase_S"][c]["timing"]["diff_COMP_CR_minus_COMP_ms"],
                             "phase_S_pass": S["phase_S"][c]["phase_S_pass"]} for c in CLASSES},
                      "controls": {k: S["controls"][k] for k in ("pass", "pass_cells", "expected_cells", "E4_clean")}},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
