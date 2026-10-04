#!/usr/bin/env python3
"""FRESH-07R native covariates (descriptive only; never a gate, never used to exclude a trial).

For every native trial (R2-10R native nm1/nm2/nd1 rows; N-04 rows) it records:
  guard_text   per task: "grab_held" when any click reply carries the focus guard's popup/grab sentence
               ("popup menu is open" or "keyboard grab"), else "none". The sentence is in the click's text
               content (content_text) and structured summary, which the original harnesses already keep in raw.
  overlay      from harness/overlay_watch.py logs (passive X map/unmap events of override-redirect root
               children in the private session): whether a Driver overlay (Cua.AgentCursorOverlay.*) is
               mapped at the task's T0, and how many overlay map / unmap events fall inside [T0_w, w_end].
Usage: covariate_native.py --trials <trials.jsonl[.gz]>... --overlay <overlay-*.jsonl[.gz]>... --out <json>
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections import defaultdict
from pathlib import Path

GRAB = ("popup menu is open", "keyboard grab")


def rows(path: Path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def tasks_of(r: dict) -> list[dict]:
    """R2-10R native rows carry one task inline; N-03/N-04 rows carry a 'tasks' list."""
    if isinstance(r.get("tasks"), list):
        return [dict(t, task=t.get("task") or (r.get("task") if len(r["tasks"]) == 1 else f"task{t.get('task_i')}"))
                for t in r["tasks"]]
    return [r]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", nargs="+", required=True)
    ap.add_argument("--overlay", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    ev = []
    cover: list[tuple[int, int]] = []  # [ready, stop] wall-ns window of each watcher file
    for f in a.overlay:
        ws = [e["w"] for e in rows(Path(f)) if "w" in e]
        if ws:
            cover.append((min(ws), max(ws)))
        for e in rows(Path(f)):
            if e.get("ev") in ("map", "unmap", "destroy") and e.get("cls") == "overlay":
                ev.append((e["w"], e["ev"], e["win"]))
            elif e.get("ev") == "ready":
                for s in e.get("initial_override_redirect", []):
                    if s.get("cls") == "overlay" and s.get("map_state") == "VIEWABLE":
                        ev.append((e["w"], "map", s["win"]))
    ev.sort()

    def mapped_at(t: int) -> bool:
        state: dict[int, bool] = {}
        for w, kind, win in ev:
            if w > t:
                break
            state[win] = kind == "map"
        return any(state.values())

    def events_in(t0: int, t1: int) -> tuple[int, int]:
        m = sum(1 for w, k, _ in ev if t0 <= w <= t1 and k == "map")
        u = sum(1 for w, k, _ in ev if t0 <= w <= t1 and k == "unmap")
        return m, u

    per_trial = []
    for f in a.trials:
        drv = None
        for r in rows(Path(f)):
            if r.get("event") == "meta":
                drv = r.get("driver_bin_name")
            if r.get("event") != "trial":
                continue
            for t in tasks_of(r):
                summaries = [" ".join([str((x.get("structured") or {}).get("summary") or "")]
                                      + [str(c) for c in (x.get("content_text") or [])])
                             for x in t.get("actions", []) if x.get("tool") == "click"]
                grab = any(any(g in s for g in GRAB) for s in summaries)
                t0, t1 = t.get("T0_w"), r.get("w_end")
                cov = {"block": r.get("block"), "id": r.get("id"), "kind": r.get("kind"), "arm": r.get("arm"),
                       "task": t.get("task") or r.get("task"), "verified": t.get("oracle_verified"),
                       "driver": drv, "clicks": len(summaries), "guard_text": "grab_held" if grab else "none"}
                if t0 and t1 and any(c0 <= t0 and t1 <= c1 for c0, c1 in cover):
                    m, u = events_in(t0, t1)
                    cov.update({"overlay_mapped_at_T0": mapped_at(t0), "overlay_map_events_in_T": m,
                                "overlay_unmap_events_in_T": u})
                else:
                    cov.update({"overlay_mapped_at_T0": None, "overlay_map_events_in_T": None,
                                "overlay_unmap_events_in_T": None})
                per_trial.append(cov)

    cells: dict[str, list[dict]] = defaultdict(list)
    for c in per_trial:
        cells[f"{c['driver']}/{c['kind']}/{c['task']}/{c['arm']}"].append(c)
    table = {}
    for k, cs in sorted(cells.items()):
        known = [c for c in cs if c["overlay_mapped_at_T0"] is not None]
        table[k] = {"n": len(cs), "grab_held": sum(c["guard_text"] == "grab_held" for c in cs),
                    "overlay_known": len(known),
                    "overlay_mapped_at_T0": sum(bool(c["overlay_mapped_at_T0"]) for c in known),
                    "overlay_mapped_inside_T": sum((c["overlay_map_events_in_T"] or 0) > 0 for c in known),
                    "median_map_events_in_T": statistics.median([c["overlay_map_events_in_T"] for c in known]) if known else None}
    out = {"schema": "fresh07r.covariate.v1", "note": "descriptive; within one binary only; not a gate",
           "overlay_files": len(a.overlay), "overlay_events": len(ev), "trials": len(per_trial), "cells": table,
           "per_trial": per_trial}
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "per_trial"}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
