#!/usr/bin/env python3
"""OWN-16W analysis: recompute the per-mode truth matrix, controls, timing and dispositions from raw/.

stdlib only. Usage: python3 analyze.py [--packet DIR] [--write]
Without --write it prints the summary JSON; with --write it writes own-16w-summary.json.
Adapted in structure from OWN-16's analyze.py (7a4f3252a); the gates are PREREG.json's.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PKT = [HERE]
MODES = ("SW", "SX", "X11")
SWAY_ROWS = ("both", "screenshot_only", "accessibility_only", "neither", "legacy_omitted",
             "unknown_field", "string_false", "string_true")
X11_ROWS = ("both", "string_false", "string_true")
OMIT = {"screenshot_only": "walk", "accessibility_only": "capture"}
STRING_ROWS = ("string_false", "string_true")
SEED = 1616
RESAMPLES = 10000


def load(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(x) for x in stream if x.strip()]


def session_env(d: Path) -> dict[str, str]:
    out = {}
    p = d / "session-env.txt"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


def calls_path(d: Path) -> Path:
    for name in ("calls.jsonl", "calls.jsonl.gz"):
        if (d / name).exists():
            return d / name
    raise FileNotFoundError(d / "calls.jsonl")


def capture_oracle(mode: str, w: dict[str, Any]) -> int:
    """Target-owned capture oracle per mode: compositor protocol log (SW), X RECORD (SX, X11)."""
    if mode == "SW":
        return w.get("wl_capture_requests", 0)
    return w.get("x_getimage", 0) + w.get("x_shmgetimage", 0)


def screenshot_complete(c: dict[str, Any]) -> bool:
    has, meta, integ, prod = c.get("has", {}), c.get("meta", {}), c.get("integrity", {}), c.get("producers", {})
    return (has.get("image_part") is True and integ.get("png_matches_reported_dims") is True
            and meta.get("screenshot_frame_valid") is True and not has.get("screenshot_error")
            and integ.get("screenshot_matches_window") is True and prod.get("capture") == 1)


def accessibility_complete(c: dict[str, Any], ref: dict[str, Any]) -> bool:
    has, meta, integ, prod = c.get("has", {}), c.get("meta", {}), c.get("integrity", {}), c.get("producers", {})
    return (has.get("elements") is True and meta.get("elements_complete") is True
            and meta.get("truncated") is False and not has.get("degraded")
            and meta.get("element_count") == ref.get("element_count")
            and integ.get("elements_digest") == ref.get("digest")
            and prod.get("walk") == 1)


def modal(values: list[Any]) -> Any:
    vals = [json.dumps(v, sort_keys=True) for v in values]
    return json.loads(max(set(vals), key=vals.count)) if vals else None


def truth_session(mode: str, d: Path) -> dict[str, Any]:
    recs = load(calls_path(d))
    calls = [r for r in recs if r.get("event") == "call" and r.get("phase") in ("cold", "warm")]
    windows = {w["index"]: w for w in recs if w.get("event") == "oracle_window" and w.get("kind") == "call"}
    idle = [w for w in recs if w.get("event") == "oracle_window" and w.get("kind") == "idle"]
    summary = next((r for r in recs if r.get("event") == "oracle_summary"), {})
    use = next((r for r in recs if r.get("event") == "usability"), {})
    meta = next((r for r in recs if r.get("event") == "meta"), {})
    both = [c for c in calls if c["row"] == "both" and not c.get("is_error")]
    ref = {"element_count": modal([c.get("meta", {}).get("element_count") for c in both]),
           "digest": modal([c.get("integrity", {}).get("elements_digest") for c in both]),
           "keys": modal([c.get("structured_keys") for c in both])}
    rows: dict[str, Any] = {}
    exceptions = sum(1 for c in calls if "exception" in c)
    for row in sorted({c["row"] for c in calls}):
        rc = [c for c in calls if c["row"] == row]
        ent: dict[str, Any] = {"n": len(rc), "exceptions": sum(1 for c in rc if "exception" in c)}
        ent["is_error"] = sum(1 for c in rc if c.get("is_error"))
        ent["capture_mark_dist"] = _dist(c.get("producers", {}).get("capture") for c in rc)
        ent["walk_mark_dist"] = _dist(c.get("producers", {}).get("walk") for c in rc)
        ent["producers_inside_dispatch"] = sum(1 for c in rc if c.get("producers", {}).get("producers_inside_dispatch"))
        ow = [windows.get(c["index"], {}) for c in rc]
        ent["oracle_windows"] = sum(1 for w in ow if w)
        ent["capture_oracle_dist"] = _dist(capture_oracle(mode, w) for w in ow if w)
        ent["x_image_reads_dist"] = _dist(w.get("x_getimage", 0) + w.get("x_shmgetimage", 0) for w in ow if w)
        ent["wl_capture_requests_dist"] = _dist(w.get("wl_capture_requests", 0) for w in ow if w)
        ent["atspi_calls_to_fixture_dist"] = _dist(w.get("atspi_calls_to_fixture", 0) for w in ow if w)
        ent["walk_oracle_dist"] = _dist(w.get("atspi_getstate_to_fixture", 0) for w in ow if w)
        ent["oracle_capture_agrees"] = sum(
            1 for c, w in zip(rc, ow) if w and (capture_oracle(mode, w) > 0) == (c.get("producers", {}).get("capture", 0) > 0))
        ent["oracle_walk_agrees"] = sum(
            1 for c, w in zip(rc, ow) if w and (w.get("atspi_getstate_to_fixture", 0) > 0) == (c.get("producers", {}).get("walk", 0) > 0))
        ent["screenshot_complete"] = sum(1 for c in rc if screenshot_complete(c))
        ent["accessibility_complete"] = sum(1 for c in rc if accessibility_complete(c, ref))
        ent["keys_equal_both"] = sum(1 for c in rc if [k for k in (c.get("structured_keys") or []) if k != "invalidated_snapshot_ids"]
                                     == [k for k in (ref["keys"] or []) if k != "invalidated_snapshot_ids"])
        ent["error_codes"] = _dist((c.get("meta", {}).get("code") for c in rc if c.get("is_error")))
        ent["error_text_heads"] = sorted({(c.get("error_text") or "")[:160] for c in rc if c.get("is_error")})
        ent["names_field"] = sum(1 for c in rc if c.get("is_error") and any(
            f in (c.get("error_text") or "") for f in ("include_screenshot", "include_accessibility_tree", "include_tree")))
        ent["frames_outside_window_dist"] = _dist(c.get("integrity", {}).get("frames_outside_window") for c in rc if c.get("has", {}).get("elements"))
        ent["png_dims"] = _dist(tuple(p.get("png_dims") or []) for c in rc for p in c.get("content", []) if p.get("type") == "image")
        ent["frame_scale"] = _dist(c.get("meta", {}).get("frame_scale") for c in rc if c.get("has", {}).get("screenshot_fields"))
        ent["screenshot_original_width"] = _dist(c.get("meta", {}).get("screenshot_original_width") for c in rc if c.get("has", {}).get("screenshot_fields"))
        ent["window_bounds"] = _dist(json.dumps(c.get("meta", {}).get("window_bounds"), sort_keys=True) for c in rc if c.get("meta", {}).get("window_bounds"))
        ent["degraded"] = sum(1 for c in rc if c.get("has", {}).get("degraded"))
        rows[row] = ent
    return {"dir": str(d.relative_to(PKT[0])), "env": session_env(d), "meta_rotation": meta.get("rotation"),
            "binary_tag": meta.get("binary_tag"), "calls": len(calls), "exceptions": exceptions,
            "ref_both": ref, "rows": rows, "oracle_summary": summary,
            "idle_windows": [{k: w.get(k) for k in ("x_getimage", "x_shmgetimage", "atspi_calls_to_fixture", "atspi_getstate_to_fixture", "wl_capture_requests")} for w in idle],
            "usability": {k: use.get(k) for k in ("token_found", "click_is_error", "click_structured", "click_error_text",
                                                  "before_counter", "after_counter", "before_seq", "after_seq", "oracle_verified")},
            "ordinal_audit": ordinal_audit(d)}


def ordinal_audit(d: Path) -> dict[str, Any]:
    """Every producer mark of the full trace lies in a get_window_state dispatch and ordinals are gap-free."""
    trace = next((p for p in (d / "phase-t.jsonl.gz", d / "phase-t.jsonl") if p.exists()), None)
    if trace is None:
        return {"present": False}
    marks = load(trace)
    out: dict[str, Any] = {"present": True}
    open_dispatch = False
    outside = 0
    for m in marks:
        if m.get("scope") == "get_window_state" and m.get("mark") == "dispatch_enter":
            open_dispatch = True
        elif m.get("scope") == "get_window_state" and m.get("mark") == "dispatch_exit":
            open_dispatch = False
        elif m.get("scope") in ("capture_window", "capture_root_region", "atspi_walk") and not open_dispatch:
            outside += 1
    out["producer_marks_outside_gws_dispatch"] = outside
    for scope in ("capture_window", "capture_root_region", "atspi_walk"):
        ns = [m.get("n") for m in marks if m.get("scope") == scope and m.get("mark") == "enter"]
        out[scope] = {"count": len(ns), "gap_free": ns == list(range(1, len(ns) + 1))}
    return out


def _dist(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        key = json.dumps(v) if not isinstance(v, str) else v
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def pooled(sessions: list[dict[str, Any]], row: str) -> dict[str, Any]:
    ents = [s["rows"].get(row) for s in sessions if row in s["rows"]]
    keys = ("n", "exceptions", "is_error", "oracle_windows", "oracle_capture_agrees", "oracle_walk_agrees",
            "screenshot_complete", "accessibility_complete", "keys_equal_both", "names_field", "degraded",
            "producers_inside_dispatch")
    out = {k: sum(e.get(k, 0) for e in ents) for k in keys}
    for k in ("capture_mark_dist", "walk_mark_dist", "capture_oracle_dist", "atspi_calls_to_fixture_dist", "walk_oracle_dist", "error_codes"):
        merged: dict[str, int] = {}
        for e in ents:
            for kk, vv in e.get(k, {}).items():
                merged[kk] = merged.get(kk, 0) + vv
        out[k] = dict(sorted(merged.items()))
    return out


def count0(dist: dict[str, int]) -> int:
    return dist.get("0", 0)


def classify_row(row: str, p: dict[str, Any], binary: str) -> str:
    n = p["n"]
    full = n > 0 and p["exceptions"] == 0
    cap0, walk0 = count0(p["capture_mark_dist"]), count0(p["walk_mark_dist"])
    ocap0, owalk0 = count0(p["capture_oracle_dist"]), count0(p["walk_oracle_dist"])
    agree = p["oracle_capture_agrees"] == n and p["oracle_walk_agrees"] == n and p["oracle_windows"] == n
    if row == "both":
        ok = full and p["capture_mark_dist"].get("1", 0) == n and p["walk_mark_dist"].get("1", 0) == n and agree \
            and p["is_error"] == 0
        return "positive_control_pass" if ok else "positive_control_fail"
    if row in OMIT:
        omitted = OMIT[row]
        if omitted == "walk":
            ran = n - walk0 + (n - owalk0)
            complete = p["screenshot_complete"] == n
        else:
            ran = n - cap0 + (n - ocap0)
            complete = p["accessibility_complete"] == n
        if ran > 0:
            return "omitted_producer_ran"
        return "honored_complete" if (full and complete and agree and p["is_error"] == 0) else "honored_partial"
    if row in ("neither", "unknown_field"):
        ok = full and p["is_error"] == n and cap0 == n and walk0 == n and ocap0 == n and owalk0 == n and p["names_field"] == n
        return "rejected_explicit" if ok else "not_rejected_cleanly"
    if row == "legacy_omitted":
        ok = full and p["is_error"] == 0 and p["capture_mark_dist"].get("1", 0) == n and p["walk_mark_dist"].get("1", 0) == n and agree
        return "default_honored" if ok else "default_not_honored"
    if row in STRING_ROWS:
        if p["is_error"] == n and cap0 == n and walk0 == n and ocap0 == n and owalk0 == n:
            codes = p["error_codes"]
            return "refused_invalid_arguments" if codes.get("invalid_arguments", 0) == n and p["names_field"] == n else "refused_other"
        if p["is_error"] == 0 and p["capture_mark_dist"].get("1", 0) == n and p["walk_mark_dist"].get("1", 0) == n:
            return "silently_accepted_default"
        return "mixed"
    return "unclassified"


def bootstrap_median_diff(pairs_by_session: dict[str, list[float]]) -> dict[str, Any]:
    rng = random.Random(SEED)
    allv = [v for vs in pairs_by_session.values() for v in vs]
    if not allv:
        return {}
    meds = []
    for _ in range(RESAMPLES):
        sample = []
        for vs in pairs_by_session.values():
            sample.extend(rng.choice(vs) for _ in vs)
        meds.append(statistics.median(sample))
    meds.sort()
    return {"n_pairs": len(allv), "median_paired_diff_ms": round(statistics.median(allv), 3),
            "ci95": [round(meds[int(0.025 * RESAMPLES)], 3), round(meds[int(0.975 * RESAMPLES) - 1], 3)]}


def timing_mode(dirs: list[Path]) -> dict[str, Any]:
    out: dict[str, Any] = {"sessions": [], "comparisons": {}}
    per_comp: dict[str, dict[str, list[float]]] = {"screenshot_only": {}, "accessibility_only": {}}
    walls: dict[str, list[float]] = {}
    split: dict[str, dict[str, list[float]]] = {}
    for d in dirs:
        recs = load(calls_path(d))
        timed = [r for r in recs if r.get("event") == "call" and r.get("phase") == "timed"]
        out["sessions"].append({"dir": str(d.relative_to(PKT[0])), "env": session_env(d), "timed_calls": len(timed),
                                "exceptions": sum(1 for r in timed if "exception" in r),
                                "errors": sum(1 for r in timed if r.get("is_error")),
                                "loadavg_1m_range": [min(r["loadavg"][0] for r in timed), max(r["loadavg"][0] for r in timed)] if timed else None,
                                "producer_check": {row: _dist((r.get("producers", {}).get("capture"), r.get("producers", {}).get("walk"))
                                                              for r in timed if r["row"] == row) for row in ("both", "screenshot_only", "accessibility_only")}})
        by_pair: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}
        for r in timed:
            by_pair.setdefault((r["pair"], r["comparison"]), {})[r["row"]] = r
            walls.setdefault(r["row"], []).append(r["wall_ms"])
        for (p, comp), rr in sorted(by_pair.items()):
            if "both" in rr and comp in rr and "exception" not in rr["both"] and "exception" not in rr[comp]:
                diff = rr[comp]["wall_ms"] - rr["both"]["wall_ms"]
                per_comp[comp].setdefault(d.name, []).append(diff)
                split.setdefault(f"{comp}:{rr[comp]['order']}", {}).setdefault(d.name, []).append(diff)
    for comp, by_s in per_comp.items():
        out["comparisons"][comp] = bootstrap_median_diff(by_s)
        out["comparisons"][comp]["by_order"] = {k.split(":")[1]: round(statistics.median([v for vs in s.values() for v in vs]), 3)
                                                for k, s in split.items() if k.startswith(comp + ":")}
    out["wall_median_ms"] = {row: round(statistics.median(v), 3) for row, v in walls.items()}
    out["wall_p95_ms"] = {row: round(sorted(v)[max(0, int(0.95 * len(v) + 0.999999) - 1)], 3) for row, v in walls.items()}
    return out


def negative(d: Path) -> dict[str, Any]:
    recs = load(calls_path(d))
    calls = [r for r in recs if r.get("event") == "call"]
    acc = [c for c in calls if c["row"] in ("both", "accessibility_only")]
    ok = [c for c in acc if c.get("producers", {}).get("walk") == 1 and c.get("meta", {}).get("degraded") is True
          and (c.get("meta", {}).get("degraded_reason") or "") and c.get("meta", {}).get("elements_complete") is False]
    so = [c for c in calls if c["row"] == "screenshot_only"]
    return {"dir": str(d.relative_to(PKT[0])), "env": session_env(d), "accessibility_requesting_calls": len(acc),
            "degraded_explicit": len(ok), "pass": len(acc) > 0 and len(ok) == len(acc),
            "degraded_reason_heads": sorted({(c.get("meta", {}).get("degraded_reason") or "")[:140] for c in acc}),
            "screenshot_only_walk0": sum(1 for c in so if c.get("producers", {}).get("walk") == 0),
            "screenshot_only_n": len(so),
            "errors": _dist((c["row"], (c.get("error_text") or "")[:120]) for c in calls if c.get("is_error"))}


def smoke(d: Path) -> dict[str, Any]:
    recs = load(calls_path(d))
    calls = [r for r in recs if r.get("event") == "call"]
    files = [r for r in recs if r.get("event") == "smoke_files"]
    shapes: dict[str, dict[str, set]] = {}
    for c in calls:
        shape = json.dumps([[k for k in (c.get("structured_keys") or []) if k != "invalidated_snapshot_ids"],
                            [p.get("type") for p in c.get("content", [])], bool(c.get("is_error"))])
        shapes.setdefault(c["tag"], {}).setdefault(c["row"], set()).add(shape)
    rows = sorted({c["row"] for c in calls})
    same_u = {row: len(set().union(*(shapes.get(t, {}).get(row, set()) for t in ("off_unset", "off_empty", "on")))) == 1
              for row in rows}
    alt_same = {row: shapes.get("alt_unset", {}).get(row) == shapes.get("off_unset", {}).get(row) for row in rows}
    trace_ok = all((f["tag"] == "on") == f["trace_file_exists"] for f in files) and all(
        not f["new_files"] for f in files if f["tag"] != "on")
    return {"dir": str(d.relative_to(PKT[0])), "env": session_env(d), "calls": len(calls),
            "trace_files": [{k: f[k] for k in ("tag", "binary", "trace_file_exists", "new_files")} for f in files],
            "trace_ok": trace_ok, "u_shapes_identical_unset_empty_on": same_u, "alt_unset_shape_equal_u_unset": alt_same,
            "pass": trace_ok and all(same_u.values()) and all(v for r, v in alt_same.items() if r not in STRING_ROWS)}


def mode_disposition(mode: str, rows_u: dict[str, str], rows_f: dict[str, str], usability_ok: bool,
                     negative_ok: bool | None) -> dict[str, Any]:
    reasons = []
    if mode == "X11":
        ok = (rows_u.get("both") == rows_f.get("both") == "positive_control_pass"
              and all(rows_f.get(r) == "refused_invalid_arguments" for r in STRING_ROWS))
        return {"disposition": "KEEP" if ok else "REVISE", "reasons": [] if ok else ["string rows not refused on F or positive control failed"]}
    for tag, rows in (("U", rows_u), ("F", rows_f)):
        for r, cls in rows.items():
            if cls == "omitted_producer_ran":
                return {"disposition": "KILL", "reasons": [f"{tag} {r}: omitted producer ran"]}
            if cls == "positive_control_fail":
                return {"disposition": "STOP", "reasons": [f"{tag} positive control failed"]}
    expected = {"screenshot_only": "honored_complete", "accessibility_only": "honored_complete",
                "neither": "rejected_explicit", "unknown_field": "rejected_explicit", "legacy_omitted": "default_honored"}
    for tag, rows in (("U", rows_u), ("F", rows_f)):
        for r, want in expected.items():
            if rows.get(r) != want:
                reasons.append(f"{tag} {r}: {rows.get(r)}")
    for r in STRING_ROWS:
        if rows_f.get(r) != "refused_invalid_arguments":
            reasons.append(f"F {r}: {rows_f.get(r)}")
    if not usability_ok:
        reasons.append("token click not verified in every truth session")
    if negative_ok is False:
        reasons.append("negative control failed")
    return {"disposition": "KEEP" if not reasons else "REVISE", "reasons": reasons}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", default=str(HERE))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    PKT[0] = Path(a.packet).resolve()
    raw = PKT[0] / "raw"
    summary: dict[str, Any] = {"schema": "cua.r2.own16w.summary.v1", "modes": {}}
    for mode in MODES:
        mdir = raw / mode
        if not mdir.exists():
            continue
        m: dict[str, Any] = {"truth": {}, "rows": {}}
        for binary in ("U", "F"):
            sess = [truth_session(mode, d) for d in sorted((mdir / binary).glob("T*")) if d.is_dir()]
            m["truth"][binary] = sess
            rows = sorted({r for s in sess for r in s["rows"]})
            m["rows"][binary] = {r: {"pooled": pooled(sess, r), "class": classify_row(r, pooled(sess, r), binary)} for r in rows}
        sess_all = m["truth"]["U"] + m["truth"]["F"]
        usability_ok = bool(sess_all) and all(s["usability"].get("oracle_verified") is True for s in sess_all)
        neg = [negative(d) for d in sorted((mdir / "U").glob("N*")) if d.is_dir()]
        m["negative"] = neg
        m["timing"] = timing_mode(sorted(d for d in (mdir / "U").glob("B*") if d.is_dir())) if list((mdir / "U").glob("B*")) else None
        m["smoke"] = [smoke(d) for d in sorted(mdir.glob("D*")) if d.is_dir()]
        m["disposition"] = mode_disposition(
            mode, {r: v["class"] for r, v in m["rows"]["U"].items()}, {r: v["class"] for r, v in m["rows"]["F"].items()},
            usability_ok if mode != "X11" else True, (all(n["pass"] for n in neg) if neg else None))
        m["usability_verified_sessions"] = f"{sum(1 for s in sess_all if s['usability'].get('oracle_verified') is True)}/{len(sess_all)}"
        summary["modes"][mode] = m
    text = json.dumps(summary, indent=1, sort_keys=True)
    if a.write:
        (Path(a.packet) / "own-16w-summary.json").write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
