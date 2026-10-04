"""B-02 analysis: recompute every number in b02-summary.json from raw/ (standard library only).

    python analyze_b02.py [--raw raw] [--out b02-summary.json]

Blocks: vmicro (admission A/B, BENCHMARK), nv (invalid-call envelopes, REAL), step0 and
step0-dbg1 (browser launch refusals under hostless v1, REAL), unit logs (UNIT), lock receipts;
fix round (hostless v2, PREREG-AMENDMENT-1): step0-r2 (STEP 0 browser probes, REAL), measured
(3 classes x K5/K5E/K5V/K5EV x 20 rounds, BENCHMARK), controls (REAL), smoke (REAL), shakedowns
(excluded). The rules are the ones in PREREG.json and PREREG-AMENDMENT-1.json. Statistics reuse
B-01's seeded bootstrap.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import tarfile
from pathlib import Path
from typing import Any

import b01_analysis as B  # copied verbatim from B-01 (seed 20261002, 10000 resamples)
import analyze_browser as AB  # browser blocks (fix round)
import step0_analysis as S0

HERE = Path(__file__).resolve().parent

# B-01 composed means (ms, T_runner) used ONLY for the labelled projection; B-01 is pending.
B01_COMPOSED_MEAN_T = {"fill": 84.9, "toggle": 53.1, "modal": 54.5}
B01_TOOLS_CALLS_IN_T = 4  # snapshot1, action1, snapshot2, action2 (B-01 forced path)
B01_UNTESTED_SHARE = {"fill": 0.512, "toggle": 0.702, "modal": 0.693}
ADM_SUBSPANS = [
    ("mcp.line_read", "mcp.parsed", "parse"),
    ("mcp.parsed", "mcp.session_validated", "session_validate"),
    ("mcp.session_validated", "mcp.tools_list_built", "proxy_tools_list_build"),
    ("mcp.tools_list_built", "mcp.admission_validated", "proxy_validate_and_drop"),
    ("mcp.admission_validated", "mcp.admitted", "proxy_other"),
    ("mcp.admitted", "mcp.identity_applied", "identity"),
    ("mcp.identity_applied", "mcp.session_begun", "begin_tool_call"),
    ("mcp.session_begun", "mcp.timer_started", "observation_timer"),
    ("mcp.timer_started", "mcp.inner_classified", "inner_classify"),
    ("mcp.inner_classified", "mcp.inner_tools_list_built", "inner_tools_list_build"),
    ("mcp.inner_tools_list_built", "mcp.inner_validated", "inner_validate_and_drop"),
    ("mcp.inner_classified", "mcp.inner_validation_skipped", "inner_skip_decision"),
    ("mcp.inner_validation_skipped", "mcp.inner_validated", "inner_skipped_tail"),
]


def _bundle_files(raw: Path, block: str) -> dict[str, str]:
    files: dict[str, str] = {}
    d = raw / block / "trials"
    if d.is_dir():
        for p in sorted(d.glob("*.jsonl")):
            files[p.name] = p.read_text()
    tgz = raw / f"{block}-trials.tar.gz"
    if tgz.exists():
        with tarfile.open(tgz, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.endswith(".jsonl"):
                    files[Path(m.name).name] = tar.extractfile(m).read().decode()
    return files


def tool_call_windows(trace: list[dict[str, Any]]) -> list[list[tuple[str, int]]]:
    """Mark sequences mcp.line_read .. mcp.inner_validated of admitted tools/call requests."""
    out, cur = [], None
    for m in trace:
        p, t = m["phase"], m["t_mono_ns"]
        if p == "mcp.line_read":
            cur = [(p, t)]
            continue
        if cur is None:
            continue
        cur.append((p, t))
        if p == "mcp.inner_validated":
            if any(x[0] == "mcp.admission_validated" for x in cur):
                out.append(cur)
            cur = None
    return out


def window_stats(win: list[tuple[str, int]]) -> dict[str, Any]:
    span = (win[-1][1] - win[0][1]) / 1e6
    marks = dict((p, t) for p, t in win)
    sub = {}
    for a, b, label in ADM_SUBSPANS:
        if a in marks and b in marks and marks[b] >= marks[a]:
            sub[label] = (marks[b] - marks[a]) / 1e6
    return {"span_ms": span, "sub": sub, "skipped": "mcp.inner_validation_skipped" in marks,
            "inner_built": "mcp.inner_tools_list_built" in marks}


def analyze_vmicro(raw: Path) -> dict[str, Any]:
    files = _bundle_files(raw, "vmicro")
    trials = []
    for name, text in files.items():
        if name.endswith(".driver-trace.jsonl"):
            continue
        summary = json.loads(text.splitlines()[-1])
        trace_text = files.get(Path(summary["driver_trace"]).name, "")
        trace = [json.loads(line) for line in trace_text.splitlines() if line.strip()]
        wins = [window_stats(w) for w in tool_call_windows(trace)]
        calls = summary["calls"]
        legacy, modern = wins[:25], wins[25:50]
        arm = summary["arm"]
        bad = []
        if len(calls) != 50 or not all(c["ok"] for c in calls):
            bad.append("call_failed")
        if len(wins) != 50:
            bad.append(f"windows={len(wins)}")
        if arm == "K5V" and not all(w["skipped"] and not w["inner_built"] for w in wins):
            bad.append("forced_path_V")
        if arm == "K5" and not all(w["inner_built"] and not w["skipped"] for w in wins):
            bad.append("forced_path_default")
        rtt = [(c["recv_ns"] - c["send_ns"]) / 1e6 for c in calls]
        trials.append({
            "trial": summary["trial"], "arm": arm, "round": summary["round"], "valid": not bad, "invalid": bad,
            "loadavg_before": summary["loadavg_before"], "loadavg_after": summary.get("loadavg_after"),
            "legacy_span_median": B.median([w["span_ms"] for w in legacy]),
            "modern_span_median": B.median([w["span_ms"] for w in modern]),
            "legacy_rtt_median": B.median(rtt[:25]), "modern_rtt_median": B.median(rtt[25:50]),
            "legacy_sub_median": {k: B.median([w["sub"][k] for w in legacy if k in w["sub"]])
                                  for k in sorted({k for w in legacy for k in w["sub"]})},
            "skips": sum(w["skipped"] for w in wins), "inner_builds": sum(w["inner_built"] for w in wins),
        })
    trials.sort(key=lambda t: t["trial"])
    by = {(t["round"], t["arm"]): t for t in trials}
    rounds = sorted({t["round"] for t in trials})
    out: dict[str, Any] = {"trials": len(trials), "valid": sum(t["valid"] for t in trials),
                           "invalid": [t["trial"] for t in trials if not t["valid"]]}
    for arm in ("K5", "K5V"):
        ts = [t for t in trials if t["arm"] == arm]
        out[arm] = {
            "n": len(ts),
            "legacy_span_median_of_trials": B.median([t["legacy_span_median"] for t in ts]),
            "modern_span_median_of_trials": B.median([t["modern_span_median"] for t in ts]),
            "legacy_rtt_median_of_trials": B.median([t["legacy_rtt_median"] for t in ts]),
            "modern_rtt_median_of_trials": B.median([t["modern_rtt_median"] for t in ts]),
            "legacy_sub_median_of_trials": {k: B.median([t["legacy_sub_median"][k] for t in ts
                                                         if k in t["legacy_sub_median"]])
                                            for k in sorted({k for t in ts for k in t["legacy_sub_median"]})},
            "skips_total": sum(t["skips"] for t in ts), "inner_builds_total": sum(t["inner_builds"] for t in ts),
            "loadavg_1m_range": [min(float(t["loadavg_before"].split()[0]) for t in ts),
                                 max(float(t["loadavg_before"].split()[0]) for t in ts)],
        }
    pairs = [(by[(r, "K5")], by[(r, "K5V")]) for r in rounds if (r, "K5") in by and (r, "K5V") in by
             and by[(r, "K5")]["valid"] and by[(r, "K5V")]["valid"]]
    for metric in ("legacy_span_median", "modern_span_median", "legacy_rtt_median", "modern_rtt_median"):
        out[f"paired_saving_{metric}"] = B.paired_diff([a[metric] for a, _ in pairs], [b[metric] for _, b in pairs])
    k5 = out["K5"]["legacy_span_median_of_trials"]
    sav = out["paired_saving_legacy_span_median"]
    out["gate_V_call"] = {
        "k5_per_call_admission_ms": k5,
        "saving_median_ms": sav["median"], "saving_ci95": sav["ci95"],
        "saving_fraction_of_k5": None if not k5 else sav["median"] / k5,
        "ci_excludes_0": bool(sav["ci95"] and sav["ci95"][0] > 0),
        "pass": bool(sav["ci95"] and sav["ci95"][0] > 0 and k5 and sav["median"] >= 0.5 * k5
                     and out["valid"] == out["trials"]),
    }
    out["per_trial"] = trials
    return out


def analyze_nv(raw: Path) -> dict[str, Any]:
    files = _bundle_files(raw, "nv")
    recs = [json.loads(t.splitlines()[-1]) for n, t in sorted(files.items()) if n.endswith("-nv.jsonl")]
    keys = sorted({k for r in recs for k in r["replies"]})
    per_case = {}
    for k in keys:
        vals = {r["replies"].get(k) for r in recs}
        by_arm = {arm: {r["replies"].get(k) for r in recs if r["arm"] == arm} for arm in ("K5", "K5V")}
        reply = next(iter(vals)) or ""
        m = re.search(r'"code":(-?\d+)', reply) if '"error"' in reply[:40] else None
        rc = re.search(r'"code":"([a-z_]+)"', reply)
        per_case[k] = {"distinct_replies": len(vals), "k5_distinct": len(by_arm["K5"]),
                       "k5v_distinct": len(by_arm["K5V"]),
                       "jsonrpc_error_code": int(m.group(1)) if m else None,
                       "tool_refusal_code": rc.group(1) if rc else None}
    return {"trials": len(recs), "by_arm": {a: sum(r["arm"] == a for r in recs) for a in ("K5", "K5V")},
            "cases": per_case, "pass": bool(recs) and all(v["distinct_replies"] == 1 for v in per_case.values())}


def analyze_step0(raw: Path) -> dict[str, Any]:
    out = {}
    for block in ("step0", "step0-dbg1"):
        man = raw / block / "run-manifest-step0.json"
        if not man.exists():
            continue
        m = json.loads(man.read_text())
        errs = [t.get("error") for t in m["trials"]]
        flat = [e if isinstance(e, str) else " | ".join(e) for e in errs]
        files = _bundle_files(raw, block)
        prepare_refused = 0
        for name, text in files.items():
            if name.endswith(".driver-trace.jsonl") and "second-driver" not in name:
                rows = [json.loads(line) for line in text.splitlines() if line.strip()]
                exits = [r for r in rows if r["phase"] == "dispatch.exit"
                         and (r.get("detail") or {}).get("tool") == "browser_prepare"]
                later = [r for r in rows if r["phase"] == "dispatch.enter"
                         and (r.get("detail") or {}).get("tool") not in ("set_agent_cursor_enabled", "browser_prepare")]
                if exits and not later:
                    prepare_refused += 1
        out[block] = {"trials": len(errs), "ok": sum(1 for t in m["trials"] if t.get("ok")),
                      "route_unavailable_in_error": sum("browser_route_unavailable" in e or
                                                        "root-owned" in e for e in flat),
                      "traces_ending_at_browser_prepare": prepare_refused,
                      "display": m.get("display")}
    return out


def analyze_unit(raw: Path) -> dict[str, Any]:
    out = {}
    for p in sorted((raw / "unit").glob("unit-run-1-*.log")):
        text = p.read_text()
        results = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored", text)
        main = max(results, key=lambda r: int(r[1])) if results else None
        b02 = re.findall(r"test (\S*(?:b02|exp_b02|exp_bound)\S*) \.\.\. (\w+)", text)
        out[p.stem.removeprefix("unit-run-1-")] = {
            "status": main[0] if main else None, "passed": int(main[1]) if main else None,
            "failed": int(main[2]) if main else None, "ignored": int(main[3]) if main else None,
            "b02_tests": sorted(set(b02))}
    return out


def projection(vm: dict[str, Any]) -> dict[str, Any]:
    per_call = vm["gate_V_call"]["saving_median_ms"] or 0.0
    out = {}
    for cls, t in B01_COMPOSED_MEAN_T.items():
        saved = per_call * B01_TOOLS_CALLS_IN_T
        out[cls] = {"label": "PROJECTION (not measured on a browser task; B-01 numbers pending)",
                    "per_task_saving_ms": saved, "share_of_b01_composed_mean_T": saved / t,
                    "b01_untested_share": B01_UNTESTED_SHARE[cls],
                    "untested_share_if_projection_held": max(0.0, B01_UNTESTED_SHARE[cls] - saved / t)}
    return out


VERDICT_TEXT = {
    "visualization": "B-01 verdict OWNER_DECISION (feedback off in every arm; the residual is overlay/platform-gate bookkeeping)",
    "settles": "B-01 K5 setting (focus settle 0 on fill; B-01 H_T OWNER_DECISION)",
    "decision": "mock chooser (live decision measured in R2-10)",
    "resolution": "IRREDUCIBLE (ref resolution before dispatch)",
    "input_prep": "IRREDUCIBLE (trusted-input focus/selection proof)",
    "dispatch": "IRREDUCIBLE (the effectful CDP call)",
    "dispatch_post": "IRREDUCIBLE",
    "driver_post_dispatch": "IRREDUCIBLE (JSON-RPC result handling)",
    "transport": "IRREDUCIBLE (stdio JSON-RPC)",
    "client_validation": "B-01 K5 setting (caller-compiled validators; B-01 H_C)",
    "runner_overhead": "IRREDUCIBLE (caller glue)",
    "verification_reads": "IRREDUCIBLE (independent oracle read; events are never the oracle)",
    "sleeps_polls": "B-01 K5 setting (10 ms poll; B-01 H_P: no material component)",
    "target_effect_lag": "IRREDUCIBLE (target-owned)",
    "unattributed": "UNTESTED",
}


def w_verdicts(step0: dict) -> dict:
    out = {}
    for cls, c in step0.get("classes", {}).items():
        rules = c.get("rules_fired", [])
        per_doc = (c["excess"]["B1_minus_B2"] or 0) > 0
        if "per-document (first observer pays)" in rules or "load timing" in rules:
            v = "IRREDUCIBLE (amendment rule: per-document / load timing)"
        elif "per-process first use" in rules:
            v = "NOT DELETED (amendment rule: per-process first use; a warm-up could only move it before T)"
        else:
            v = "UNDECIDED (amendment rules)"
        out[cls] = {"amendment_rule_verdict": v, "rules_fired": rules,
                    "w_knob_justified": c.get("w_knob_justified"),
                    "session_reuse_bound_ms": c.get("session_reuse_bound_ms"),
                    "per_document_work_shown": per_doc,
                    "spec_rule": ("IRREDUCIBLE for the per-document part (STEP 0 shows per-document work: B1 - B2 > 0)"
                                  if per_doc else "no per-document work shown")}
    return out


def browser(raw: Path, nv_ref: dict | None) -> dict:
    out: dict = {}
    if (raw / "step0-r2-trials.tar.gz").exists():
        out["step0_r2"] = S0.build(raw / "step0-r2-trials.tar.gz")
        out["step0_r2"].pop("per_trial", None)
    if (raw / "shake-r2-step0-trials.tar.gz").exists():
        sh = S0.build(raw / "shake-r2-step0-trials.tar.gz")
        out["shake_r2_step0"] = {"trials": sh["trials"], "excluded": True}
    measured = AB.load(raw, "measured")
    ctrl = AB.load(raw, "controls")
    smk = AB.load(raw, "smoke")
    shakes = AB.load(raw, "shake-r2") + AB.load(raw, "shake-r2b")
    out["shakedowns"] = {"trials": len(shakes), "excluded": True,
                         "outcomes": sorted({f"{t['summary']['kind']}:{t['summary'].get('outcome')}" for t in shakes})}
    if not measured:
        return out
    rows = [AB.trial_row(t) for t in measured]
    out["measured"] = {"trials": len(rows), "valid": sum(r["valid"] for r in rows), "classes": {}}
    controls = AB.controls(ctrl, nv_ref)
    ne3 = AB.e_trials_n_e3([measured, ctrl])
    out["controls"] = controls
    out["N-E3"] = ne3
    out["smoke"] = AB.smoke(smk)
    ne_ok = (controls["N-E1"]["n"] > 0 and controls["N-E1"]["pass"] == controls["N-E1"]["n"]
             and controls["N-E2"]["n"] > 0 and controls["N-E2"]["pass"] == controls["N-E2"]["n"] and ne3["pass"])
    env_ok = bool(nv_ref) and controls["N-V_browser_runner"]["pass"]
    w = w_verdicts(out.get("step0_r2", {}))
    out["W"] = w
    all_measured = measured + ctrl
    out["invariants"] = {
        "duplicate_completion_mutations": sum(1 for t in all_measured if (t["summary"].get("completion_mutations") or 0) > 1),
        "unverified_successes": sum(1 for t in all_measured if t["summary"].get("outcome") == "verified"
                                    and not t["summary"].get("oracle_exact_match")),
        "stale_ref_dispatches": controls["N-W1"]["stale_ref_dispatches"],
        "non_loopback_connect_attempts": sum((t["summary"].get("network") or {}).get("non_loopback_connect_attempts", 0)
                                             for t in measured + ctrl + smk),
    }
    for cls in AB.CLASSES:
        cr = [r for r in rows if r["cls"] == cls]
        arms = {a: AB.arm_block([r for r in cr if r["arm"] == a]) for a in AB.ARMS}
        validity = {a: (arms[a]["valid"] >= 19 and arms[a]["n"] == 20) for a in AB.ARMS}
        inv_ok = (out["invariants"]["duplicate_completion_mutations"] == 0 and out["invariants"]["unverified_successes"] == 0
                  and out["invariants"]["stale_ref_dispatches"] == 0)
        pairs = {f"K5-{a}": {"T_oracle": AB.paired(cr, "K5", a, "T_oracle_ms"),
                             "T_runner": AB.paired(cr, "K5", a, "T_runner_ms"),
                             "bind_plus_T_oracle": AB.paired(cr, "K5", a, "bind_plus_T_oracle_ms"),
                             "endpoint_component": AB.paired(cr, "K5", a, "endpoint_ms"),
                             "admission_component": AB.paired(cr, "K5", a, "admission_ms")}
                 for a in ("K5E", "K5V", "K5EV")}
        k5_ep, k5_adm = arms["K5"]["endpoint_ms_median"], arms["K5"]["admission_ms_median"]
        pe, pv = pairs["K5-K5E"]["T_oracle"], pairs["K5-K5V"]["T_oracle"]
        e_ci = bool(pe["ci95"] and pe["ci95"][0] > 0)
        e_frac = None if not k5_ep else pe["median"] / k5_ep
        if not ne_ok:
            ev = "IRREDUCIBLE (a takeover/restart/fresh-process control failed)"
        elif e_ci and e_frac is not None and e_frac >= 0.5 and validity["K5E"]:
            ev = "OWNER_DECISION"
        else:
            ev = "NOT_MATERIAL (saving not shown on T_oracle)"
        v_ci = bool(pv["ci95"] and pv["ci95"][0] > 0)
        v_frac = None if not k5_adm else pv["median"] / k5_adm
        if not env_ok:
            vv = "IRREDUCIBLE (envelopes differ)"
        elif v_ci and v_frac is not None and v_frac >= 0.5 and validity["K5V"]:
            vv = "DELETED (KEEP)"
        else:
            vv = "NOT_MATERIAL (saving not shown on T_oracle)"
        s_ratio = AB.ratio(cr, "K5", "K5EV")
        keep = {"K5": True, "K5V": vv == "DELETED (KEEP)", "K5E": False, "K5EV": False}
        held = [a for a in AB.ARMS if validity[a] and inv_ok and keep[a]]
        best = min(held, key=lambda a: arms[a]["T_oracle_ms"]["median"]) if held else None
        held_incl_e = [a for a in AB.ARMS if validity[a] and inv_ok and
                       (keep[a] or (a == "K5E" and ev == "OWNER_DECISION") or
                        (a == "K5EV" and ev == "OWNER_DECISION" and keep["K5V"]))]
        best_incl_e = min(held_incl_e, key=lambda a: arms[a]["T_oracle_ms"]["median"]) if held_incl_e else None
        def e2_for(arm: str | None) -> dict | None:
            if not arm:
                return None
            b = arms[arm]
            meanT = b["T_runner_ms"]["mean"]
            rows_e2 = []
            for c in B.COMPONENTS:
                ms, share = b["components_mean_ms"][c], b["shares"][c]
                material = ms is not None and (ms >= AB.THRESH_MS or (share or 0) >= AB.THRESH_SHARE)
                if c == "observation":
                    verdict = ("IRREDUCIBLE (one fresh semantic_v2 snapshot per action); cold-first-snapshot excess: W "
                               + w.get(cls, {}).get("amendment_rule_verdict", "n/a"))
                elif c == "revalidate":
                    verdict = f"endpoint re-proof: E {ev}; remaining steps IRREDUCIBLE (per-mutation binding re-proof, #73)"
                elif c == "driver_pre_dispatch":
                    verdict = f"admission: V {vv}; the residual single validation and its glue UNTESTED (includes trace-mark cost)"
                else:
                    verdict = VERDICT_TEXT[c]
                rows_e2.append({"component": c, "mean_ms": ms, "share": share, "material": material,
                                "verdict": verdict if material else "below threshold"})
            sub = b["sub_mean_ms"]
            residual = sub.get("pre_admission_validate", 0.0) + sub.get("pre_inner_validate", 0.0)
            untested = {"admission_residual_after_V": residual if arm in AB.V_ARMS else 0.0,
                        "unattributed": b["components_mean_ms"]["unattributed"] or 0.0}
            if w.get(cls, {}).get("amendment_rule_verdict", "").startswith("UNDECIDED"):
                untested["first_snapshot_cold_excess"] = AB.mean([r["first_snapshot_excess_ms"] for r in cr
                                                                  if r["arm"] == arm and r["valid"]]) or 0.0
            return {"arm": arm, "T_runner_mean_ms": meanT, "T_oracle_median_ms": b["T_oracle_ms"]["median"],
                    "rows": rows_e2, "untested_ms": untested,
                    "untested_share": (sum(untested.values()) / meanT) if meanT else None}

        e2 = {"rule": "best composed arm = lowest median T_oracle among arms whose validity gates held and whose knobs are all DELETED (KEEP); E is at best OWNER_DECISION, so the best arm including OWNER_DECISION knobs is decomposed separately",
              "best_composed_arm": best, "best": e2_for(best),
              "best_including_owner_decision_arm": best_incl_e, "best_including_owner_decision": e2_for(best_incl_e)}
        out["measured"]["classes"][cls] = {
            "arms": {a: {k: v for k, v in arms[a].items()} for a in AB.ARMS}, "validity_19_of_20": validity,
            "paired": pairs, "S_K5_over_K5EV": s_ratio,
            "E": {"k5_endpoint_component_median_ms": k5_ep, "saving_median_ms": pe["median"], "saving_ci95": pe["ci95"],
                  "saving_fraction_of_component": e_frac, "controls_pass": ne_ok, "verdict": ev,
                  "moved_check_bind_plus_T": pairs["K5-K5E"]["bind_plus_T_oracle"]},
            "V": {"k5_admission_component_median_ms": k5_adm, "saving_median_ms": pv["median"], "saving_ci95": pv["ci95"],
                  "saving_fraction_of_component": v_frac, "envelopes_identical": env_ok, "verdict": vv},
            "E2": e2,
        }
        out["measured"]["per_trial"] = [{k: r.get(k) for k in ("trial", "cls", "arm", "round", "valid", "reasons", "T_oracle_ms",
                                                               "T_runner_ms", "bind_ms", "endpoint_ms", "admission_ms",
                                                               "first_snapshot_excess_ms", "loadavg_1m")} for r in rows]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "b02-summary.json"))
    a = ap.parse_args()
    raw = Path(a.raw)
    vm = analyze_vmicro(raw)
    nv = analyze_nv(raw)
    nv_files = _bundle_files(raw, "nv")
    nv_recs = [json.loads(t.splitlines()[-1]) for n, t in sorted(nv_files.items()) if n.endswith("-nv.jsonl")]
    nv_ref = nv_recs[0]["replies"] if (nv_recs and nv["pass"]) else None
    br = browser(raw, nv_ref)
    m = br.get("measured", {}).get("classes", {})
    summary = {
        "schema": "cua.r2.b02.summary.v2",
        "vmicro": vm,
        "nv": nv,
        "step0_browser_launch_hostless_v1": analyze_step0(raw),
        "unit": analyze_unit(raw),
        "browser": br,
        "verdicts": {
            "H_E": {c: m[c]["E"]["verdict"] for c in m} if m else "not run",
            "H_V": {c: m[c]["V"]["verdict"] for c in m} if m else "not run",
            "H_V_per_call": ("per-call deletion confirmed (BENCHMARK+REAL)" if vm["gate_V_call"]["pass"]
                             else "per-call NOT_MATERIAL"),
            "H_W": {c: v["amendment_rule_verdict"] for c, v in br.get("W", {}).items()},
        },
    }
    summary = json.loads(json.dumps(summary, sort_keys=True, default=lambda x: round(x, 6) if isinstance(x, float) else str(x)))
    Path(a.out).write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    g = vm["gate_V_call"]
    print(json.dumps({"vmicro_valid": f'{vm["valid"]}/{vm["trials"]}', "saving": g["saving_median_ms"],
                      "gate": g["pass"], "nv_pass": nv["pass"], "verdicts": summary["verdicts"]}, indent=1))


if __name__ == "__main__":
    main()
