"""Read-only re-analysis of B-01's committed REAL traces for B-02 STEP 0 (localization only).

    python b01_snapshot_reanalysis.py [--out raw/b01-trace-reanalysis.json]

Source: B-01 packet raw/trials-measured.tar.gz at commit 6689610d5 (read with ``git show``;
B-01 is PENDING, so these are B-01's numbers, not B-02 measurements). Per class, over every
measured trial: the first vs second semantic_v2 snapshot by Driver sub-span, the owned-endpoint
re-proof span per mutation (reval.native_window -> reval.endpoint) and the MCP admission span
per tools/call (mcp.line_read -> mcp.inner_validated).
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import subprocess
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
B01_COMMIT = "6689610d5a2619cb45dd4328b2921c89f88967be"
B01_TAR = "docs/experiments/b-01-browser-critpath-2026-10-02/raw/trials-measured.tar.gz"
SNAP = ["snap.enter", "snap.attached", "snap.document", "snap.frame_tree", "snap.layout_cdp_done", "snap.indexed",
        "snap.ax_cdp_done", "snap.ax_composed", "snap.collected", "snap.stored"]
LABEL = {"snap.attached": "attach (Target.attachToTarget)", "snap.document": "DOM.getDocument",
         "snap.frame_tree": "Page.getFrameTree", "snap.layout_cdp_done": "DOMSnapshot+layout metrics",
         "snap.indexed": "indexing", "snap.ax_cdp_done": "Accessibility.getFullAXTree",
         "snap.ax_composed": "AX composition", "snap.collected": "collect tail", "snap.stored": "page/outcome/store"}


def med(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 3) if xs else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "raw" / "b01-trace-reanalysis.json"))
    a = ap.parse_args()
    blob = subprocess.run(["git", "show", f"{B01_COMMIT}:{B01_TAR}"], cwd=HERE, capture_output=True, check=True).stdout
    blob_sha = subprocess.run(["git", "rev-parse", f"{B01_COMMIT}:{B01_TAR}"], cwd=HERE, capture_output=True,
                              text=True, check=True).stdout.strip()
    traces: dict[str, list[dict]] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile() and m.name.endswith(".driver-trace.jsonl"):
                text = tar.extractfile(m).read().decode()
                traces[Path(m.name).name] = [json.loads(line) for line in text.splitlines() if line.strip()]
    out: dict = {"source": {"commit": B01_COMMIT, "path": B01_TAR, "blob": blob_sha, "traces": len(traces)},
                 "evidence_class": "REAL (B-01's run, re-analysed read-only; B-01 pending)", "classes": {}}
    for cls in ("fill", "toggle", "modal"):
        first: dict[str, list[float]] = {}
        second: dict[str, list[float]] = {}
        endpoint, admission, n = [], [], 0
        for name, rows in traces.items():
            if f"-{cls}-" not in name:
                continue
            n += 1
            snaps, cur = [], None
            for r in rows:
                p = r["phase"]
                if p == "snap.enter":
                    cur = {p: r["t_mono_ns"]}
                elif cur is not None and p in SNAP:
                    cur.setdefault(p, r["t_mono_ns"])
                    if p == "snap.stored":
                        snaps.append(cur)
                        cur = None
            for i, r in enumerate(rows):
                if r["phase"] == "reval.endpoint" and i and rows[i - 1]["phase"] == "reval.native_window":
                    endpoint.append((r["t_mono_ns"] - rows[i - 1]["t_mono_ns"]) / 1e6)
            start = None
            for r in rows:
                if r["phase"] == "mcp.line_read":
                    start = r["t_mono_ns"]
                elif r["phase"] == "mcp.inner_validated" and start is not None:
                    admission.append((r["t_mono_ns"] - start) / 1e6)
                    start = None
            # The snapshots after navigate: B-01 trials take exactly two semantic_v2 snapshots in T.
            post = [s for s in snaps if "snap.document" in s][-2:]
            if len(post) == 2:
                for k, s in enumerate(post):
                    prev = "snap.enter"
                    dst = first if k == 0 else second
                    for sp in SNAP[1:]:
                        if sp in s and prev in s:
                            dst.setdefault(sp, []).append((s[sp] - s[prev]) / 1e6)
                            prev = sp
                    dst.setdefault("total", []).append((s["snap.stored"] - s["snap.enter"]) / 1e6)
        rows_out = {}
        for sp in SNAP[1:] + ["total"]:
            f, s = med(first.get(sp, [])), med(second.get(sp, []))
            rows_out[LABEL.get(sp, sp)] = {"first_median_ms": f, "second_median_ms": s,
                                          "excess_ms": None if f is None or s is None else round(f - s, 3)}
        out["classes"][cls] = {"trials": n, "snapshot_first_vs_second": rows_out,
                               "endpoint_reproof_per_mutation_median_ms": med(endpoint), "endpoint_n": len(endpoint),
                               "admission_span_per_call_median_ms": med(admission), "admission_n": len(admission)}
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for cls, c in out["classes"].items():
        print(cls, c["endpoint_reproof_per_mutation_median_ms"], c["admission_span_per_call_median_ms"],
              {k: v["excess_ms"] for k, v in c["snapshot_first_vs_second"].items()})


if __name__ == "__main__":
    main()
