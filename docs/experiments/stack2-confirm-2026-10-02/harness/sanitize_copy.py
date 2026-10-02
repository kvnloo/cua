"""Copy the committable subset of each measured run dir into the packet's raw/runs/, replacing local path prefixes.

usage: sanitize_copy.py <mapping.json> <src runs dir> <dst raw/runs dir> <run_id> [...]
mapping.json (local, never committed): {"replace": [["<local prefix>", "<placeholder>"], ...], "forbid": ["<regex>", ...]}
(adapted from the ADDR sanitize_copy.py). The layout keeps what the oracle reads (meta/stdout, cwd/**, fixture/
state.after.json), so verify_artifacts.py can re-run the oracle. Also copied: run.json, meta/{timeline.log,exit_code,
mask.inside,env.inside,session.env,stderr,live-home-stat.*,hermes.start,hermes.end,worktree-head}, fixture/state.before.json,
the private agent.log/errors.log. NOT copied: state.db (full tool results), config, Chrome profile, screenshots cache,
the observer spool (it is frozen in dataset/events.jsonl). Fails if any forbidden string survives. Writes
sanitized.json listing every file whose text changed, so a verifier can tell a sanitization effect from a defect.
"""
import json
import re
import sys
from pathlib import Path

FILES = ["run.json", "meta/timeline.log", "meta/exit_code", "meta/mask.inside", "meta/env.inside", "meta/session.env",
         "meta/stdout", "meta/stderr", "meta/live-home-stat.before", "meta/live-home-stat.after", "meta/hermes.start",
         "meta/hermes.end", "meta/worktree-head", "fixture/state.before.json", "fixture/state.after.json",
         "home/.hermes/logs/agent.log", "home/.hermes/logs/errors.log"]


def main() -> None:
    mp = json.loads(Path(sys.argv[1]).read_text())
    src, dst = Path(sys.argv[2]), Path(sys.argv[3])
    reps = sorted(mp["replace"], key=lambda x: -len(x[0]))
    bad, changed = [], []
    for rid in sys.argv[4:]:
        rels = list(FILES) + sorted(str(p.relative_to(src / rid)) for p in (src / rid / "cwd").rglob("*") if p.is_file())
        for rel in rels:
            s = src / rid / rel
            if not s.exists():
                continue
            raw = s.read_text(encoding="utf-8", errors="replace")
            text = raw
            for a, b in reps:
                text = text.replace(a, b)
            if text != raw:
                changed.append(f"{rid}/{rel}")
            d = dst / rid / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(text, encoding="utf-8")
            bad += [f"{rid}/{rel}: {m.group(0)}" for f in mp["forbid"] for m in re.finditer(f, text)][:3]
    (dst / "sanitized.json").write_text(json.dumps({"files_with_replacements": changed}, indent=1) + "\n")
    if bad:
        print("FORBIDDEN STRINGS SURVIVED:\n" + "\n".join(bad[:50]))
        sys.exit(1)
    print(f"copied {len(sys.argv) - 4} runs; {len(changed)} files had local prefixes replaced")


if __name__ == "__main__":
    main()
