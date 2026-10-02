"""UNIT_FAKE_DRIVER structural counts: work per task for arm A vs arm D on the real caller.

Runs the real jev-use ``run.run`` (A: no flag, D: ``--guarded-completion``) through
``run_d.run_trial`` with the in-memory fake Driver (``fake_driver.py``) and the lane
fixture server, N times per arm, and reports only structural counts (decisions,
program creation/verification calls, snapshots, mutations, tool calls). No timing
from this script is evidence of anything; it is not a browser, not the Driver, and
not a measured trial.

    JEV_USE_DIR=<jev-use> python structural_unit.py [N] > raw/unit/structural-work.json
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
from collections import Counter
from pathlib import Path

import d_analysis as D
import i107_fixture as fx
import run_d as R

FIELDS = ("decisions", "plan_calls", "plans_bound", "resolve_calls", "snapshots_full", "snapshots_query",
          "bind_reads", "driver_mutations", "journal_submits", "wrong_target_submits")


def main(n: int) -> dict:
    server = fx.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    out: dict = {"evidence": "UNIT_FAKE_DRIVER (real caller + PR 4316 guard; fake Driver; no browser)",
                 "n_per_arm": n, "arms": {}}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            opts = R.Options(driver="fake", out=Path(tmp), binary_sha256="n/a", caller_tree="n/a",
                             lock_label="unit", fake=True)
            for arm in ("A", "D"):
                rows = []
                for i in range(n):
                    spec = {"name": f"s-{i:02d}-{arm}", "block": "s", "plan": "unit", "pair": f"s-p{i:02d}",
                            "order": "AD", "arm": arm, "condition": "W-quiet", "variant": "quiet", "cohort": "K1",
                            "comparison": "CMP-D", "kind": "measured", "control": None}
                    asyncio.run(R.run_trial(spec, opts, url))
                trials = [t for t in D.load_trials(Path(tmp) / "trials") if t["summary"]["arm"] == arm]
                for t in trials:
                    c = D.counts(t)
                    rows.append({**{k: c[k] for k in FIELDS}, "decision_routes": c["decision_routes"],
                                 "guard": c["guard"], "outcome": t["summary"]["outcome"],
                                 "tools": [e["tool"] for e in t["events"] if e["event"] == "call_send"]})
                out["arms"][arm] = {
                    "per_task": {k: sorted(Counter(r[k] for r in rows).items()) for k in FIELDS},
                    "decision_routes": sorted(Counter(json.dumps(r["decision_routes"]) for r in rows).items()),
                    "guard": sorted(Counter(json.dumps(r["guard"]) for r in rows).items()),
                    "outcomes": sorted(Counter(r["outcome"] for r in rows).items()),
                    "tool_sequence": sorted(Counter(json.dumps(r["tools"]) for r in rows).items()),
                }
    finally:
        server.shutdown()
        server.server_close()
    return out


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5), indent=1, sort_keys=True))
