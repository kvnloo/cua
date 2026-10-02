"""B-02 analysis: recompute every number in b02-summary.json from raw/ (standard library only).

    python analyze_b02.py [--raw raw] [--out b02-summary.json]

Blocks: vmicro (admission A/B, BENCHMARK), nv (invalid-call envelopes, REAL), step0 and
step0-dbg1 (browser launch refusals, REAL), unit logs (UNIT), lock receipts. The rules are
the ones in PREREG.json (runnable_blocks). Statistics reuse B-01's seeded bootstrap.
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "b02-summary.json"))
    a = ap.parse_args()
    raw = Path(a.raw)
    vm = analyze_vmicro(raw)
    summary = {
        "schema": "cua.r2.b02.summary.v1",
        "vmicro": vm,
        "nv": analyze_nv(raw),
        "step0_browser_launch": analyze_step0(raw),
        "unit": analyze_unit(raw),
        "projection_V_to_browser_classes": projection(vm),
        "verdicts": {
            "H_E": "BLOCKED (UNIT only; no Driver-launched browser under hostless)",
            "H_V": ("per-call deletion confirmed (BENCHMARK+REAL); whole-task verdict BLOCKED"
                    if vm["gate_V_call"]["pass"] else "per-call NOT_MATERIAL; whole-task verdict BLOCKED"),
            "H_W": "BLOCKED (no knob built; STEP 0 browser probes blocked; not IRREDUCIBLE)",
        },
    }
    Path(a.out).write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    g = vm["gate_V_call"]
    print(json.dumps({"vmicro_valid": f'{vm["valid"]}/{vm["trials"]}', "k5_per_call_ms": g["k5_per_call_admission_ms"],
                      "saving": g["saving_median_ms"], "ci": g["saving_ci95"], "fraction": g["saving_fraction_of_k5"],
                      "gate": g["pass"], "nv_pass": summary["nv"]["pass"]}, indent=1))


if __name__ == "__main__":
    main()
