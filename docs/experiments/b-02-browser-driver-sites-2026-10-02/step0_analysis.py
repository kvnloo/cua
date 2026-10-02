"""B-02 STEP 0 (fix round): summarize the browser localization probes (excluded from gates).

    python3 step0_analysis.py <raw-dir-or-tar.gz> [--out step0-summary.json]

Per probe trial (step0_probe.py) it reads the Driver phase trace and the runner events:

- each Driver snapshot (snapA1, snapA2, snapB1, snapB2, snapC1_after_raw, snapD1_after_1s): the
  snap.enter -> snap.serialized total and the CDP sub-spans (attach, DOM.getDocument,
  Page.getFrameTree, DOMSnapshot+layout, AX tree);
- the raw second-process CDP timings (rawA on the warm document, rawC first on a cold document);
- the endpoint proof sub-spans of every full discovery (ep.family_scanned, ep.fds_scanned,
  ep.net_parsed, ep.json_version) and the reval.native_window -> reval.endpoint interval;
- the second Driver process bind outcome.

Then it applies the W decision rule of PREREG-AMENDMENT-1.json.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tarfile
from pathlib import Path
from typing import Any

SNAPS = ["snapA1", "snapA2", "snapB1", "snapB2", "snapC1_after_raw", "snapD1_after_1s"]
SUB = [("attach", "snap.enter", "snap.attached"), ("dom_get_document", "snap.attached", "snap.document"),
       ("frame_tree", "snap.document", "snap.frame_tree"), ("layout_snapshot", "snap.frame_tree", "snap.layout_cdp_done"),
       ("ax_tree", "snap.indexed", "snap.ax_cdp_done"), ("total", "snap.enter", "snap.serialized")]
EP = ["ep.family_scanned", "ep.fds_scanned", "ep.net_parsed", "ep.json_version"]


def files(src: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if src.is_dir():
        for p in (src / "trials").glob("*.jsonl"):
            out[f"trials/{p.name}"] = p.read_text()
    else:
        with tarfile.open(src, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.endswith(".jsonl"):
                    out[m.name.removeprefix("./")] = tar.extractfile(m).read().decode()
    return out


def med(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 3) if xs else None


def windows(events: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    out, open_ = {}, {}
    for e in events:
        if e["event"] == "call_send":
            open_[e["label"]] = e["t_mono_ns"]
        elif e["event"] == "call_return" and e["label"] in open_:
            out[e["label"]] = (open_.pop(e["label"]), e["t_mono_ns"])
    return out


def snap_spans(trace: list[dict[str, Any]], w: tuple[int, int]) -> dict[str, float]:
    marks = {}
    for m in trace:
        if w[0] <= m["t_mono_ns"] <= w[1] and m["phase"].startswith("snap.") and m["phase"] not in marks:
            marks[m["phase"]] = m["t_mono_ns"]
    out = {}
    for name, a, b in SUB:
        if a in marks and b in marks:
            out[name] = (marks[b] - marks[a]) / 1e6
    out["call_ms"] = (w[1] - w[0]) / 1e6
    return out


def endpoint_proofs(trace: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Each full discovery: the intervals between consecutive ep.* marks, plus the preceding gap."""
    proofs, i = [], 0
    while i < len(trace):
        if trace[i]["phase"] == "ep.family_scanned":
            seq = trace[i:i + 4]
            if [m["phase"] for m in seq] == EP:
                start = trace[i - 1]["t_mono_ns"] if i > 0 else seq[0]["t_mono_ns"]
                proofs.append({"before_family_scan_mark_ms": (seq[0]["t_mono_ns"] - start) / 1e6,
                               "fds_scan_ms": (seq[1]["t_mono_ns"] - seq[0]["t_mono_ns"]) / 1e6,
                               "net_parse_ms": (seq[2]["t_mono_ns"] - seq[1]["t_mono_ns"]) / 1e6,
                               "json_version_ms": (seq[3]["t_mono_ns"] - seq[2]["t_mono_ns"]) / 1e6,
                               "family_detail": seq[0].get("detail"), "json_detail": seq[3].get("detail"),
                               "left_mark": trace[i - 1]["phase"] if i > 0 else None})
                i += 4
                continue
        i += 1
    return proofs


def reval_endpoint(trace: list[dict[str, Any]]) -> list[float]:
    out, t = [], None
    for m in trace:
        if m["phase"] == "reval.native_window":
            t = m["t_mono_ns"]
        elif m["phase"] == "reval.endpoint" and t is not None:
            out.append((m["t_mono_ns"] - t) / 1e6)
            t = None
    return out


