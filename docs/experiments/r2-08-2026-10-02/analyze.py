"""R2-08 analysis: recompute every pre-registered number from raw/ trial files.

usage:
  python3 analyze.py [--raw raw] [--write r2-08-summary.json]

Definitions follow PREREG.json. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SEED = 20261002
RESAMPLES = 10000
BASE_CONSTRAINTS = {"type": "text", "required": True, "pattern": None, "maxlength": None, "minlength": None}
MEASURED_DIRS = ("base", "neg", "n2ctl")


def load(raw: Path, sub: str) -> list[tuple[list[dict[str, Any]], dict[str, Any]]]:
    out = []
    for f in sorted((raw / sub).glob("*/trials/*.jsonl")):
        events = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        out.append((events, events[-1]))
    return out


def first(events: list[dict[str, Any]], name: str, **match: Any) -> dict[str, Any] | None:
    for e in events:
        if e["event"] == name and all(e.get(k) == v for k, v in match.items()):
            return e
    return None


def span(events: list[dict[str, Any]], label: str) -> float | None:
    s, r = first(events, "call_send", label=label), first(events, "call_return", label=label)
    return None if not (s and r) else (r["t_mono_ns"] - s["t_mono_ns"]) / 1e6


def ms(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    return None if not (a and b) else (b["t_mono_ns"] - a["t_mono_ns"]) / 1e6


def derive(events: list[dict[str, Any]], s: dict[str, Any]) -> dict[str, Any]:
    arm = s["arm"]
    vs = s.get("value_sha16")
    j = s.get("journal") or []
    start = first(events, "task_start")
    polls = first(events, "oracle_polls") or {}
    confirmed = polls.get("confirmed_ns")
    T = None if not (start and confirmed) else (confirmed - start["t_mono_ns"]) / 1e6
    submits = [e for e in j if e["kind"] == "submit"]
    mutations = [e for e in j if e["kind"] == "mutation" and e["event"] != "reset"]
    validates = [e for e in j if e["kind"] == "validate"]
    first_submit_t = min((e["t_mono_ns"] for e in submits), default=None)
    norm_submits = [{"method": e["method"], "path": e["path"], "content_type": e["content_type"],
                     "fields": e["fields"], "value": "<value>" if e["value_sha16"] == vs else e["value_sha16"],
                     "status": e["status"], "effect": e["effect"], "reason": e.get("reason")} for e in submits]
    norm_mut = [{"event": e["event"], "value": "<value>" if e.get("value_sha16") == vs else e.get("value_sha16")}
                for e in mutations]
    side = sorted([["POST", e["path"]] for e in submits] + [["POST", "/validate"] for e in validates]
                  + [["POST", e["path"]] for e in j if e["kind"] == "post_other"])
    init = (first(events, "initial_state") or {}).get("state")
    final = (first(events, "final_state") or first(events, "final_state_after_error") or {}).get("state")
    signature = {"initial_state": init, "final_state": final, "submits": norm_submits, "mutations": norm_mut,
                 "side_effect_requests": side, "validate_events": len(validates)}
    d: dict[str, Any] = {
        "id": s["id"], "arm": arm, "variant": s["variant"], "phase": s["phase"], "round": s.get("round"),
        "value_kind": s["value_kind"], "error": s.get("error"), "outcome_error": s.get("outcome") == "harness_error",
        "confirmed": confirmed is not None, "final_tag": polls.get("final_tag"), "T_ms": T,
        "loadavg_before": s.get("loadavg_before"), "signature": signature,
        "validate_matching": sum(1 for e in validates if e["value_sha16"] == vs),
        "validate_matching_before_submit": sum(1 for e in validates if e["value_sha16"] == vs
                                               and first_submit_t is not None and e["t_mono_ns"] < first_submit_t),
        "probe_invalid": sum(1 for e in j if e["kind"] == "probe" and e.get("event") == "invalid"),
        "renders": sum(1 for e in j if e["kind"] == "render"),
        "renders_browser": sum(1 for e in j if e["kind"] == "render" and e.get("user_agent_is_browser")),
        "page_loaded": (first(events, "page_loaded") or {}).get("ok"),
        "poll_count": len(polls.get("polls") or []),
        "eligibility": s.get("eligibility"),
        "submit_headers": [{k: e[k] for k in ("has_origin", "has_referer", "has_cookie", "user_agent_is_browser")}
                           for e in submits],
    }
    after = [e for e in events if start and "t_mono_ns" in e and e["t_mono_ns"] >= start["t_mono_ns"]]
    calls = [e for e in after if e["event"] == "call_send"]
    if arm == "API":
        post_ret = first(events, "post_return")
        d["forced_path_ok"] = bool(first(events, "post_send") and post_ret and post_ret.get("status") is not None
                                   and first(events, "eligibility_return"))
        d["post_status"] = None if not post_ret else post_ret.get("status")
        comps = {"eligibility_read": ms(first(events, "eligibility_send"), first(events, "eligibility_return")),
                 "eligibility_check": ms(first(events, "eligibility_return"), first(events, "eligibility_checked")),
                 "post": ms(first(events, "post_send"), post_ret),
                 "verify": None if not (post_ret and confirmed) else (confirmed - post_ret["t_mono_ns"]) / 1e6}
        final_ret = post_ret
    else:
        dec = [e for e in events if e["event"] == "decided"]
        ret_type, ret_click = first(events, "call_return", label="type"), first(events, "call_return", label="click")
        d["forced_path_ok"] = bool(len(dec) == 2 and dec[0]["candidate"] == "type-verification-value"
                                   and dec[0]["tool"] == "browser_type" and dec[0].get("replace") is True
                                   and dec[1]["candidate"] == "submit-form" and dec[1]["tool"] == "browser_click"
                                   and dec[1].get("input_route") == "dom_event"
                                   and ret_type and ret_type.get("ok") and ret_click and ret_click.get("ok"))
        comps = {"snapshot1": span(events, "snapshot1"),
                 "decide1": ms(first(events, "decide_start", step=1), first(events, "decided", step=1)),
                 "type": span(events, "type"), "snapshot2": span(events, "snapshot2"),
                 "decide2": ms(first(events, "decide_start", step=2), first(events, "decided", step=2)),
                 "click": span(events, "click"),
                 "verify": None if not (ret_click and confirmed) else (confirmed - ret_click["t_mono_ns"]) / 1e6}
        final_ret = ret_click
    if T is not None and all(v is not None for v in comps.values()):
        comps["unattributed"] = T - sum(comps.values())
    d["components_ms"] = comps
    d["work"] = {
        "driver_calls_in_T": len(calls),
        "observations_in_T": sum(1 for e in calls if e["tool"] == "get_browser_state"),
        "actions_in_T": sum(1 for e in calls if e["tool"] in ("browser_type", "browser_click")),
        "visualized_actions_in_T": sum(1 for e in calls if e["tool"] in ("browser_type", "browser_click")) if arm == "G_on" else 0,
        "decisions_in_T": sum(1 for e in after if e["event"] == "decided"),
        "caller_http_requests_in_T": (2 if arm == "API" else 0) + len(polls.get("polls") or []),
    }
    d["action_sends"] = {"post": sum(1 for e in events if e["event"] == "post_send"),
                         "click": sum(1 for e in events if e["event"] == "call_send" and e.get("tool") == "browser_click"),
                         "type": sum(1 for e in events if e["event"] == "call_send" and e.get("tool") == "browser_type")}
    # Stale-ref audit (GUI): every action must directly follow an ok snapshot of the same tab
    # (no other Driver call in between), and no action result may report a stale ref or failure.
    if arm != "API":
        audit = {"actions": 0, "after_fresh_ok_snapshot": 0, "same_tab_as_snapshot": 0, "stale_or_error_results": 0}
        last_ret: dict[str, Any] | None = None
        snap_tab = None
        for e in after:
            action = e.get("tool") in ("browser_type", "browser_click")
            if e["event"] == "call_send" and action:
                res = (last_ret or {}).get("result") if (last_ret or {}).get("tool") == "get_browser_state" else None
                fresh = bool(last_ret and last_ret.get("ok") and isinstance(res, dict)
                             and res.get("mode") == "snapshot" and res.get("status") == "ok")
                audit["after_fresh_ok_snapshot"] += fresh
                snap_tab = res.get("tab_id") if fresh else None
            elif e["event"] == "call_return":
                if action:
                    res = e.get("result")
                    audit["actions"] += 1
                    audit["same_tab_as_snapshot"] += bool(snap_tab and snap_tab in json.dumps(res))
                    audit["stale_or_error_results"] += bool(not e.get("ok") or not isinstance(res, dict) or "error" in res
                                                            or "stale" in json.dumps(res).lower())
                last_ret = e
        d["stale_ref_audit"] = audit
    d["pos"] = s.get("pos")
    d["final_action_return_to_confirm_ms"] = None if not (final_ret and confirmed) else (confirmed - final_ret["t_mono_ns"]) / 1e6
    return d


def pct(values: list[float], q: float) -> float:
    v = sorted(values)
    k = max(0, min(len(v) - 1, int(-(-q * len(v) // 1)) - 1))
    return v[k]


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": round(statistics.median(values), 3), "p95": round(pct(values, 0.95), 3),
            "min": round(min(values), 3), "max": round(max(values), 3)}


def boot_ci(diffs: list[float]) -> list[float] | None:
    if not diffs:
        return None
    rng = random.Random(SEED)
    meds = sorted(statistics.median(rng.choices(diffs, k=len(diffs))) for _ in range(RESAMPLES))
    return [round(meds[int(0.025 * RESAMPLES)], 3), round(meds[int(0.975 * RESAMPLES) - 1], 3)]


def predicted(d: dict[str, Any]) -> bool:
    """Per-trial predicted outcome for negative variants (PREREG.negatives)."""
    sig, subs = d["signature"], d["signature"]["submits"]
    if d["error"] or not d["forced_path_ok"] or not d["page_loaded"]:
        return False
    v, arm = d["variant"], d["arm"]
    accepted_one = (len(subs) == 1 and subs[0]["effect"] == "accepted" and subs[0]["value"] == "<value>"
                    and len(sig["mutations"]) == 1)
    if v == "n1" and arm != "API":
        return d["confirmed"] and accepted_one and subs[0]["fields"] == ["nonce", "value"]
    if v == "n1":
        return (not d["confirmed"] and sig["final_state"] == {"submitted": None} and len(subs) == 1
                and subs[0]["fields"] == ["value"] and subs[0]["status"] == 403 and subs[0]["effect"] == "refused"
                and subs[0]["reason"] in ("missing_nonce", "stale_nonce") and sig["mutations"] == [])
    if v == "n2" and d["value_kind"] == "valid":
        return d["confirmed"] and accepted_one
    if v == "n2" and arm != "API":
        return (not d["confirmed"] and sig["final_state"] == {"submitted": None} and subs == []
                and sig["mutations"] == [])
    if v == "n2":
        return d["confirmed"] and accepted_one and subs[0]["fields"] == ["value"]
    if v == "n3" and arm != "API":
        return d["confirmed"] and accepted_one and d["validate_matching_before_submit"] >= 1
    if v == "n3":
        return d["confirmed"] and accepted_one and sig["validate_events"] == 0
    return False


def compute(raw: Path) -> dict[str, Any]:
    trials = {sub: [derive(ev, s) for ev, s in load(raw, sub)] for sub in MEASURED_DIRS}
    base = trials["base"]
    by_round: dict[int, dict[str, dict[str, Any]]] = {}
    for d in base:
        by_round.setdefault(d["round"], {})[d["arm"]] = d
    rounds = []
    for r in sorted(by_round):
        arms = by_round[r]
        api, gon, goff = arms.get("API"), arms.get("G_on"), arms.get("G_off")
        gui_ok = all(g and g["confirmed"] and g["forced_path_ok"] and not g["error"] for g in (gon, goff))
        el = (api or {}).get("eligibility") or {}
        elig_ok = bool(el.get("eligible_by_contract") and el.get("field_constraints") == BASE_CONSTRAINTS
                       and el.get("token_satisfies_constraints") is True and el.get("extra_fields") == [])
        api_ok = bool(api and api["confirmed"] and api["forced_path_ok"] and not api["error"])
        if not gui_ok:
            status = "not_established"
        elif api_ok and elig_ok and api["signature"] == goff["signature"] == gon["signature"]:
            status = "equivalent"
        else:
            status = "differs"
        diff_keys = [] if not (api and goff) else sorted(
            k for k in api["signature"] if api["signature"][k] != goff["signature"].get(k))
        rounds.append({"round": r, "status": status, "api_confirmed": api_ok, "eligibility_ok": elig_ok,
                       "gui_ok": gui_ok, "api_vs_goff_signature_diff_keys": diff_keys,
                       "T_ms": {a: (arms.get(a) or {}).get("T_ms") for a in ("G_on", "G_off", "API")}})
    n_equiv = sum(1 for r in rounds if r["status"] == "equivalent")
    d_off = [r["T_ms"]["API"] - r["T_ms"]["G_off"] for r in rounds if r["T_ms"]["API"] is not None and r["T_ms"]["G_off"] is not None]
    d_on = [r["T_ms"]["API"] - r["T_ms"]["G_on"] for r in rounds if r["T_ms"]["API"] is not None and r["T_ms"]["G_on"] is not None]
    ci_off = boot_ci(d_off)
    timing = {
        "per_arm_T_ms": {a: stats([d["T_ms"] for d in base if d["arm"] == a and d["T_ms"] is not None]) for a in ("G_on", "G_off", "API")},
        "paired_API_minus_G_off": {**stats(d_off), "ci95": ci_off,
                                   "pairs_api_faster": sum(1 for x in d_off if x < 0)},
        "paired_API_minus_G_on": {**stats(d_on), "ci95": boot_ci(d_on), "pairs_api_faster": sum(1 for x in d_on if x < 0)},
        "speedup_median_G_off_over_API": None,
        "components_ms": {a: {k: stats([d["components_ms"][k] for d in base if d["arm"] == a and d["components_ms"].get(k) is not None])
                              for k in (["eligibility_read", "eligibility_check", "post", "verify", "unattributed"] if a == "API" else
                                        ["snapshot1", "decide1", "type", "snapshot2", "decide2", "click", "verify", "unattributed"])}
                          for a in ("G_on", "G_off", "API")},
        "order_API_vs_G_off": {"G_off_first": sum(1 for r in sorted(by_round) if "API" in by_round[r] and "G_off" in by_round[r]
                                                  and int(by_round[r]["G_off"]["pos"]) < int(by_round[r]["API"]["pos"])),
                               "API_first": sum(1 for r in sorted(by_round) if "API" in by_round[r] and "G_off" in by_round[r]
                                                and int(by_round[r]["API"]["pos"]) < int(by_round[r]["G_off"]["pos"]))},
        "loadavg_1m_range": [min(float(d["loadavg_before"].split()[0]) for d in base), max(float(d["loadavg_before"].split()[0]) for d in base)] if base else None,
    }
    pa, po = timing["per_arm_T_ms"]["API"], timing["per_arm_T_ms"]["G_off"]
    if pa.get("n") and po.get("n"):
        timing["speedup_median_G_off_over_API"] = round(po["median"] / pa["median"], 2)
    work = {a: {k: stats([d["work"][k] for d in base if d["arm"] == a]) for k in base[0]["work"]} for a in ("G_on", "G_off", "API")} if base else {}
    negatives = {}
    neg = trials["neg"]
    for v in ("n1", "n2", "n3"):
        rows = {}
        for route, arms in (("GUI", ("G_off",)), ("API", ("API",))):
            sel = [d for d in neg if d["variant"] == v and d["arm"] in arms]
            rows[route] = {"n": len(sel), "predicted": sum(1 for d in sel if predicted(d)),
                           "confirmed": sum(1 for d in sel if d["confirmed"]),
                           "failures": [d["id"] for d in sel if not predicted(d)],
                           "eligible_by_contract": sum(1 for d in sel if (d["eligibility"] or {}).get("eligible_by_contract")) if route == "API" else None}
        extra = {}
        sel_gui = [d for d in neg if d["variant"] == v and d["arm"] != "API"]
        sel_api = [d for d in neg if d["variant"] == v and d["arm"] == "API"]
        if v == "n1":
            extra = {"gui_submit_fields": sorted({",".join(s["fields"]) for d in sel_gui for s in d["signature"]["submits"]}),
                     "api_refusal_reasons": sorted({s["reason"] for d in sel_api for s in d["signature"]["submits"] if s["reason"]}),
                     "api_status": sorted({s["status"] for d in sel_api for s in d["signature"]["submits"]}),
                     "api_extra_fields_seen_by_check": sorted({",".join((d["eligibility"] or {}).get("extra_fields") or []) for d in sel_api})}
        if v == "n2":
            extra = {"gui_probe_invalid_trials": sum(1 for d in sel_gui if d["probe_invalid"] >= 1),
                     "gui_submits_total": sum(len(d["signature"]["submits"]) for d in sel_gui),
                     "api_check_token_satisfies_constraints_false": sum(1 for d in sel_api if (d["eligibility"] or {}).get("token_satisfies_constraints") is False)}
        if v == "n3":
            extra = {"gui_validate_matching_before_submit_trials": sum(1 for d in sel_gui if d["validate_matching_before_submit"] >= 1),
                     "api_validate_events_total": sum(d["signature"]["validate_events"] for d in sel_api),
                     "final_state_equal_shape": sorted({json.dumps(d["signature"]["final_state"]) for d in sel_gui + sel_api}),
                     "api_scripts_seen_by_check": sorted({(d["eligibility"] or {}).get("scripts") for d in sel_api})}
        disc = n_equiv == len(rounds) == 20 and all(rows[k]["n"] == 10 and rows[k]["predicted"] == 10 for k in rows)
        negatives[v] = {**rows, "discriminating": disc, "evidence": extra}
    ctl = trials["n2ctl"]
    n2ctl = {"n": len(ctl), "predicted": sum(1 for d in ctl if predicted(d)), "failures": [d["id"] for d in ctl if not predicted(d)]}
    every = base + neg + ctl
    invariants = {
        "trials_total": len(every),
        "duplicate_mutations": sum(1 for d in every if len(d["signature"]["mutations"]) > 1),
        "duplicate_submit_requests": sum(1 for d in every if len(d["signature"]["submits"]) > 1),
        "errors": [d["id"] for d in every if d["error"] or d["outcome_error"]],
        "unverified_successes_by_construction": 0,
        "success_oracle": "fixture GET /state only (target-owned); Driver results are never the success signal",
        "refusals_effect_refused": sum(1 for d in neg if d["variant"] == "n1" and d["arm"] == "API"
                                       and d["signature"]["submits"] and d["signature"]["submits"][0]["effect"] == "refused"),
        "page_loaded_before_T": sum(1 for d in every if d["page_loaded"]),
        "initial_state_none": sum(1 for d in every if d["signature"]["initial_state"] == {"submitted": None}),
        "api_requests_built_from_contract_only": "SOURCE: run_cross_surface.api_task builds the body from DOCUMENTED_CONTRACT only",
        "api_post_retries": sum(max(0, d["action_sends"]["post"] - 1) for d in every if d["arm"] == "API"),
        "gui_action_retries": sum(max(0, d["action_sends"]["click"] - 1) + max(0, d["action_sends"]["type"] - 1)
                                  for d in every if d["arm"] != "API"),
        "api_trials_with_exactly_one_post": sum(1 for d in every if d["arm"] == "API" and d["action_sends"]["post"] == 1),
        "api_trials": sum(1 for d in every if d["arm"] == "API"),
        "gui_trials": sum(1 for d in every if d["arm"] != "API"),
        "gui_actions": sum(d["stale_ref_audit"]["actions"] for d in every if d["arm"] != "API"),
        "gui_actions_after_fresh_ok_snapshot": sum(d["stale_ref_audit"]["after_fresh_ok_snapshot"] for d in every if d["arm"] != "API"),
        "gui_actions_same_tab_as_snapshot": sum(d["stale_ref_audit"]["same_tab_as_snapshot"] for d in every if d["arm"] != "API"),
        "gui_stale_ref_dispatches": sum(d["stale_ref_audit"]["stale_or_error_results"] for d in every if d["arm"] != "API"),
    }
    g1 = n_equiv == 20 and len(rounds) == 20
    g2 = all(negatives[v]["discriminating"] for v in negatives)
    g3 = bool(ci_off and (ci_off[1] < 0 or ci_off[0] > 0))
    if any(r["status"] == "differs" for r in rounds) or not g2:
        disposition = "KILL"
    elif g1 and g3:
        disposition = "KEEP"
    else:
        disposition = "REVISE"
    return {
        "schema": "cua.r2-08.summary.v1",
        "counts": {k: len(v) for k, v in trials.items()},
        "base_equivalence": {"rounds": len(rounds), "equivalent": n_equiv,
                             "status_counts": {s: sum(1 for r in rounds if r["status"] == s) for s in ("equivalent", "differs", "not_established")},
                             "gui_confirmed": {a: sum(1 for d in base if d["arm"] == a and d["confirmed"]) for a in ("G_on", "G_off")},
                             "api_confirmed": sum(1 for d in base if d["arm"] == "API" and d["confirmed"]),
                             "forced_path_ok": {a: sum(1 for d in base if d["arm"] == a and d["forced_path_ok"]) for a in ("G_on", "G_off", "API")},
                             "reference_signature": base[0]["signature"] if base else None,
                             "api_extra_get_reads": sorted({d["renders"] - d["renders_browser"] for d in base if d["arm"] == "API"}),
                             "gui_extra_get_reads": sorted({d["renders"] - d["renders_browser"] for d in base if d["arm"] != "API"}),
                             "submit_headers_gui": sorted({json.dumps(h, sort_keys=True) for d in base if d["arm"] != "API" for h in d["submit_headers"]}),
                             "submit_headers_api": sorted({json.dumps(h, sort_keys=True) for d in base if d["arm"] == "API" for h in d["submit_headers"]}),
                             "rounds_detail": rounds},
        "timing": timing,
        "work_in_T": work,
        "negatives": negatives,
        "n2_valid_value_gui_control": n2ctl,
        "invariants": invariants,
        "gates": {"G1_base_equivalence_20_of_20": g1, "G2_negatives_discriminate_10_of_10": g2,
                  "G3_paired_CI_excludes_0": g3},
        "disposition": disposition,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default=str(HERE / "raw"))
    p.add_argument("--write")
    a = p.parse_args()
    summary = compute(Path(a.raw))
    text = json.dumps(summary, indent=1, sort_keys=True) + "\n"
    if a.write:
        Path(a.write).write_text(text)
    print(json.dumps({"disposition": summary["disposition"], "gates": summary["gates"], "counts": summary["counts"]}, indent=1))


if __name__ == "__main__":
    main()
