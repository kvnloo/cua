"""B-08 per-trial extraction (standard library only). Shared by analyze_b08.py and verify_artifacts.py.
Derived from B-06's b06_rows.py (blob b223954a at 31bc98a95; this file's git history shows every change).

One row per trial = B-04's ``b04_rows.row`` (harness/b04/b04_rows.py, blob-identical: T_oracle, T_land, call
windows, Driver snapshot spans and sub-spans, route receipts, E4 flags) plus the B-06 receipts and the B-08
additions:

- arm (C / Wa / Wb / P2 / SMOKE), plan, block, round, attempt, Williams row and position;
- process identity: Driver pid and Chrome browser pid with their /proc start times, read after the
  warm-up (warm arms) and immediately before the task navigate; ``pids_ok`` = both present and alive,
  and for warm arms identical (pid and start time) at warm-up and at task start;
- warm-up duration (``warmup_start`` -> ``warmup_end``, outside T);
- positive control: the measured CLOCK_MONOTONIC sleep inside T (``pc_sleep_ms``; arm P2, right after
  snapshot1 returns);
- PRIMARY metric ``T_j_ms`` = max(journal completion ts, caller-side return of the last accepted mutation)
  - task_start (return of the task browser_navigate). The fixture server's journal timestamp and the
  runner's stamps are CLOCK_MONOTONIC in one process (time.monotonic_ns), so the resolution is the
  clock's, not the 2 ms sampler's. SECONDARY ``T_oracle_ms`` = B-04's rule on the 2 ms sampler;
  ``agree_2_5`` = |T_j - T_oracle| <= 2.5 ms;
- Driver identity from the trial record (name, sha256, version);
- actual route / producer per accepted action: receipt route, the Driver dispatch mark seen inside the
  call window (click.cdp_send / type.insert_send), the decision producer (compiled / provider /
  guarded-completion) and the candidate input_route;
- E4 counters: stale dispatch, ambiguous dispatch, duplicate mutation, unverified success, blind replay,
  refusal returned as success (and non-loopback connects).

valid = b04 validity with the telemetry receipt read as off ('false', the B-08 Driver environment; B-04 checks
'0') AND T_j defined AND pids_ok AND (P2: the sleep was measured) AND no refusal returned as success AND
E4 counters 0. Smoke trials use the same rule with the DEFAULT configuration receipts (b04 arm_ok).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "harness" / "b04"))
import b04_rows as B  # noqa: E402

load_dir, load_tar, windows, snap_measures, ev_first = B.load_dir, B.load_tar, B.windows, B.snap_measures, B.ev_first
WARM = {"Wa", "Wb", "P2"}
DRIVER_SHA256 = "6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa"
DRIVER_VERSION = "cua-driver 0.32.0"
DRIVER_NAME = "cua-driver-b07-231f6e8bb"
TELEMETRY_OFF = "false"
AGREE_MS = 2.5
DISPATCH_MARK = {"browser_click": "click.cdp_send", "browser_type": "type.insert_send"}


def _same(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    return bool(a and b and a.get("pid") == b.get("pid") and a.get("starttime") == b.get("starttime"))


def _alive(x: dict[str, Any] | None) -> bool:
    return bool(x and x.get("alive") and x.get("pid"))


def completion_ts(cls: str, journal: list[dict[str, Any]]) -> list[int]:
    if cls == "fill":
        return [e["t_mono_ns"] for e in journal if e["event"] == "submit"]
    key = "checked" if cls == "toggle" else "modal"
    return [e["t_mono_ns"] for e in journal if e["event"] == "update" and key in e.get("fields", {})]


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


def row(t: dict[str, Any]) -> dict[str, Any]:
    s = t["summary"]
    r = B.row(t)
    arm = s.get("b08_arm")
    r.update({"b08_arm": arm, "plan": s.get("probe"), "attempt": s.get("attempt"), "williams_row": s.get("williams_row"),
              "pos_in_round": s.get("pos_in_round"), "config": s.get("arm"), "kind": s.get("kind")})
    pre = s.get("pids_pretask") or {}
    wu = s.get("pids_warmup") or {}
    r["driver_pid"] = (pre.get("driver") or {}).get("pid")
    r["driver_starttime"] = (pre.get("driver") or {}).get("starttime")
    r["chrome_pid"] = (pre.get("chrome") or {}).get("pid")
    r["chrome_starttime"] = (pre.get("chrome") or {}).get("starttime")
    r["chrome_exe"] = (pre.get("chrome") or {}).get("exe")
    r["driver_exe"] = (pre.get("driver") or {}).get("exe")
    ok = _alive(pre.get("driver")) and _alive(pre.get("chrome"))
    if arm in WARM:
        same = _same(wu.get("driver"), pre.get("driver")) and _same(wu.get("chrome"), pre.get("chrome"))
        ok = ok and same
        r["pids_same_warmup_task"] = same
    else:
        r["pids_same_warmup_task"] = None
    r["pids_ok"] = ok
    ws, we = ev_first(t, "warmup_start"), ev_first(t, "warmup_end")
    r["warmup_span_ms"] = (we["t_mono_ns"] - ws["t_mono_ns"]) / 1e6 if (ws and we) else (0.0 if arm not in WARM else None)
    r["pc_sleep_ms"] = s["pc_sleep_ns"] / 1e6 if s.get("pc_sleep_ns") is not None else None
    w = windows(t)
    r["refusal_as_success"] = any(x.get("ok") and (x.get("effect") == "refused" or x.get("status") == "refused")
                                  for k, x in w.items() if k.startswith("action"))
    # PRIMARY T_j (journal + caller return, one CLOCK_MONOTONIC)
    ts = ev_first(t, "task_start")
    ts_ns = ts["t_mono_ns"] if ts else None
    comp = completion_ts(s.get("cls"), s.get("journal") or [])
    acc = [a for a in action_calls(t) if a.get("ok")]
    last_ret = max((a["t1"] for a in acc), default=None)
    r["journal_completion_n"] = len(comp)
    r["journal_completion_rel_ms"] = None if (not comp or ts_ns is None) else (comp[0] - ts_ns) / 1e6
    r["T_j_ms"] = (None if (ts_ns is None or len(comp) != 1 or last_ret is None)
                   else (max(comp[0], last_ret) - ts_ns) / 1e6)
    r["T_j_from"] = None if r["T_j_ms"] is None else ("journal" if comp[0] >= last_ret else "caller_return")
    r["agree_abs_ms"] = (None if (r["T_j_ms"] is None or r["T_oracle_ms"] is None)
                         else abs(r["T_j_ms"] - r["T_oracle_ms"]))
    r["agree_2_5"] = None if r["agree_abs_ms"] is None else r["agree_abs_ms"] <= AGREE_MS
    # Driver identity in the trial record
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
    # b04 validity with the telemetry receipt read as 'false' (B-04 checks '0'; same switch, see module doc)
    b04_core = (s.get("outcome") == "verified" and bool(s.get("oracle_exact_match")) and s.get("poller_first_ok_ns") is not None
                and r["T_oracle_ms"] is not None and not s.get("oracle_reverted_after_ok")
                and s.get("completion_mutations") == 1 and not r["stale_dispatch"] and r["route_ok"] and r["arm_ok"]
                and r["resnap_ok"] and r["non_loopback"] == 0 and tele_ok)
    variant_ok = (r["caller_variant"] == {"prep": "default", "route": "default"}
                  and not (r["caller_variant_counts"] or {}).get("prep_fast")
                  and not (r["caller_variant_counts"] or {}).get("route_fast"))
    r["telemetry_off"] = tele_ok
    r["caller_default_ok"] = variant_ok
    r["valid"] = bool(b04_core and r["T_j_ms"] is not None and ok and r["driver_id_ok"] and variant_ok
                      and (arm != "P2" or r["pc_sleep_ms"] is not None) and not r["refusal_as_success"]
                      and not any(r["e4"].values()))
    r["arm_receipts_ok"] = r["arm_ok"]
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
         "completion_mutations": s.get("completion_mutations"), "driver_sha256": s.get("driver_sha256"),
         "driver_version": s.get("driver_version"), "driver_env_exp": s.get("driver_env_exp"),
         "driver_env_telemetry": s.get("driver_env_telemetry"), "error": s.get("error"),
         "loadavg_before_1m": float(s["loadavg_before"].split()[0]) if s.get("loadavg_before") else None}
    r["pass"] = bool(s.get("dom_replace") == "replaced" and env.get("effect") == "refused"
                     and s.get("nw2_mutations_from_stale_action") == 0 and s.get("marker_in_fresh_snapshot")
                     and s.get("outcome") == "verified" and s.get("oracle_exact_match") is True
                     and s.get("completion_mutations") == 1 and s.get("driver_sha256") == DRIVER_SHA256
                     and s.get("driver_version") == DRIVER_VERSION)
    return r
