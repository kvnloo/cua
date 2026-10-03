"""R2-07c analysis: gates G1-G6, scripted timing (COMP vs COMP_CR), Phase L live COMP+CR.

Reads only the packet's raw/ bundles (<block>-trials.tar.gz, run manifests, routines, provider ledger)
and writes r2-07c-summary.json. Reuses the R2-10 per-trial row (analyze_r2_10.browser_row: T_oracle,
B-01/B-02 decomposition, forced-path and arm-configuration checks, E4 accounting) unchanged by import.

usage (under hostless): python analyze_r2_07c.py [--raw raw] [--out r2-07c-summary.json]
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "harness"), str(HERE / "harness" / "src" / "r2-10-composition-2026-10-02"),
                str(HERE / "harness" / "src" / "r2-10-composition-2026-10-02" / "harness" / "src" / "r2-07-2026-10-02" / "harness")]
import analyze_r2_10 as A  # noqa: E402  (also puts the B-02/B-01 analysis modules on sys.path)
import compiled_routine_tm as crt  # noqa: E402

B = A.B
CLASSES = ["toggle", "modal"]
TIMING_GATE_MS = 2.0
VERDICTS_CR = dict(A.BROWSER_VERDICTS)
VERDICTS_CR["provider_decision"] = "DELETED_IF_KEEP"


def med(xs):
    return A.med(xs)


def mean(xs):
    return A.mean(xs)


# ── io ────────────────────────────────────────────────────────────────────────

def load_block(raw: Path, block: str) -> list[dict[str, Any]]:
    path = raw / f"{block}-trials.tar.gz"
    if not path.exists():
        return []
    files: dict[str, str] = {}
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile():
                name = m.name[2:] if m.name.startswith("./") else m.name
                files[name] = tar.extractfile(m).read().decode()
    out = []
    for name in sorted(files):
        if not name.endswith(".jsonl") or name.endswith(".driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in files[name].splitlines() if x.strip()]
        s = lines[-1]
        if s.get("event") != "summary":
            continue
        trace_text = files.get(s["driver_trace"]) if s.get("driver_trace") else None
        trace = [json.loads(x) for x in trace_text.splitlines() if x.strip()] if trace_text else []
        out.append({"name": s["trial"], "summary": s, "events": lines[:-1], "trace": trace, "bundle": path.name,
                    "block": block})
    return out


def manifests(raw: Path, block: str) -> list[dict[str, Any]]:
    d = raw / f"{block}-manifests"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []


# ── per-trial row ─────────────────────────────────────────────────────────────

def click_route_ok(t: dict[str, Any], accepted: list[dict[str, Any]]) -> list[str]:
    reasons = []
    windows = {w["label"]: w for w in B._windows(t["events"])}
    for m in accepted:
        if m.get("tool") != "browser_click":
            reasons.append(f"tool={m.get('tool')}")
            continue
        if m.get("input_route") != "dom_event":
            reasons.append(f"click_input_route={m.get('input_route')}")
        if m.get("route") != "dom":
            reasons.append(f"click_receipt_route={m.get('route')}")
        w = windows.get(m["label"])
        if w and not any(x["phase"] == "click.cdp_send" and w["t0"] <= x["t_mono_ns"] <= w["t1"] for x in t["trace"]):
            reasons.append("click_without_cdp_send")
    return reasons


def row_of(t: dict[str, Any]) -> dict[str, Any]:
    """R2-10 browser_row; COMP_CR cells get R2-10's arm-configuration checks (kind 'smoke' view, arm
    COMP) plus the compiled-replay forced path: two dom_event clicks with click.cdp_send, route
    'compiled' only, 0 decisions and 0 provider requests (warm/admission on the normal page)."""
    s = t["summary"]
    if s.get("arm") == "COMP":
        row = A.browser_row(t, None)
        row["block"] = t["block"]
        row["provider_requests"] = None
        return row
    view = copy.deepcopy(t)
    view["summary"]["kind"] = "smoke"
    view["summary"]["arm"] = "COMP"
    row = A.browser_row(view, None)
    row.update({"arm": "COMP_CR", "kind": s.get("kind"), "block": t["block"]})
    muts = s.get("mutations") or []
    accepted = [m for m in muts if m.get("result") == "accepted"]
    routes = s.get("routes") or []
    kind = s.get("kind")
    reasons = list(row["reasons"])
    reasons = [r for r in reasons if not r.startswith("not_verified") and r != "T_oracle_undefined"]
    if kind in ("warm", "admission"):
        if not row["verified"]:
            reasons.append(f"not_verified:{s.get('outcome')}:{s.get('oracle_exact_match')}:{s.get('completion_mutations')}")
        if row["T_oracle_ms"] is None:
            reasons.append("T_oracle_undefined")
        if [m.get("tool") for m in accepted] != ["browser_click", "browser_click"]:
            reasons.append(f"tools={[m.get('tool') for m in accepted]}")
        if routes != ["compiled"]:
            reasons.append(f"routes={routes}")
        if row["provider_decisions"] != 0:
            reasons.append(f"decisions={row['provider_decisions']}")
        if (s.get("provider_requests") or {}).get("attempts", 0) != 0:
            reasons.append("provider_requests_in_warm")
    elif kind == "train":
        if not row["verified"]:
            reasons.append(f"not_verified:{s.get('outcome')}:{s.get('oracle_exact_match')}:{s.get('completion_mutations')}")
        if [m.get("tool") for m in accepted] != ["browser_click", "browser_click"]:
            reasons.append(f"tools={[m.get('tool') for m in accepted]}")
        if routes != ["provider", "provider"]:
            reasons.append(f"routes={routes}")
    row["reasons"] = reasons
    row["valid"] = not reasons
    row["routine"] = s.get("routine")
    row["routine_outcome"] = s.get("routine_outcome")
    row["fallback"] = s.get("fallback")
    row["provider_requests"] = s.get("provider_requests")
    row["provider_models"] = s.get("provider_models")
    rm = (s.get("routine") or {}).get("mutations") or []
    row["e4"]["dispatches_after_unknown"] = A.dispatches_after_unknown(rm)
    row["e4"]["ambiguous_dispatch"] = sum(1 for m in rm if m.get("unique_matches", 1) != 1 and m.get("result") == "accepted")
    # launcher receipts: every accepted mutation fresh; every non-fresh attempt refused (effect=refused)
    row["g3"] = {"accepted": len(accepted), "accepted_fresh": sum(1 for m in accepted if m.get("fresh")),
                 "nonfresh_attempts": sum(1 for m in muts if not m.get("fresh")),
                 "nonfresh_refused": sum(1 for m in muts if not m.get("fresh") and m.get("result") == "refused"
                                         and (m.get("driver_result") or {}).get("effect") == "refused")}
    row["refusals"] = [{"code": m.get("code"), "effect": (m.get("driver_result") or {}).get("effect"),
                        "fresh": m.get("fresh")} for m in muts if m.get("result") == "refused"]
    row["accepted_mutations"] = len(accepted)
    row["completion_mutations"] = s.get("completion_mutations")
    row["journal_events"] = Counter(e.get("event") for e in s.get("journal") or [])
    snap1 = A.first_window(t["events"], "snapshot1")
    row["t_to_end_ms"] = ((s["t_end_ns"] - snap1["t0"]) / 1e6) if (snap1 and s.get("t_end_ns")) else None
    row["training"] = s.get("training")
    row["dom_replace"] = s.get("dom_replace")
    row["superseded"] = s.get("superseded")
    row["session_replaced"] = s.get("session_replaced")
    row["fault_fired"] = s.get("fault_fired")
    row["g5_row"] = s.get("g5_row")
    row["journal_before_release"] = s.get("journal_before_release")
    row["observations"] = len((s.get("routine") or {}).get("observations") or [])
    row["routine_mutations"] = rm
    row["dropped_not_unique"] = s.get("dropped_not_unique")
    row["driver"] = {k: s.get(k) for k in ("driver_name", "driver_sha256", "driver_version")}
    return row


def nw2_row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    env = s.get("nw2_stale_envelope") or {}
    ok = (env.get("effect") == "refused" and env.get("code") == "browser_ref_stale"
          and s.get("nw2_mutations_from_stale_action") == 0 and s.get("outcome") == "verified"
          and s.get("oracle_exact_match") is True)
    return {"trial": t["name"], "cls": s.get("cls"), "block": t["block"], "stale_effect": env.get("effect"),
            "stale_code": env.get("code"), "stale_mutations": s.get("nw2_mutations_from_stale_action"),
            "outcome": s.get("outcome"), "pass": ok, "loadavg_1m": float(str(s.get("loadavg_before", "nan")).split()[0])}


# ── gates ─────────────────────────────────────────────────────────────────────

def g4_pass(r: dict[str, Any]) -> tuple[bool, str]:
    k = r["kind"]
    rm = r["routine_mutations"]
    fb = r.get("fallback") or {}
    cm = r["completion_mutations"] or 0
    e4 = r["e4"]
    e4_clean = (e4["caller_stale_dispatch"] == 0 and e4["duplicate_mutation"] == 0 and e4["unverified_success"] == 0
                and e4["refusal_returned_as_success"] == 0 and e4["blind_replay"] == 0
                and e4["dispatches_after_unknown"] == 0 and e4["ambiguous_dispatch"] == 0)
    if not e4_clean:
        return False, "e4"
    routine_dispatch_after_fail = 0
    if fb:
        idx = fb.get("index")
        routine_dispatch_after_fail = sum(1 for m in rm if isinstance(m.get("step"), int) and idx is not None
                                          and m["step"] >= idx)
    if k in ("n1", "n2"):
        ok = bool(fb) and routine_dispatch_after_fail == 0 and cm == 0 and r["outcome"] != "verified"
        return ok, f"fallback={fb.get('reason')} cm={cm} outcome={r['outcome']}"
    if k == "n3":
        ok = (bool(fb) and "ambiguous" in str(fb.get("reason")) and routine_dispatch_after_fail == 0 and cm == 0
              and r["outcome"] != "verified")
        return ok, f"fallback={fb.get('reason')} cm={cm} dropped={r.get('dropped_not_unique')}"
    if k == "n4a":
        refs = r["refusals"]
        ok = (r["dom_replace"] == "replaced" and len(refs) == 1 and refs[0]["code"] == "browser_ref_stale"
              and refs[0]["effect"] == "refused" and r["observations"] == 3 and r["verified"] and cm == 1
              and not fb)
        return ok, f"refusals={refs} obs={r['observations']} cm={cm}"
    if k == "n4b":
        refs = r["refusals"]
        rebinds_ok = all(x["code"] == "browser_ref_stale" and x["effect"] == "refused" for x in refs) and len(refs) <= 1
        ok = (r.get("superseded") is not None and r["verified"] and cm == 1 and rebinds_ok
              and r["observations"] == 2 + len(refs) and r["g3"]["accepted_fresh"] == r["g3"]["accepted"] and not fb)
        return ok, f"refusals={refs} obs={r['observations']} cm={cm}"
    if k == "n5":
        sr = r.get("session_replaced") or {}
        ok = (sr.get("old_target_in_new_session") == "refused" and r["verified"] and cm == 1
              and r["g3"]["accepted_fresh"] == r["g3"]["accepted"] and not fb)
        return ok, f"probe={sr.get('old_target_in_new_session')}:{sr.get('old_target_refusal_code')} cm={cm}"
    if k == "n6":
        ok = (r["journal_events"].get("dialog_opened", 0) >= 1 and bool(fb) and fb.get("index") == 1
              and routine_dispatch_after_fail == 0 and cm == 0 and r["outcome"] != "verified")
        return ok, f"dialog={r['journal_events'].get('dialog_opened', 0)} fallback={fb} cm={cm}"
    if k == "n7":
        ok = (bool(fb) and fb.get("index") == 0 and len(rm) == 0 and r["verified"] and cm == 1
              and r["accepted_mutations"] == 1)
        return ok, f"fallback={fb.get('reason')} accepted={r['accepted_mutations']} cm={cm}"
    if k == "n8":
        ok = r["accepted_mutations"] == 0 and cm == 0 and r["outcome"] != "verified"
        return ok, f"accepted={r['accepted_mutations']} cm={cm} fallback={fb.get('reason')}"
    if k == "g5":
        row = r["g5_row"]
        exp = {"verified_by_reconcile"} if row != "withheld_unresolved" else {"verified_by_reconcile", "unknown"}
        ok = bool(r["fault_fired"]) and r["routine_outcome"] in exp and cm <= 1
        return ok, f"{row}: {r['routine_outcome']} fired={r['fault_fired']} cm={cm}"
    return False, f"unknown kind {k}"


def timing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cls in CLASSES:
        by_round: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
        for r in rows:
            if r["cls"] == cls and r.get("round") is not None and r["round"] >= 0 and r["kind"] in ("measured", "warm"):
                by_round[r["round"]][r["arm"]] = r
        pairs, failed, loads = [], [], []
        for rnd in sorted(by_round):
            a, b = by_round[rnd].get("COMP"), by_round[rnd].get("COMP_CR")
            if not (a and b and a["valid"] and b["valid"] and a["T_oracle_ms"] is not None and b["T_oracle_ms"] is not None):
                failed.append({"round": rnd, "COMP": None if a is None else a["reasons"],
                               "COMP_CR": None if b is None else b["reasons"]})
                continue
            pairs.append((a["T_oracle_ms"], b["T_oracle_ms"]))
            loads += [a["loadavg_1m"], b["loadavg_1m"]]
        diff = B.paired_diff([p[1] for p in pairs], [p[0] for p in pairs])  # COMP_CR - COMP
        s = A.ratio_stat(pairs)
        n_rounds = len(by_round)
        out[cls] = {"rounds": n_rounds, "valid_pairs": len(pairs), "failed_pairs": failed,
                    "median_T_COMP_ms": med([p[0] for p in pairs]), "median_T_COMP_CR_ms": med([p[1] for p in pairs]),
                    "diff_COMP_CR_minus_COMP_ms": diff, "S_COMP_over_COMP_CR": s,
                    "loadavg_1m": {"min": min(loads) if loads else None, "median": med(loads), "max": max(loads) if loads else None},
                    "gate_ci_upper_le_2ms": bool(diff.get("ci95") and diff["ci95"][1] <= TIMING_GATE_MS and not failed
                                                 and n_rounds == 30)}
    return out


def decomposition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for r in rows if r.get("components")]
    if not rows:
        return {"n": 0}
    keys = list(rows[0]["components"])
    comp = {k: mean([r["components"][k] for r in rows]) for k in keys}
    t_runner = mean([r["T_runner_ms"] for r in rows])
    untested = sum(v for k, v in comp.items() if VERDICTS_CR.get(k) == "UNTESTED")
    return {"n": len(rows), "mean_T_runner_ms": t_runner, "mean_T_oracle_ms": mean([r["T_oracle_ms"] for r in rows]),
            "components_ms": comp,
            "share": {k: (v / t_runner if t_runner else None) for k, v in comp.items()},
            "coverage_mean": mean([r.get("coverage") for r in rows]),
            "untested_share": untested / t_runner if t_runner else None,
            "irreducible_ms": sum(v for k, v in comp.items() if VERDICTS_CR.get(k) == "IRREDUCIBLE")}


def e4_total(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = ["caller_stale_dispatch", "duplicate_mutation", "unverified_success", "refusal_returned_as_success",
            "blind_replay", "dispatches_after_unknown", "ambiguous_dispatch"]
    return {k: sum(int((r.get("e4") or {}).get(k, 0)) for r in rows) for k in keys}


def analyze(raw: Path) -> dict[str, Any]:
    S: dict[str, Any] = {"schema": "r2-07c.summary.v1"}
    blocks = {b: load_block(raw, b) for b in ("gate", "gate2", "neg", "nw2", "rec", "timed", "costs", "lshake", "live")}
    S["blocks"] = {b: len(v) for b, v in blocks.items()}
    rows = {b: [row_of(t) if t["summary"].get("kind") != "nw2" else None for t in v] for b, v in blocks.items()}
    S["failed_session_blocks"] = {"gate": [r["trial"] for r in rows["gate"]]}
    cr_rows = [r for b in ("gate2", "neg", "rec", "timed", "costs", "lshake", "live") for r in rows[b]
               if r is not None and r["arm"] == "COMP_CR"]

    # artifacts + authority scan
    arts = {}
    for p in sorted((raw / "artifacts").glob("*.json")) if (raw / "artifacts").exists() else []:
        art = json.loads(p.read_text())
        arts[p.name] = {"problems": crt.check_artifact_authority_tm(art), "task_class": art.get("task_class"),
                        "steps": [s["logical_target"] for s in art.get("steps", [])]}
    S["artifacts"] = arts
    S["authority_clean"] = bool(arts) and all(not v["problems"] for v in arts.values())

    # G1 / G2
    trains = [r for r in cr_rows if r["kind"] == "train"]
    adms = [r for r in cr_rows if r["kind"] == "admission"]
    S["G1"] = {cls: {"n": len([r for r in trains if r["cls"] == cls]),
                     "verified_compiled_clean": sum(1 for r in trains if r["cls"] == cls and r["verified"]
                                                    and (r["training"] or {}).get("compile_error") is None
                                                    and (r["training"] or {}).get("authority_problems") == []),
                     "rows": [{"trial": r["trial"], "verified": r["verified"], "valid": r["valid"],
                               "training": {k: (r["training"] or {}).get(k) for k in ("compile_ms", "compile_error", "admitted")}}
                              for r in trains if r["cls"] == cls]} for cls in CLASSES}
    for cls in CLASSES:
        S["G1"][cls]["pass"] = S["G1"][cls]["n"] > 0 and S["G1"][cls]["n"] == S["G1"][cls]["verified_compiled_clean"]
    S["G2"] = {cls: {"n": len([r for r in adms if r["cls"] == cls]),
                     "pass_n": sum(1 for r in adms if r["cls"] == cls and r["verified"] and r["valid"] and not r["fallback"]
                                   and r["provider_decisions"] == 0 and r["g3"]["accepted_fresh"] == r["g3"]["accepted"])}
               for cls in CLASSES}
    for cls in CLASSES:
        S["G2"][cls]["pass"] = S["G2"][cls]["n"] > 0 and S["G2"][cls]["n"] == S["G2"][cls]["pass_n"]
    # G3
    acc = sum(r["g3"]["accepted"] for r in cr_rows)
    fresh = sum(r["g3"]["accepted_fresh"] for r in cr_rows)
    nfa = sum(r["g3"]["nonfresh_attempts"] for r in cr_rows)
    nfr = sum(r["g3"]["nonfresh_refused"] for r in cr_rows)
    S["G3"] = {"cells": len(cr_rows), "accepted_mutations": acc, "accepted_fresh": fresh, "nonfresh_attempts": nfa,
               "nonfresh_attempts_refused_effect_refused": nfr, "pass": acc > 0 and acc == fresh and nfa == nfr}
    # G4
    g4: dict[str, Any] = {}
    for r in rows["neg"]:
        if r is None:
            continue
        key = r["kind"] if r["kind"] != "n8" else f"n8:{r['cls']}-on-{r['page_cls']}"
        ok, note = g4_pass(r)
        cell = g4.setdefault(key, {}).setdefault(r["cls"], {"n": 0, "pass": 0, "notes": []})
        cell["n"] += 1
        cell["pass"] += int(ok)
        cell["notes"].append(f"{r['trial']}: {'PASS' if ok else 'FAIL'} {note}")
    nw2 = [nw2_row(t) for t in blocks["nw2"]]
    g4["nw2"] = {cls: {"n": sum(1 for x in nw2 if x["cls"] == cls), "pass": sum(1 for x in nw2 if x["cls"] == cls and x["pass"]),
                       "rows": [x for x in nw2 if x["cls"] == cls]} for cls in CLASSES}
    S["G4"] = g4
    expected = {**{k: CLASSES for k in ("n1", "n2", "n3", "n4a", "n4b", "n5", "n6", "n7", "nw2")},
                "n8:toggle-on-fill": ["toggle"], "n8:toggle-on-modal": ["toggle"], "n8:modal-on-toggle": ["modal"]}
    S["G4_pass"] = all(cls in g4.get(k, {}) and g4[k][cls]["n"] == 5 and g4[k][cls]["pass"] == 5
                       for k, cl in expected.items() for cls in cl)
    # G5
    g5: dict[str, Any] = {}
    for r in rows["rec"]:
        ok, note = g5_ok = g4_pass(r)
        cell = g5.setdefault(r["g5_row"], {}).setdefault(r["cls"], {"n": 0, "pass": 0, "outcomes": Counter(), "notes": []})
        cell["n"] += 1
        cell["pass"] += int(ok)
        cell["outcomes"][r["routine_outcome"]] += 1
        cell["notes"].append(f"{r['trial']}: {'PASS' if ok else 'FAIL'} {note}")
        cell.setdefault("completion_mutations_max", 0)
        cell["completion_mutations_max"] = max(cell["completion_mutations_max"], r["completion_mutations"] or 0)
        cell.setdefault("dispatches_after_unknown", 0)
        cell["dispatches_after_unknown"] += r["e4"]["dispatches_after_unknown"]
    S["G5"] = g5
    reps = {"applied_ack_lost": 5, "delayed_after_first_unchanged_read": 5, "withheld_unresolved": 3}
    S["G5_pass"] = all(row in g5 and cls in g5[row] and g5[row][cls]["n"] == n and g5[row][cls]["pass"] == n
                       for row, n in reps.items() for cls in CLASSES)
    # timing (block 'timed') + G6
    trows = [r for r in rows["timed"] if r is not None]
    S["timing"] = timing(trows)
    S["timing_pass"] = all(S["timing"][c]["gate_ci_upper_le_2ms"] for c in CLASSES)
    crows = [r for r in rows["costs"] if r is not None]
    g6: dict[str, Any] = {}
    for cls in CLASSES:
        tr = [r for r in trows if r["cls"] == cls and r["kind"] == "train"]
        ad = [r for r in trows if r["cls"] == cls and r["kind"] == "admission"]
        wm = [r for r in trows if r["cls"] == cls and r["kind"] == "warm"]
        fb = [r for r in crows if r["cls"] == cls and r["kind"] == "n7"]
        wr = [r for r in crows if r["cls"] == cls and r["kind"] == "n8"]
        g6[cls] = {
            "training": {"n": len(tr), "T_oracle_ms": [r["T_oracle_ms"] for r in tr], "decisions": [r["provider_decisions"] for r in tr]},
            "compile_ms": [(r["training"] or {}).get("compile_ms") for r in tr],
            "admission": {"n": len(ad), "T_oracle_ms": [r["T_oracle_ms"] for r in ad]},
            "warm": {"n": len(wm), "verified": sum(1 for r in wm if r["valid"]), "median_T_oracle_ms": med([r["T_oracle_ms"] for r in wm]),
                     "mean_T_oracle_ms": mean([r["T_oracle_ms"] for r in wm])},
            "fallback_n7": {"n": len(fb), "verified": sum(1 for r in fb if r["verified"]),
                            "median_T_oracle_ms": med([r["T_oracle_ms"] for r in fb]),
                            "decisions_per_cell": mean([r["provider_decisions"] for r in fb]),
                            "g4_rules_pass": sum(1 for r in fb if g4_pass(r)[0])},
            "wrong_match_n8": {"n": len(wr), "median_t_first_obs_to_end_ms": med([r["t_to_end_ms"] for r in wr]),
                               "decisions_per_cell": mean([r["provider_decisions"] for r in wr]),
                               "dispatches": sum(r["accepted_mutations"] for r in wr),
                               "g4_rules_pass": sum(1 for r in wr if g4_pass(r)[0])},
        }
        allinv = [r["T_oracle_ms"] for r in tr + wm if r["T_oracle_ms"] is not None]
        charge = sum(x for x in g6[cls]["compile_ms"] if x) + sum(x for x in g6[cls]["admission"]["T_oracle_ms"] if x)
        if wm and tr:
            g6[cls]["amortized_mean_T_ms_train_plus_warm"] = (sum(allinv) + charge) / (len(tr) + len(wm))
            g6[cls]["ratio_of_means_amortized_over_warm"] = g6[cls]["amortized_mean_T_ms_train_plus_warm"] / mean([r["T_oracle_ms"] for r in wm])
    S["G6"] = g6
    S["G6_pass"] = all(g6[c]["training"]["n"] >= 1 and g6[c]["fallback_n7"]["n"] == 5 and g6[c]["wrong_match_n8"]["n"] == 5
                       and g6[c]["fallback_n7"]["g4_rules_pass"] == 5 and g6[c]["wrong_match_n8"]["g4_rules_pass"] == 5
                       for c in CLASSES)
    S["timing_decomposition"] = {cls: {arm: decomposition([r for r in trows if r["cls"] == cls and r["arm"] == arm
                                                           and r["kind"] in ("measured", "warm") and r["valid"]])
                                       for arm in ("COMP", "COMP_CR")} for cls in CLASSES}
    S["phase_S_pass"] = all([S["G1"][c]["pass"] for c in CLASSES] + [S["G2"][c]["pass"] for c in CLASSES]
                            + [S["G3"]["pass"], S["G4_pass"], S["G5_pass"], S["G6_pass"], S["timing_pass"],
                               S["authority_clean"]])

    # Phase L
    lrows = [r for r in rows["live"] if r is not None]
    lman = manifests(raw, "live")
    not_run = [x for m in lman for x in m.get("not_run", [])]
    L: dict[str, Any] = {"manifests": len(lman), "not_run": not_run,
                         "kind_changes": [x for m in lman for x in m.get("kind_changes", [])],
                         "provider_models": {}}
    for m in lman:
        for k, v in (m.get("provider_models") or {}).items():
            L["provider_models"][k] = L["provider_models"].get(k, 0) + v
    for cls in CLASSES:
        inv = [r for r in lrows if r["cls"] == cls and r["kind"] in ("train", "warm")]
        tr = [r for r in inv if r["kind"] == "train"]
        wm = [r for r in inv if r["kind"] == "warm"]
        ad = [r for r in lrows if r["cls"] == cls and r["kind"] == "admission"]
        nr = [x for x in not_run if f"-{cls}-" in x["trial"]]
        warm_planned = 29
        warm_valid = sum(1 for r in wm if r["valid"])
        fallbacks = sum(1 for r in wm if r["fallback"])
        n_inv = len(inv)
        t_all = [r["T_oracle_ms"] for r in inv if r["T_oracle_ms"] is not None]
        compile_ms = sum((r["training"] or {}).get("compile_ms") or 0 for r in tr)
        adm_T = sum(r["T_oracle_ms"] or 0 for r in ad)
        mean_all = (sum(t_all) + compile_ms + adm_T) / n_inv if n_inv else None
        mean_warm = mean([r["T_oracle_ms"] for r in wm])
        L[cls] = {
            "invocations_run": n_inv, "planned": 30, "not_run": nr,
            "training": [{"trial": r["trial"], "verified": r["verified"], "T_oracle_ms": r["T_oracle_ms"],
                          "decisions": r["provider_decisions"], "requests": r["provider_requests"],
                          "admitted": (r["training"] or {}).get("admitted"),
                          "compile_ms": (r["training"] or {}).get("compile_ms")} for r in tr],
            "admission": [{"trial": r["trial"], "verified": r["verified"], "valid": r["valid"], "T_oracle_ms": r["T_oracle_ms"]} for r in ad],
            "warm": {"n_run": len(wm), "planned": warm_planned, "valid": warm_valid,
                     "validity": warm_valid / warm_planned, "fallbacks": fallbacks,
                     "provider_requests": sum((r["provider_requests"] or {}).get("attempts", 0) for r in wm),
                     "decisions": sum(r["provider_decisions"] for r in wm),
                     "median_T_oracle_ms": med([r["T_oracle_ms"] for r in wm]), "mean_T_oracle_ms": mean_warm,
                     "T_oracle_ms_all": [r["T_oracle_ms"] for r in wm],
                     "invalid": [{"trial": r["trial"], "reasons": r["reasons"]} for r in wm if not r["valid"]]},
            "amortized_mean_T_ms": mean_all,
            "ratio_of_means_amortized_over_warm": (mean_all / mean_warm) if (mean_all and mean_warm) else None,
            "decisions_per_invocation": (sum(r["provider_decisions"] for r in inv) / 30),
            "decisions_total": sum(r["provider_decisions"] for r in inv),
            "requests_total_incl_admission": sum((r["provider_requests"] or {}).get("attempts", 0) for r in inv + ad),
            "decomposition_warm": decomposition([r for r in wm if r["valid"]]),
            "decomposition_all_invocations": decomposition([r for r in inv if r["verified"]]),
            "decomposition_training": decomposition([r for r in tr if r["verified"]]),
            "loadavg_1m": {"min": min((r["loadavg_1m"] for r in inv), default=None), "median": med([r["loadavg_1m"] for r in inv]),
                           "max": max((r["loadavg_1m"] for r in inv), default=None)},
        }
    S["phase_L"] = L
    # provider ledger
    led = []
    p = raw / "provider-ledger.jsonl"
    if p.exists():
        led = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    att = [x for x in led if x.get("kind") == "attempt"]
    S["provider"] = {"attempts": len(att), "reached": sum(1 for x in att if x.get("reached")),
                     "blocked_by_cap": sum(1 for x in led if x.get("kind") == "blocked_by_cap"),
                     "by_layer": dict(Counter(x.get("layer") for x in att)),
                     "status": dict(Counter(str(x.get("status")) for x in att)),
                     "request_id_present": sum(1 for x in att if x.get("request_id_present")),
                     "hosts": sorted({str(x.get("host")) for x in att})}
    # E4 over every COMP_CR cell (+ COMP timing cells)
    S["E4_COMP_CR"] = e4_total(cr_rows)
    S["E4_COMP"] = e4_total([r for r in trows if r["arm"] == "COMP"])
    S["E4_clean"] = all(v == 0 for v in S["E4_COMP_CR"].values()) and all(v == 0 for v in S["E4_COMP"].values())
    # disposition
    lw_ok = all(S["phase_L"][c]["warm"]["valid"] == 29 for c in CLASSES)
    fb_rate = max(S["phase_L"][c]["warm"]["fallbacks"] / 29 for c in CLASSES)
    truncated = bool(not_run)
    kill = (S["E4_COMP_CR"]["caller_stale_dispatch"] or S["E4_COMP_CR"]["ambiguous_dispatch"]
            or S["E4_COMP_CR"]["duplicate_mutation"] or S["E4_COMP_CR"]["unverified_success"])
    phase_l_run = bool(lrows)
    failed_gates = [name for name, ok in (
        ("G1", all(S["G1"][c]["pass"] for c in CLASSES)), ("G2", all(S["G2"][c]["pass"] for c in CLASSES)),
        ("G3", S["G3"]["pass"]), ("G4", S["G4_pass"]), ("G5", S["G5_pass"]), ("G6", S["G6_pass"]),
        ("timing_non_regression", S["timing_pass"]), ("authority", S["authority_clean"])) if not ok]
    if kill:
        disp = "KILL"
    elif S["phase_S_pass"] and phase_l_run and lw_ok and S["E4_clean"] and S["authority_clean"]:
        disp = "KEEP"
    elif S["phase_S_pass"] and phase_l_run and (fb_rate > 0.10 or truncated):
        disp = "REVISE"
    elif not S["phase_S_pass"]:
        disp = "NO_PREREGISTERED_RULE_FIRED: Phase S gate failure -> Phase L not run (pre-registered precondition)"
    else:
        disp = "NO_PREREGISTERED_RULE_FIRED"
    S["disposition_by_rule"] = {"disposition": disp, "phase_S_pass": S["phase_S_pass"], "failed_gates": failed_gates,
                                "phase_L_run": phase_l_run, "phase_L_warm_valid_100": lw_ok if phase_l_run else None,
                                "phase_L_fallback_rate_max": fb_rate if phase_l_run else None,
                                "phase_L_truncated": truncated}
    return S


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--out", default=str(HERE / "r2-07c-summary.json"))
    a = p.parse_args()
    S = analyze(Path(a.raw))
    Path(a.out).write_text(json.dumps(S, indent=1, sort_keys=True, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)) + "\n")
    print(json.dumps({"disposition": S["disposition_by_rule"], "G3": S["G3"], "G4_pass": S["G4_pass"], "G5_pass": S["G5_pass"],
                      "G6_pass": S["G6_pass"], "timing_pass": S["timing_pass"], "provider": S["provider"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
