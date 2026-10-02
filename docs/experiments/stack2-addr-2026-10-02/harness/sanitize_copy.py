"""Copy the committable subset of each run dir into the packet's raw/, replacing local path prefixes.

usage: sanitize_copy.py <mapping.json> <src runs dir> <dst raw/runs dir> <run_id> [...]
mapping.json (local, never committed): {"replace": [["<local prefix>", "<placeholder>"], ...], "forbid": ["<regex>", ...]}
Copied per run: run.json, oracle.json, run_summary.json, join/*, meta/{timeline.log,exit_code,mask.inside,
env.inside,session.env,stdout,stderr,live-home-stat.*,hermes.start,hermes.end}, fixture/state.*.json,
observer events.jsonl, shadow/{decisions.full.jsonl,sidecar_summary.json,backend_load.json,sidecar.log},
shadow/z0int-home/receipts/*.jsonl. NOT copied: state.db (holds full tool results), config, Chrome profile.
Fails if any forbidden string survives.
"""
import json
import re
import sys
from pathlib import Path

FILES = ["run.json", "oracle.json", "run_summary.json", "join/join_summary.json", "join/observations.jsonl",
         "join/api_lane_labels.jsonl", "meta/timeline.log", "meta/exit_code", "meta/mask.inside", "meta/env.inside",
         "meta/session.env", "meta/stdout", "meta/stderr", "meta/live-home-stat.before", "meta/live-home-stat.after",
         "meta/hermes.start", "meta/hermes.end", "fixture/state.before.json", "fixture/state.after.json",
         "home/.hermes/plugin-data/z0-hermes-observer/events.jsonl", "shadow/decisions.full.jsonl",
         "shadow/sidecar_summary.json", "shadow/backend_load.json", "shadow/sidecar.log", "shadow/sidecar_rc",
         "shadow/z0int-home/receipts/decisions.jsonl", "shadow/z0int-home/receipts/outcomes.jsonl"]


def main() -> None:
    mp = json.loads(Path(sys.argv[1]).read_text())
    src, dst = Path(sys.argv[2]), Path(sys.argv[3])
    reps = sorted(mp["replace"], key=lambda x: -len(x[0]))
    bad = []
    for rid in sys.argv[4:]:
        for rel in FILES:
            s = src / rid / rel
            if not s.exists():
                continue
            text = s.read_text(encoding="utf-8", errors="replace")
            for a, b in reps:
                text = text.replace(a, b)
            if rel == "run_summary.json" or rel == "run.json":
                pass
            d = dst / rid / ("observer/events.jsonl" if rel.endswith("events.jsonl") else rel)
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(text, encoding="utf-8")
            bad += [f"{rid}/{rel}: {m.group(0)}" for f in mp["forbid"] for m in re.finditer(f, text)][:3]
    if bad:
        print("FORBIDDEN STRINGS SURVIVED:\n" + "\n".join(bad[:50]))
        sys.exit(1)
    print(f"copied {len(sys.argv) - 4} runs")


if __name__ == "__main__":
    main()
