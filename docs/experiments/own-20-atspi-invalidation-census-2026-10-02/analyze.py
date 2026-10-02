#!/usr/bin/env python3
"""OWN-20 analysis: join listener events to mutation windows, decide relevant deltas from the fresh
observation (+ fixture state file), and classify each scope with the PRE-REGISTERED rule.

usage: analyze.py <raw-dir> <out-dir>      (pure stdlib; reads raw/<block>/*.jsonl[.gz])

Everything reported is recomputed from raw/ here; verify_artifacts.py re-imports this module and
compares against the committed summaries.
"""

from __future__ import annotations

import gzip
import json
import statistics
import sys
from pathlib import Path
from typing import Any

QUIESCE_NS = 1000 * 1_000_000
EV = "org.a11y.atspi.Event."
ROOT = "/org/a11y/atspi/accessible/root"

# mutation_id -> (scope, variant, delta rule)
ROWS: dict[str, tuple[str, str, str]] = {
    "text_v1": ("text", "v1_fixture", "text"),
    "text_v2": ("text", "v2_driver", "text"),
    "focus_v1": ("focus", "v1_fixture", "focus"),
    "focus_v2": ("focus", "v2_driver", "focus"),
    "selection_v1": ("selection", "v1_fixture", "selection"),
    "selection_v2": ("selection", "v2_driver", "selection"),
    "checkbox_v1": ("checkbox", "v1_fixture", "checkbox"),
    "checkbox_v2": ("checkbox", "v2_driver", "checkbox"),
    "child_add_pts": ("child_add", "v1_fixture", "children"),
    "child_add_stp": ("child_add", "v1_fixture", "children"),
    "child_remove_pts": ("child_remove", "v1_fixture", "children"),
    "child_remove_stp": ("child_remove", "v1_fixture", "children"),
    "recreate": ("node_recreate", "v1_fixture", "recreate"),
    "window_create": ("window", "v1_fixture", "window"),
    "window_destroy": ("window", "v1_fixture", "window"),
    "exit_v1": ("process_lifecycle", "v1_harness_sigterm", "exit"),
    "exit_v2": ("process_lifecycle", "v2_driver", "exit"),
    "process_start": ("process_lifecycle", "harness_spawn", "start"),
    "post_restart_probe": ("restart_pipeline", "v1_fixture", "checkbox"),
    "registry_restart": ("registry_restart", "harness_registry", "none_expected"),
    "post_registry_probe": ("registry_restart", "v1_fixture", "checkbox"),
    "noop": ("control_noop", "v1_fixture", "none_expected"),
    "decoy": ("control_decoy", "decoy_fixture", "none_expected"),
    "listener_cycle": ("listener_subscription", "v1_fixture", "checkbox"),
}

# Scope classification inputs (PREREG.json "classification").
IN_APP_INHERITED = ["recreate", "exit_v1", "exit_v2", "process_start", "post_restart_probe", "post_registry_probe"]
SCOPES: dict[str, dict[str, Any]] = {
    "text": {"own": ["text_v1", "text_v2"], "inherited": IN_APP_INHERITED},
    "focus": {"own": ["focus_v1", "focus_v2"], "inherited": IN_APP_INHERITED},
    "selection": {"own": ["selection_v1", "selection_v2"], "inherited": IN_APP_INHERITED},
    "checkbox": {"own": ["checkbox_v1", "checkbox_v2"], "inherited": IN_APP_INHERITED},
    "child_add": {"own": ["child_add_pts", "child_add_stp"], "inherited": IN_APP_INHERITED},
    "child_remove": {"own": ["child_remove_pts", "child_remove_stp"], "inherited": IN_APP_INHERITED},
    "node_recreate": {"own": ["recreate"], "inherited": [r for r in IN_APP_INHERITED if r != "recreate"]},
    "window": {"own": ["window_create", "window_destroy"], "inherited": IN_APP_INHERITED},
    "process_lifecycle": {"own": ["exit_v1", "exit_v2", "process_start"], "inherited": []},
    "restart_pipeline": {"own": ["post_restart_probe"], "inherited": []},
    "registry_restart": {"own": ["post_registry_probe"], "inherited": []},
    "listener_subscription": {"own": ["listener_cycle"], "inherited": [], "listener": "fresh"},
}
MIN_REPS_PER_ROW = 20
# AMENDMENT-1: only round-0 blocks (schedule seq 1-18, one block of every type) ran under the EXCLUSIVE
# quiet-lane lock; every reported timing comes from them. Counts and classification use all blocks.
TIMING_MAX_SEQ = 18


