#!/usr/bin/env python3
"""summarize.py <grade.json> <summary.json>: preregistered aggregates (PREREG.json metrics / gates) from grade.json."""
import json
import math
import statistics as st
import sys

g = json.load(open(sys.argv[1]))


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def arm(rounds, name):
    rs = [r for r in rounds if r["arm"] == name]
    ag = [a for r in rs for a in r["agents"]]
    k = sum(a["success"] for a in ag)
    res = [r["resources"] for r in rs]
    def m(key, f=st.mean):
        v = [x.get(key) for x in res if x.get(key) is not None]
        return round(f(v), 1) if v else None
    return {
        "rounds": len(rs), "agent_runs": len(ag), "successes": k, "success_rate": round(k / len(ag), 3) if ag else None,
        "success_wilson95": wilson(k, len(ag)),
        "makespan_s": {"median": round(st.median(r["makespan_s"] for r in rs), 1) if rs else None,
                       "min": min((r["makespan_s"] for r in rs), default=None), "max": max((r["makespan_s"] for r in rs), default=None)},
        "successes_per_min_pooled": round(60 * k / sum(r["makespan_s"] for r in rs), 3) if rs else None,
        "agent_runs_per_min_pooled": round(60 * len(ag) / sum(r["makespan_s"] for r in rs), 3) if rs else None,
        "agent_wall_s_median": round(st.median(a["agent_wall_s"] for a in ag if a["agent_wall_s"]), 1) if ag else None,
        "api_calls_per_run_median": st.median(a["api_ok"] for a in ag) if ag else None,
        "api_errors_total": sum(a["api_error"] for a in ag),
        "max_prompt_tokens": max((a["max_prompt_tokens"] or 0 for a in ag), default=None),
        "stale_ref_results_total": sum(a["stale_ref_results"] for a in ag),
        "runs_with_stale_ref": sum(a["stale_ref_results"] > 0 for a in ag),
        "element_index_refusals_total": sum(a["element_index_refusals"] for a in ag),
        "runs_with_element_index_refusal": sum(a["element_index_refusals"] > 0 for a in ag),
        "approval_blocks_total": sum(a["approval_blocks"] for a in ag),
        "duplicate_effect_runs": sum(a["duplicate_effect"] for a in ag),
        "save_presses_total": sum(a["save_presses"] for a in ag),
        "foreign_view_runs": sum(bool(a["foreign_views_after"]) for a in ag),
        "focus_not_on_own_fixture_after": sum(not a["focused_after_is_fixture"] for a in ag),
        "unpaired_focus_out_total": sum(a["unpaired_focus_out"] for a in ag),
        "hermes_nonzero_exit": sum((a["hermes_exit"] or 0) != 0 for a in ag),
        "agent_timeouts_rc124": sum(a["agent_rc"] == 124 for a in ag),
        "transcripts_missing": sum(a["transcript_missing"] for a in ag),
        "own_model_call_overlap_s_median": round(st.median(r["own_model_call_overlap_s"] for r in rs), 1) if rs else None,
        "model_requests_foreign_total": sum(r["model_requests_foreign"] or 0 for r in rs),
        "rounds_with_foreign_requests": sum((r["model_requests_foreign"] or 0) > 0 for r in rs),
        "resources": {
            "round_tree_cpu_pct_mean": m("round_tree_cpu_pct_mean"), "round_tree_rss_mib_peak_max": m("round_tree_rss_mib_peak", max),
            "per_session_rss_mib_peak_max": max((max(x["per_session_rss_mib_peak"] or [0]) for x in res if x.get("per_session_rss_mib_peak")), default=None),
            "ollama_cpu_pct_mean": m("ollama_cpu_pct_mean"), "ollama_rss_mib_peak_max": m("ollama_rss_mib_peak", max),
            "gpu_mem_used_mib_peak_max": m("gpu_mem_used_mib_peak", max), "gpu_mem_used_mib_mean": m("gpu_mem_used_mib_mean"),
            "gpu_util_pct_mean": m("gpu_util_pct_mean"), "loadavg1_max": m("loadavg_max1", max),
        },
    }


main = g["main_rounds"]
pairs = {}
for r in main:
    pairs.setdefault(r["round"].split("-")[0], {})[r["arm"]] = r
sp = []
for p, d in sorted(pairs.items()):
    if "seq" in d and "conc" in d:
        sp.append({"pair": p, "seq_s": d["seq"]["makespan_s"], "conc_s": d["conc"]["makespan_s"],
                   "speedup": round(d["seq"]["makespan_s"] / d["conc"]["makespan_s"], 3),
                   "foreign_requests": [d["seq"]["model_requests_foreign"], d["conc"]["model_requests_foreign"]],
                   "successes": [d["seq"]["successes"], d["conc"]["successes"]]})
clean = [x for x in sp if all((f or 0) == 0 for f in x["foreign_requests"])]
look = g["lookalike_rounds"]
look_ag = [a for r in look for a in r["agents"]]
cl = g["cross_landings_main"] + g["cross_landings_lookalike"]
summary = {
    "schema": "cua.stack.multiseat.summary.v1",
    "topology": "N=4 separate headless sway 1.12 sessions (one per agent), shared local model server",
    "arms": {"SEQ": arm(main, "seq"), "CONC": arm(main, "conc")},
    "throughput_pairs": sp,
    "speedup": {"n_pairs": len(sp), "pairs_conc_faster": sum(x["speedup"] > 1 for x in sp),
                "median": round(st.median(x["speedup"] for x in sp), 3) if sp else None,
                "min": min((x["speedup"] for x in sp), default=None), "max": max((x["speedup"] for x in sp), default=None),
                "clean_pairs_no_foreign_requests": len(clean),
                "clean_median": round(st.median(x["speedup"] for x in clean), 3) if clean else None},
    "lookalike": {"rounds": len(look), "agent_runs": len(look_ag), "successes": sum(a["success"] for a in look_ag),
                  "foreign_view_runs": sum(bool(a["foreign_views_after"]) for a in look_ag),
                  "focus_not_on_own_fixture_after": sum(not a["focused_after_is_fixture"] for a in look_ag),
                  "same_pid_and_window_handles": sorted({(a["fixture_pid"]) for a in look_ag})},
    "interference": {"agent_runs_checked": sum(len(r["agents"]) for r in main + look), "journals_checked": sum(len(r["agents"]) for r in main + look),
                     "cross_session_landings": len(cl), "landings": cl,
                     "foreign_view_runs": sum(bool(a["foreign_views_after"]) for r in main + look for a in r["agents"]),
                     "focus_not_on_own_fixture_after": sum(not a["focused_after_is_fixture"] for r in main + look for a in r["agents"])},
    "crosswire": g["crosswire"]["summary"],
    "seat_lookalike": {"reps": len(g["seat_lookalike"]), "pass": sum(r.get("pass", False) for r in g["seat_lookalike"]),
                       "cross_seat_landings": sum(r.get("cross_seat_landings", 0) for r in g["seat_lookalike"])},
    "seat_driver": {"reps": len(g["seat_driver"]),
                    "per_agent_seat_binding_observed": sum(r.get("per_agent_seat_binding", False) for r in g["seat_driver"]),
                    "seats_used": [r.get("seats_used_by_two_driver_agents") for r in g["seat_driver"]]},
}
json.dump(summary, open(sys.argv[2], "w"), indent=1)
print(json.dumps({k: summary[k] for k in ("speedup", "interference")}, indent=1)[:2000])
