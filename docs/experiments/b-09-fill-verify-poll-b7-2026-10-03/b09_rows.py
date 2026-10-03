"""B-09 per-trial extraction (standard library only). Shared by analyze_b09.py and verify_artifacts.py.
Derived from B-08's b08_rows.py (blob-identical copy in this lane's first commit; git history shows every change).

One row per trial = B-04's ``b04_rows.row`` (harness/b04/b04_rows.py, blob-identical: T_oracle, call windows,
Driver snapshot spans, route receipts, E4 flags) plus the B-08 receipts and the B-09 additions:

- arm (BASE / P10a / P10b / P1 / P0 / PC / SMOKE), plan, block, round, attempt, Williams row and position;
- lane receipts: the lane variables set for the trial (``lane_env``), the verify-poll interval the compiled
  routine read (``verify_poll_interval_s``), the interval stamped on every poll sleep, and that the Driver
  environment carried no CUA_LANE_EXP_* variable; ``lane_ok`` = all equal the arm's PREREG values;
- process identity: Driver pid and Chrome browser pid with /proc start time immediately before the task
  navigate (every trial is cold); ``pids_ok`` = both present and alive;
- positive control: the measured CLOCK_MONOTONIC sleep inside T (``pc_sleep_ms``; arm PC, after snapshot1);
- PRIMARY ``T_runner_ms`` = first verified oracle read return (oracle_return outcome verified) - snapshot1
  call_send (R2-10's T, the one B-08 Part E decomposes);
- SECONDARY ``T_j_ms`` (B-08: max(journal completion ts, caller return of the last accepted mutation) -
  task_start) and ``T_oracle_ms`` (B-04 rule on the 2 ms sampler);
- verify-poll accounting after the last accepted mutation returns (``tail_start``): ``n_reads`` (oracle reads up
  to and including the verified one), ``n_sleeps`` and ``poll_sleep_ms`` (paired poll_sleep_start/_end of the
  compiled routine, or sleep_start/_end of the step loop), ``effect_latency_ms`` = journal completion ts -
  tail_start (may be negative when the server commits before the Driver returns);
- Driver identity from the trial record (name, sha256, version);
- actual route / producer per accepted action (receipt route, Driver dispatch mark in the call window, producer);
- E4 counters: stale dispatch, ambiguous dispatch, duplicate mutation, unverified success, blind replay,
  refusal returned as success (and non-loopback connects).

valid = b04 validity with the telemetry receipt read as off ('false') AND T_runner and T_j defined AND pids_ok AND
Driver identity AND caller variant default AND lane_ok AND (PC: the sleep was measured) AND no refusal returned
as success AND E4 counters 0. SMOKE uses the same rule with the DEFAULT configuration receipts (b04 arm_ok).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "harness" / "b04"))
import b04_rows as B  # noqa: E402

load_dir, load_tar, windows, snap_measures, ev_first = B.load_dir, B.load_tar, B.windows, B.snap_measures, B.ev_first
DRIVER_SHA256 = "6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa"
DRIVER_VERSION = "cua-driver 0.32.0"
DRIVER_NAME = "cua-driver-b07-231f6e8bb"
TELEMETRY_OFF = "false"
DISPATCH_MARK = {"browser_click": "click.cdp_send", "browser_type": "type.insert_send"}
POLL_ENV = "CUA_LANE_EXP_ROUTINE_POLL_MS"
PC_ENV = "CUA_LANE_EXP_PC_SLEEP_MS"
# arm -> (config, lane_env, verify-poll interval in s or None for the step loop)
ARM_SPEC: dict[str, tuple[str, dict[str, str | None], float | None]] = {
    "BASE": ("DEFAULT", {POLL_ENV: None, PC_ENV: None}, None),
    "P10a": ("COMP", {POLL_ENV: None, PC_ENV: None}, 0.010),
    "P10b": ("COMP", {POLL_ENV: None, PC_ENV: None}, 0.010),
    "P1": ("COMP", {POLL_ENV: "1", PC_ENV: None}, 0.001),
    "P0": ("COMP", {POLL_ENV: "0", PC_ENV: None}, 0.0),
    "PC": ("COMP", {POLL_ENV: None, PC_ENV: "15"}, 0.010),
    "SMOKE": ("DEFAULT", {POLL_ENV: None, PC_ENV: None}, None),
}


def completion_ts(journal: list[dict[str, Any]]) -> list[int]:
    return [e["t_mono_ns"] for e in journal if e["event"] == "submit"]


def action_calls(t: dict[str, Any]) -> list[dict[str, Any]]:
    """Every action call (browser_type / browser_click) in order, with the candidate routed just before it."""
    out: list[dict[str, Any]] = []
    sends: dict[str, dict[str, Any]] = {}
    last_routed: dict[str, Any] | None = None
    k = -1
    for e in t["events"]:
        if e["event"] == "routed":
            k += 1
            last_routed = {**e, "k": k}
        elif e["event"] == "call_send" and e.get("tool") in DISPATCH_MARK:
            sends[e["label"]] = {"label": e["label"], "tool": e["tool"], "t0": e["t_mono_ns"],
                                 "candidate": (last_routed or {}).get("candidate"),
                                 "decision_route": (last_routed or {}).get("route"),
                                 "routed_index": (last_routed or {}).get("k")}
            last_routed = None
        elif e["event"] == "call_return" and e.get("label") in sends:
            c = sends.pop(e["label"])
            c.update({"t1": e["t_mono_ns"], "ok": e.get("ok"), "route": e.get("route"), "effect": e.get("effect"),
                      "status": e.get("status"), "refused": bool(e.get("refused")), "code": e.get("code"),
                      "error": e.get("error")})
            out.append(c)
    for c in sends.values():  # sent, never returned (cut trial): effect unknown
        c.update({"t1": None, "ok": None, "refused": False})
        out.append(c)
    return out


def e4_counts(t: dict[str, Any], r: dict[str, Any]) -> dict[str, int]:
    s = t["summary"]
    acts = action_calls(t)
    accepted = [a for a in acts if a.get("ok")]
    ambiguous = sum(1 for a in acts if a.get("ok") is None or (a.get("ok") is False and not a.get("refused")))
    if s.get("outcome") not in ("verified", "refuted", "abstained") and accepted:
        ambiguous += 1  # a dispatch landed or may have landed and the trial ended unreconciled
    keys = [(a["tool"], a.get("candidate")) if a.get("candidate") is not None else (a["tool"], "routine") for a in accepted]
    blind = sum(keys.count(k) - 1 for k in set(keys))
    return {"stale_dispatch": int(bool(r.get("stale_dispatch"))), "ambiguous_dispatch": ambiguous,
            "duplicate_mutation": int(bool(r.get("duplicate_mutation"))),
            "unverified_success": int(bool(r.get("unverified_success"))), "blind_replay": blind,
            "refusal_returned_as_success": int(bool(r.get("refusal_as_success"))),
            "non_loopback_connect": int(r.get("non_loopback") or 0)}


def routes_producers(t: dict[str, Any]) -> list[dict[str, Any]]:
    """Per accepted action: receipt route, Driver dispatch mark in the call window, decision producer
    (``compiled`` for a compiled-replay step, else the step loop's routed route) and the candidate input_route."""
    s, trace = t["summary"], t["trace"]
    out = []
    routes = list(s.get("routes") or [])
    inputs = list(s.get("input_routes") or [])
    for a in action_calls(t):
        if not a.get("ok"):
            continue
        mark = DISPATCH_MARK[a["tool"]]
        seen = any(m["phase"] == mark and a["t0"] <= m["t_mono_ns"] <= (a["t1"] or a["t0"]) for m in trace)
        k = a.get("routed_index")
        if a.get("candidate") is None and routes[:1] == ["compiled"]:
            producer, inp = "compiled", None
        else:
            producer = a.get("decision_route")
            inp = inputs[k] if (k is not None and k < len(inputs)) else None
        out.append({"label": a["label"], "tool": a["tool"], "receipt_route": a.get("route"), "effect": a.get("effect"),
                    "dispatch_mark": mark if seen else None, "producer": producer, "input_route": inp})
    return out


def _pairs(events: list[dict[str, Any]], a: str, b: str, lo: int, hi: int) -> list[tuple[int, int]]:
    out, start = [], None
    for e in events:
        if e["event"] == a:
            start = e["t_mono_ns"]
        elif e["event"] == b and start is not None:
            if lo <= start <= hi:
                out.append((start, e["t_mono_ns"]))
            start = None
    return out


def poll_accounting(t: dict[str, Any], tail_start: int | None, t1: int | None, comp: list[int]) -> dict[str, Any]:
    ev = t["events"]
    if tail_start is None or t1 is None:
        return {"n_reads": None, "n_sleeps": None, "poll_sleep_ms": None, "effect_latency_ms": None,
                "poll_intervals_ms": []}
    reads = [e for e in ev if e["event"] == "oracle_send" and tail_start <= e["t_mono_ns"] <= t1]
    sleeps = _pairs(ev, "poll_sleep_start", "poll_sleep_end", tail_start, t1) + _pairs(ev, "sleep_start", "sleep_end", tail_start, t1)
    ivals = sorted({round(float(e["interval_ms"]), 6) for e in ev if e["event"] == "poll_sleep_start" and "interval_ms" in e})
    return {"n_reads": len(reads), "n_sleeps": len(sleeps), "poll_sleep_ms": sum(b - a for a, b in sleeps) / 1e6,
            "effect_latency_ms": (comp[0] - tail_start) / 1e6 if len(comp) == 1 else None,
            "poll_intervals_ms": ivals}


def lane_receipts(s: dict[str, Any], arm: str | None, intervals: list[float]) -> bool:
    if arm not in ARM_SPEC:
        return False
    _cfg, lane_env, ival = ARM_SPEC[arm]
    ok = s.get("lane_env") == lane_env and not s.get("driver_env_lane")
    if ival is not None:  # compiled routine: interval read by the routine and stamped on every sleep
        ok = ok and s.get("verify_poll_interval_s") == ival and all(abs(x - ival * 1000.0) < 1e-6 for x in intervals)
    return bool(ok)


def row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    r = B.row(t)
    arm = s.get("b09_arm")
    r.update({"b09_arm": arm, "plan": s.get("probe"), "attempt": s.get("attempt"), "williams_row": s.get("williams_row"),
              "pos_in_round": s.get("pos_in_round"), "config": s.get("arm"), "kind": s.get("kind")})
    pre = s.get("pids_pretask") or {}
    r["driver_pid"] = (pre.get("driver") or {}).get("pid")
    r["driver_starttime"] = (pre.get("driver") or {}).get("starttime")
    r["chrome_pid"] = (pre.get("chrome") or {}).get("pid")
    r["chrome_starttime"] = (pre.get("chrome") or {}).get("starttime")
    r["pids_ok"] = bool((pre.get("driver") or {}).get("alive") and (pre.get("chrome") or {}).get("alive"))
    r["pc_sleep_ms"] = s["pc_sleep_ns"] / 1e6 if s.get("pc_sleep_ns") is not None else None
    w = windows(t)
    r["refusal_as_success"] = any(x.get("ok") and (x.get("effect") == "refused" or x.get("status") == "refused")
                                  for k, x in w.items() if k.startswith("action"))
    ts = ev_first(t, "task_start")
    ts_ns = ts["t_mono_ns"] if ts else None
    comp = completion_ts(s.get("journal") or [])
    acc = [a for a in action_calls(t) if a.get("ok")]
    last_ret = max((a["t1"] for a in acc), default=None)
    # PRIMARY T_runner (R2-10 T): snapshot1 send -> first verified oracle read return
    s1 = w.get("snapshot1")
    ver = next((e for e in t["events"] if e["event"] == "oracle_return" and e.get("outcome") == "verified"), None)
    t1 = ver["t_mono_ns"] if ver else None
    r["T_runner_ms"] = None if (s1 is None or t1 is None) else (t1 - s1["t0"]) / 1e6
    # SECONDARY T_j (B-08)
    r["journal_completion_n"] = len(comp)
    r["T_j_ms"] = (None if (ts_ns is None or len(comp) != 1 or last_ret is None)
                   else (max(comp[0], last_ret) - ts_ns) / 1e6)
    pa = poll_accounting(t, last_ret, t1, comp)
    r.update(pa)
    r["lane_env"] = s.get("lane_env")
    r["verify_poll_interval_s"] = s.get("verify_poll_interval_s")
    r["lane_ok"] = lane_receipts(s, arm, pa["poll_intervals_ms"])
    r["driver_name"] = s.get("driver_name")
    r["driver_version"] = s.get("driver_version")
    r["driver_id_ok"] = (s.get("driver_sha256") == DRIVER_SHA256 and s.get("driver_version") == DRIVER_VERSION
                         and s.get("driver_name") == DRIVER_NAME)
    r["actions"] = routes_producers(t)
    r["caller_variant"] = s.get("caller_variant")
    r["caller_variant_counts"] = s.get("caller_variant_counts")
    r["e4"] = e4_counts(t, r)
    r["valid_b04"] = r["valid"]
    tele_ok = s.get("driver_env_telemetry") == TELEMETRY_OFF
    cfg_ok = arm in ARM_SPEC and s.get("arm") == ARM_SPEC[arm][0]
    b04_core = (s.get("outcome") == "verified" and bool(s.get("oracle_exact_match")) and s.get("poller_first_ok_ns") is not None
                and r["T_oracle_ms"] is not None and not s.get("oracle_reverted_after_ok")
                and s.get("completion_mutations") == 1 and not r["stale_dispatch"] and r["route_ok"] and r["arm_ok"]
                and r["resnap_ok"] and r["non_loopback"] == 0 and tele_ok)
    variant_ok = (r["caller_variant"] == {"prep": "default", "route": "default"}
                  and not (r["caller_variant_counts"] or {}).get("prep_fast")
                  and not (r["caller_variant_counts"] or {}).get("route_fast"))
    r["telemetry_off"] = tele_ok
    r["caller_default_ok"] = variant_ok
    r["config_ok"] = cfg_ok
    r["valid"] = bool(b04_core and cfg_ok and r["T_runner_ms"] is not None and r["T_j_ms"] is not None
                      and r["pids_ok"] and r["driver_id_ok"] and variant_ok and r["lane_ok"]
                      and (arm != "PC" or r["pc_sleep_ms"] is not None) and not r["refusal_as_success"]
                      and not any(r["e4"].values()))
    return r


def nw2_row(t: dict[str, Any]) -> dict[str, Any]:
    """FIX-01 detached-node refusal carry-over (B-02 N-W2): pass = DOM node replaced between snapshot and
    action; the stale action came back effect=refused; 0 completion mutations from it (no detached effect);
    the action re-derived from a fresh snapshot completed the task with exactly one completion mutation."""
    s = t["summary"]
    env = s.get("nw2_stale_envelope") or {}
    r = {"trial": s.get("trial"), "cls": s.get("cls"), "round": s.get("round"), "dom_replace": s.get("dom_replace"),
         "stale_envelope": env, "detached_effects": s.get("nw2_mutations_from_stale_action"),
         "marker_in_fresh_snapshot": s.get("marker_in_fresh_snapshot"), "fresh_candidate": s.get("nw2_fresh_candidate"),
         "outcome": s.get("outcome"), "oracle_exact_match": s.get("oracle_exact_match"),
         "completion_mutations": s.get("completion_mutations"), "driver_name": s.get("driver_name"),
         "driver_sha256": s.get("driver_sha256"), "driver_version": s.get("driver_version"),
         "driver_env_exp": s.get("driver_env_exp"), "driver_env_telemetry": s.get("driver_env_telemetry"),
         "lane_env": s.get("lane_env"), "error": s.get("error"),
         "loadavg_before_1m": float(s["loadavg_before"].split()[0]) if s.get("loadavg_before") else None}
    r["pass"] = bool(s.get("dom_replace") == "replaced" and env.get("effect") == "refused"
                     and s.get("nw2_mutations_from_stale_action") == 0 and s.get("marker_in_fresh_snapshot")
                     and s.get("outcome") == "verified" and s.get("oracle_exact_match") is True
                     and s.get("completion_mutations") == 1 and s.get("driver_sha256") == DRIVER_SHA256
                     and s.get("driver_version") == DRIVER_VERSION and s.get("driver_name") == DRIVER_NAME)
    return r
