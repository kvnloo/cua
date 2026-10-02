#!/usr/bin/env python3
"""OWN-16 analysis: recompute the selector truth table from raw/ (stdlib only).

usage: analyze.py <packet-dir>   -> writes own-16-matrix.json and own-16-summary.json

Inputs (all under raw/): S1/, S2/ (measured), N1/ (negative), D1/ (smoke), each with
calls.jsonl (harness ledger) and session-env.txt; measured sessions also carry
phase-m.jsonl (the Driver's full measurement-only trace) and oracle/xrecord.jsonl +
oracle/dbus-monitor.log.gz (the independent producer-boundary oracle).
Gates and decision rules are the ones frozen in PREREG.json.
"""

from __future__ import annotations

import gzip
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

MEASURED = ("S1", "S2")
ROWS = ("both", "screenshot_only", "accessibility_only", "neither", "legacy_omitted", "unknown_field",
        "wrong_type_supplementary")
MATRIX_ROWS = ROWS[:-1]
OMITTED = {"screenshot_only": "walk", "accessibility_only": "capture"}
SEED, RESAMPLES = 1616, 10000
GRACE_NS = 30_000_000


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def calls(records: list[dict], phases: tuple[str, ...]) -> list[dict]:
    return [r for r in records if r["event"] == "call" and r["phase"] in phases]