def is_timing_block(block_id: str) -> bool:
    return int(block_id[1:3]) <= TIMING_MAX_SEQ
UNUSABLE_FN1_RATE = 0.25


def l2_match(mid: str, ev: dict[str, Any], names: dict[str, Any]) -> bool:
    """Scope-typed (L2) invalidator: an event whose type names this scope's change."""
    iface, member, detail = ev.get("interface") or "", ev.get("member"), ev.get("detail")
    sender = ev.get("sender")
    rule = ROWS[mid][2]
    tgt = names["target_all"]
    if rule in ("exit", "start"):
        name = names["old_target"] if rule == "exit" else names["new_target"]
        if not name:
            return False
        if iface == "org.freedesktop.DBus" and member == "NameOwnerChanged":
            p = ev.get("payload") or []
            if len(p) == 3 and p[0] == name:
                return (p[2] == "") if rule == "exit" else (p[1] == "")
        if iface == EV + "Object" and member == "ChildrenChanged" and ev.get("path") == ROOT \
                and sender in names["registry"]:
            data = ev.get("any_data") or []
            return detail == ("remove" if rule == "exit" else "add") and bool(data) and data[0] == name
        return False
    if sender not in tgt or not iface.startswith(EV):
        return False
    obj = iface == EV + "Object"
    if rule == "text":
        return obj and (member == "TextChanged" or (member == "PropertyChange" and detail == "accessible-value"))
    if rule == "focus":
        return (obj and member == "StateChanged" and detail == "focused") or iface == EV + "Focus"
    if rule == "selection":
        return obj and (member in ("SelectionChanged", "ActiveDescendantChanged")
                        or (member == "StateChanged" and detail == "selected"))
    if rule == "checkbox":
        return obj and member == "StateChanged" and detail == "checked"
    if rule == "children":
        if mid.startswith("child_add"):
            return obj and member == "ChildrenChanged" and detail == "add"
        return obj and ((member == "ChildrenChanged" and detail == "remove")
                        or (member == "StateChanged" and detail == "defunct" and ev.get("detail1") == 1))
    if rule == "recreate":  # removal of the old node is what invalidates the known node
        return obj and ((member == "ChildrenChanged" and detail == "remove")
                        or (member == "StateChanged" and detail == "defunct" and ev.get("detail1") == 1))
    if rule == "window":
        if mid == "window_create":
            return iface == EV + "Window" and member == "Create" or \
                (obj and member == "ChildrenChanged" and detail == "add" and ev.get("path") == ROOT)
        return iface == EV + "Window" and member == "Destroy" or \
            (obj and member == "ChildrenChanged" and detail == "remove" and ev.get("path") == ROOT)
    return False


