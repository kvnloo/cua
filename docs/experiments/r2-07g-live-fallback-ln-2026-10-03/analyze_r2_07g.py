"""R2-07g analysis: quiet toggle non-regression block (block t), carry-over controls (block ctl), live modal
forced-fallback re-run and toggle literal-rename negative (block l2), and the provider ledger.

Reads only the packet's raw/ (and, for the pooled LF rate, the committed R2-07e summary) and writes
r2-07g-summary.json + headline-numbers.json. Reuses, by import and unchanged, the R2-07e analysis
(latest_pairs, fb_row) and through it the R2-07d analysis (rows_of, g1_g2, g3_of, pair_stats, e4_clean, jsonl)
and the R2-07c analysis (load_block, manifests, row_of, g4_pass, nw2_row, decomposition, e4_total).

PRE-REGISTERED with PREREG.json (verify_artifacts.py checks they are unchanged since the PREREG commit):
``t_gate``, ``lf_gate``, ``e2_mapping``, ``false_success`` and their constants.

usage (under hostless): python analyze_r2_07g.py [--raw raw] [--out r2-07g-summary.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

T_ROUNDS = 40
GATE_MS = 2.0
LF_PLANNED = 3
LANE_CAP = {"reached": 16, "attempts": 20}

HERE = Path(__file__).resolve().parent
R207E_PKT = HERE.parent / "r2-07e-modal-gate-phase-l-2026-10-03"
sys.path.insert(0, str(R207E_PKT))
import analyze_r2_07e as AE  # noqa: E402  (puts the R2-07d and R2-07c analyses on sys.path)

AD = AE.AD
AC = AE.AC
CLASSES = AD.CLASSES
med, mean = AD.med, AD.mean


# ── pre-registered gate functions ────────────────────────────────────────────

def t_gate(pairs: list[tuple[float, float]], failed: list[Any], not_run: list[Any]) -> dict[str, Any]:
    """H_T, R2-07d PREREG text unchanged: median paired T_oracle(COMP_CR warm) - T_oracle(COMP), 95% seeded
    paired bootstrap CI (b01_analysis.paired_diff via analyze_r2_07d.pair_stats: seed 20261002, 10000
    resamples); PASS iff CI upper <= +2.0 ms AND all 40 pairs ran AND every timing cell is valid."""
    st = AD.pair_stats(pairs) if pairs else {"n": 0, "diff_COMP_CR_minus_COMP_ms": {}}
    ci = (st.get("diff_COMP_CR_minus_COMP_ms") or {}).get("ci95")
    st["pass"] = bool(ci and ci[1] <= GATE_MS and not failed and not not_run and len(pairs) == T_ROUNDS)
    return st


def false_success(row: dict[str, Any]) -> bool:
    """Success reported without the independent oracle confirming exactly one completion mutation."""
    reported = row.get("outcome") == "verified" or row.get("routine_outcome") in ("verified", "fallback_verified")
    return bool((reported and not row.get("verified")) or int((row.get("E4") or {}).get("unverified_success", 0)))


def lf_gate(lf: list[dict[str, Any] | None], planned: int = LF_PLANNED) -> dict[str, Any]:
    """Modal fallback gate: PASS iff all ``planned`` new LF invocations ran and verified (R2-07c g4_pass n7 row
    + oracle verified, exactly 1 completion mutation), with >= 1 live decision each, 0 false success, E4 0,
    and every decision counted (decided events == provider ledger attempts of that trial). A NOT_RUN LF
    stays in the denominator and fails the gate."""
    ran = [r for r in lf if r is not None]
    ok_rows = [r for r in ran if r["verified"] and r["row_pass"] and (r["decisions"] or 0) >= 1]
    fs = sum(1 for r in ran if false_success(r))
    e4 = sum(sum(int(v) for v in (r.get("E4") or {}).values()) for r in ran)
    counted = all(r.get("decisions_counted") for r in ran)
    return {"planned": planned, "ran": len(ran), "verified": len(ok_rows), "false_success": fs, "E4_total": e4,
            "every_decision_counted": counted,
            "pass": len(ran) == planned and len(ok_rows) == planned and fs == 0 and e4 == 0 and counted}


def e2_mapping(lf_pass: bool) -> dict[str, Any]:
    """E2 mapping of the live modal provider-decision component, fixed before the run."""
    return {"live_modal_provider_decision_component": "DELETED" if lf_pass else "OWNER_DECISION",
            "basis": ("admitted COMP+CR: warm 29/29 with 0 decisions (R2-07e) plus a shown live forced fallback"
                      if lf_pass else
                      "deletion works on warm (R2-07e 29/29, 0 decisions), but admitting a routine whose live "
                      "fallback continuation succeeds k/4 is an admission-policy choice"),
            "fallback_continuation_decisions": "IRREDUCIBLE",
            "fallback_basis": "invariant: a failed precondition must re-decide from the current state; blind replay is forbidden",
            "modal_lineage": "KEEP" if lf_pass else "REVISE",
            "depends_on": "owner accepting the SOURCE-forced n7_presat substitution for the literal rename "
                          "(BrowserSemanticSource.find matches role+name exactly, so a renamed target cannot verify)"}


# ── analysis ─────────────────────────────────────────────────────────────────

def default(o: Any) -> Any:
    return AD.default(o)


def part_t(raw: Path) -> dict[str, Any]:
    rows = [r for r in AD.rows_of(raw, "t") if r["cls"] == "toggle"]
    gate_log = AD.jsonl(raw / "t-load-gate.jsonl")
    progress = json.loads((raw / "t-progress.json").read_text()) if (raw / "t-progress.json").exists() else {}
    lp = AE.latest_pairs(rows, "toggle", list(range(T_ROUNDS)))
    st = t_gate(lp["pairs"], lp["failed"], lp["not_run"])
    gg = AD.g1_g2(rows, "toggle")
    g3 = AD.g3_of(rows)
    e4 = AC.e4_total(rows)
    trows = [r for r in rows if r["kind"] in ("measured", "warm") and r["valid"]]
    wm = [r for r in rows if r["kind"] == "warm"]
    T: dict[str, Any] = {
        "cells": len(rows),
        "interrupted_units": sorted(f"{x['unit']}#a{x['attempt']}" for x in progress.get("interrupted", [])),
        "load_gate": {"attempts": len(gate_log), "starts": sum(1 for g in gate_log if g["start"]),
                      "end_chunk": sum(1 for g in gate_log if not g["start"]),
                      "started_after_wait": sum(1 for g in gate_log if g["start"] and g["waited_s"] > 0),
                      "load_at_start_max": max((g["load_at_start"] for g in gate_log if g["start"]), default=None),
                      "load_at_start_median": med([g["load_at_start"] for g in gate_log if g["start"]]),
                      "chunks": sorted({g["chunk"] for g in gate_log}, key=lambda x: int(x))},
        "timing": {**st, "planned_pairs": T_ROUNDS, "valid_pairs": len(lp["pairs"]), "failed_pairs": lp["failed"],
                   "not_run_rounds": lp["not_run"],
                   "loadavg_1m": {"min": min(lp["loads"]) if lp["loads"] else None, "median": med(lp["loads"]),
                                  "max": max(lp["loads"]) if lp["loads"] else None},
                   "gate_975_view": AE.paired_gate([p[1] for p in lp["pairs"]], [p[0] for p in lp["pairs"]])},
        "sensitivity_load_le_3": AD.pair_stats(lp["pairs_q"]) if lp["pairs_q"] else {"n": 0},
        "G1": gg["G1"], "G2": gg["G2"], "training": gg["training"], "admission": gg["admission"],
        "G3": g3, "E4": e4, "E4_clean": AD.e4_clean(e4),
        "warm": {"n": len(wm), "valid": sum(1 for r in wm if r["valid"]), "fallbacks": sum(1 for r in wm if r["fallback"]),
                 "decisions": sum(r["provider_decisions"] for r in wm)},
        "decomposition": {arm: AC.decomposition([r for r in trows if r["arm"] == arm]) for arm in ("COMP", "COMP_CR")},
        "first_trial_utc": min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)}
    T["H_T"] = "PASS" if st["pass"] else "FAIL"
    T["toggle_keep_reconfirmed"] = bool(st["pass"] and g3["pass"] and AD.e4_clean(e4))
    return T


def part_c(raw: Path) -> dict[str, Any]:
    blocks = AC.load_block(raw, "ctl")
    rows = [AC.row_of(t) for t in blocks if t["summary"].get("kind") not in ("nw2", "smoke")]
    for t, r in zip([t for t in blocks if t["summary"].get("kind") not in ("nw2", "smoke")], rows):
        r["utc_start"] = t["summary"].get("utc_start")
    C: dict[str, Any] = {"cells": len(blocks)}
    g4: dict[str, Any] = {}
    for r in rows:
        if r["kind"] in ("train", "admission"):
            continue
        key = r["kind"] if r["kind"] != "n8" else f"n8:{r['cls']}-on-{r['page_cls']}"
        ok, note = AC.g4_pass(r)
        cell = g4.setdefault(key, {}).setdefault(r["cls"], {"n": 0, "pass": 0, "notes": []})
        cell["n"] += 1
        cell["pass"] += int(ok)
        cell["notes"].append(f"{r['trial']}: {'PASS' if ok else 'FAIL'} {note}")
    smoke = []
    for t in blocks:
        s = t["summary"]
        if s.get("kind") != "smoke":
            continue
        ok = (s.get("outcome") == "verified" and s.get("oracle_exact_match") is True and s.get("completion_mutations") == 1
              and s.get("driver_env_exp") == {} and s.get("driver_env_trace_set") is False and s.get("arm") == "BASE")
        smoke.append({"trial": t["name"], "cls": s.get("cls"), "pass": ok})
    g4["default_smoke"] = {cls: {"n": sum(1 for x in smoke if x["cls"] == cls),
                                 "pass": sum(1 for x in smoke if x["cls"] == cls and x["pass"])} for cls in CLASSES}
    C["rows"] = g4
    expected = {"n4a": (CLASSES, 1), "n4b": (CLASSES, 1), "n8:toggle-on-modal": (["toggle"], 1),
                "n8:modal-on-toggle": (["modal"], 1), "default_smoke": (CLASSES, 3)}
    C["expected_cells"] = sum(len(cl) * n for cl, n in expected.values())
    C["pass_cells"] = sum(min(g4.get(k, {}).get(c, {}).get("pass", 0), n) for k, (cl, n) in expected.items() for c in cl)
    C["G1_G2"] = {cls: {k: v for k, v in AD.g1_g2(rows, cls).items() if k in ("G1", "G2")} for cls in CLASSES}
    e4 = AC.e4_total(rows)
    C["E4"] = e4
    C["E4_clean"] = AD.e4_clean(e4)
    n4b = [r for r in rows if r["kind"] == "n4b"]
    C["G3_nonfresh_refused"] = {"n4b_cells": len(n4b),
                                "nonfresh_attempts": sum(r["g3"]["nonfresh_attempts"] for r in n4b),
                                "nonfresh_refused_effect_refused": sum(r["g3"]["nonfresh_refused"] for r in n4b)}
    C["all_pass"] = bool(C["pass_cells"] == C["expected_cells"] and C["E4_clean"]
                         and all(C["G1_G2"][c]["G1"]["pass"] and C["G1_G2"][c]["G2"]["pass"] for c in CLASSES))
    C["first_trial_utc"] = min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)
    return C


def l2_row(r: dict[str, Any] | None, summ: dict[str, Any], ledger: list[dict[str, Any]],
           events: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    v = AE.fb_row(r, summ)
    if v is None:
        return None
    s = summ.get(r["trial"], {})
    lines = [x for x in ledger if x.get("kind") == "attempt" and x.get("trial") == r["trial"]]
    decided_events = len(s.get("decisions") or []) + (1 if s.get("provider_error") else 0)
    clicks = [m.get("label") or m.get("tool") for m in (s.get("mutations") or []) if m.get("result") == "accepted"]
    v.update({"routine_outcome": r.get("routine_outcome"), "ledger_lines": len(lines),
              "ledger_reached": sum(1 for x in lines if x.get("reached")),
              "decisions_counted": decided_events == len(lines) == (r["provider_requests"] or {}).get("attempts", -1),
              "provider_error": s.get("provider_error"), "stop": s.get("stop"),
              "accepted_click_labels": clicks, "candidates": s.get("candidates"),
              "non_completion_accepted": (r["accepted_mutations"] or 0) - (r["completion_mutations"] or 0),
              "reobserve_count": sum(1 for x in v["decided"] if x == "reobserve"),
              "offered_per_step": [e.get("ids") for e in events.get(r["trial"], []) if e.get("event") == "cand_done"],
              "budget_exhausted": r.get("outcome") == "budget_exhausted"})
    v["false_success"] = false_success(v)
    return v


def part_l2(raw: Path, controls_pass: bool) -> dict[str, Any]:
    rows = AD.rows_of(raw, "l2")
    blk = AC.load_block(raw, "l2")
    summ = {t["name"]: t["summary"] for t in blk}
    evs = {t["name"]: t["events"] for t in blk}
    man = AC.manifests(raw, "l2")
    ledger = AD.jsonl(raw / "provider-ledger.jsonl")
    not_run = [x for m in man for x in m.get("not_run", [])]
    L: dict[str, Any] = {"run": bool(rows), "manifests": len(man), "not_run": not_run,
                         "stopped_for_budget": [m.get("stopped_for_budget") for m in man if m.get("stopped_for_budget")],
                         "retrains": [x for m in man for x in m.get("retrains", [])], "provider_models": {},
                         "controls_pass": controls_pass}
    for m in man:
        for k, val in (m.get("provider_models") or {}).items():
            L["provider_models"][k] = L["provider_models"].get(k, 0) + val
    for cls in CLASSES:
        crow = [r for r in rows if r["cls"] == cls]
        gg = AD.g1_g2(crow, cls)
        L[f"training_{cls}"] = {"G1": gg["G1"], "G2": gg["G2"], "training": gg["training"], "admission": gg["admission"],
                                "decisions": sum(r["provider_decisions"] for r in crow if r["kind"] in ("train", "admission")),
                                "requests": sum(((r["provider_requests"] or {}).get("attempts", 0)) for r in crow
                                                if r["kind"] in ("train", "admission"))}
    lf_rows = sorted([r for r in rows if r["cls"] == "modal" and r["kind"] == "n7"], key=lambda r: r["round"])
    lf = [l2_row(r, summ, ledger, evs) for r in lf_rows]
    lf_nr = [x for x in not_run if "-modal-" in x["trial"] and "-n7-" in x["trial"]]
    lf_all = lf + [None] * len(lf_nr)
    L["LF"] = lf
    L["LF_not_run"] = lf_nr
    L["LF_gate"] = lf_gate(lf_all)
    L["LF_completion_offered_every_step"] = [all("confirm-choice" in (ids or []) for ids in x["offered_per_step"])
                                            and bool(x["offered_per_step"]) for x in lf]
    ln = next((r for r in rows if r["cls"] == "toggle" and r["kind"] == "n1"), None)
    L["LN"] = l2_row(ln, summ, ledger, evs)
    L["LN_not_run"] = [x for x in not_run if "-toggle-" in x["trial"] and "-n1-" in x["trial"]]
    lnv = L["LN"]
    L["LN_expected_outcome_met"] = (None if lnv is None else
                                    bool(lnv["row_pass"] and not lnv["verified"] and lnv["completion_mutations"] == 0
                                         and not lnv["false_success"]))
    live = [r for r in rows if r["kind"] in ("n7", "n1")]
    L["E4_live"] = AC.e4_total(live)
    L["E4_all_cells"] = AC.e4_total(rows)
    L["E4_clean"] = AD.e4_clean(L["E4_all_cells"])
    L["G3"] = AD.g3_of(rows)
    L["loadavg_1m"] = {"min": min((r["loadavg_1m"] for r in rows), default=None), "median": med([r["loadavg_1m"] for r in rows]),
                       "max": max((r["loadavg_1m"] for r in rows), default=None)}
    # pooled with R2-07e's single modal LF (descriptive; n = 4 estimates no rate)
    prior = json.loads((R207E_PKT / "r2-07e-summary.json").read_text())["part_L"]["modal"]["LF"]
    prior_ok = bool(prior and prior.get("verified") and prior.get("row_pass"))
    L["LF_pooled_with_r2_07e"] = {"k": L["LF_gate"]["verified"] + int(prior_ok), "n": LF_PLANNED + 1,
                                  "r2_07e": {"trial": prior.get("trial"), "verified": prior_ok, "outcome": prior.get("outcome"),
                                             "decided": prior.get("decided")},
                                  "failure_modes": dict(Counter(
                                      ("verified" if (x and x["verified"]) else
                                       "not_run" if x is None else
                                       f"{x['outcome']}:{'reobserve_x' + str(x['reobserve_count']) if x['reobserve_count'] else 'no_reobserve'}")
                                      for x in lf_all + [{"verified": prior_ok, "outcome": prior.get("outcome"),
                                                          "reobserve_count": sum(1 for c in prior.get("decided") or [] if c == "reobserve")}]))}
    L["first_trial_utc"] = min((r["utc_start"] for r in rows if r.get("utc_start")), default=None)
    return L


def provider(raw: Path) -> dict[str, Any]:
    led = AD.jsonl(raw / "provider-ledger.jsonl")
    att = [x for x in led if x.get("kind") == "attempt"]
    reached = sum(1 for x in att if x.get("reached"))
    return {"attempts": len(att), "reached": reached,
            "blocked_by_cap": sum(1 for x in led if x.get("kind") == "blocked_by_cap"),
            "by_trial": dict(Counter(x.get("trial") for x in att)),
            "by_layer": dict(Counter(x.get("layer") for x in att)),
            "status": dict(Counter(str(x.get("status")) for x in att)),
            "request_id_present": sum(1 for x in att if x.get("request_id_present")),
            "hosts": sorted({str(x.get("host")) for x in att}), "paths": sorted({str(x.get("path")) for x in att}),
            "latency_ms_median": med([x["latency_ms"] for x in att if x.get("latency_ms") is not None]),
            "lane_cap": LANE_CAP, "within_cap": len(att) <= LANE_CAP["attempts"] and reached <= LANE_CAP["reached"]}


def analyze(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "r2-07g.summary.v1"}
    S["part_T"] = part_t(raw)
    S["part_C"] = part_c(raw)
    S["part_L2"] = part_l2(raw, S["part_C"]["all_pass"])
    S["provider"] = provider(raw)
    arts = {}
    for p in sorted((raw / "artifacts").glob("*.json")) if (raw / "artifacts").exists() else []:
        art = json.loads(p.read_text())
        arts[p.name] = {"problems": AC.crt.check_artifact_authority_tm(art), "task_class": art.get("task_class"),
                        "steps": [s["logical_target"] for s in art.get("steps", [])]}
    S["artifacts"] = arts
    S["authority_clean"] = bool(arts) and all(not v["problems"] for v in arts.values())
    starts = [x for x in (S["part_T"]["first_trial_utc"], S["part_C"]["first_trial_utc"], S["part_L2"]["first_trial_utc"]) if x]
    S["first_measured_trial_utc"] = min(starts) if starts else None
    lfg = S["part_L2"]["LF_gate"]
    S["e2"] = e2_mapping(lfg["pass"])
    T = S["part_T"]
    S["disposition"] = {
        "H_T": T["H_T"], "toggle_lineage": "KEEP" if T["toggle_keep_reconfirmed"] else "REVISE",
        "H_LF": "PASS" if lfg["pass"] else "FAIL", "modal_lineage": S["e2"]["modal_lineage"],
        "e2_live_modal_provider_decision": S["e2"]["live_modal_provider_decision_component"],
        "e2_fallback_continuation_decisions": "IRREDUCIBLE",
        "toggle_LN": ("NOT_RUN" if S["part_L2"]["LN"] is None else
                      "refused at the failed precondition, 0 completion, no success reported"
                      if S["part_L2"]["LN_expected_outcome_met"] else "unexpected outcome (see LN row)"),
        "controls": "PASS" if S["part_C"]["all_pass"] else "FAIL",
        "authority_clean": S["authority_clean"],
        "e4_kill_candidate": (not T["E4_clean"]) or (not S["part_C"]["E4_clean"]) or (not S["part_L2"]["E4_clean"])}
    d = S["disposition"]
    d["lineage"] = f"toggle {d['toggle_lineage']} / modal {d['modal_lineage']}"
    return S


def headlines(S: dict[str, Any]) -> dict[str, Any]:
    """Every number the README headline cites, with the exact text that must appear in README.md."""
    H: dict[str, Any] = {}
    t = S["part_T"]["timing"]
    dci = (t.get("diff_COMP_CR_minus_COMP_ms") or {})
    if dci.get("ci95"):
        H["T_diff95"] = {"value": [round(dci["median"], 3), round(dci["ci95"][0], 3), round(dci["ci95"][1], 3)],
                         "text": f"{dci['median']:+.1f} ms [{dci['ci95'][0]:+.1f}, {dci['ci95'][1]:+.1f}]"}
        H["T_medians"] = {"value": [round(t["median_T_COMP_ms"], 3), round(t["median_T_COMP_CR_ms"], 3)],
                          "text": f"{t['median_T_COMP_ms']:.1f} -> {t['median_T_COMP_CR_ms']:.1f} ms"}
    H["T_pairs"] = {"value": t["valid_pairs"], "text": f"{t['valid_pairs']}/{t['planned_pairs']} pairs valid"}
    H["H_T"] = {"value": S["part_T"]["H_T"], "text": f"H_T {S['part_T']['H_T']}"}
    sens = S["part_T"]["sensitivity_load_le_3"]
    if (sens.get("diff_COMP_CR_minus_COMP_ms") or {}).get("ci95"):
        sd = sens["diff_COMP_CR_minus_COMP_ms"]
        H["T_sensitivity"] = {"value": [sens["n"], round(sd["median"], 3), round(sd["ci95"][0], 3), round(sd["ci95"][1], 3)],
                              "text": f"{sens['n']} pairs: {sd['median']:+.1f} ms [{sd['ci95'][0]:+.1f}, {sd['ci95'][1]:+.1f}]"}
    g = S["part_T"]["load_gate"]
    H["T_load_gate"] = {"value": [g["attempts"], g["starts"], g["end_chunk"]],
                        "text": f"{g['attempts']} gate attempts, {g['starts']} starts, {g['end_chunk']} chunk ends"}
    C = S["part_C"]
    H["controls"] = {"value": [C["pass_cells"], C["expected_cells"]], "text": f"controls {C['pass_cells']}/{C['expected_cells']} pass"}
    L = S["part_L2"]
    lg = L["LF_gate"]
    H["LF"] = {"value": [lg["verified"], lg["planned"]], "text": f"LF {lg['verified']}/{lg['planned']} verified"}
    H["H_LF"] = {"value": S["disposition"]["H_LF"], "text": f"H_LF {S['disposition']['H_LF']}"}
    pk = L["LF_pooled_with_r2_07e"]
    H["LF_pooled"] = {"value": [pk["k"], pk["n"]], "text": f"pooled with R2-07e {pk['k']}/{pk['n']}"}
    H["E2"] = {"value": S["e2"]["live_modal_provider_decision_component"],
               "text": f"live modal provider-decision component: {S['e2']['live_modal_provider_decision_component']}"}
    P = S["provider"]
    H["provider"] = {"value": [P["attempts"], P["reached"]], "text": f"{P['attempts']} attempts / {P['reached']} reached"}
    H["lineage"] = {"value": S["disposition"]["lineage"], "text": f"Lineage disposition: {S['disposition']['lineage']}"}
    return H


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "r2-07g-summary.json"))
    p.add_argument("--headlines", default=str(HERE / "headline-numbers.json"))
    a = p.parse_args()
    S = json.loads(json.dumps(analyze(Path(a.raw)), sort_keys=True, default=default))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    Path(a.headlines).write_text(json.dumps(headlines(S), indent=1, sort_keys=True) + "\n")
    print(json.dumps({"disposition": S["disposition"], "provider": {k: S["provider"][k] for k in ("attempts", "reached")},
                      "T": {k: S["part_T"]["timing"].get(k) for k in ("valid_pairs", "pass", "median_T_COMP_ms",
                                                                       "median_T_COMP_CR_ms", "diff_COMP_CR_minus_COMP_ms")},
                      "LF_gate": S["part_L2"]["LF_gate"],
                      "controls": {k: S["part_C"][k] for k in ("all_pass", "pass_cells", "expected_cells", "E4_clean")}},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
