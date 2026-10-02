"""Freeze the deduplicated set of REAL shadow requests (both question ids) from measured shadow-arm runs.

usage: build_frozen.py <raw dir> <plan.json> <out frozen_requests.jsonl>
Order: question_id, then state_hash (deterministic). Each row is the exact DecisionRequest mapping the sidecar
sent, plus "_state_hash" and "_first_seen" (run_id/opportunity_id) for provenance.
"""
import hashlib
import json
import sys
from pathlib import Path

raw, plan_p, out_p = map(Path, sys.argv[1:4])
plan = json.loads(plan_p.read_text())["runs"]
seen = {}
for r in plan:
    if r["set"] != "measured" or r["arm"] not in ("on", "outage"):
        continue
    p = raw / "runs" / r["run_id"] / "shadow" / "decisions.full.jsonl"
    for line in (p.read_text().splitlines() if p.exists() else []):
        d = json.loads(line)
        key = (d["question_id"], d["state_hash"])
        if key not in seen:
            seen[key] = {**d["request"], "_state_hash": d["state_hash"], "_first_seen": f"{r['run_id']}/{d['opportunity_id']}"}
rows = [seen[k] for k in sorted(seen)]
body = "".join(json.dumps(x, sort_keys=True) + "\n" for x in rows)
out_p.write_text(body)
print(json.dumps({"n": len(rows), "by_question": {q: sum(k[0] == q for k in seen) for q in sorted({k[0] for k in seen})},
                  "sha256": hashlib.sha256(body.encode()).hexdigest()}))