def opener(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else open(path, encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() and Path(str(path) + ".gz").exists():
        path = Path(str(path) + ".gz")
    if not path.exists():
        return []
    with opener(path) as stream:
        return [json.loads(x) for x in stream if x.strip()]


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(-(-q * len(s) // 1)) - 1))  # nearest-rank
    return s[k]


def stats(values: list[float]) -> dict[str, Any]:
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0}
    return {"n": len(v), "median": round(statistics.median(v), 3), "p95": round(pct(v, 0.95), 3),
            "min": round(min(v), 3), "max": round(max(v), 3)}


def oracle_value(rule: str, state: dict[str, Any] | None) -> Any:
    st = state or {}
    ctl = st.get("control") or {}
    return {
        "text": ctl.get("note_text"), "focus": ctl.get("focus"), "selection": ctl.get("selection"),
        "checkbox": st.get("agreed"), "children": ctl.get("dynamic"), "recreate": ctl.get("recreatable_generation"),
        "window": ctl.get("aux_window"), "none_expected": st.get("seq"),
    }.get(rule)


OBS_DIGEST = {"text": "text", "selection": "selection", "checkbox": "checkbox", "children": "children",
              "recreate": "recreate", "window": "windows_of_target", "none_expected": "full"}


def decide_delta(mid: str, rec: dict[str, Any]) -> dict[str, Any]:
    rule = ROWS[mid][2]
    b, a = rec.get("before") or {}, rec.get("after") or {}
    out: dict[str, Any] = {"rule": rule}
    if rule == "exit":
        before_ok = not b.get("gws", {}).get("is_error") and (b.get("element_count") or 0) > 0
        after_gone = bool(a.get("gws", {}).get("is_error")) or (a.get("element_count") or 0) == 0
        out["obs_delta"] = before_ok and after_gone \
            and b.get("digests", {}).get("task_windows") != a.get("digests", {}).get("task_windows")
        out["oracle_delta"] = (rec.get("mutation") or {}).get("exit_rc") is not None
        out["obs_fields"] = {"before_elements": b.get("element_count"), "after_error": a.get("error_text"),
                             "before_windows": b.get("windows"), "after_windows": a.get("windows")}
    elif rule == "start":
        mut = rec.get("mutation") or {}
        out["obs_delta"] = b.get("digests", {}).get("task_windows") != a.get("digests", {}).get("task_windows") \
            and (a.get("element_count") or 0) > 0
        out["oracle_delta"] = bool(mut.get("start", {}).get("m_published")) and rec.get("pid_after") != rec.get("pid_before")
        out["obs_fields"] = {"before_windows": b.get("windows"), "after_windows": a.get("windows"),
                             "after_elements": a.get("element_count")}
    else:
        key = OBS_DIGEST.get(rule)
        if key is None:  # focus: get_window_state exposes no focus field on Linux
            out["obs_delta"] = None
        else:
            out["obs_delta"] = b.get("digests", {}).get(key) != a.get("digests", {}).get(key)
        ob, oa = oracle_value(rule, b.get("state")), oracle_value(rule, a.get("state"))
        out["oracle_delta"] = ob != oa
        fkey = {"window": None, "none_expected": None}.get(rule, rule)
        out["obs_fields"] = {"before": (b.get("fields") or {}).get(fkey) if fkey else b.get("windows"),
                             "after": (a.get("fields") or {}).get(fkey) if fkey else a.get("windows")}
        out["oracle_fields"] = {"before": ob, "after": oa}
        out["before_digest"] = b.get("digests", {}).get(key) if key else None
        out["after_digest"] = a.get("digests", {}).get(key) if key else None
    if rule == "none_expected":
        out["relevant_delta"] = bool(out["obs_delta"]) or bool(out["oracle_delta"])
    else:
        out["relevant_delta"] = bool(out["obs_delta"]) or bool(out["oracle_delta"])
    out["obs_oracle_agree"] = None if out["obs_delta"] is None else (out["obs_delta"] == out["oracle_delta"])
    return out


def analyze_block(bdir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    recs = load_jsonl(bdir / "mutations.jsonl")
    events = load_jsonl(bdir / "events.jsonl")
    meta: dict[str, Any] = {"block_id": bdir.name}
    env = {}
    if (bdir / "session-env.txt").exists():
        for line in (bdir / "session-env.txt").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    meta["session_env"] = env
    start = next((r for r in recs if r.get("event") == "block_start"), {})
    meta.update(block_type=start.get("block_type"), display=start.get("display"), loadavg_start=start.get("loadavg"))
    lr = next((r for r in recs if r.get("event") == "listener_ready"), None)
    ls = next((r for r in recs if r.get("event") == "listener_stop"), None)
    meta["listener"] = {
        "subscription_ms": (lr or {}).get("ready", {}).get("subscription_ms"),
        "spawn_to_ready_ms": (lr or {}).get("spawn_to_ready_ms"),
        "register_errors": (lr or {}).get("ready", {}).get("register_errors"),
        "cleanup_ms": ((ls or {}).get("cleanup") or {}).get("cleanup_ms"),
        "stop_to_exit_ms": (ls or {}).get("stop_to_exit_ms"),
    }
    pid_of: dict[str, Any] = {}
    for e in events:
        if e.get("event") == "name_pid" and e.get("pid") is not None:
            pid_of[e["name"]] = e["pid"]
    signals = [e for e in events if e.get("event") == "signal"]
    # Registry bus names: owner(s) of org.a11y.atspi.Registry over the block, plus Registry-interface senders.
    registry = {e["sender"] for e in signals if (e.get("interface") or "") == "org.a11y.atspi.Registry"}
    for e in signals:
        p = e.get("payload") or []
        if e.get("member") == "NameOwnerChanged" and len(p) == 3 and p[0] == "org.a11y.atspi.Registry" and p[2]:
            registry.add(p[2])
    fx = [r for r in recs if r.get("event") == "fixture_start"]
    target_pids = {r["pid"] for r in fx if r.get("role") == "target"}
    decoy_pids = {r["pid"] for r in fx if r.get("role") == "decoy"}
    muts = [r for r in recs if r.get("event") == "mutation"]
    for r in muts:
        target_pids |= {r.get("pid_before"), r.get("pid_after")} - {None}
    names_by_pid: dict[Any, set[str]] = {}
    for n, p in pid_of.items():
        names_by_pid.setdefault(p, set()).add(n)
    target_all = set().union(*[names_by_pid.get(p, set()) for p in target_pids]) if target_pids else set()
    decoy_names = set().union(*[names_by_pid.get(p, set()) for p in decoy_pids]) if decoy_pids else set()
    meta["identity"] = {"target_names": sorted(target_all), "decoy_names": sorted(decoy_names),
                        "registry_names": sorted(registry), "unresolved_senders": sorted(
                            {e["sender"] for e in signals if e["sender"].startswith(":") and e["sender"] not in pid_of})}
    rows = []
    for r in muts:
        mid = r["mutation_id"]
        scope, variant, rule = ROWS[mid]
        row: dict[str, Any] = {"block_id": r["block_id"], "mutation_id": mid, "scope": scope, "variant": variant,
                               "rep": r["rep"], "index": r["index"], "loadavg": r.get("loadavg"),
                               "display": meta["display"]}
        if "failure" in r:
            row["failure"] = r["failure"]
        mut = r.get("mutation") or {}
        row["producer"] = mut.get("producer")
        if "m_mut_start" not in r or "m_mut_end" not in r:
            row["failure"] = row.get("failure") or "no mutation window"
            rows.append(row)
            continue
        ack = ((mut.get("control") or {}).get("ack")) or {}
        m_ref = ack.get("m_start") or (mut.get("m_start")) or (mut.get("call") or {}).get("m0") or r["m_mut_start"]
        lo, hi = r["m_mut_start"], r["m_mut_end"] + QUIESCE_NS
        row["m_ref_kind"] = "fixture_ack_m_start" if ack.get("m_start") else (
            "harness_m_start" if mut.get("m_start") else ("driver_call_m0" if mut.get("call") else "harness_mut_start"))
        row["mutation_ms"] = (r["m_mut_end"] - r["m_mut_start"]) / 1e6
        if ack:
            row["fixture_op_ms"] = (ack["m_end"] - ack["m_start"]) / 1e6
            row["fixture_error"] = ack.get("error")
        if mut.get("call"):
            row["driver_call"] = {k: mut["call"].get(k) for k in ("tool", "ms", "is_error", "exception")}
            row["driver_structured"] = mut.get("structured")
        old_names = names_by_pid.get(r.get("pid_before"), set())
        new_names = names_by_pid.get(r.get("pid_after"), set())
        names = {"target_all": target_all, "registry": registry,
                 "old_target": next(iter(sorted(old_names)), None), "new_target": next(iter(sorted(new_names)), None)}
        src = signals
        if scope == "listener_subscription":
            fresh = load_jsonl(bdir / f"fresh-{r['rep']:02d}.jsonl")
            src = [e for e in fresh if e.get("event") == "signal"]
            fready = next((e for e in fresh if e.get("event") == "ready"), {})
            fclean = next((e for e in fresh if e.get("event") == "cleanup"), {})
            hv = mut.get("fresh_listener") or {}
            stop = r.get("fresh_listener_stop") or {}
            row["fresh_listener"] = {"subscription_ms": fready.get("subscription_ms"),
                                     "spawn_to_ready_ms": hv.get("spawn_to_ready_ms"),
                                     "ready_to_mutation_ms": ((ack.get("m_start") or r["m_mut_start"]) - fready.get("m_ns", 0)) / 1e6 if fready else None,
                                     "cleanup_ms": fclean.get("cleanup_ms"), "stop_to_exit_ms": stop.get("stop_to_exit_ms")}
            # the retained listener is the reference for the same mutation
            ref_l2 = [e for e in signals if lo <= e["m_ns"] <= hi and l2_match(mid, e, names)]
            row["retained_listener_l2"] = bool(ref_l2)
        win = [e for e in src if lo <= e["m_ns"] <= hi]
        row["events"] = [{"t_ms": round((e["m_ns"] - m_ref) / 1e6, 3), "sender_role": _role(e, target_all, decoy_names, registry),
                          "sender": e["sender"], "path": e.get("path"), "iface": (e.get("interface") or "").replace(EV, "Event."),
                          "member": e.get("member"), "detail": e.get("detail"), "detail1": e.get("detail1"),
                          "l2": l2_match(mid, e, names)} for e in win]
        at_spi = [e for e in win if (e.get("interface") or "").startswith(EV)]
        tgt_ev = [e for e in at_spi if e["sender"] in target_all]
        l2 = [e for e in win if l2_match(mid, e, names)]
        if rule in ("exit", "start"):
            l1 = l2 + [e for e in tgt_ev if e not in l2]
        else:
            l1 = tgt_ev
        row["l1_present"], row["l2_present"] = bool(l1), bool(l2)
        row["l2_types"] = sorted({f'{(e.get("interface") or "").split(".")[-1]}:{e.get("member")}:{e.get("detail") or ""}' for e in l2})
        if rule == "exit":
            row["l2_atspi_registry"] = any(e.get("member") == "ChildrenChanged" for e in l2)
            row["l2_bus_nameowner"] = any(e.get("member") == "NameOwnerChanged" for e in l2)
        if rule == "start":
            row["l2_atspi_registry"] = any(e.get("member") == "ChildrenChanged" for e in l2)
            row["l2_bus_nameowner"] = any(e.get("member") == "NameOwnerChanged" for e in l2)
        if mid == "recreate":
            row["add_named"] = any(e.get("member") == "ChildrenChanged" and e.get("detail") == "add"
                                   and e["sender"] in target_all for e in win)
        row["first_l2_ms"] = round((min(e["m_ns"] for e in l2) - m_ref) / 1e6, 3) if l2 else None
        row["first_l1_ms"] = round((min(e["m_ns"] for e in l1) - m_ref) / 1e6, 3) if l1 else None
        row["last_target_event_ms"] = round((max(e["m_ns"] for e in tgt_ev) - m_ref) / 1e6, 3) if tgt_ev else None
        if mut.get("call"):
            row["first_l2_after_return_ms"] = round((min(e["m_ns"] for e in l2) - mut["call"]["m1"]) / 1e6, 3) if l2 else None
        row["target_event_count"] = len(tgt_ev)
        row["spurious_target_events"] = sum(1 for e in tgt_ev if not l2_match(mid, e, names))
        row["foreign_atspi_events"] = sum(1 for e in at_spi if e["sender"] not in target_all)
        row["decoy_events"] = sum(1 for e in at_spi if e["sender"] in decoy_names)
        row["lifecycle_signals"] = sum(1 for e in win if e.get("member") == "NameOwnerChanged"
                                       or (e.get("interface") or "") == "org.a11y.atspi.Registry"
                                       or e.get("member") == "Available")
        if "failure" not in row:
            row.update(decide_delta(mid, r))
            d = row["relevant_delta"]
            row["false_negative_l2"] = bool(d and not row["l2_present"])
            row["false_negative_l1"] = bool(d and not row["l1_present"])
            row["false_positive_target"] = bool((not d) and row["l1_present"])
            row["false_positive_any_atspi"] = bool((not d) and at_spi)
        rows.append(row)
    return rows, meta


def _role(e, target, decoy, registry):
    s = e["sender"]
    if s in target:
        return "target"
    if s in decoy:
        return "decoy"
    if s in registry:
        return "registry"
    if s == "org.freedesktop.DBus":
        return "bus"
    return "other"


def summarize(rows: list[dict[str, Any]], metas: list[dict[str, Any]]) -> dict[str, Any]:
    by_mid: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_mid.setdefault(r["mutation_id"], []).append(r)
    per_row = {}
    for mid, rs in sorted(by_mid.items()):
        ok = [r for r in rs if "failure" not in r]
        delta = [r for r in ok if r["relevant_delta"]]
        nod = [r for r in ok if not r["relevant_delta"]]
        tok = [r for r in ok if is_timing_block(r["block_id"])]
        tdelta = [r for r in tok if r["relevant_delta"]]
        per_row[mid] = {
            "scope": ROWS[mid][0], "variant": ROWS[mid][1], "attempted": len(rs), "timing_reps": len(tok), "failures": len(rs) - len(ok),
            "failure_texts": sorted({r["failure"] for r in rs if "failure" in r}),
            "relevant_delta": len(delta), "no_delta": len(nod),
            "obs_delta": sum(1 for r in ok if r.get("obs_delta")), "oracle_delta": sum(1 for r in ok if r.get("oracle_delta")),
            "obs_unobservable": sum(1 for r in ok if r.get("obs_delta") is None),
            "obs_oracle_disagree": sum(1 for r in ok if r.get("obs_oracle_agree") is False),
            "l2_present_in_delta": sum(1 for r in delta if r["l2_present"]),
            "l1_present_in_delta": sum(1 for r in delta if r["l1_present"]),
            "false_negative_l2": sum(1 for r in delta if r["false_negative_l2"]),
            "false_negative_l1": sum(1 for r in delta if r["false_negative_l1"]),
            "false_positive_target": sum(1 for r in nod if r["false_positive_target"]),
            "false_positive_any_atspi": sum(1 for r in nod if r["false_positive_any_atspi"]),
            "l2_types_seen": sorted({t for r in delta for t in r["l2_types"]}),
            "first_l2_ms": stats([r["first_l2_ms"] for r in tdelta]),
            "first_l1_ms": stats([r["first_l1_ms"] for r in tdelta]),
            "last_target_event_ms": stats([r["last_target_event_ms"] for r in tok]),
            "first_l2_after_return_ms": stats([r.get("first_l2_after_return_ms") for r in tdelta]),
            "spurious_target_events_median": statistics.median([r["spurious_target_events"] for r in ok]) if ok else None,
            "foreign_atspi_events_total": sum(r["foreign_atspi_events"] for r in ok),
            "decoy_events_total": sum(r["decoy_events"] for r in ok),
            "lifecycle_signals_total": sum(r["lifecycle_signals"] for r in ok),
            "fixture_op_ms": stats([r.get("fixture_op_ms") for r in tok]),
            "mutation_ms": stats([r.get("mutation_ms") for r in tok]),
            "driver_call_ms": stats([(r.get("driver_call") or {}).get("ms") for r in tok]),
            "driver_effects": sorted({json.dumps(r.get("driver_structured"), sort_keys=True) for r in ok if r.get("driver_structured")}),
        }
        if mid in ("exit_v1", "exit_v2", "process_start"):
            per_row[mid]["l2_atspi_registry_in_delta"] = sum(1 for r in delta if r.get("l2_atspi_registry"))
            per_row[mid]["l2_bus_nameowner_in_delta"] = sum(1 for r in delta if r.get("l2_bus_nameowner"))
        if mid == "recreate":
            per_row[mid]["add_named_in_delta"] = sum(1 for r in delta if r.get("add_named"))
            per_row[mid]["obs_label_level_unchanged"] = sum(1 for r in ok if r.get("obs_delta") is False)
        if mid == "listener_cycle":
            per_row[mid]["retained_listener_l2_in_delta"] = sum(1 for r in delta if r.get("retained_listener_l2"))
            for k in ("subscription_ms", "spawn_to_ready_ms", "ready_to_mutation_ms", "cleanup_ms", "stop_to_exit_ms"):
                per_row[mid]["fresh_" + k] = stats([(r.get("fresh_listener") or {}).get(k) for r in tok])
    classes = {}
    for scope, spec in SCOPES.items():
        own = [r for mid in spec["own"] for r in by_mid.get(mid, []) if "failure" not in r and r["relevant_delta"]]
        n = len(own)
        fn2 = sum(1 for r in own if r["false_negative_l2"])
        fn1 = sum(1 for r in own if r["false_negative_l1"])
        inh = {mid: per_row.get(mid, {}).get("false_negative_l2", 0) for mid in spec["inherited"]}
        inh_n = {mid: per_row.get(mid, {}).get("relevant_delta", 0) for mid in spec["inherited"]}
        inh_fn = sum(inh.values())
        own_n = {mid: per_row.get(mid, {}).get("relevant_delta", 0) for mid in spec["own"]}
        underpowered = any(v < MIN_REPS_PER_ROW for v in own_n.values()) or any(v < MIN_REPS_PER_ROW for v in inh_n.values())
        if n == 0:
            verdict = "NO_DELTA_OBSERVED"
        elif fn2 == 0 and inh_fn == 0:
            verdict = "SAFE_INVALIDATOR" + ("_UNDERPOWERED" if underpowered else "")
        elif fn1 / n < UNUSABLE_FN1_RATE:
            verdict = "NOISY_HINT"
        else:
            verdict = "UNUSABLE_ALWAYS_OBSERVE"
        any_fn = fn2 + inh_fn > 0
        classes[scope] = {
            "verdict": verdict, "own_rows": own_n, "own_delta_reps": n, "own_fn_l2": fn2, "own_fn_l1": fn1,
            "inherited_fn_l2": inh, "inherited_delta_reps": inh_n, "underpowered": underpowered,
            "event_absence_authorizes_reuse": False,
            "recommendation": "always observe (a relevant false negative exists)" if any_fn else
                              "always observe; events may wake a re-observation (finite zero is not a universal guarantee; skipping is out of scope)",
            "listener": spec.get("listener", "retained"),
        }
    blocks = {m["block_id"]: m for m in metas}
    sub = [m["listener"]["subscription_ms"] for m in metas]
    return {
        "per_row": per_row, "classification": classes,
        "listener_timing_retained": {k: stats([m["listener"][k] for m in metas if is_timing_block(m["block_id"])]) for k in
                                     ("subscription_ms", "spawn_to_ready_ms", "cleanup_ms", "stop_to_exit_ms")},
        "listener_register_errors": sum(len(m["listener"]["register_errors"] or []) for m in metas),
        "blocks": len(metas), "mutations_attempted": len(rows),
        "mutations_failed": sum(1 for r in rows if "failure" in r),
        "displays": sorted({str(m.get("display")) for m in metas}),
        "driver_versions": sorted({m["session_env"].get("driver_version", "") for m in metas}),
        "driver_sha256": sorted({m["session_env"].get("driver_sha256", "") for m in metas}),
        "unresolved_senders_total": sum(len(m["identity"]["unresolved_senders"]) for m in metas),
        "block_identity": {b: m["identity"] for b, m in sorted(blocks.items())},
        "subscription_samples": len([s for s in sub if s is not None]),
    }


def run(raw: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, metas = [], []
    for bdir in sorted(p for p in raw.iterdir() if p.is_dir()):
        r, m = analyze_block(bdir)
        rows.extend(r)
        metas.append(m)
    return rows, summarize(rows, metas)


def main() -> int:
    raw, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rows, summary = run(raw)
    with gzip.open(out / "own-20-rows.jsonl.gz", "wt", encoding="utf-8") as stream:
        for r in rows:
            stream.write(json.dumps(r, sort_keys=True) + "\n")
    (out / "own-20-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({s: c["verdict"] for s, c in summary["classification"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
