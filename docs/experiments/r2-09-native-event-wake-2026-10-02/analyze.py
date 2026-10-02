#!/usr/bin/env python3
"""R2-09 analysis (pre-registered metrics; stdlib only).

usage: analyze.py <raw-dir> <summary.json> <trial-metrics.jsonl>

Reads every raw/<label>/trials.jsonl(.gz), keeps every trial (the latest
attempt of a planned cell decides it; superseded attempts stay listed), and
writes per-trial metrics plus the summary tables:

* per family / task / arm: n, valid route, oracle verified, effect visible at
  return, median and p95 of T, T_land, T_return, the post-DoAction wait span,
  effect-after-DoAction-reply, effect-after-return; EW wake reasons and event
  latency (wake vs the page's own journal arrival of the effect);
* paired within-round differences vs the family's B arm, T_B - T_X, median
  with a 10000-resample percentile bootstrap over rounds (seed 909), and
  S = median T_B / median T_X;
* controls a-d with the independent listener's acted-object / foreign events.
"""

from __future__ import annotations

import gzip
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

FAMILY_BASE = {"M": "B", "F": "B_F0", "G": "B"}
ARM_ENV = {
    "B": {}, "S0": {"CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS": "0"},
    "EW": {"CUA_DRIVER_EXP_NATIVE_POST_ACTION_WAKE": "event"},
    "B_F0": {"CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS": "0"},
    "S0_F0": {"CUA_DRIVER_EXP_NATIVE_POST_ACTION_SLEEP_MS": "0", "CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS": "0"},
    "EW_F0": {"CUA_DRIVER_EXP_NATIVE_POST_ACTION_WAKE": "event", "CUA_DRIVER_EXP_FOCUS_GUARD_SETTLE_MS": "0"},
}
ARM_KNOBS = {
    "B": set(), "S0": {"post_action_sleep_ms=0"}, "EW": {"post_action_wake=event"},
    "B_F0": {"focus_guard_settle_ms=0"}, "S0_F0": {"post_action_sleep_ms=0", "focus_guard_settle_ms=0"},
    "EW_F0": {"post_action_wake=event", "focus_guard_settle_ms=0"},
}
WAKE_MEMBERS = {"StateChanged", "TextChanged", "PropertyChange"}
SEED = 909
RESAMPLES = 10000


