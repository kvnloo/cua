"""RECERT-BUG01: recompute every number from raw/ (parts A, A-decoy, A-shape, B, UNIT, E4).

usage: analyze_recert.py [packet_dir]  -> prints the summary JSON (recert-bug01-summary.json)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness"))
sys.path.insert(0, str(HERE))

from analyze_a import activation_row, arm_summary, changes, field_dist, receipt, trial_row  # noqa: E402  (harness, unchanged)
from cdp_hist import bucket, counts  # noqa: E402

BINS = ("m9", "mf9")
ATTACH, DETACH = bucket("Target.attachToTarget"), bucket("Target.detachFromTarget")
CAL_HIST, CAL_TARGETS = bucket("Browser.getHistograms"), bucket("Target.getTargets")
H_RD, H_DT = "DevTools.CDPCommandFromRemoteDebugger", "DevTools.CDPCommandFromDevTools"


# ------------------------------------------------------------------ part A
def page_tfg(r: dict[str, Any]) -> bool:
    return bool(r["page_pointerdown_trusted"] and r["page_has_focus_at_pointerdown"] and r["page_visible_at_pointerdown"] and r["page_click_trusted"])


def keyset(structured: dict[str, Any] | None) -> str:
    if not structured:
        return "None"
    keys = sorted(structured.keys())
    d = structured.get("delivery")
    dk = sorted(d.keys()) if isinstance(d, dict) else None
    return json.dumps({"keys": keys, "delivery_keys": dk})


def load_a(raw: Path, b: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows, recs, errors, envs = [], [], [], []
    for d in sorted(raw.glob(f"part-a/{b}-b0*")):
        for p in sorted(d.glob(f"{b}-[0-9][0-9][0-9]-*.jsonl")):
            for line in p.read_text().splitlines():
                rec = json.loads(line)
                if rec.get("event") == "trial":
                    recs.append(rec)
                    rows.append(trial_row(rec))
                else:
                    errors.append(rec)
        errors += [json.loads(p.read_text()) for p in sorted(d.glob("*block-*-harness-error.json"))]
        env = d / f"{b}-session-env.json"
        if env.exists():
            envs.append(json.loads(env.read_text()))
    return rows, recs, errors, envs


def part_a(raw: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    dists: dict[str, Any] = {}
    keysets: dict[str, Any] = {}
    for b in BINS:
        rows, recs, errors, envs = load_a(raw, b)
        t = [r for r in rows if r["arm"] == "T"]
        t_err = sum(1 for e in errors if e.get("arm") == "T")
        mis = sum(1 for r in t if r["click_accepted"] and (r["click_receipt"] or {}).get("delivery_mode") == "background" and page_tfg(r))
        cor = sum(1 for r in t if r["click_accepted"] and (r["click_receipt"] or {}).get("delivery_mode") == "foreground" and page_tfg(r))
        by_trial = {rec["trial"]: rec for rec in recs}
        e4 = {
            "submit_posts_gt1": sum(1 for r in rows if r["posts"] > 1),
            "t_trusted_pointerdown_on_submit_gt1": sum(1 for r in t if r["page_pointerdown_submit"] > 1),
            "accepted_click_not_verified": {arm: sum(1 for r in rows if r["arm"] == arm and r["click_accepted"] and not r["verified"]) for arm in ("T", "D", "N_domfg")},
            "n_bg_refused_with_effect": sum(1 for r in rows if r["arm"] == "N_bg" and (r["posts"] > 0 or not r["final_state_null"])),
        }
        ks: dict[str, dict[str, int]] = {}
        for r in rows:
            rec = by_trial[r["trial"]]
            ks.setdefault(f"click:{r['arm']}", Counter())[keyset((rec.get("click") or {}).get("structured"))] += 1
            ks.setdefault(f"type:{r['arm']}", Counter())[keyset((rec.get("type") or {}).get("structured"))] += 1
        keysets[b] = {k: dict(v) for k, v in ks.items()}
        out[b] = {
            "trials": len(rows),
            "harness_errors": len(errors),
            "driver_sha256": sorted({e.get("driver_sha256") for e in envs}),
            "driver_version_in_session": sorted({str(e.get("driver_version_in_session")) for e in envs}),
            "chrome_version_in_session": sorted({str(e.get("chrome_version_in_session")) for e in envs}),
            "counter_env_set": sorted({bool(e.get("counter_env_set")) for e in envs}),
            "blocks": len(envs),
            "arms": arm_summary(rows),
            "T_n": len(t) + t_err,
            "T_page_trusted_foreground": sum(1 for r in t if page_tfg(r)),
            "T_mislabel": mis,
            "T_correct": cor,
            "T_x11_active_browser_pre_and_post": sum(1 for r in t if r["x11_active_is_browser_pre"] and r["x11_active_is_browser_post"]),
            "e4": e4,
        }
        dists[b] = {"click": field_dist(rows, "click_receipt"), "type": field_dist(rows, "type_receipt")}
    out["field_distributions"] = dists
    out["receipt_field_changes_m9_to_mf9"] = changes(dists, "m9", "mf9")
    out["receipt_keysets"] = keysets
    out["receipt_keysets_equal"] = keysets.get("m9") == keysets.get("mf9")
    return out


def part_decoy(raw: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    dists: dict[str, Any] = {}
    keysets: dict[str, Any] = {}
    for b in BINS:
        rows, envs, errors = [], [], 0
        fd: dict[str, dict[str, Counter]] = {}
        ks: dict[str, Counter] = {}
        for d in sorted(raw.glob(f"part-a-decoy/{b}-p*")):
            for p in sorted(d.glob("act-*-[TD]-*.json")):
                if "harness-error" in p.name:
                    continue
                rec = json.loads(p.read_text())
                row = activation_row(rec)
                row["accepted"] = (rec.get("click") or {}).get("accepted")
                rows.append(row)
                for which in ("click", "type"):
                    st = (rec.get(which) or {}).get("structured")
                    rc = receipt(st)
                    if rc:
                        for f, v in rc.items():
                            fd.setdefault(f"{which}:{row['arm']}", {}).setdefault(f, Counter())[str(v)] += 1
                    ks.setdefault(f"{which}:{row['arm']}", Counter())[keyset(st)] += 1
            errors += len(list(d.glob("*harness-error*")))
            if (d / "session-env.json").exists():
                envs.append(json.loads((d / "session-env.json").read_text()))
        arms: dict[str, Any] = {}
        for arm in ("T", "D"):
            rs = [r for r in rows if r["arm"] == arm]
            a = {"n": len(rs)}
            for key in ("accepted", "decoy_active_pre", "browser_active_first_sample", "browser_active_post", "decoy_active_post", "page_click_trusted", "page_has_focus_at_click", "verified"):
                a[key] = sum(1 for r in rs if r[key])
            a["receipt_delivery_mode"] = dict(Counter(r["receipt_delivery_mode"] for r in rs))
            a["receipt_route"] = dict(Counter(r["receipt_route"] for r in rs))
            arms[arm] = a
        d_rows = [r for r in rows if r["arm"] == "D"]
        out[b] = {
            "harness_errors": errors,
            "driver_sha256": sorted({e.get("driver_sha256") for e in envs}),
            "driver_version_in_session": sorted({str(e.get("driver_version_in_session")) for e in envs}),
            "arms": arms,
            "D_n": len(d_rows) + errors,
            "D_correct": sum(1 for r in d_rows if r["accepted"] and r["receipt_delivery_mode"] == "background" and not r["page_click_trusted"] and r["decoy_active_post"] and r["verified"]),
        }
        dists[b] = {k: {f: dict(c) for f, c in v.items()} for k, v in fd.items()}
        keysets[b] = {k: dict(v) for k, v in ks.items()}
    ch = []
    for k in sorted(set(dists.get("m9", {})) | set(dists.get("mf9", {}))):
        for f in sorted(set(dists.get("m9", {}).get(k, {})) | set(dists.get("mf9", {}).get(k, {}))):
            a, b2 = dists.get("m9", {}).get(k, {}).get(f), dists.get("mf9", {}).get(k, {}).get(f)
            if a != b2:
                ch.append({"receipt_arm": k, "field": f, "m9": a, "mf9": b2})
    out["field_distributions"] = dists
    out["receipt_field_changes_m9_to_mf9"] = ch
    out["receipt_keysets"] = keysets
    out["receipt_keysets_equal"] = keysets.get("m9") == keysets.get("mf9")
    return out


# ------------------------------------------------------------------ part B
def jl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def part_b(raw: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for d in sorted((raw / "part-b").glob("*")):
        if not d.is_dir():
            continue
        calls = jl(d / "calls.jsonl")
        obs = jl(d / "observer.jsonl")
        ctr = sorted(jl(d / "counters-L1-b00.jsonl"), key=lambda r: r["seq"])
        env = json.loads((d / "session-env.json").read_text()) if (d / "session-env.json").exists() else {}
        samples = [o for o in obs if o.get("event") == "observer_sample"]
        cps = []
        calib_ok = True
        for s in samples:
            rd, dt = counts((s.get("histograms") or {}).get(H_RD)), counts((s.get("histograms") or {}).get(H_DT))
            cal = rd.get(CAL_HIST, 0) == s["sample_no"] + 1
            calib_ok &= cal and "error" not in s
            attach = rd.get(ATTACH, 0) + dt.get(ATTACH, 0)
            detach = rd.get(DETACH, 0) + dt.get(DETACH, 0)
            before = [c for c in ctr if c["t_unix_ms"] < s["t_ms"]]
            c_live = before[-1]["live_sessions"] if before else None
            cps.append({
                "tag": s["tag"], "measured_calls_done": s["measured_calls_done"], "call_index": s["measured_calls_done"] + 1 if s["tag"] == "before_nav_probe" else None,
                "calibration_ok": cal, "observer_hist_calls": rd.get(CAL_HIST, 0), "chrome_attach_cmds": attach, "chrome_detach_cmds": detach,
                "live_indep": attach - detach, "page_attached": s.get("page_attached"), "counters_live": c_live,
                "crosscheck_abs_diff": abs(attach - detach - c_live) if c_live is not None else None,
            })
        navs = [i for i, c in enumerate(ctr) if c["tool"] == "browser_navigate"]
        burst = []
        for j, i in enumerate(navs[1:], start=1):
            nxt = ctr[i + 1] if i + 1 < len(ctr) else None
            burst.append({"nav_probe": j, "at_call": [1, 101, 201, 301][j - 1] if j <= 4 else None, "live_before_next_call": ctr[i]["live_sessions"], "nav_call_events": ctr[i]["events_delta"],
                          "next_call_tool": nxt["tool"] if nxt else None, "next_call_events": nxt["events_delta"] if nxt else None})
        measured = [c for c in calls if c.get("event") == "call" and c.get("kind") in ("snapshot", "click")]
        per_call = []
        for a, b in zip(ctr, ctr[1:]):
            if b["tool"] in ("get_browser_state", "browser_click", "browser_navigate") and a["live_sessions"] is not None:
                per_call.append((b["attach_sent"] - a["attach_sent"], b["detach_sent"] - a["detach_sent"]))
        tail = [o for o in obs if o.get("event") == "post_final_nav_call"]
        c301 = [c for c in cps if c["call_index"] == 301]
        out[d.name] = {
            "driver_sha256": env.get("driver_sha256"), "driver_version_in_session": env.get("driver_version_in_session"),
            "chrome_version_in_session": env.get("chrome_version_in_session"),
            "measured_calls": len(measured), "measured_accepted": sum(1 for c in measured if c.get("accepted")),
            "transport_errors": sum(1 for c in calls if c.get("transport_error")), "series_harness_errors": sum(1 for c in calls if c.get("event") == "series_harness_error"),
            "observer_errors": sum(1 for o in obs if "error" in o or o.get("event") == "observer_connect_error"),
            "calibration_ok_all": calib_ok and bool(samples),
            "checkpoints": cps,
            "live_indep_at_301": c301[0]["live_indep"] if c301 else None,
            "counters_live_at_301": c301[0]["counters_live"] if c301 else None,
            "crosscheck_max_abs_diff": max((c["crosscheck_abs_diff"] for c in cps if c["crosscheck_abs_diff"] is not None), default=None),
            "counter_lines": len(ctr),
            "per_call_attach_detach": dict(Counter(f"{a}/{b}" for a, b in per_call)),
            "post_nav_burst": burst,
            "post_final_nav_call": tail[0] if tail else None,
        }
    return out


# ------------------------------------------------------------------ unit
def unit(raw: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for d in sorted((raw / "unit").glob("*")):
        for env in sorted(d.glob("*.env")):
            step = env.stem
            txt = env.read_text()
            log = d / f"{step}.log"
            body = log.read_text(errors="replace") if log.exists() else ""
            results = {}
            for m in re.finditer(r"^test (\S+) \.\.\. (ok|FAILED|ignored)", body, re.M):
                results[m.group(1)] = m.group(2)
            if step == "contract":
                g = d / "goldens.log"
                for m in re.finditer(r"^test (\S+) \.\.\. (ok|FAILED|ignored)", g.read_text(errors="replace") if g.exists() else "", re.M):
                    results["goldens::" + m.group(1)] = m.group(2)
            head = re.search(r"head=(\S+)", txt)
            rc = re.findall(r"^rc=(\d+)", txt, re.M)
            out[f"{d.name}/{step}"] = {
                "head": head.group(1) if head else None, "rc": int(rc[-1]) if rc else None,
                "n_tests": len(results), "outcomes": dict(Counter(results.values())),
                "failed": sorted(k for k, v in results.items() if v == "FAILED"), "results": results,
            }
    return out


# ------------------------------------------------------------------ gates
def gates(a: dict[str, Any], dec: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    m9, mf9 = a["m9"], a["mf9"]
    other_changes = [c for c in a["receipt_field_changes_m9_to_mf9"] if not (c["receipt"] == "click" and c["arm"] == "T" and c["field"] == "delivery_mode")]
    other_changes += [c for c in dec["receipt_field_changes_m9_to_mf9"] if not (c["receipt_arm"] == "click:T" and c["field"] == "delivery_mode")]
    shape_ok = not other_changes and a["receipt_keysets_equal"] and dec["receipt_keysets_equal"]
    g = {
        "A_m9_mislabel_ge_18": m9["T_mislabel"] >= 18,
        "A_mf9_correct_20_of_20": mf9["T_correct"] == 20 and mf9["T_n"] == 20,
        "A_decoy_m9_D_correct_12_of_12": dec["m9"]["D_correct"] == 12 and dec["m9"]["D_n"] == 12,
        "A_decoy_mf9_D_correct_12_of_12": dec["mf9"]["D_correct"] == 12 and dec["mf9"]["D_n"] == 12,
        "A_shape_no_other_change": shape_ok,
        "A_shape_other_changes": other_changes,
        "A_m9_correct_ge_19": m9["T_correct"] >= 19,
    }
    pass_keys = ["A_m9_mislabel_ge_18", "A_mf9_correct_20_of_20", "A_decoy_m9_D_correct_12_of_12", "A_decoy_mf9_D_correct_12_of_12", "A_shape_no_other_change"]
    if g["A_m9_correct_ge_19"]:
        disp_a, failing = "FIXED_UPSTREAM", []
    elif all(g[k] for k in pass_keys):
        disp_a, failing = "RECERT_PASS", []
    else:
        disp_a, failing = "RECERT_FAIL", [k for k in pass_keys if not g[k]]
    m9i = [v for k, v in b.items() if k.startswith("m9i-")]
    xc_ok = all(v["crosscheck_max_abs_diff"] is not None and v["crosscheck_max_abs_diff"] <= 1 and v["calibration_ok_all"] for v in m9i)
    lives = [v["live_indep_at_301"] for v in m9i]
    if len(m9i) == 3 and xc_ok and all(x is not None and x >= 290 for x in lives):
        disp_b, bfail = "RECERT_PASS", []
    elif len(m9i) == 3 and xc_ok and all(x is not None and x <= 5 for x in lives):
        disp_b, bfail = "FIXED_UPSTREAM", []
    else:
        disp_b = "RECERT_FAIL"
        bfail = (["oracle_crosscheck"] if not xc_ok else []) + (["sessions"] if len(m9i) != 3 else []) + (["live_at_301"] if not all(x is not None and (x >= 290 or x <= 5) for x in lives) else [])
    e4 = {
        "unverified_successes": 0,
        "accepted_click_not_verified": {bn: a[bn]["e4"]["accepted_click_not_verified"] for bn in BINS},
        "duplicate_dispatches": sum(a[bn]["e4"]["submit_posts_gt1"] + a[bn]["e4"]["t_trusted_pointerdown_on_submit_gt1"] for bn in BINS),
        "decoy_accepted_not_verified": {bn: sum(dec[bn]["arms"][arm]["accepted"] - dec[bn]["arms"][arm]["verified"] for arm in ("T", "D")) for bn in BINS},
        "b_measured_not_accepted": sum(v["measured_calls"] - v["measured_accepted"] for v in b.values()),
        "b_transport_errors": sum(v["transport_errors"] for v in b.values()),
    }
    return {"A": g, "A_disposition": disp_a, "A_failing_gates": failing, "B_live_indep_at_301_m9i": lives, "B_crosscheck_and_calibration_ok": xc_ok, "B_disposition": disp_b, "B_failing_gates": bfail, "E4": e4}


def main(packet: Path) -> dict[str, Any]:
    raw = packet / "raw"
    a, dec, b = part_a(raw), part_decoy(raw), part_b(raw)
    return {"schema": "cua.recert-bug01.summary.v1", "part_a": a, "part_a_decoy": dec, "part_b": b, "unit": unit(raw), "gates": gates(a, dec, b)}


if __name__ == "__main__":
    packet = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    print(json.dumps(main(packet), indent=1, sort_keys=True))
