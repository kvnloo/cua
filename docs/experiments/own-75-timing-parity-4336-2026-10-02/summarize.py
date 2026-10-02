#!/usr/bin/env python3
"""Build own-75-summary.json from raw/ (stdlib only; run under bin/hostless).

verify_artifacts.py recomputes every number here from raw/ and compares. Timing VALUES are never
summarized (the PREREG makes no timing claim); only field presence, alias equalities, the
behaviour-identity digests, oracle outcomes, mutation rows, lock receipts and session variables.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

COMMON = ["semantic_observe_ms", "visual_observe_ms", "candidate_build_ms", "provider_decision_ms",
          "decision_ms", "action_ms", "total_step_ms"]


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def unit() -> dict:
    out = {}
    for arm in ("head", "m0"):
        rc = json.loads((HERE / f"raw/unit/{arm}-rc.json").read_text())
        py = (HERE / f"raw/unit/{arm}-python-unittest.log").read_text()
        tsl = (HERE / f"raw/unit/{arm}-ts-test.log").read_text()
        out[arm] = {
            "rc": {k: v for k, v in sorted(rc.items()) if k not in ("arm", "head", "jev_use_tree", "jev_use_dirty")},
            "jev_use_tree": rc["jev_use_tree"],
            "python_tests_ran": int(re.search(r"^Ran (\d+) tests", py, re.M).group(1)),
            "python_skipped": re.findall(r"^(test_\S+) \(.*\) \.\.\. skipped '([^']*)'", py, re.M),
            "python_failed": re.findall(r"^(test_\S+) \(.*\) \.\.\. (?:FAIL|ERROR)$", py, re.M),
            "ts": {k: int(re.search(rf"^# {k} (\d+)$", tsl, re.M).group(1)) for k in ("tests", "pass", "fail", "skipped")},
        }
    return out


def mutation() -> list[dict]:
    return [{k: r[k] for k in ("id", "language", "applied", "rc", "detected", "control_pass", "first_assertion")}
            for r in jsonl(HERE / "raw/mutation/mutations.jsonl")]


def field_contract(real: Path) -> dict:
    """S2 REAL: per-step field checks on every head and m0 step event."""
    rows = {"head": {"steps": 0, "all_common": 0, "scope_parse_only": 0, "alias_provider": 0, "alias_action": 0,
                     "legacy_all": 0, "parse_ms_present": 0, "parse_ms_equal_visual": 0, "visual_status": {}},
            "m0": {"steps": 0, "any_common_or_scope": 0, "legacy_all": 0, "visual_status": {}}}
    for record in jsonl(real / "trials.jsonl"):
        if record.get("harness_error"):
            continue
        arm = record["arm"]
        for event in analyze.load_jsonl_gz(real / "trials" / record["trial_id"] / "events.jsonl.gz"):
            if event.get("event") != "step":
                continue
            r = rows[arm]
            r["steps"] += 1
            status = str(event.get("visual", {}).get("status"))
            r["visual_status"][status] = r["visual_status"].get(status, 0) + 1
            legacy = "decide_ms" in event and "act_ms" in event and "observe_ms" in event.get("observation", {})
            r["legacy_all"] += legacy
            if arm == "m0":
                r["any_common_or_scope"] += any(k in event for k in COMMON + ["visual_observe_scope"])
                continue
            r["all_common"] += all(k in event for k in COMMON)
            r["scope_parse_only"] += event.get("visual_observe_scope") == "parse_only"
            r["alias_provider"] += event.get("provider_decision_ms") == event.get("decide_ms")
            r["alias_action"] += event.get("action_ms") == event.get("act_ms")
            if "parse_ms" in event.get("visual", {}):
                r["parse_ms_present"] += 1
                r["parse_ms_equal_visual"] += event["visual"]["parse_ms"] == event.get("visual_observe_ms")
    return rows


def lock_and_env(real: Path) -> dict:
    ledger = jsonl(real / "lock-ledger.jsonl")
    excerpt = jsonl(real / "quiet-lane-ledger-excerpt.jsonl")
    env = {p.stem: json.loads(p.read_text()) for p in sorted((real / "session-env").glob("*.json"))}
    records = jsonl(real / "trials.jsonl")
    loads = [x for r in records for x in (r.get("loadavg_start", [None])[0], r.get("loadavg_end", [None])[0])
             if x is not None]
    return {
        "packet_ledger_blocks": len({e["block"] for e in ledger}),
        "packet_ledger_events": len(ledger),
        "quiet_timed_receipts": len(excerpt),
        "quiet_timed_rc": sorted({e["rc"] for e in excerpt}),
        "session_env_blocks": len(env),
        "session_env_values": sorted({json.dumps({k: v for k, v in e.items() if k != "block"}, sort_keys=True)
                                      for e in env.values()}),
        "first_trial_start_utc": min(r["start_utc"] for r in records if "start_utc" in r),
        "last_trial_end_utc": max(r["end_utc"] for r in records),
        "loadavg_1m_min": min(loads), "loadavg_1m_max": max(loads),
    }


def main() -> None:
    real = HERE / "raw/real"
    summary = {
        "schema": "cua.own75.summary.v2",
        "unit": unit(),
        "mutation": mutation(),
        "real_analysis": analyze.analyze(real),
        "field_contract": field_contract(real),
        "lock_and_env": lock_and_env(real),
    }
    (HERE / "own-75-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"unit": {a: summary["unit"][a]["rc"] for a in ("head", "m0")},
                      "mutations_detected": sum(1 for r in summary["mutation"] if r["detected"]),
                      "real_trials": summary["real_analysis"]["trials"],
                      "real_verified": summary["real_analysis"]["trials_verified"],
                      "field_contract": summary["field_contract"],
                      "lock_and_env": summary["lock_and_env"]}, indent=1))


if __name__ == "__main__":
    main()