def open_lines(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(-(-q * len(s) // 1)) - 1))  # nearest rank
    return s[k]


def med(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def r2(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def matches(state: Any, exp: dict[str, Any], schema: str | None) -> bool:
    return isinstance(state, dict) and (schema is None or state.get("schema") == schema) \
        and all(state.get(k) == v for k, v in exp.items())


def mark(marks: list[dict], scope: str, prefix: str, after_wall: int | None = None) -> dict | None:
    for m in marks:
        if m.get("scope") == scope and str(m.get("mark", "")).startswith(prefix):
            if after_wall is None or m["wall_ns"] >= after_wall:
                return m
    return None


def trial_metrics(r: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: r.get(k) for k in ("id", "family", "round", "slot", "target", "task", "arm",
                                                 "kind", "variant", "delivery", "label", "failure")}
    out["loadavg1"] = (r.get("loadavg") or [None])[0]
    out["verified"] = bool(r.get("oracle_verified"))
    actions = r.get("actions") or []
    marks = r.get("marks") or []
    ss = r.get("state_samples")
    exp = r.get("expected") or {}
    schema = "cua.r209_web_state_v1" if r.get("target") == "chrome" else "cua.gtk3_task_state_v1"
    knobs = {m["mark"] for m in marks if m.get("scope") == "exp_knob"}
    out["knob_marks"] = sorted(knobs)
    out["knobs_match_arm"] = knobs == ARM_KNOBS.get(r.get("arm"), set())
    last = actions[-1] if actions else None
    click = next((a for a in actions if a["tool"] == "click"), None)
    rec_click = (click or {}).get("structured", {})
    out["click_route"] = rec_click.get("route")
    out["click_delivery"] = (rec_click.get("delivery") or {}).get("mode")
    out["click_effect"] = rec_click.get("effect")
    out["click_error"] = (click or {}).get("error")
    sv = next((a for a in actions if a["tool"] == "set_value"), None)
    if sv is not None:
        out["set_value_route"] = sv.get("structured", {}).get("route")
        out["set_value_effect"] = sv.get("structured", {}).get("effect")
    dar = mark(marks, "atspi_action", "do_action_replied")
    psd = mark(marks, "atspi_action", "post_sleep_done")
    out["do_action_marks"] = sum(1 for m in marks if m.get("mark") == "do_action_replied")
    wake = mark(marks, "atspi_action", "post_wake_") if dar else None
    wake_end = None
    if dar:
        for m in marks:
            if m.get("scope") == "atspi_action" and str(m.get("mark", "")).startswith(
                    ("post_wake_event", "post_wake_deadline", "post_wake_stream_closed")):
                wake_end = m
                break
    opened = mark(marks, "atspi_action", "post_wake_open")
    if opened:
        parts = opened["mark"].split()
        out["acted_bus"], out["acted_path"] = (parts[1], parts[2]) if len(parts) >= 3 else (None, None)
    if wake_end:
        out["wake_reason"] = wake_end["mark"].split()[0].replace("post_wake_", "")
        out["wake_kind"] = wake_end["mark"].split()[1] if len(wake_end["mark"].split()) > 1 else None
        out["wake_ms"] = r2((wake_end["wall_ns"] - dar["wall_ns"]) / 1e6)
    out["wait_ms"] = r2((psd["wall_ns"] - dar["wall_ns"]) / 1e6) if (dar and psd) else None

    # route validity (pre-registered)
    if r.get("kind") in ("main", "smoke") or str(r.get("kind", "")).startswith("ctl"):
        if r.get("target") == "chrome":
            ok = (out["click_route"] == "accessibility" and out["click_delivery"] == "background"
                  and dar is not None and psd is not None and out["knobs_match_arm"])
            if "EW" in str(r.get("arm")):
                ok = ok and opened is not None and wake_end is not None
            out["valid_route_prereg"] = bool(ok) and click is not None and out["click_error"] is None
            out["valid_route"] = out["valid_route_prereg"]
        else:
            base_ok = out["click_route"] == "global_input" and out["click_delivery"] == "foreground"
            if r.get("task") == "text":
                base_ok = base_ok and out.get("set_value_route") is not None
            base_ok = base_ok and click is not None and out["click_error"] is None
            # As pre-registered: knob marks exactly the arm's. The knobs are read (and
            # marked) only when perform_action_ref runs, so on the XTest route S0/EW
            # can never show their marks: this rule cannot hold by construction.
            out["valid_route_prereg"] = bool(base_ok and out["knobs_match_arm"])
            # Amended (post hoc, see README Deviations): the Driver env carries exactly the
            # arm's CUA_DRIVER_EXP_* values, and no DoAction and no knob mark occurred.
            out["env_match_arm"] = (r.get("driver_env_exp") or {}) == ARM_ENV.get(r.get("arm"), {})
            out["valid_route"] = bool(base_ok and out["env_match_arm"] and out["do_action_marks"] == 0
                                      and not knobs)
    if ss and last is not None:
        anchor = ss["anchor_ns"]
        ret_us = (last["m1"] - anchor) / 1000
        out["T_return_ms"] = r2(ret_us / 1000)
        first_after = next((i for i, t in enumerate(ss["t0_us"]) if t >= ret_us), None)
        out["visible_at_return"] = bool(first_after is not None
                                        and matches(ss["states"][ss["idx"][first_after]], exp, schema))
        conf = next((i for i, t in enumerate(ss["t0_us"])
                     if t >= ret_us and matches(ss["states"][ss["idx"][i]], exp, schema)), None)
        out["T_ms"] = r2(ss["t1_us"][conf] / 1000) if conf is not None else None
        land = next((i for i, ix in enumerate(ss["idx"]) if matches(ss["states"][ix], exp, schema)), None)
        out["T_land_ms"] = r2(ss["t1_us"][land] / 1000) if land is not None else None
        # duplicates: the final sampled state must have seq exactly expected (main tasks)
        final = ss["states"][ss["idx"][-1]] if ss["idx"] else None
        if isinstance(final, dict) and "seq" in exp:
            out["final_seq_ok"] = final.get("seq") == exp["seq"]
        fs = r.get("final_state") or {}
        if r.get("target") == "chrome" and isinstance(fs, dict):
            effect = next((j for j in fs.get("journal", []) if j["kind"] == "state"), None)
            clickj = next((j for j in fs.get("journal", []) if j["kind"] == "click"), None)
            out["n_state_entries"] = sum(1 for j in fs.get("journal", []) if j["kind"] == "state")
            if effect:
                out["effect_after_return_ms"] = r2((effect["m_ns"] - last["m1"]) / 1e6)
                if dar:
                    out["effect_after_reply_ms"] = r2((effect["w_ns"] - dar["wall_ns"]) / 1e6)
                if wake_end and out.get("wake_reason") == "event":
                    out["event_latency_ms"] = r2((wake_end["wall_ns"] - effect["w_ns"]) / 1e6)
            if clickj and dar:
                out["page_click_after_reply_ms"] = r2((clickj["w_ns"] - dar["wall_ns"]) / 1e6)
    # independent listener (controls)
    lst = r.get("listener")
    if lst and dar and r.get("T0_w") is not None:
        off = r["T0_w"] - r["T0_m"]  # wall = mono + off (harness clock pair)
        deadline_wall = dar["wall_ns"] + 50_000_000
        sigs = [e for e in lst if e.get("event") == "signal" and e.get("member") in WAKE_MEMBERS
                and str(e.get("interface", "")).endswith("Event.Object")]
        acted = [e for e in sigs if e["sender"] == out.get("acted_bus") and e["path"] == out.get("acted_path")
                 and not (e["member"] == "StateChanged" and e.get("detail") == "defunct")]
        window = [e for e in sigs if dar["wall_ns"] - 20_000_000 <= e["m_ns"] + off <= deadline_wall]
        out["listener_acted_events"] = [(e["member"], e.get("detail"), e.get("detail1"),
                                         r2((e["m_ns"] + off - dar["wall_ns"]) / 1e6)) for e in acted][:10]
        out["listener_foreign_in_wait"] = sum(1 for e in window if e not in acted)
        out["listener_foreign_samples"] = [(e["sender"], e["path"].rsplit("/", 1)[-1], e["member"], e.get("detail"),
                                            r2((e["m_ns"] + off - dar["wall_ns"]) / 1e6))
                                           for e in window if e not in acted][:8]
        if out.get("wake_reason") == "event" and wake_end:
            # Not a false wake when an acted-object event reached the bus no later than
            # 5 ms after the Driver's wake mark (two independent bus clients).
            backed = [e for e in acted if e["m_ns"] + off <= wake_end["wall_ns"] + 5_000_000
                      and e["m_ns"] + off >= dar["wall_ns"] - 50_000_000]
            out["false_wake"] = not backed
        else:
            out["false_wake"] = False
    if r.get("perturb"):
        p = r["perturb"]
        out["perturb_restarted"] = p.get("restarted") or p.get("dropped")
        if p.get("kill_m_ns") and dar and r.get("T0_w") is not None:
            off = r["T0_w"] - r["T0_m"]
            out["registry_kill_after_reply_ms"] = r2((p["kill_m_ns"] + off - dar["wall_ns"]) / 1e6)
        out["registry_pid_changed"] = (p.get("registry_pid_before") is not None
                                       and r.get("registry_pid_after") not in (None, p.get("registry_pid_before")))
    return out


def boot_ci(pairs_by_round: dict[int, float]) -> tuple[float | None, float | None, float | None]:
    vals = list(pairs_by_round.values())
    if not vals:
        return None, None, None
    rng = random.Random(SEED)
    stats = []
    for _ in range(RESAMPLES):
        sample = [vals[rng.randrange(len(vals))] for _ in vals]
        stats.append(statistics.median(sample))
    stats.sort()
    return statistics.median(vals), stats[int(0.025 * RESAMPLES)], stats[int(0.975 * RESAMPLES) - 1]


def boot_ratio(base: dict[int, float], arm: dict[int, float]) -> tuple[float | None, float | None, float | None]:
    rounds = sorted(set(base) & set(arm))
    if not rounds:
        return None, None, None
    rng = random.Random(SEED)
    stats = []
    for _ in range(RESAMPLES):
        rs = [rounds[rng.randrange(len(rounds))] for _ in rounds]
        stats.append(statistics.median([base[x] for x in rs]) / statistics.median([arm[x] for x in rs]))
    stats.sort()
    point = statistics.median([base[x] for x in rounds]) / statistics.median([arm[x] for x in rounds])
    return point, stats[int(0.025 * RESAMPLES)], stats[int(0.975 * RESAMPLES) - 1]


def main() -> None:
    raw = Path(sys.argv[1])
    summary_path, metrics_path = Path(sys.argv[2]), Path(sys.argv[3])
    attempts: dict[str, list[dict]] = {}
    blocks = []
    for path in sorted(list(raw.glob("*/trials.jsonl")) + list(raw.glob("*/trials.jsonl.gz"))):
        label = path.parent.name
        rows = list(open_lines(path))
        meta = next((x for x in rows if x["event"] == "meta"), {})
        end = next((x for x in rows if x["event"] == "end"), None)
        blocks.append({"label": label, "block": meta.get("block"), "n_trials": sum(1 for x in rows if x["event"] == "trial"),
                       "failures": end.get("failures") if end else None, "complete": end is not None,
                       "net_refused": (end or {}).get("net", {}).get("refused_non_loopback_connects"),
                       "chrome_version": meta.get("chrome_version"), "driver_sha256": meta.get("driver_sha256"),
                       "session_a11y_enabled": (meta.get("session_a11y") or {}).get("enabled"),
                       "display_collision": meta.get("display_collision")})
        for x in rows:
            if x["event"] == "trial":
                x["label"] = label
                attempts.setdefault(x["id"], []).append(x)
    latest = {}
    superseded = []
    for tid, xs in attempts.items():
        xs.sort(key=lambda x: x.get("w_begin") or 0)
        latest[tid] = xs[-1]
        superseded += [{"id": tid, "label": x["label"], "failure": x.get("failure")} for x in xs[:-1]]
    metrics = [trial_metrics(r) for r in latest.values()]
    with open(metrics_path, "w", encoding="utf-8") as stream:
        for m in sorted(metrics, key=lambda m: m["id"]):
            stream.write(json.dumps(m, sort_keys=True) + "\n")

    cells: dict[str, Any] = {}
    paired: dict[str, Any] = {}
    for fam, base in FAMILY_BASE.items():
        fam_rows = [m for m in metrics if m["family"] == fam]
        for task in sorted({m["task"] for m in fam_rows}):
            by_arm: dict[str, list[dict]] = {}
            for m in fam_rows:
                if m["task"] == task:
                    by_arm.setdefault(m["arm"], []).append(m)
            for arm, rows in sorted(by_arm.items()):
                ok = [m for m in rows if m["verified"] and m.get("valid_route")]
                ews = [m for m in rows if m.get("wake_reason")]
                cells[f"{fam}/{task}/{arm}"] = {
                    "n": len(rows), "valid_route": sum(1 for m in rows if m.get("valid_route")),
                    "valid_route_prereg": sum(1 for m in rows if m.get("valid_route_prereg")),
                    "verified": sum(1 for m in rows if m["verified"]),
                    "visible_at_return": sum(1 for m in rows if m.get("visible_at_return")),
                    "not_visible_at_return": sum(1 for m in rows if m.get("visible_at_return") is False),
                    "final_seq_ok": sum(1 for m in rows if m.get("final_seq_ok")),
                    "click_routes": sorted({str(m.get("click_route")) for m in rows}),
                    "do_action_marks_total": sum(m.get("do_action_marks", 0) for m in rows),
                    "T_median": r2(med([m["T_ms"] for m in ok if m.get("T_ms") is not None])),
                    "T_p95": r2(pct([m["T_ms"] for m in ok if m.get("T_ms") is not None], 0.95)),
                    "T_land_median": r2(med([m["T_land_ms"] for m in ok if m.get("T_land_ms") is not None])),
                    "T_return_median": r2(med([m["T_return_ms"] for m in ok if m.get("T_return_ms") is not None])),
                    "wait_median": r2(med([m["wait_ms"] for m in rows if m.get("wait_ms") is not None])),
                    "wait_p95": r2(pct([m["wait_ms"] for m in rows if m.get("wait_ms") is not None], 0.95)),
                    "effect_after_reply_median": r2(med([m["effect_after_reply_ms"] for m in rows
                                                         if m.get("effect_after_reply_ms") is not None])),
                    "effect_after_reply_max": r2(max([m["effect_after_reply_ms"] for m in rows
                                                      if m.get("effect_after_reply_ms") is not None], default=None)),
                    "effect_after_reply_positive": sum(1 for m in rows if (m.get("effect_after_reply_ms") or -1) > 0),
                    "effect_after_return_max": r2(max([m["effect_after_return_ms"] for m in rows
                                                       if m.get("effect_after_return_ms") is not None], default=None)),
                    "wake_reasons": {k: sum(1 for m in ews if m["wake_reason"] == k)
                                     for k in sorted({m["wake_reason"] for m in ews})},
                    "wake_kinds": {k: sum(1 for m in ews if m.get("wake_kind") == k)
                                   for k in sorted({str(m.get("wake_kind")) for m in ews if m.get("wake_kind")})},
                    "wake_ms_median": r2(med([m["wake_ms"] for m in ews if m.get("wake_ms") is not None])),
                    "event_latency_median": r2(med([m["event_latency_ms"] for m in rows
                                                    if m.get("event_latency_ms") is not None])),
                    "event_latency_min": r2(min([m["event_latency_ms"] for m in rows
                                                 if m.get("event_latency_ms") is not None], default=None)),
                    "event_latency_max": r2(max([m["event_latency_ms"] for m in rows
                                                 if m.get("event_latency_ms") is not None], default=None)),
                    "loadavg1_median": r2(med([m["loadavg1"] for m in rows if m.get("loadavg1") is not None])),
                }
            base_t = {m["round"]: m["T_ms"] for m in by_arm.get(base, [])
                      if m["verified"] and m.get("valid_route") and m.get("T_ms") is not None}
            base_ret = {m["round"]: m["T_return_ms"] for m in by_arm.get(base, [])
                        if m["verified"] and m.get("valid_route") and m.get("T_return_ms") is not None}
            for arm, rows in sorted(by_arm.items()):
                if arm == base:
                    continue
                arm_t = {m["round"]: m["T_ms"] for m in rows
                         if m["verified"] and m.get("valid_route") and m.get("T_ms") is not None}
                arm_ret = {m["round"]: m["T_return_ms"] for m in rows
                           if m["verified"] and m.get("valid_route") and m.get("T_return_ms") is not None}
                d = {k: base_t[k] - arm_t[k] for k in set(base_t) & set(arm_t)}
                dr = {k: base_ret[k] - arm_ret[k] for k in set(base_ret) & set(arm_ret)}
                p, lo, hi = boot_ci(d)
                pr, lor, hir = boot_ci(dr)
                s, slo, shi = boot_ratio(base_t, arm_t)
                paired[f"{fam}/{task}/{base}-{arm}"] = {
                    "n_pairs": len(d), "T_base_minus_arm_median": r2(p), "ci95": [r2(lo), r2(hi)],
                    "ci_excludes_0": bool(lo is not None and (lo > 0 or hi < 0)),
                    "T_return_base_minus_arm_median": r2(pr), "T_return_ci95": [r2(lor), r2(hir)],
                    "S": r2(s), "S_ci95": [r2(slo), r2(shi)]}

    controls = {}
    for code in ("a", "b", "c", "d", "c2"):
        rows = [m for m in metrics if m["family"] == f"C{code}"]
        if not rows:
            continue
        controls[code] = {
            "n": len(rows), "verified": sum(1 for m in rows if m["verified"]),
            "valid_route": sum(1 for m in rows if m.get("valid_route")),
            "wake_reasons": {k: sum(1 for m in rows if m.get("wake_reason") == k)
                             for k in sorted({str(m.get("wake_reason")) for m in rows})},
            "wake_kinds": {k: sum(1 for m in rows if m.get("wake_kind") == k)
                           for k in sorted({str(m.get("wake_kind")) for m in rows if m.get("wake_kind")})},
            "wake_ms": [m.get("wake_ms") for m in rows],
            "false_wakes": sum(1 for m in rows if m.get("false_wake")),
            "foreign_events_in_wait_median": r2(med([m["listener_foreign_in_wait"] for m in rows
                                                    if m.get("listener_foreign_in_wait") is not None])),
            "trials_with_foreign_events_in_wait": sum(1 for m in rows if (m.get("listener_foreign_in_wait") or 0) > 0),
            "trials_with_acted_event_in_listener": sum(1 for m in rows if m.get("listener_acted_events")),
            "visible_at_return": sum(1 for m in rows if m.get("visible_at_return")),
            "click_effects": sorted({str(m.get("click_effect")) for m in rows}),
            "wait_max": r2(max([m["wait_ms"] for m in rows if m.get("wait_ms") is not None], default=None)),
            "perturbed": sum(1 for m in rows if m.get("perturb_restarted")),
            "registry_pid_changed": sum(1 for m in rows if m.get("registry_pid_changed")),
            "registry_kill_after_reply_ms": [m.get("registry_kill_after_reply_ms") for m in rows
                                             if m.get("registry_kill_after_reply_ms") is not None],
            "final_seq_ok": sum(1 for m in rows if m.get("final_seq_ok")),
        }
    smoke = [m for m in metrics if m["family"] == "D"]
    summary = {
        "schema": "r209.summary.v1", "blocks": blocks, "superseded_attempts": superseded,
        "planned_cells_latest": len(latest),
        "verified_latest": sum(1 for m in metrics if m["verified"]),
        "failures_latest": [{"id": m["id"], "failure": m.get("failure")} for m in metrics if not m["verified"]],
        "cells": cells, "paired_vs_base": paired, "controls": controls,
        "smoke": {"n": len(smoke), "verified": sum(1 for m in smoke if m["verified"]),
                  "knob_marks": sorted({k for m in smoke for k in m["knob_marks"]}),
                  "wait_ms": [m.get("wait_ms") for m in smoke]},
        "stats": {"bootstrap": "percentile, resample rounds", "resamples": RESAMPLES, "seed": SEED,
                  "p95": "nearest rank"},
    }
    summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"latest": len(latest), "verified": summary["verified_latest"],
                      "failures": len(summary["failures_latest"])}))


if __name__ == "__main__":
    main()
