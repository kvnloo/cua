"""B-06: R2-10R's own cold first-snapshot excess on binary R' (BENCHMARK re-analysis, standard library).

B-04's r210_observation.py rule applied to R2-10R's accepted raw (c183b95e3,
docs/experiments/r2-10r-recert-2026-10-03/raw/browser/scripted-trials.tar.gz): one row per COMP
measured scripted trial (admission rows excluded): Driver span of snapshot1 and snapshot2 (first
snap.enter -> first snap.serialized inside the caller's call window, b04_rows.snap_measures) and
E_R' = span(snapshot1) - span(snapshot2). A row is valid when the outcome is verified with exactly one
completion mutation. Also copies the R2-10R COMP decomposition rows (mean T, untested ms/share,
observation) from r2-10r-summary.json @ c183b95e3 into raw/r10r-comp-rows.json.

    python3 r10r_observation.py --tar <scripted-trials.tar.gz> --summary <r2-10r-summary.json> --out-dir raw

The tarball is not copied into this packet; its sha256 and the summary's sha256 are recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import b06_rows as R

SRC = "exp/r2-10r-recert-a2-20261003 @ c183b95e35f5af7f2548dec3720b58a65214d9da"
TAR_PATH = "docs/experiments/r2-10r-recert-2026-10-03/raw/browser/scripted-trials.tar.gz"
SUM_PATH = "docs/experiments/r2-10r-recert-2026-10-03/r2-10r-summary.json"


def rows_for(path: Path) -> list[dict]:
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
        out.append({"trial": name, "cls": s.get("cls"), "mode": s.get("mode"), "valid": valid,
                    "snapshot1_span_ms": m1["span_ms"], "snapshot2_span_ms": m2["span_ms"], "E_R_ms": e,
                    "snapshot1_sub": m1["sub"]})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tar", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()
    out = Path(a.out_dir)
    rows = rows_for(Path(a.tar))
    doc = {"schema": "b-06.r10r-observation.v1", "source_packet": SRC, "source_path": TAR_PATH,
           "source_sha256": hashlib.sha256(Path(a.tar).read_bytes()).hexdigest(),
           "filter": "arm COMP, kind measured, not admission; valid = verified and 1 completion mutation",
           "rule": "B-04 r210_observation.py: E_R = span(snapshot1) - span(snapshot2)", "rows": rows}
    (out / "r10r-observation-rows.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    summ_bytes = Path(a.summary).read_bytes()
    dec = json.loads(summ_bytes)["browser"]["scripted"]["decomposition"]
    comp = {"schema": "b-06.r10r-comp-rows.v1", "source": {"packet": SRC, "path": SUM_PATH,
                                                           "sha256": hashlib.sha256(summ_bytes).hexdigest(),
                                                           "key": "browser.scripted.decomposition"},
            "rows": {k: {"n": v["n"], "mean_T_ms": v["mean_T_ms"], "untested_ms": v["untested_ms"],
                         "untested_share": v["untested_share"],
                         "observation_ms": v["components"]["observation"]["mean_ms"],
                         "observation_verdict": v["components"]["observation"]["verdict"],
                         "untested_components": sorted(c for c, x in v["components"].items() if x["verdict"] == "UNTESTED")}
                     for k, v in dec.items() if k.endswith("/COMP")}}
    (out / "r10r-comp-rows.json").write_text(json.dumps(comp, indent=1, sort_keys=True) + "\n")
    for cls in ("fill", "toggle", "modal"):
        v = [r["E_R_ms"] for r in rows if r["cls"] == cls and r["valid"] and r["E_R_ms"] is not None]
        print(cls, f"{len(v)}/{len([r for r in rows if r['cls'] == cls])}", round(sum(v) / len(v), 2) if v else None,
              comp["rows"].get(f"{cls}/COMP", {}).get("untested_share"))


if __name__ == "__main__":
    main()
