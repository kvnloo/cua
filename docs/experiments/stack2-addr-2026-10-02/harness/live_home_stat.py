"""Report the PREREG secondary 'live Hermes home stat before/after' from the committed raw files (stdlib only).

For every run (raw/runs/*/meta/live-home-stat.{before,after}; lines are '<path>|<mtime>|<size>') it lists which
paths changed during the run. Attribution check: if a path also changes BETWEEN two consecutive runs (after-stat of
one run vs before-stat of the next, a window in which no lane run was active), something outside the lane writes it.
Inside each run Hermes sees the live home only as an empty tmpfs (meta/mask.inside), so a lane run cannot write it.
usage: live_home_stat.py <raw dir> <out json>
"""
import json
import sys
from pathlib import Path


def stat(p: Path) -> dict:
    out = {}
    for line in p.read_text().splitlines():
        if line.strip():
            path, mtime, size = line.rsplit("|", 2)
            out[path] = (mtime, size)
    return out


def changed(a: dict, b: dict) -> list:
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


raw, out_p = Path(sys.argv[1]), Path(sys.argv[2])
ledger = {}
for line in (raw / "drive-ledger.jsonl").read_text().splitlines():
    r = json.loads(line)
    if "harness_error" not in r:
        ledger[r["run_id"]] = r
runs = []
for rd in sorted((raw / "runs").iterdir()):
    m = rd / "meta"
    if not (m / "live-home-stat.before").exists() or rd.name not in ledger:
        continue
    b, a = stat(m / "live-home-stat.before"), stat(m / "live-home-stat.after")
    runs.append({"run_id": rd.name, "started": ledger[rd.name]["started"], "before": b, "after": a,
                 "changed_during": changed(b, a)})
runs.sort(key=lambda r: r["started"])
during, between = {}, {}
for r in runs:
    for k in r["changed_during"]:
        during[k] = during.get(k, 0) + 1
gaps = 0
for prev, nxt in zip(runs, runs[1:]):
    gaps += 1
    for k in changed(prev["after"], nxt["before"]):
        between[k] = between.get(k, 0) + 1
res = {
    "schema": "stack2_addr.live_home_stat.v1", "runs": len(runs), "inter_run_gaps": gaps,
    "runs_with_any_change": sum(bool(r["changed_during"]) for r in runs),
    "changed_during_runs_by_path": dict(sorted(during.items())),
    "changed_between_runs_by_path": dict(sorted(between.items())),
    "per_run_changed": {r["run_id"]: r["changed_during"] for r in runs},
}
out_p.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
print(json.dumps({k: res[k] for k in ("runs", "inter_run_gaps", "runs_with_any_change", "changed_during_runs_by_path",
                                      "changed_between_runs_by_path")}))
