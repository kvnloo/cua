#!/usr/bin/env python3
"""R2-10R drift row D1 analysis (standard library only): first-snapshot grace vs explicit timeout.

Reads raw/drift/d1/trials.jsonl.gz (native, arms G = timeout_ms omitted, E = timeout_ms 1000) and,
for the browser call-graph mark count, the scripted/controls/Phase 0 browser trial bundles. Rules
are the ones in PREREG.json ``drift_row_D1``.

usage: analyze_d1.py [--raw raw] [--out d1-summary.json]
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "harness" / "src" / "b-02-browser-driver-sites-2026-10-02"))
import b01_analysis as B  # noqa: E402  (seeded bootstrap: seed 20261002, 10000 resamples)

GRACE_SYMBOLS = ("resolve_timeout_ms_with_first_snapshot_grace", "contains_semantic_window")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def span_ms(marks: list[dict[str, Any]], tool: str, nth: int) -> float | None:
    """Driver-side span of the nth call of ``tool``: dispatch_enter -> dispatch_exit marks."""
    enters = [m["t_mono_ns"] for m in marks if m.get("phase") == tool and m.get("session") == "dispatch_enter"]
    exits = [m["t_mono_ns"] for m in marks if m.get("phase") == tool and m.get("session") == "dispatch_exit"]
    if len(enters) <= nth or len(exits) <= nth:
        return None
    return (exits[nth] - enters[nth]) / 1e6


def browser_mark_counts(raw: Path) -> dict[str, Any]:
    bundles = sorted((raw / "browser").glob("*-trials.tar.gz")) + sorted((raw / "phase0").glob("*-trials.tar.gz"))
    traces = 0
    tool_marks: Counter = Counter()
    lines_total = 0
    for path in bundles:
        with tarfile.open(path, "r:gz") as tar:
            for m in tar.getmembers():
                if not (m.isfile() and m.name.endswith(".driver-trace.jsonl")):
                    continue
                traces += 1
                for line in tar.extractfile(m).read().decode().splitlines():
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    lines_total += 1
                    if rec.get("session") == "dispatch_enter":
                        tool_marks[rec.get("phase")] += 1
                    if any(s in line for s in GRACE_SYMBOLS):
                        tool_marks["__grace_symbol_text__"] += 1
    return {"bundles": [p.name for p in bundles], "trace_files": traces, "trace_lines": lines_total,
            "dispatch_enter_by_tool": dict(sorted(tool_marks.items())),
            "get_window_state_dispatches": tool_marks.get("get_window_state", 0),
            "grace_symbol_text_hits": tool_marks.get("__grace_symbol_text__", 0)}


def analyze(raw: Path) -> dict[str, Any]:
    rows = [r for r in read_jsonl(raw / "drift" / "d1" / "trials.jsonl.gz") if r.get("event") == "trial"]
    out: dict[str, Any] = {"schema": "r2-10r.d1-summary.v1", "n": len(rows)}
    per = []
    for r in rows:
        f = (r.get("first") or {})
        s = f.get("summary") or {}
        s2 = (r.get("second") or {}).get("summary") or {}
        marks = r.get("marks") or []
        per.append({"id": r["id"], "arm": r["arm"], "pair": r["pair"], "pos": r["pos"], "valid": r.get("valid"),
                    "failure": r.get("failure"), "loadavg_1m": (r.get("loadavg") or [None])[0],
                    "T_ms": f.get("T_ms"), "timeout_ms": s.get("timeout_ms"), "walk_elapsed_ms": s.get("walk_elapsed_ms"),
                    "truncated": s.get("truncated"), "truncation_reason": s.get("truncation_reason"),
                    "nodes_visited": s.get("nodes_visited"), "nodes_pending": s.get("nodes_pending"),
                    "element_count": s.get("element_count"), "elements_complete": s.get("elements_complete"),
                    "elements_digest": s.get("elements_digest"), "tree_markdown_digest": s.get("tree_markdown_digest"),
                    "second_timeout_ms": s2.get("timeout_ms"), "second_elements_digest": s2.get("elements_digest"),
                    "second_truncated": s2.get("truncated"),
                    "driver_span_ms": span_ms(marks, "get_window_state", 0),
                    "gws_dispatch_marks": sum(1 for m in marks if m.get("phase") == "get_window_state"
                                              and m.get("session") == "dispatch_enter"),
                    "state_unchanged": r.get("state_before") == r.get("state_after")})
    out["rows"] = per
    by = {a: [p for p in per if p["arm"] == a] for a in ("G", "E")}
    digests = Counter(p["elements_digest"] for p in per)
    md_digests = Counter(p["tree_markdown_digest"] for p in per)
    out["gate"] = {
        "trials": len(per), "valid": sum(1 for p in per if p["valid"]),
        "forced_path_G_2000": sum(1 for p in by["G"] if p["timeout_ms"] == 2000),
        "forced_path_E_1000": sum(1 for p in by["E"] if p["timeout_ms"] == 1000),
        "second_call_default_1000": sum(1 for p in per if p["second_timeout_ms"] == 1000),
        "elements_digest_distinct": len(digests), "elements_digest_modal_count": digests.most_common(1)[0][1] if digests else 0,
        "tree_markdown_digest_distinct": len(md_digests),
        "second_digest_equal_first": sum(1 for p in per if p["second_elements_digest"] == p["elements_digest"]),
        "truncated_false": sum(1 for p in per if p["truncated"] is False),
        "state_unchanged": sum(1 for p in per if p["state_unchanged"]),
    }
    g = out["gate"]
    g["digests_identical_40_of_40"] = bool(g["trials"] == 40 and g["elements_digest_distinct"] == 1
                                           and g["elements_digest_modal_count"] == 40)
    g["truncated_false_40_of_40"] = g["truncated_false"] == 40
    g["pass"] = bool(g["digests_identical_40_of_40"] and g["truncated_false_40_of_40"] and g["valid"] == 40
                     and g["forced_path_G_2000"] == 20 and g["forced_path_E_1000"] == 20)
    stats: dict[str, Any] = {}
    for a, ps in by.items():
        v = [p for p in ps if p["valid"]]
        stats[a] = {k: {"median": statistics.median(xs), "min": min(xs), "max": max(xs)} if xs else None
                    for k in ("T_ms", "walk_elapsed_ms", "driver_span_ms", "nodes_visited", "nodes_pending", "element_count")
                    for xs in [[p[k] for p in v if p[k] is not None]]}
    out["by_arm"] = stats
    pairs = {}
    for p in per:
        pairs.setdefault(p["pair"], {})[p["arm"]] = p
    good = [(d["G"], d["E"]) for _, d in sorted(pairs.items()) if "G" in d and "E" in d and d["G"]["valid"] and d["E"]["valid"]]
    out["paired"] = {
        "n_pairs": len(good),
        "T_ms_G_minus_E": B.paired_diff([g_["T_ms"] for g_, _ in good], [e["T_ms"] for _, e in good]),
        "driver_span_ms_G_minus_E": B.paired_diff([g_["driver_span_ms"] for g_, e in good if g_["driver_span_ms"] is not None and e["driver_span_ms"] is not None],
                                                  [e["driver_span_ms"] for g_, e in good if g_["driver_span_ms"] is not None and e["driver_span_ms"] is not None]),
        "walk_elapsed_ms_G_minus_E": B.paired_diff([g_["walk_elapsed_ms"] for g_, _ in good], [e["walk_elapsed_ms"] for _, e in good]),
    }
    out["loadavg_1m"] = {"min": min((p["loadavg_1m"] for p in per if p["loadavg_1m"] is not None), default=None),
                         "median": statistics.median([p["loadavg_1m"] for p in per if p["loadavg_1m"] is not None]) if per else None,
                         "max": max((p["loadavg_1m"] for p in per if p["loadavg_1m"] is not None), default=None)}
    out["browser_marks"] = browser_mark_counts(raw)
    out["native_gws_dispatch_marks_per_trial"] = dict(Counter(p["gws_dispatch_marks"] for p in per))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "raw"))
    ap.add_argument("--out", default=str(HERE / "d1-summary.json"))
    args = ap.parse_args()
    S = analyze(Path(args.raw))
    Path(args.out).write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"gate": S["gate"], "paired_T": S["paired"]["T_ms_G_minus_E"],
                      "browser_gws": S["browser_marks"]["get_window_state_dispatches"]}, indent=1))


if __name__ == "__main__":
    main()