def build(src: Path) -> dict[str, Any]:
    fs = files(src)
    trials = []
    for name in sorted(fs):
        if not name.endswith(".jsonl") or "driver-trace" in name:
            continue
        lines = [json.loads(x) for x in fs[name].splitlines() if x.strip()]
        s = lines[-1]
        if s.get("event") != "summary":
            continue
        trace = [json.loads(x) for x in fs.get(s["driver_trace"], "").splitlines() if x.strip()]
        w = windows(lines[:-1])
        snaps = {k: snap_spans(trace, w[k]) for k in SNAPS if k in w}
        trials.append({"trial": s["trial"], "cls": s["cls"], "snaps": snaps,
                       "rawA": s.get("rawA_warm_doc_second_process"), "rawC": s.get("rawC_cold_doc_second_process"),
                       "second_driver_bind": s.get("second_driver_bind"), "proofs": endpoint_proofs(trace),
                       "reval_endpoint_ms": reval_endpoint(trace), "loadavg_before": s.get("loadavg_before")})
    out: dict[str, Any] = {"trials": len(trials), "classes": {}}
    for cls in ("fill", "toggle", "modal"):
        ts = [t for t in trials if t["cls"] == cls and all(k in t["snaps"] for k in SNAPS)]
        if not ts:
            continue
        c: dict[str, Any] = {"n": len(ts)}
        for k in SNAPS:
            c[k] = {name: med([t["snaps"][k][name] for t in ts if name in t["snaps"][k]])
                    for name, _a, _b in SUB}
        tot = {k: [t["snaps"][k]["total"] for t in ts] for k in SNAPS}
        att = {k: [t["snaps"][k]["attach"] for t in ts] for k in SNAPS}
        exA = [a - b for a, b in zip(tot["snapA1"], tot["snapA2"])]
        exB = [a - b for a, b in zip(tot["snapB1"], tot["snapB2"])]
        exC = [a - b for a, b in zip(tot["snapC1_after_raw"], tot["snapB2"])]
        exD = [a - b for a, b in zip(tot["snapD1_after_1s"], tot["snapB2"])]
        attA = [a - b for a, b in zip(att["snapA1"], att["snapA2"])]
        c["excess"] = {"A1_minus_A2": med(exA), "B1_minus_B2": med(exB), "C1_minus_B2": med(exC),
                       "D1_minus_B2": med(exD), "attach_A1_minus_A2": med(attA),
                       "attach_per_call_A2": med(att["snapA2"])}
        by_sub = {}
        for name, _a, _b in SUB[:-1]:
            by_sub[name] = {"A1_minus_A2": med([t["snaps"]["snapA1"][name] - t["snaps"]["snapA2"][name] for t in ts]),
                            "B1_minus_B2": med([t["snaps"]["snapB1"][name] - t["snaps"]["snapB2"][name] for t in ts]),
                            "D1_minus_B2": med([t["snaps"]["snapD1_after_1s"][name] - t["snaps"]["snapB2"][name] for t in ts])}
        c["excess_by_subspan"] = by_sub
        rawc = [t["rawC"] for t in ts if t["rawC"] and "total" in t["rawC"]]
        rawa = [t["rawA"] for t in ts if t["rawA"] and "total" in t["rawA"]]
        c["raw_second_process"] = {
            "rawC_cold_first": {k: med([r[k] for r in rawc]) for k in ("attach", "dom_get_document", "frame_tree",
                                                                       "layout_snapshot", "ax_tree", "total")},
            "rawA_warm": {k: med([r[k] for r in rawa]) for k in ("attach", "dom_get_document", "frame_tree",
                                                                 "layout_snapshot", "ax_tree", "total")}}
        proofs = [p for t in ts for p in t["proofs"]]
        c["endpoint_full_proof"] = {
            "n": len(proofs), **{k: med([p[k] for p in proofs]) for k in ("before_family_scan_mark_ms", "fds_scan_ms",
                                                                            "net_parse_ms", "json_version_ms")},
            "reval_native_window_to_endpoint_ms": med([x for t in ts for x in t["reval_endpoint_ms"]]),
            "family_detail_example": proofs[0]["family_detail"] if proofs else None}
        a, b = c["excess"]["A1_minus_A2"], c["excess"]["B1_minus_B2"]
        rules = []
        if a and a > 0:
            if b is not None and b <= 0.25 * a:
                rules.append("per-process first use")
            if b is not None and b >= 0.5 * a and c["excess"]["C1_minus_B2"] is not None and c["excess"]["C1_minus_B2"] <= 0.5 * b:
                rules.append("per-document (first observer pays)")
            if b is not None and b >= 0.5 * a and c["excess"]["D1_minus_B2"] is not None and c["excess"]["D1_minus_B2"] <= 0.5 * b:
                rules.append("load timing")
            reuse = (c["excess"]["attach_A1_minus_A2"] or 0) + (c["excess"]["attach_per_call_A2"] or 0)
            c["session_reuse_bound_ms"] = round(reuse, 3)
            c["session_reuse_bound_share_of_excess"] = round(reuse / a, 3)
            c["w_knob_justified"] = reuse >= 0.5 * a
        c["rules_fired"] = rules
        out["classes"][cls] = c
    out["second_driver_bind"] = sorted({json.dumps(t["second_driver_bind"], sort_keys=True) for t in trials})
    out["per_trial"] = [{"trial": t["trial"], "totals": {k: round(v["total"], 3) for k, v in t["snaps"].items()
                                                          if "total" in v}} for t in trials]
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("--out")
    a = p.parse_args()
    res = build(Path(a.src))
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