def p95(values: list[float]) -> float:
    s = sorted(values)
    return s[max(0, -(-95 * len(s) // 100) - 1)]


def outcome(row: str, c: dict) -> str:
    if c.get("exception"):
        return "exception"
    if c["is_error"]:
        return "rejected"
    has, prod = c["has"], c["producers"]
    tree = has["elements"] or has["tree_markdown"]
    shot = has["image_part"] or has["screenshot_fields"]
    if row == "screenshot_only":
        if tree:
            return "silently_ignored"
        return "schema_only" if prod["walk"] > 0 else ("honored" if shot else "degraded")
    if row in ("accessibility_only", "wrong_type_supplementary"):
        if shot:
            return "silently_ignored"
        return "schema_only" if prod["capture"] > 0 else ("honored" if tree else "degraded")
    # default rows (both, legacy_omitted) and rows the contract should reject
    if row in ("neither", "unknown_field"):
        return "silently_ignored" if (tree or shot or prod["capture"] or prod["walk"]) else "accepted_empty"
    return "honored" if (tree and shot and prod["capture"] == 1 and prod["walk"] == 1) else "partial"


def modal(values: list):
    return Counter(json.dumps(v, sort_keys=True) for v in values).most_common(1)[0][0]


# Deviation D1 (README): the frozen harness's integrity() returned before its screenshot
# checks whenever a response had no `elements`, so for every row the two screenshot checks
# are recomputed here from the raw per-call fields with the PREREG formula.
def png_matches_reported(c: dict) -> bool | None:
    dims = [p.get("png_dims") for p in c.get("content", []) if p["type"] == "image"]
    m = c.get("meta", {})
    if not dims or "screenshot_width" not in m:
        return None
    return all(d == [m["screenshot_width"], m["screenshot_height"]] for d in dims)


def screenshot_matches_window(c: dict) -> bool | None:
    m = c.get("meta", {})
    wb = m.get("window_bounds")
    if "screenshot_width" not in m or not wb:
        return None
    scale = m.get("frame_scale") or 1.0
    return (abs(m["screenshot_width"] - wb["width"] * scale) <= 1.0
            and abs(m["screenshot_height"] - wb["height"] * scale) <= 1.0)


# Deviation D2 (README): `invalidated_snapshot_ids` is a notice about the PREVIOUS call's
# snapshot (present after any successful observation, absent after an error), so it is
# excluded when response shapes are compared across rows.
CONTEXT_KEYS = {"invalidated_snapshot_ids"}


def shape_keys(c: dict) -> list[str]:
    return sorted(k for k in c.get("structured_keys", []) if k not in CONTEXT_KEYS)


def screenshot_complete(c: dict) -> bool:
    m = c["meta"]
    return bool(c["has"]["image_part"] and png_matches_reported(c) is True
                and m.get("screenshot_frame_valid") is True and not c["has"]["screenshot_error"]
                and screenshot_matches_window(c) is True and c["producers"]["capture"] == 1)


def accessibility_complete(c: dict, ref_count, ref_digest) -> bool:
    i, m = c["integrity"], c["meta"]
    return bool(c["has"]["elements"] and m.get("elements_complete") is True and m.get("truncated") is False
                and not c["has"]["degraded"] and json.dumps(m.get("element_count")) == ref_count
                and json.dumps(i.get("elements_digest")) == ref_digest and i.get("frames_outside_window") == 0
                and c["producers"]["walk"] == 1)


def bootstrap(row_by_s: dict, both_by_s: dict) -> tuple[float, float, float]:
    rng = random.Random(SEED)
    point = statistics.median(sum(row_by_s.values(), [])) - statistics.median(sum(both_by_s.values(), []))
    diffs = []
    for _ in range(RESAMPLES):
        a, b = [], []
        for s in row_by_s:
            xs, ys = row_by_s[s], both_by_s[s]
            a += [xs[rng.randrange(len(xs))] for _ in xs]
            b += [ys[rng.randrange(len(ys))] for _ in ys]
        diffs.append(statistics.median(a) - statistics.median(b))
    diffs.sort()
    return point, diffs[int(0.025 * RESAMPLES)], diffs[int(0.975 * RESAMPLES) - 1]


def phase_audit(marks: list[dict]) -> dict:
    """From the Driver's full trace: every producer invocation lies inside one tool dispatch;
    ordinals are gap-free; count producer invocations by enclosing tool."""
    scopes = ("capture_window", "capture_root_region", "atspi_walk")
    windows, open_ = [], {}
    for m in marks:
        if m["mark"] == "dispatch_enter":
            open_[m["scope"]] = m["wall_ns"]
        elif m["mark"] == "dispatch_exit" and m["scope"] in open_:
            windows.append((open_.pop(m["scope"]), m["wall_ns"], m["scope"]))
    by_tool, outside = Counter(), 0
    ordinals = defaultdict(list)
    for m in marks:
        if m["scope"] in scopes and m["mark"] == "enter":
            ordinals[m["scope"]].append(m["n"])
            tool = next((w[2] for w in windows if w[0] <= m["wall_ns"] <= w[1]), None)
            if tool is None:
                outside += 1
            else:
                by_tool[f'{tool}:{m["scope"]}'] += 1
    gap_free = all(v == list(range(1, len(v) + 1)) for v in ordinals.values())
    exits = Counter(f'{m["scope"]}:{m["mark"]}' for m in marks if m["scope"] in scopes and m["mark"] != "enter")
    return {"producer_invocations_by_tool": dict(by_tool), "producer_invocations_outside_dispatch": outside,
            "ordinals_gap_free": gap_free, "exit_marks": dict(exits),
            "invocations": {k: len(v) for k, v in ordinals.items()}}


def parse_monitor_times(text: str) -> list[int]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^method call time=(\d+)\.(\d+) ", line)
        if m:
            out.append(int(m.group(1)) * 1_000_000_000 + int(m.group(2).ljust(6, "0")[:6]) * 1000)
    return out


def oracle_check(sdir: Path, recs: list[dict]) -> dict:
    by_index = {c["index"]: c for c in calls(recs, ("oracle",))}
    wins = [r for r in recs if r["event"] == "oracle_window"]
    xev = [e for e in load(sdir / "oracle" / "xrecord.jsonl") if "op" in e]
    dtimes = parse_monitor_times(gzip.decompress((sdir / "oracle" / "dbus-monitor.log.gz").read_bytes()).decode(
        errors="replace"))
    rows, agree, recomputed_ok = [], 0, 0
    idle = None
    for w in wins:
        hi = w["w1"] + (GRACE_NS if w["kind"] == "call" else 0)
        x = sum(1 for e in xev if w["w0"] <= e["t_ns"] <= hi)
        d = sum(1 for t in dtimes if w["w0"] <= t <= hi)
        same = (x == w["x_getimage"] + w["x_shmgetimage"]) and (d == w["atspi_calls_total"])
        recomputed_ok += same
        if w["kind"] == "idle":
            idle = {"x_image_reads": x, "atspi_calls": d}
            continue
        c = by_index[w["index"]]
        p = c["producers"]
        ok = (x == p["capture"]) and ((w["atspi_calls_to_fixture"] > 0) == (p["walk"] == 1))
        agree += ok
        rows.append({"row": w["row"], "x_image_reads": x, "atspi_calls_to_fixture": w["atspi_calls_to_fixture"],
                     "atspi_calls_from_driver": w["atspi_calls_from_driver"], "mark_capture": p["capture"],
                     "mark_walk": p["walk"], "agree": ok})
    per_row = {}
    for r in ROWS:
        rr = [x for x in rows if x["row"] == r]
        per_row[r] = {"n": len(rr), "agree": sum(x["agree"] for x in rr),
                      "x_image_reads": sorted({x["x_image_reads"] for x in rr}),
                      "atspi_calls_to_fixture": sorted({x["atspi_calls_to_fixture"] for x in rr})}
    return {"calls": len(rows), "agree": agree, "idle": idle,
            "idle_clean": idle == {"x_image_reads": 0, "atspi_calls": 0},
            "windows_recomputed_match": recomputed_ok, "windows": len(wins), "per_row": per_row}


def analyze(pkt: Path) -> tuple[dict, dict]:
    raw = pkt / "raw"
    sess = {s: load(raw / s / "calls.jsonl") for s in ("S1", "S2", "N1", "D1")}
    env = {s: dict(l.split("=", 1) for l in (raw / s / "session-env.txt").read_text().splitlines() if "=" in l)
           for s in sess}
    matrix: dict = {"rows": {}, "sessions": {}}
    summary: dict = {"experiment": "OWN-16", "sessions": {}, "rows": {}}

    for s in MEASURED:
        recs = sess[s]
        summary["sessions"][s] = {
            "driver_version": env[s].get("driver_version"), "driver_sha256": env[s].get("driver_sha256"),
            "session_atspi": env[s].get("session_atspi"),
            "lock_events": next(r for r in recs if r["event"] == "end")["lock_events"],
            "calls_total": len(calls(recs, ("cold", "warm", "oracle", "usability"))),
            "exceptions": sum(1 for c in calls(recs, ("cold", "warm", "oracle", "usability")) if c.get("exception")),
            "phase_audit": phase_audit(load(raw / s / "phase-m.jsonl")),
            "oracle": oracle_check(raw / s, recs),
            "usability": next((r for r in recs if r["event"] == "usability"), None),
        }

    positive_ok = True
    for row in ROWS:
        rr: dict = {"per_session": {}}
        warm_by_s, cold = {}, []
        all_ok_omit, all_complete, outcomes = True, True, Counter()
        integ = Counter()
        for s in MEASURED:
            recs = sess[s]
            cw = [c for c in calls(recs, ("cold", "warm")) if c["row"] == row]
            both = [c for c in calls(recs, ("cold", "warm")) if c["row"] == "both" and not c.get("exception")]
            ref_count = modal([c["meta"].get("element_count") for c in both])
            ref_digest = modal([c["integrity"].get("elements_digest") for c in both])
            ref_keys = modal([shape_keys(c) for c in both])
            ref_raw_keys = modal([c["structured_keys"] for c in both])
            oc = Counter(outcome(row, c) for c in cw)
            outcomes.update(oc)
            caps = Counter(c["producers"]["capture"] for c in cw if "producers" in c)
            walks = Counter(c["producers"]["walk"] for c in cw if "producers" in c)
            inside = all(c["producers"]["producers_inside_dispatch"] for c in cw if "producers" in c)
            if row in OMITTED:
                omit_zero = sum(1 for c in cw if c["producers"][OMITTED[row]] == 0)
                complete = sum(1 for c in cw if (screenshot_complete(c) if row == "screenshot_only"
                                                 else accessibility_complete(c, ref_count, ref_digest)))
                all_ok_omit &= omit_zero == len(cw) == 21
                all_complete &= complete == len(cw)
            else:
                omit_zero, complete = None, None
            if row == "both":
                positive_ok &= len(cw) == 21 and all(c["producers"]["capture"] == 1 and c["producers"]["walk"] == 1
                                                     for c in cw)
            for c in cw:
                i = c.get("integrity", {})
                integ["frames_outside_window"] += i.get("frames_outside_window") or 0
                integ["screenshot_frames_outside_image"] += i.get("screenshot_frames_outside_image") or 0
                integ["screenshot_frames_inconsistent"] += i.get("screenshot_frames_inconsistent") or 0
                integ["png_dim_mismatch"] += png_matches_reported(c) is False
                integ["screenshot_window_mismatch"] += screenshot_matches_window(c) is False
            warm = [c["wall_ms"] for c in cw if c["phase"] == "warm" and not c.get("exception")]
            warm_by_s[s] = warm
            cold += [{"session": s, "wall_ms": c["wall_ms"], "process_cold": c["index"] == 0}
                     for c in cw if c["phase"] == "cold"]
            pngs = Counter(p["sha256"] for c in cw for p in c.get("content", []) if p["type"] == "image")
            both_pngs = Counter(p["sha256"] for c in both for p in c.get("content", []) if p["type"] == "image")
            rr["per_session"][s] = {
                "n_cold_warm": len(cw), "outcomes": dict(oc), "capture_counts": dict(caps), "walk_counts": dict(walks),
                "producers_inside_dispatch": inside, "omitted_producer_zero": omit_zero, "remaining_complete": complete,
                "warm_median_ms": statistics.median(warm) if warm else None, "warm_p95_ms": p95(warm) if warm else None,
                "response_bytes_median": statistics.median([c["response_bytes"] for c in cw if "response_bytes" in c]),
                "structured_keys_equal_both": all(json.dumps(shape_keys(c), sort_keys=True) == ref_keys for c in cw),
                "structured_keys_equal_both_strict_calls": sum(
                    1 for c in cw if json.dumps(c["structured_keys"], sort_keys=True) == ref_raw_keys),
                "is_error": sorted({c["is_error"] for c in cw}),
                "png_identical_to_both": (set(pngs) <= set(both_pngs)) if pngs else None,
                "dispatch_ms_median": statistics.median([c["producers"]["dispatch_ms"] for c in cw if c["phase"] == "warm"]),
                "walk_span_ms_median": (statistics.median([x for c in cw if c["phase"] == "warm"
                                                           for x in c["producers"]["producer_ms"]["atspi_walk"]])
                                        if any(c["producers"]["producer_ms"]["atspi_walk"] for c in cw) else None),
                "capture_span_ms_median": (statistics.median([x for c in cw if c["phase"] == "warm"
                                                              for x in c["producers"]["producer_ms"]["capture_window"]])
                                           if any(c["producers"]["producer_ms"]["capture_window"] for c in cw) else None),
                "driver_walk_elapsed_ms_median": (statistics.median([c["meta"]["walk_elapsed_ms"] for c in cw
                                                                      if "walk_elapsed_ms" in c.get("meta", {})])
                                                  if any("walk_elapsed_ms" in c.get("meta", {}) for c in cw) else None),
            }
            if row in ("neither", "unknown_field", "wrong_type_supplementary"):
                rr["per_session"][s]["error_texts"] = sorted({c.get("error_text") or "" for c in cw if c["is_error"]})
                rr["per_session"][s]["error_meta"] = sorted({json.dumps(c["meta"], sort_keys=True) for c in cw
                                                             if c["is_error"]})
        pooled = sum(warm_by_s.values(), [])
        rr["warm_n"] = len(pooled)
        rr["warm_median_ms"] = statistics.median(pooled)
        rr["warm_p95_ms"] = p95(pooled)
        rr["cold"] = cold
        rr["outcomes"] = dict(outcomes)
        rr["integrity_violations"] = dict(integ)
        if row != "both":
            point, lo, hi = bootstrap(warm_by_s, {s: [c["wall_ms"] for c in calls(sess[s], ("warm",))
                                                    if c["row"] == "both" and not c.get("exception")]
                                                  for s in MEASURED})
            rr["warm_diff_vs_both_ms"] = {"point": point, "ci95": [lo, hi]}
        # classification
        if row == "both":
            rr["class"] = "positive_control_pass" if positive_ok else "positive_control_FAIL"
        elif row in OMITTED:
            schema_only = outcomes.get("schema_only", 0) > 0
            ignored = outcomes.get("silently_ignored", 0) > 0
            ci_ok = rr["warm_diff_vs_both_ms"]["ci95"][1] < 0
            if schema_only:
                rr["class"] = "schema_only"
            elif ignored or not all_ok_omit:
                rr["class"] = "unsupported_ambiguous"
            elif all_ok_omit and all_complete and ci_ok:
                rr["class"] = "latency_real_selector"
            elif not all_complete:
                rr["class"] = "remaining_modality_incomplete"
            else:
                rr["class"] = "honored_no_latency_gain"
            rr["remaining_truthful"] = all_complete
        elif row in ("neither", "unknown_field"):
            names = {"neither": ("include_accessibility_tree", "include_screenshot"), "unknown_field": ("include_tree",)}[row]
            texts = [t for s in MEASURED for t in rr["per_session"][s].get("error_texts", [])]
            clear = bool(texts) and all(all(n in t for n in names) for t in texts)
            all_rej = outcomes == Counter({"rejected": 42})
            zero = all(rr["per_session"][s]["capture_counts"] == {"0": 21} or rr["per_session"][s]["capture_counts"] == {0: 21}
                       for s in MEASURED) and all(rr["per_session"][s]["walk_counts"] in ({0: 21}, {"0": 21})
                                                  for s in MEASURED)
            rr["class"] = "rejected_explicit" if (all_rej and zero and clear) else "unsupported_ambiguous"
            rr["machine_code"] = sorted({m for s in MEASURED for m in rr["per_session"][s]["error_meta"]})
        elif row == "legacy_omitted":
            ok = outcomes == Counter({"honored": 42}) and all(rr["per_session"][s]["structured_keys_equal_both"]
                                                               for s in MEASURED)
            rr["class"] = "default_honored" if ok else "unsupported_ambiguous"
        else:
            top = outcomes.most_common(1)[0][0]
            rr["class"] = {"silently_ignored": "silently_ignored (supplementary)", "rejected": "rejected (supplementary)",
                           "honored": "honored (supplementary)", "schema_only": "schema_only (supplementary)"}.get(
                top, f"{top} (supplementary)")
        matrix["rows"][row] = {k: rr[k] for k in ("class", "outcomes", "warm_n", "warm_median_ms", "warm_p95_ms")
                               if k in rr}
        matrix["rows"][row]["selector"] = sess["S1"][0]["rows"][row]
        matrix["rows"][row]["capture_counts"] = {s: rr["per_session"][s]["capture_counts"] for s in MEASURED}
        matrix["rows"][row]["walk_counts"] = {s: rr["per_session"][s]["walk_counts"] for s in MEASURED}
        if "warm_diff_vs_both_ms" in rr:
            matrix["rows"][row]["warm_diff_vs_both_ms"] = rr["warm_diff_vs_both_ms"]
        summary["rows"][row] = rr

    # negative control
    n_calls = calls(sess["N1"], ("cold", "warm"))
    req_a11y = [c for c in n_calls if c["row"] in ("both", "accessibility_only")]
    neg_pass = bool(req_a11y) and all(
        not c.get("exception") and c["producers"]["walk"] == 1 and c["meta"].get("degraded") is True
        and bool(c["meta"].get("degraded_reason")) and c["meta"].get("elements_complete") is False
        for c in req_a11y)
    reasons = Counter(re.sub(r"reply-serial: \d+", "reply-serial: N", c["meta"].get("degraded_reason", ""))[:200]
                      for c in req_a11y)
    shot_rows = [c for c in n_calls if c["row"] == "screenshot_only"]
    summary["negative_control"] = {
        "session_atspi": env["N1"].get("session_atspi"), "calls": len(n_calls), "accessibility_requested": len(req_a11y),
        "pass": neg_pass, "walk_counts": dict(Counter(c["producers"]["walk"] for c in req_a11y)),
        "degraded_reasons": dict(reasons),
        "elements_complete": dict(Counter(str(c["meta"].get("elements_complete")) for c in req_a11y)),
        "element_count": dict(Counter(str(c["meta"].get("element_count")) for c in req_a11y)),
        "screenshot_only_walk_counts": dict(Counter(c["producers"]["walk"] for c in shot_rows)),
        "screenshot_only_capture_counts": dict(Counter(c["producers"]["capture"] for c in shot_rows)),
        "accessibility_only_capture_counts": dict(Counter(c["producers"]["capture"] for c in n_calls
                                                          if c["row"] == "accessibility_only")),
        "warm_median_ms": {r: statistics.median([c["wall_ms"] for c in n_calls if c["row"] == r and c["phase"] == "warm"])
                           for r in ("both", "accessibility_only", "screenshot_only")},
        "exceptions": sum(1 for c in n_calls if c.get("exception")),
    }
    # smoke
    d_calls = calls(sess["D1"], ("smoke",))
    shapes = defaultdict(lambda: defaultdict(set))
    for c in d_calls:
        shapes[c["row"]][c["tag"]].add(json.dumps([c.get("structured_keys"), [p["type"] for p in c.get("content", [])],
                                                   c.get("is_error")]))
    shape_identical = {r: len({frozenset(v) for v in t.values()}) == 1 and len(t) == 4 for r, t in shapes.items()}
    files = {r["tag"]: r for r in sess["D1"] if r["event"] == "smoke_files"}
    no_trace = all(not files[t]["trace_file_exists"] and not files[t]["new_files"] for t in ("off_unset", "off_empty", "main_unset"))
    summary["smoke"] = {"calls": len(d_calls), "shape_identical_per_row": shape_identical,
                        "no_trace_file_when_off": no_trace, "trace_file_when_on": files["on"]["trace_file_exists"],
                        "pass": no_trace and all(shape_identical.values()) and len(shape_identical) == len(ROWS),
                        "exceptions": sum(1 for c in d_calls if c.get("exception"))}

    # oracle + overall
    orc_ok = all(summary["sessions"][s]["oracle"]["agree"] == summary["sessions"][s]["oracle"]["calls"] > 0
                 and summary["sessions"][s]["oracle"]["idle_clean"] for s in MEASURED)
    audit_ok = all(summary["sessions"][s]["phase_audit"]["ordinals_gap_free"] for s in MEASURED)
    classes = {r: summary["rows"][r]["class"] for r in ROWS}
    failing = [r for r in MATRIX_ROWS if classes[r] in ("schema_only", "unsupported_ambiguous")]
    untruthful = [r for r in OMITTED if not summary["rows"][r].get("remaining_truthful", True)]
    if not positive_ok:
        overall = "STOP (positive control failed)"
    elif not orc_ok:
        overall = "BLOCKED (oracle disagreement)"
    elif untruthful:
        overall = "KILL"
    elif failing or not summary["negative_control"]["pass"] or not summary["smoke"]["pass"] or not audit_ok:
        overall = "REVISE"
    elif all(classes[r] == "latency_real_selector" for r in OMITTED) and classes["neither"] == "rejected_explicit" \
            and classes["unknown_field"] == "rejected_explicit" and classes["legacy_omitted"] == "default_honored":
        overall = "KEEP"
    else:
        overall = "REVISE"
    summary["overall"] = {"disposition": overall, "row_classes": classes, "revise_rows": failing,
                          "untruthful_rows": untruthful, "positive_control": positive_ok, "oracle_corroborated": orc_ok,
                          "ordinals_gap_free": audit_ok,
                          "negative_control": summary["negative_control"]["pass"], "smoke": summary["smoke"]["pass"]}
    matrix["overall"] = summary["overall"]
    matrix["sessions"] = {s: {"driver_sha256": env[s].get("driver_sha256"), "driver_version": env[s].get("driver_version")}
                          for s in sess}
    return matrix, summary


def main() -> None:
    pkt = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)
    matrix, summary = analyze(pkt)
    (pkt / "own-16-matrix.json").write_text(json.dumps(matrix, indent=1, sort_keys=True) + "\n")
    (pkt / "own-16-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary["overall"], indent=1))


if __name__ == "__main__":
    main()
