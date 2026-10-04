#!/usr/bin/env python3
"""Build own-75-summary.json from raw/ (stdlib only). verify_artifacts.py recomputes and compares."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402


def unit() -> dict:
    out = {}
    for arm in ("head", "m0"):
        rc = json.loads((HERE / f"raw/unit/{arm}-rc.json").read_text())
        py = (HERE / f"raw/unit/{arm}-python-unittest.log").read_text()
        tsl = (HERE / f"raw/unit/{arm}-ts-test.log").read_text()
        out[arm] = {
            "rc": {k: v for k, v in rc.items() if k not in ("arm", "head", "jev_use_tree", "jev_use_dirty")},
            "jev_use_tree": rc["jev_use_tree"],
            "python_tests_ran": int(re.search(r"^Ran (\d+) tests", py, re.M).group(1)),
            "python_skipped": re.findall(r"^(test_\S+) \(.*\) \.\.\. skipped '([^']*)'", py, re.M),
            "python_failed": re.findall(r"^(test_\S+) \(.*\) \.\.\. (?:FAIL|ERROR)$", py, re.M),
            "ts": {k: int(re.search(rf"^# {k} (\d+)$", tsl, re.M).group(1)) for k in ("tests", "pass", "fail", "skipped")},
        }
    return out


def mutation() -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "raw/mutation/mutations.jsonl").read_text().splitlines()]
    return [{k: r[k] for k in ("id", "language", "applied", "rc", "detected", "control_pass", "first_assertion")}
            for r in rows]


def main() -> None:
    summary = {
        "schema": "cua.own75.summary.v1",
        "unit": unit(),
        "mutation": mutation(),
        "real_analysis": analyze.analyze(HERE / "raw/real"),
    }
    (HERE / "own-75-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"unit": {a: summary["unit"][a]["rc"] for a in ("head", "m0")},
                      "mutations_detected": sum(1 for r in summary["mutation"] if r["detected"]),
                      "real_trials": summary["real_analysis"]["trials"],
                      "real_verified": summary["real_analysis"]["trials_verified"]}, indent=1))


if __name__ == "__main__":
    main()
