"""Score one frozen example file with one backend via the #386 score_examples (CONFIRM: unchanged SAMPLES wrapper; exp/stack-confirm copy of the scorer).

  python score_lane.py <hermes_worktree> <examples.jsonl> <backend> <output.jsonl>

Thin wrapper so both lanes go through the same code path: per-row backend errors are recorded, a
backend that cannot start yields a full coverage gap, and per-row timing is attached. Offline only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path


def main() -> None:
    hermes_wt, examples_path, backend, output = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    spec = importlib.util.spec_from_file_location(
        "shadow_api_failure", hermes_wt / "lab" / "z0_hermes_observer" / "shadow_api_failure.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    examples = module.read_jsonl(examples_path)
    started = time.perf_counter()
    rows = module.score_examples(examples, backend, None)
    module.write_jsonl(output, rows)
    errors = [r.get("backend_error") for r in rows if r.get("backend_error")]
    print(json.dumps({"backend": backend, "examples": len(rows), "backend_errors": len(errors),
                      "first_error": errors[0] if errors else None,
                      "process_scoring_wall_s": round(time.perf_counter() - started, 3)}, sort_keys=True))


if __name__ == "__main__":
    main()
