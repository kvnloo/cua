#!/usr/bin/env python3
"""Validate every AR fixture and control N times on one Driver (correctness only).

Runs INSIDE the private session (see run_in_session.sh). Trials are interleaved
round-robin over the requested (fixture, kind) cells with per-cell seeds, so a
cell's ten trials see ten different layouts. Writes, under ``--run-root``:

  private/ledger.jsonl   every trial record (full, kept out of the Driver sandbox)
  summary.json           per-cell pass counts, failure reasons, outcomes, and the
                         union of external signatures (the champion reference set)

No timing claim is made from these runs: T_ms is recorded only to check that the
done stamp exists and follows the effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ar_trial import Harness, loadavg, run_trial  # noqa: E402

CELLS = {
    "gtk3_checkbox": ("reference", "negative_stale_token", "negative_no_action", "canary_absent",
                      "canary_disabled", "delayed_effect", "focus_steal"),
    "gtk3_text": ("text_save",),
    "browser": ("fill_submit",),
    # Driver-free oracle validation for the browser spot check (see ar_trial.run_browser_selfcheck).
    "browser_selfcheck": ("xdotool_trusted", "js_untrusted"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wt", required=True)
    p.add_argument("--driver", required=True)
    p.add_argument("--driver-label", default="champion")
    p.add_argument("--run-root", required=True)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--cells", nargs="*", default=None, help="fixture:kind ... (default: all)")
    p.add_argument("--seed-base", type=int, default=1000)
    p.add_argument("--no-bus-monitor", action="store_true")
    args = p.parse_args()
    if os.environ.get("WAYLAND_DISPLAY") or any(k.startswith("HYPRLAND_") for k in os.environ) \
            or not os.environ.get("DISPLAY"):
        raise SystemExit("refusing: not inside the isolated X11 session")
    cells = [tuple(c.split(":", 1)) for c in args.cells] if args.cells else \
        [(f, k) for f, kinds in CELLS.items() for k in kinds]
    run_root = Path(args.run_root)
    h = Harness(Path(args.wt), Path(args.driver), run_root, bus_monitor=not args.no_bus_monitor,
                driver_label=args.driver_label)
    ledger = open(h.private / "ledger.jsonl", "a")
    meta = {"event": "meta", "driver_sha256": sha256(Path(args.driver)), "driver_label": args.driver_label,
            "cells": cells, "n": args.n, "loadavg": loadavg(), "t_start_utc": time.strftime("%FT%TZ", time.gmtime()),
            "fixture_sha256": {f.name: sha256(f) for f in sorted(HERE.glob("*.py"))}}
    ledger.write(json.dumps(meta, sort_keys=True) + "\n")
    results: dict[str, list] = {f"{f}:{k}": [] for f, k in cells}
    index = 0
    try:
        for rnd in range(args.n):
            for ci, (fixture, kind) in enumerate(cells):
                seed = args.seed_base + rnd * 100 + ci
                rec = run_trial(h, fixture, kind, seed, index)
                index += 1
                ledger.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
                ledger.flush()
                results[f"{fixture}:{kind}"].append(rec)
                v = rec["verdict"]
                print(json.dumps({"i": rec["index"], "cell": f"{fixture}:{kind}", "seed": seed,
                                  "passed": v["passed"], "reasons": v["reasons"],
                                  "outcome": (rec.get("caller") or {}).get("outcome"),
                                  "T_ms": rec.get("T_ms"), "err": rec.get("harness_error")}), flush=True)
    finally:
        h.close()
    summary = {"schema": "cua.ar.fixture_validation_v1", "driver_label": args.driver_label,
               "driver_sha256": meta["driver_sha256"], "n_per_cell": args.n,
               "fixture_sha256": meta["fixture_sha256"], "cells": {}}
    for cell, recs in results.items():
        sigs = sorted({s for r in recs for s in ((r.get("external") or {}).get("signature") or [])})
        summary["cells"][cell] = {
            "trials": len(recs),
            "passed": sum(1 for r in recs if r["verdict"]["passed"]),
            "outcomes": sorted({str((r.get("caller") or {}).get("outcome")) for r in recs}),
            "failures": [{"trial": r["trial"], "reasons": r["verdict"]["reasons"], "error": r.get("harness_error")}
                         for r in recs if not r["verdict"]["passed"]],
            "error_codes": sorted({str((r.get("caller") or {}).get("error_code")) for r in recs
                                   if (r.get("caller") or {}).get("error_code")}),
            "routes": sorted({str(c.get("structured", {}).get("route")) for r in recs
                              for c in (r.get("caller") or {}).get("calls", [])
                              if c.get("tool") in ("click", "set_value", "browser_click", "browser_type")}),
            "mutation_counts": sorted({(r.get("oracle") or {}).get("mutation_count",
                                                                  (r.get("oracle") or {}).get("posts"))
                                       for r in recs}, key=str),
            "do_action_on_bus": sorted({(r.get("extra") or {}).get("do_action_on_bus") for r in recs}, key=str),
            "external_signature_union": sigs,
            "T_ms_present": sum(1 for r in recs if r.get("T_ms") is not None),
        }
    (run_root / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=str) + "\n")
    total = sum(c["trials"] for c in summary["cells"].values())
    passed = sum(c["passed"] for c in summary["cells"].values())
    print(f"done: {passed}/{total} passed; summary {run_root / 'summary.json'}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
