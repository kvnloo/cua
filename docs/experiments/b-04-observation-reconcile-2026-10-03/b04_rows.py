"""B-04 per-trial extraction (standard library only): one row per trial from the runner's event
log, its summary line and the Driver phase trace. Shared by analyze_b04.py and verify_artifacts.py.

Definitions (PREREG.json ``estimators``):
- call window of label L: caller ``call_send``/``call_return`` with label L (monotonic ns);
- Driver span of a semantic_v2 observation: first ``snap.enter`` -> first ``snap.serialized`` inside its
  call window (primary estimator);
- Driver walk of an observation (second estimator): the Driver's in-process tree walks inside the
  window, excluding every CDP round trip: (snap.indexed - snap.layout_cdp_done)
  + sum(snap.ax_composed - preceding snap.ax_cdp_done) + (snap.outcome - snap.oopif_done);
- excess = span(snapshot1) - span(resnap1) (P3 arm B: span(snapshot1) - span(resnap1) after presnap).
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Any

SUB = [("attach", "snap.enter", "snap.attached"), ("dom_get_document", "snap.attached", "snap.document"),
       ("frame_tree", "snap.document", "snap.frame_tree"), ("layout_snapshot", "snap.frame_tree", "snap.layout_cdp_done"),
       ("index", "snap.layout_cdp_done", "snap.indexed"), ("ax_tree", "snap.indexed", "snap.ax_cdp_done"),
       ("ax_compose", "snap.ax_cdp_done", "snap.ax_composed"), ("collected_to_oopif", "snap.ax_composed", "snap.oopif_done"),
       ("page_outcome", "snap.oopif_done", "snap.outcome"), ("store_serialize", "snap.outcome", "snap.serialized")]
EXPECTED_ROUTES = {"fill": ["trusted_input", "dom"], "toggle": ["dom", "dom"], "modal": ["dom", "dom"]}


def load_dir(trials_dir: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(trials_dir.glob("*.jsonl")):
        if p.name.endswith(".driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        s = lines[-1]
        tp = trials_dir / Path(s["driver_trace"]).name if s.get("driver_trace") else None
        trace = ([json.loads(x) for x in tp.read_text().splitlines() if x.strip()] if tp and tp.exists() else [])
        out.append({"summary": s, "events": lines[:-1], "trace": trace})
    return out


def load_tar(path: Path) -> list[dict[str, Any]]:
    files: dict[str, str] = {}
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.endswith(".jsonl"):
                files[Path(m.name).name] = tar.extractfile(m).read().decode()
    out = []
    for name in sorted(files):
        if name.endswith(".driver-trace.jsonl"):
            continue
        lines = [json.loads(x) for x in files[name].splitlines() if x.strip()]
        s = lines[-1]
        text = files.get(Path(s["driver_trace"]).name, "") if s.get("driver_trace") else ""
        out.append({"summary": s, "events": lines[:-1], "trace": [json.loads(x) for x in text.splitlines() if x.strip()]})
    return out


def windows(t: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sends: dict[str, dict[str, Any]] = {}
    out: dict[str, dict[str, Any]] = {}
    for e in t["events"]:
        if e["event"] == "call_send":
            sends[e["label"]] = e
        elif e["event"] == "call_return" and e["label"] in sends and e["label"] not in out:
            s = sends[e["label"]]
            out[e["label"]] = {"label": e["label"], "tool": e.get("tool"), "t0": s["t_mono_ns"], "t1": e["t_mono_ns"],
                               "ok": e.get("ok"), "route": e.get("route"), "effect": e.get("effect"),
                               "n_refs": e.get("n_refs"), "refused": e.get("refused"), "code": e.get("code")}
    return out


def marks_in(trace: list[dict[str, Any]], w: dict[str, Any] | None) -> list[tuple[str, int]]:
    if w is None:
        return []
    return [(m["phase"], m["t_mono_ns"]) for m in trace if w["t0"] <= m["t_mono_ns"] <= w["t1"]]


def snap_measures(trace: list[dict[str, Any]], w: dict[str, Any] | None) -> dict[str, Any]:
    ms = [(p, t) for p, t in marks_in(trace, w) if p.startswith("snap.")]
    first: dict[str, int] = {}
    for p, t in ms:
        first.setdefault(p, t)
    out: dict[str, Any] = {"call_ms": None if w is None else (w["t1"] - w["t0"]) / 1e6}
    if "snap.enter" in first and "snap.serialized" in first:
        out["span_ms"] = (first["snap.serialized"] - first["snap.enter"]) / 1e6
    else:
        out["span_ms"] = None
    walk = 0
    ok = all(k in first for k in ("snap.layout_cdp_done", "snap.indexed", "snap.oopif_done", "snap.outcome"))
    if ok:
        walk += first["snap.indexed"] - first["snap.layout_cdp_done"]
        walk += first["snap.outcome"] - first["snap.oopif_done"]
        last_cdp = None
        n_ax = 0
        for p, t in ms:
            if p == "snap.ax_cdp_done":
                last_cdp = t
            elif p == "snap.ax_composed" and last_cdp is not None:
                walk += t - last_cdp
                last_cdp = None
                n_ax += 1
        ok = n_ax >= 1
    out["walk_ms"] = walk / 1e6 if ok else None
    out["sub"] = {k: (first[b] - first[a]) / 1e6 for k, a, b in SUB if a in first and b in first}
    return out


def ev_first(t: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((e for e in t["events"] if e["event"] == name), None)


def row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    w = windows(t)
    trace = t["trace"]
    r: dict[str, Any] = {k: s.get(k) for k in ("trial", "cls", "arm", "block", "round", "probe", "P", "D", "variant",
                                                "resnap", "inject_ms", "inject_mode", "mode", "outcome",
                                                "oracle_exact_match", "completion_mutations", "routes")}
    r["cell"] = s["trial"].split("-", 3)[3] if s.get("trial", "").count("-") >= 3 else None
    ts = ev_first(t, "task_start")
    ts_ns = ts["t_mono_ns"] if ts else None
    poller = s.get("poller_first_ok_ns")
    nav = w.get("navigate")
    r["navigate_ms"] = None if nav is None else (nav["t1"] - nav["t0"]) / 1e6
    ww, wsn = w.get("warm_navigate"), w.get("warm_snapshot")
    r["warmup_ms"] = (wsn["t1"] - ww["t0"]) / 1e6 if (ww and wsn) else (0.0 if s.get("P") == "cold" else None)
    r["warm_navigate_ms"] = None if ww is None else (ww["t1"] - ww["t0"]) / 1e6
    r["T_oracle_ms"] = None if (ts_ns is None or poller is None) else (poller - ts_ns) / 1e6
    r["T_oracle_P4_ms"] = (None if (r["T_oracle_ms"] is None or r["warmup_ms"] is None)
                           else r["T_oracle_ms"] + r["warmup_ms"])
    r["T_oracle_P4_incl_nav_ms"] = (None if (r["T_oracle_P4_ms"] is None or r["navigate_ms"] is None)
                                    else r["T_oracle_P4_ms"] + r["navigate_ms"])
    s1 = w.get("snapshot1")
    r["T_oracle_r210_ms"] = None if (s1 is None or poller is None) else (poller - s1["t0"]) / 1e6
    r["nav_return_to_snapshot1_send_ms"] = None if (nav is None or s1 is None) else (s1["t0"] - nav["t1"]) / 1e6
    de, ds = ev_first(t, "delay_end"), ev_first(t, "delay_start")
    r["delay_ms"] = None if (de is None or ds is None) else (de["t_mono_ns"] - ds["t_mono_ns"]) / 1e6
    for lab in ("snapshot1", "resnap1", "presnap", "warm_snapshot", "snapshot2", "snapshot3"):
        m = snap_measures(trace, w.get(lab))
        r[f"{lab}_span_ms"], r[f"{lab}_walk_ms"], r[f"{lab}_call_ms"] = m["span_ms"], m["walk_ms"], m["call_ms"]
        if lab in ("snapshot1", "resnap1", "presnap"):
            r[f"{lab}_sub"] = m["sub"]
        r[f"{lab}_n_refs"] = None if w.get(lab) is None else w[lab].get("n_refs")
    r["excess_ms"] = (None if (r["snapshot1_span_ms"] is None or r["resnap1_span_ms"] is None)
                      else r["snapshot1_span_ms"] - r["resnap1_span_ms"])
    r["excess_walk_ms"] = (None if (r["snapshot1_walk_ms"] is None or r["resnap1_walk_ms"] is None)
                           else r["snapshot1_walk_ms"] - r["resnap1_walk_ms"])
    r["excess_b03_ms"] = (None if (r["snapshot1_span_ms"] is None or r["snapshot2_span_ms"] is None)
                          else r["snapshot1_span_ms"] - r["snapshot2_span_ms"])
    inj = s.get("inject_record")
    r["inject_vs_nav"] = None
    if inj and nav:
        r["inject_vs_nav"] = {"start_after_nav_send_ms": (inj["t_start_ns"] - nav["t0"]) / 1e6,
                              "end_minus_nav_return_ms": (inj.get("t_end_ns", 0) - nav["t1"]) / 1e6}
    r["inject_fired"] = bool(inj)
    # forced path, route and invariants
    acts = [w[k] for k in sorted(w, key=lambda k: w[k]["t0"]) if k.startswith("action")]
    r["action_routes"] = [a.get("route") for a in acts if a.get("ok")]
    order = [w[k] for k in sorted(w, key=lambda k: w[k]["t0"])
             if w[k]["tool"] in ("get_browser_state", "browser_navigate", "browser_click", "browser_type")]
    stale = bool(s.get("action_error")) or any(a.get("ok") is False for a in acts)
    for i, x in enumerate(order):
        if x["label"].startswith("action") and (i == 0 or order[i - 1]["tool"] != "get_browser_state"
                                                 or order[i - 1]["label"] in ("bind", "presnap", "warm_snapshot")):
            stale = True
    r["stale_dispatch"] = stale
    r["refusals"] = len(s.get("refusals") or [])
    phases = [m["phase"] for m in trace]
    r["v_marks"] = phases.count("mcp.inner_validation_skipped")
    r["inner_validated_marks"] = phases.count("mcp.inner_validated")
    r["exp_knob_marks"] = phases.count("exp_knob")
    r["driver_env_exp"] = s.get("driver_env_exp")
    r["driver_env_telemetry"] = s.get("driver_env_telemetry")
    r["fallback"] = s.get("fallback")
    r["duplicate_mutation"] = (s.get("completion_mutations") or 0) > 1
    r["unverified_success"] = s.get("outcome") == "verified" and not s.get("oracle_exact_match")
    r["non_loopback"] = (s.get("network") or {}).get("non_loopback_connect_attempts", 0)
    r["loadavg_before_1m"] = float(s["loadavg_before"].split()[0]) if s.get("loadavg_before") else None
    r["loadavg_after_1m"] = float(s["loadavg_after"].split()[0]) if s.get("loadavg_after") else None
    r["route_ok"] = r["action_routes"] == EXPECTED_ROUTES.get(s.get("cls"), [])
    arm_ok = True
    if s.get("arm") == "COMP":
        arm_ok = (r["driver_env_exp"] or {}).get("CUA_DRIVER_EXP_ADMISSION_TOOLS_CACHE") == "1" and r["v_marks"] > 0
        if s.get("cls") == "fill":
            arm_ok = arm_ok and (r["driver_env_exp"] or {}).get("CUA_DRIVER_EXP_TYPE_FOCUS_SETTLE_MS") == "0" \
                and (s.get("routes") or [None])[0] == "compiled"
    elif s.get("arm") == "DEFAULT":
        arm_ok = not r["driver_env_exp"] and r["v_marks"] == 0
    r["arm_ok"] = arm_ok
    r["resnap_ok"] = (not s.get("resnap")) or (r["snapshot1_span_ms"] is not None and r["resnap1_span_ms"] is not None)
    r["valid"] = (s.get("outcome") == "verified" and bool(s.get("oracle_exact_match")) and poller is not None
                  and s.get("completion_mutations") == 1 and not stale and r["route_ok"] and arm_ok and r["resnap_ok"]
                  and r["non_loopback"] == 0 and r["driver_env_telemetry"] == "0"
                  and (not s.get("inject_ms") or r["inject_fired"]))
    return r
