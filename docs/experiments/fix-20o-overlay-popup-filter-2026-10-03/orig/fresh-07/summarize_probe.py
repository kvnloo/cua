#!/usr/bin/env python3
"""FRESH-07: summarize the probe ledger (raw/probe/probe.jsonl) into probe-summary.json.

usage: summarize_probe.py <probe.jsonl> [<out.json>]
Per binary: overlay map state at every read point, shape rectangle counts, focus / active /
stack-top / pointer-child identity, the guard fields of both clicks, the oracle verdicts, and the
startup ordering (overlay first VIEWABLE / first seen vs the MCP initialize reply).
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

POINTS = ["S1_idle", "S2_on_pre", "S2_on_after", "S2_on_settled", "S3_disabled_idle", "S3_off_pre",
          "S3_off_after", "S3_off_settled"]


def ov(read: dict | None) -> str:
    if not read:
        return "MISSING"
    rows = read.get("overlays") or []
    if not rows:
        return "NONE"
    return "+".join(f"{r['map_state']}(b{r.get('bounding_rects')},i{r.get('input_rects')})" for r in rows)


def overlay_ids(read: dict | None) -> set:
    return {r["window"] for r in (read or {}).get("overlays") or []}


def summarize(path: Path) -> dict:
    runs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = next(r for r in runs if r.get("event") == "meta")
    end = next((r for r in runs if r.get("event") == "end"), {})
    runs = [r for r in runs if r.get("event") == "run"]
    per: dict = collections.defaultdict(lambda: {"runs": 0, "failures": [], "points": collections.defaultdict(collections.Counter),
                                                 "guard_on": collections.Counter(), "guard_off": collections.Counter(),
                                                 "grab_held_on": 0, "grab_held_off": 0, "oracle_on": 0, "oracle_off": 0,
                                                 "overlay_in_mapped_or": collections.Counter(), "startup": [],
                                                 "focus_identity": collections.Counter()})
    for r in runs:
        b = per[r["binary"]]
        b["runs"] += 1
        if "failure" in r:
            b["failures"].append(r["failure"])
        for p in POINTS:
            b["points"][p][ov(r.get(p))] += 1
            read = r.get(p)
            if read:
                ids = overlay_ids(read)
                b["overlay_in_mapped_or"][f"{p}:{any(m['window'] in ids for m in read.get('mapped_or') or [])}"] += 1
                b["focus_identity"][f"{p}:pointer_child_is_overlay={read.get('pointer_child') in ids}"] += 1
        for tag in ("on", "off"):
            c = r.get(f"S{2 if tag == 'on' else 3}_{tag}_click") or {}
            g = c.get("guard") or {}
            # The structured focus-guard fields are reduced away by the public action contract;
            # the guard's summary sentence survives in the text content (focus_guard.rs summary()).
            texts = c.get("text") or []
            grab_text = any("holds a keyboard grab" in t for t in texts)
            outcome_text = next((t.split("focus_outcome=")[1].split(")")[0] for t in texts if "focus_outcome=" in t), None)
            b[f"guard_{tag}"][json.dumps({"grab_held_text": grab_text, "focus_outcome_text": outcome_text,
                                          **{k: g.get(k) for k in ("focus_changed", "focus_outcome", "grab_held_by")}},
                                         sort_keys=True)] += 1
            if g.get("grab_held_by") is not None or grab_text:
                b[f"grab_held_{tag}"] += 1
            o = r.get(f"S{2 if tag == 'on' else 3}_{tag}_oracle") or {}
            b[f"oracle_{tag}"] += 1 if o.get("verified") else 0
        t_spawn, t_init = r.get("t_spawn_ns"), r.get("t_init_reply_ns")
        first_seen = first_viewable = first_unmapped = None
        for tr in (r.get("poller") or {}).get("transitions") or []:
            states = [s[1] for s in tr["overlays"]]
            if states and first_seen is None:
                first_seen = tr["t_mono_ns"]
            if "VIEWABLE" in states and first_viewable is None:
                first_viewable = tr["t_mono_ns"]
            if "UNMAPPED" in states and first_unmapped is None:
                first_unmapped = tr["t_mono_ns"]
        ms = lambda t: None if (t is None or t_spawn is None) else round((t - t_spawn) / 1e6, 2)  # noqa: E731
        b["startup"].append({"run": r["run"], "init_reply_ms": ms(t_init), "overlay_first_seen_ms": ms(first_seen),
                             "overlay_first_viewable_ms": ms(first_viewable), "overlay_first_unmapped_ms": ms(first_unmapped),
                             "viewable_before_init": (first_viewable is not None and t_init is not None and first_viewable < t_init),
                             "transitions": len((r.get("poller") or {}).get("transitions") or [])})
        # focus/active/stack identity between points within a run (does any map transition move them?)
        sig = [(p, (r.get(p) or {}).get("focus"), (r.get(p) or {}).get("active"), (r.get(p) or {}).get("stack_top"))
               for p in POINTS if r.get(p)]
        b["focus_identity"]["stable_focus_active_stacktop_all_points=" + str(len({s[1:] for s in sig}) == 1)] += 1
    out = {"meta": meta, "end": end, "binaries": {}}
    for name, b in per.items():
        out["binaries"][name] = {
            "runs": b["runs"], "failures": b["failures"],
            "points": {p: dict(c) for p, c in b["points"].items()},
            "guard_on": dict(b["guard_on"]), "guard_off": dict(b["guard_off"]),
            "grab_held_by_on": b["grab_held_on"], "grab_held_by_off": b["grab_held_off"],
            "oracle_verified_on": b["oracle_on"], "oracle_verified_off": b["oracle_off"],
            "overlay_in_guard_popup_view": dict(b["overlay_in_mapped_or"]),
            "focus_identity": dict(b["focus_identity"]),
            "startup": b["startup"],
            "startup_viewable_before_init": sum(1 for s in b["startup"] if s["viewable_before_init"]),
        }
    return out


def main() -> None:
    src = Path(sys.argv[1])
    res = summarize(src)
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
