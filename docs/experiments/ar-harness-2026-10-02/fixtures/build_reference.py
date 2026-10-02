#!/usr/bin/env python3
"""Merge validation summaries into the champion reference and a sanitised summary.

usage: build_reference.py --out-dir <fixtures dir> <summary.json> [<summary.json> ...]

champion_reference.json  per cell: union of external signatures, Driver error codes,
                         action routes, DoAction counts and mutation counts seen on the
                         champion. G2 compares a candidate trial's signature against
                         ``external_signature_union`` of its cell (extra entries fail).
validation-summary.json  pass counts and failure reasons per cell, no paths.
Pure file work; no Driver, no display.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_ABS = re.compile(r"/(?:home|mnt|tmp|run)/[^\s\"']*")


def sanitize(obj):
    if isinstance(obj, str):
        return _ABS.sub("<abs-path>", obj)
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    return obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", required=True)
    p.add_argument("summaries", nargs="+")
    args = p.parse_args()
    summaries = [json.loads(Path(s).read_text()) for s in args.summaries]
    shas = {s["driver_sha256"] for s in summaries}
    if len(shas) != 1:
        raise SystemExit(f"summaries come from different Drivers: {sorted(shas)}")
    reference = {"schema": "cua.ar.champion_reference_v1", "driver_sha256": shas.pop(), "cells": {}}
    validation = {"schema": "cua.ar.fixture_validation_summary_v1", "driver_sha256": reference["driver_sha256"],
                  "fixture_sha256": summaries[-1]["fixture_sha256"], "cells": {}}
    for summary in summaries:
        for cell, c in summary["cells"].items():
            ref = reference["cells"].setdefault(cell, {"external_signature_union": [], "error_codes": [],
                                                       "routes": [], "do_action_on_bus": [],
                                                       "mutation_counts": [], "outcomes": []})
            for key in ref:
                ref[key] = sorted(set(map(str, ref[key])) | set(map(str, c.get(key, []))))
            val = validation["cells"].setdefault(cell, {"trials": 0, "passed": 0, "failures": []})
            val["trials"] += c["trials"]
            val["passed"] += c["passed"]
            val["failures"] += c["failures"]
            val["T_ms_present"] = val.get("T_ms_present", 0) + c.get("T_ms_present", 0)
    out = Path(args.out_dir)
    (out / "champion_reference.json").write_text(json.dumps(sanitize(reference), indent=1, sort_keys=True) + "\n")
    (out / "validation-summary.json").write_text(json.dumps(sanitize(validation), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
