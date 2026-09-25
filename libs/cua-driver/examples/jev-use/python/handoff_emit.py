"""Write the Linux-producible handoff tables by calling the shipped functions."""

from __future__ import annotations

import json
from pathlib import Path

from action_consumer import required_cases
from caller_route import route
from core import Candidate
from goal_gates import accept_completion, use_model_done_gate
from guarded_run import ChildStatus, FreshObservation, GuardedRunPlan, PlannedChild, second_child_allowed
from observation_replay import Observation, policy_killed, replay
from run_length import execute_capped, recommend_cap, wasted_after_stop
from task_battery import evaluate


def _candidate(candidate_id: str, tool: str | None, capture_id: str | None = None) -> Candidate:
    return Candidate(candidate_id, candidate_id, tool, {}, capture_id=capture_id)


def _plan() -> GuardedRunPlan:
    return GuardedRunPlan(
        PlannedChild("type-verification-value", "browser_type"),
        PlannedChild("submit-form", "browser_click"),
        "proof",
        "ref-submit",
    )


def browser_transitions() -> list[dict[str, str]]:
    return [
        {"state": "current", "event": "same ref and generation", "next": "bound", "dispatch": "allowed"},
        {"state": "current", "event": "same label, new generation", "next": "stale", "dispatch": "refused"},
        {"state": "current", "event": "ref missing", "next": "stale", "dispatch": "refused"},
    ]


def replay_comparison() -> dict[str, object]:
    recorded = [
        Observation("gtk-entry", frozenset({"object:text-changed:insert"}), True, "recorded"),
    ]
    synthetic = [
        Observation("rev-1", frozenset(), False, "synthetic"),
        Observation("rev-1", frozenset(), False, "synthetic"),
    ]
    policies = ("always", "no_trusted_invalidator")
    return {
        "production_skipping": False,
        "recorded": {policy: replay(recorded, policy).__dict__ for policy in policies},
        "synthetic_noop": {policy: replay(synthetic, policy).__dict__ for policy in policies},
        "false_reuse_kills": policy_killed(
            replay(
                [
                    Observation("rev-1", frozenset(), False, "synthetic"),
                    Observation("rev-1", frozenset(), True, "synthetic"),
                ],
                "no_trusted_invalidator",
            )
        ),
        "break_even": [
            {"platform": "linux-gtk3-entry", "skips": 0, "note": "recorded text-change is not reused"},
            {"platform": "macOS", "skips": None, "missing_machine": "macOS"},
            {"platform": "Windows", "skips": None, "missing_machine": "Windows"},
        ],
    }


def battery_table() -> list[dict[str, object]]:
    form = evaluate(
        "form-fill",
        [_candidate("type-verification-value", "browser_type"), _candidate("reobserve", None)],
    )
    modal = evaluate(
        "ambiguous-modal",
        [_candidate("click-a", "click"), _candidate("click-b", "click"), _candidate("reobserve", None)],
    )
    return [
        {"task": form.name, "fast_path": form.fast_path, "decisions": form.decisions, "wall_time_ms": None},
        {"task": modal.name, "fast_path": modal.fast_path, "decisions": modal.decisions, "wall_time_ms": None},
    ]


def cap_report() -> dict[str, object]:
    plan = _plan()
    fresh = FreshObservation("proof", "ref-submit", "capture-2")
    failed: ChildStatus = "refuted"
    rows = []
    for cap in (1, 2, 4):
        ran = execute_capped(plan, [failed], [fresh], cap)
        rows.append({"cap": cap, "first_status": failed, "ran": ran, "wasted": wasted_after_stop(cap, ran)})
    return {"rows": rows, "recommendation": recommend_cap(7, 10), "wall_time_ms": None}


def dispatch_counts() -> list[dict[str, object]]:
    plan = _plan()
    fresh = FreshObservation("proof", "ref-submit", "capture-2")
    rows = []
    for status in ("verified", "refuted", "unknown", "stale", "rebound", "refused"):
        allowed = second_child_allowed(status, None if status == "stale" else fresh, plan)
        rows.append({"status": status, "first_dispatch": 1, "second_dispatch": int(allowed)})
    return rows


def goal_table() -> list[dict[str, object]]:
    return [
        {
            "task": "jev-use fixture with /state",
            "model_done_gate": use_model_done_gate(has_independent_oracle=True),
            "completed": accept_completion(model_says_done=True, oracle_succeeded=False),
        },
        {
            "task": "no independent oracle",
            "model_done_gate": use_model_done_gate(has_independent_oracle=False),
            "completed": accept_completion(model_says_done=True, oracle_succeeded=None),
        },
    ]


def routing_table() -> list[dict[str, str]]:
    semantic = [_candidate("type-verification-value", "browser_type"), _candidate("reobserve", None)]
    visual = [_candidate("submit-form", "click", "cap"), _candidate("reobserve", None)]
    two = [_candidate("click-a", "click"), _candidate("click-b", "click")]
    cases = [
        (semantic, "single"),
        (visual, "single"),
        (two, "single"),
        (semantic, "run"),
        (semantic, "reobserve"),
        (semantic, "abstain"),
    ]
    return [{"decision": kind, "route": route(candidates, kind)} for candidates, kind in cases]


def linux_classification(census: dict) -> dict:
    types = set(census.get("event_types") or [])
    return {
        "host": census.get("host"),
        "signals": [
            {
                "event": event,
                "class": "noisy hint",
                "safe_for_reuse": False,
                "reason": "false negatives were not measured",
            }
            for event in sorted(types)
        ],
        "recommendation": "event absence stays always-observe; no Linux scope supports unchanged_since",
        "not_tested": census.get("not_tested"),
    }


def write_all(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    census_path = directory.parent / "atspi-census-20260925.json"
    census = json.loads(census_path.read_text(encoding="utf-8"))
    (directory / "issue-20-classification.json").write_text(
        json.dumps(linux_classification(census), indent=2) + "\n"
    )
    (directory / "issue-17-transitions.json").write_text(json.dumps(browser_transitions(), indent=2) + "\n")
    (directory / "issue-21-comparison.json").write_text(json.dumps(replay_comparison(), indent=2) + "\n")
    (directory / "issue-23-goals.json").write_text(json.dumps(goal_table(), indent=2) + "\n")
    (directory / "issue-24-battery.json").write_text(json.dumps(battery_table(), indent=2) + "\n")
    (directory / "issue-25-caps.json").write_text(json.dumps(cap_report(), indent=2) + "\n")
    (directory / "issue-33-dispatch.json").write_text(json.dumps(dispatch_counts(), indent=2) + "\n")
    (directory / "issue-44-routing.json").write_text(json.dumps(routing_table(), indent=2) + "\n")


if __name__ == "__main__":
    import json

    write_all(Path(__file__).resolve().parents[5] / "scripts" / "repro" / "handoff")
