"""B-04: R2-10's own cold first-snapshot excess on binary R (BENCHMARK re-analysis, standard library).

Reads R2-10's raw browser trial tarballs (accepted packet @ 030f6bdbf,
docs/experiments/r2-10-composition-2026-10-02/raw/browser/{scripted,live}-trials.tar.gz) and writes one
row per COMP measured trial: Driver span of snapshot1 and snapshot2 (first snap.enter -> first
snap.serialized inside the caller's call window, b04_rows.snap_measures), E_R = span(snapshot1) -
span(snapshot2) (the B-02/B-03 definition: snapshot2 is the post-first-action re-snapshot), and the
walk-only spans. Admission rows are excluded; a row counts if the outcome is verified with exactly one
completion mutation.

    python3 r210_observation.py --scripted <scripted-trials.tar.gz> --live <live-trials.tar.gz> \
        --out raw/r210-observation-rows.json

The tarballs are not copied into this packet (they live in the R2-10 packet); the output records each
tarball's sha256 so the rows can be re-derived from the R2-10 packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import b04_rows as R


def rows_for(path: Path, layer: str) -> list[dict]:
    out = []
    for t in R.load_tar(path):
        s = t["summary"]
        name = s.get("trial", "")
        if s.get("arm") != "COMP" or s.get("kind") != "measured" or name.endswith("-admission"):
            continue
        w = R.windows(t)
        m1 = R.snap_measures(t["trace"], w.get("snapshot1"))
        m2 = R.snap_measures(t["trace"], w.get("snapshot2"))
        valid = s.get("outcome") == "verified" and s.get("completion_mutations") == 1
        e = None if (m1["span_ms"] is None or m2["span_ms"] is None) else m1["span_ms"] - m2["span_ms"]
        ew = None if (m1["walk_ms"] is None or m2["walk_ms"] is None) else m1["walk_ms"] - m2["walk_ms"]
        out.append({"trial": name, "layer": layer, "cls": s.get("cls"), "mode": s.get("mode"), "valid": valid,
                    "snapshot1_span_ms": m1["span_ms"], "snapshot2_span_ms": m2["span_ms"], "E_R_ms": e,
                    "snapshot1_walk_ms": m1["walk_ms"], "snapshot2_walk_ms": m2["walk_ms"], "E_R_walk_ms": ew,
                    "snapshot1_sub": m1["sub"]})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scripted", required=True)
    p.add_argument("--live", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    rows = rows_for(Path(a.scripted), "scripted") + rows_for(Path(a.live), "live")
    src = {"scripted": hashlib.sha256(Path(a.scripted).read_bytes()).hexdigest(),
           "live": hashlib.sha256(Path(a.live).read_bytes()).hexdigest()}
    doc = {"schema": "b-04.r210-observation.v1", "source_packet": "exp/r2-10-composition-2026-10-02 @ 030f6bdbf",
           "source_paths": {"scripted": "docs/experiments/r2-10-composition-2026-10-02/raw/browser/scripted-trials.tar.gz",
                            "live": "docs/experiments/r2-10-composition-2026-10-02/raw/browser/live-trials.tar.gz"},
           "source_sha256": src, "filter": "arm COMP, kind measured, not admission; valid = verified and 1 completion mutation",
           "rows": rows}
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    for layer in ("scripted", "live"):
        for cls in ("fill", "toggle", "modal"):
            v = [r["E_R_ms"] for r in rows if r["layer"] == layer and r["cls"] == cls and r["valid"] and r["E_R_ms"] is not None]
            n = len([r for r in rows if r["layer"] == layer and r["cls"] == cls])
            print(layer, cls, f"{len(v)}/{n}", round(sum(v) / len(v), 2) if v else None)


if __name__ == "__main__":
    main()
