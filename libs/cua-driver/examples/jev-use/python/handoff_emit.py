"""Write the Linux-producible handoff tables by calling the shipped functions."""

from __future__ import annotations

import json
from pathlib import Path

from action_consumer import required_cases, typed_choice
from browser_revision import transition_rows
from caller_route import route
from cancellation_lifetime import Lifetime, coverage_report
from core import Candidate
from goal_gates import task_rows
from guarded_run import (
    ChildStatus,
    Decision,
    FreshObservation,
    GuardedRunPlan,
    PlannedChild,
    admit_guarded_run,
    second_child_allowed,
)
from stale_batch import Child, Target, run_batch
from observation_replay import Observation, policy_killed, replay
from run_length import execute_capped, recommend_cap, wasted_after_stop
from task_battery import battery_table as interleaved_battery


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
    return transition_rows()


def browser_not_run() -> dict[str, object]:
    return {
        "live_browser_battery": "not run",
        "gap": "no browser fixture was run on this Linux host",
        "missing": [
            "navigation",
            "tab switch",
            "frame or document replacement",
            "browser process restart",
            "independent fixture state from a live page",
        ],
    }


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
    return interleaved_battery()


def cap_report() -> dict[str, object]:
    plan = _plan()
    fresh = FreshObservation("proof", "ref-submit", "capture-2")
    failed: ChildStatus = "refuted"
    rows = []
    for cap in (1, 2, 4):
        ran = execute_capped(plan, [failed], [fresh], cap)
        rows.append({"cap": cap, "first_status": failed, "ran": ran, "wasted": wasted_after_stop(cap, ran)})
    return {"rows": rows, "recommendation": recommend_cap(7, 10), "wall_time_ms": None}


def fixture_submitted(world: dict[str, object]) -> bool:
    """Retained app-state fact. second_child_allowed does not read it."""
    return world.get("submitted") is True


def dispatch_counts() -> list[dict[str, object]]:
    plan = _plan()
    fresh = FreshObservation("proof", "ref-submit", "capture-2")
    worlds = {
        "verified": {"submitted": True},
        "refuted": {"submitted": False},
        "unknown": {"submitted": True},
        "stale": {"submitted": False},
        "rebound": {"submitted": False},
        "refused": {"submitted": False},
    }
    rows = []
    for status in ("verified", "refuted", "unknown", "stale", "rebound", "refused"):
        allowed = second_child_allowed(status, None if status == "stale" else fresh, plan)
        rows.append(
            {
                "status": status,
                "first_dispatch": 1,
                "second_dispatch": int(allowed),
                "app_state_reached": fixture_submitted(worlds[status]),
            }
        )
    return rows


def injection_report() -> list[dict[str, object]]:
    """Dispatch counts after a lost or unverifiable effect. Replay stays at zero."""
    plan = _plan()
    fresh = FreshObservation("proof", "ref-submit", "capture-2")
    cases = (
        ("response lost", "unknown", None, "unverifiable", "unavailable", {"submitted": True}),
        ("verification unavailable", "unknown", fresh, "unverifiable", "unavailable", {"submitted": True}),
        ("verification unknown", "unknown", fresh, "unverifiable", "unavailable", {"submitted": True}),
        ("provider failure after first child", "refuted", fresh, "refused", "completed", {"submitted": False}),
        ("cancellation after partial acceptance", "unknown", fresh, "unverifiable", "unavailable", {"submitted": True}),
        ("stale next child", "stale", None, "unverifiable", "unavailable", {"submitted": False}),
        ("refused next child", "refused", fresh, "refused", "skipped", {"submitted": False}),
        ("process disappears after dispatch", "stale", None, "unverifiable", "unavailable", {"submitted": False}),
    )
    rows = []
    for name, status, observation, effect, seen, world in cases:
        choice = typed_choice(effect, seen, passive_success=False)
        rows.append(
            {
                "case": name,
                "first_dispatch": 1,
                "replay_dispatch": int(choice == "continue"),
                "second_dispatch": int(second_child_allowed(status, observation, plan)),
                "typed": choice,
                "app_state_reached": fixture_submitted(world),
            }
        )
    return rows


def session_isolation() -> dict[str, object]:
    """Two caller objects. Finishing one does not release the other."""
    first = Lifetime("req-a")
    second = Lifetime("req-b")
    first.admit()
    first.native_exit()
    first.release()
    second.admit()
    foreign_rejected = False
    try:
        first.finish("req-b")
    except RuntimeError:
        foreign_rejected = True
    from browser_revision import BrowserNode, StaleRefError, bind

    node_a = BrowserNode("ref-a", 1, "Submit")
    node_b = BrowserNode("ref-b", 1, "Submit")
    bind(node_a, "ref-a", 1)
    cross_refused = False
    try:
        bind(node_b, "ref-a", 1)
    except StaleRefError:
        cross_refused = True
    own_b = bind(node_b, "ref-b", 1)
    plan_a = _plan()
    plan_b = GuardedRunPlan(plan_a.first, plan_a.second, "other-token", "other-ref")
    borrowed = FreshObservation(plan_b.token, plan_a.submit_ref, "capture-2")
    return {
        "lifetime_foreign_rejected": foreign_rejected,
        "lifetime_events_shared": first.events == second.events,
        "browser_cross_ref_refused": cross_refused,
        "other_session_ref_still_binds": own_b.ref,
        "borrowed_token_authorizes_plan": second_child_allowed("verified", borrowed, plan_a),
        "capture_registry": "not introduced",
        "concurrent_processes": "not executed",
    }


def selector_report(root: Path) -> list[dict[str, str]]:
    probe = (root / "scripts/repro/handoff/linux-host-probe.txt").read_text(encoding="utf-8")
    window = (root / "libs/cua-driver/rust/crates/cua-driver-contract/src/windows.rs").read_text(encoding="utf-8")
    verify = (root / "libs/cua-driver/rust/crates/cua-driver-contract/src/verification.rs").read_text(encoding="utf-8")
    limits = []
    if "daemon is not running" in probe:
        limits.append("daemon is not running")
    if "no top-level windows" in probe:
        limits.append("no top-level windows")
    if "cua-driver 0.28.2" in probe:
        limits.append("installed binary is 0.28.2, not the pinned commit")
    runtime = "not captured; " + "; ".join(limits)
    both_rejected = "window observation requires accessibility or screenshot capture" in window
    return [
        {
            "selector": "include_accessibility_tree",
            "linux_source": "present" if "include_accessibility_tree" in window else "absent",
            "linux_runtime": runtime,
            "macos_runtime": "not measured on this host",
            "windows_runtime": "not measured on this host",
            "missing_machine": "Missing machine: macOS. Missing machine: Windows.",
        },
        {
            "selector": "include_screenshot",
            "linux_source": "present" if "include_screenshot" in window and "include_screenshot" in verify else "absent",
            "linux_runtime": runtime,
            "macos_runtime": "not measured on this host",
            "windows_runtime": "not measured on this host",
            "missing_machine": "Missing machine: macOS. Missing machine: Windows.",
        },
        {
            "selector": "both disabled",
            "linux_source": "rejected by validate" if both_rejected else "not found",
            "linux_runtime": runtime,
            "macos_runtime": "not measured on this host",
            "windows_runtime": "not measured on this host",
            "missing_machine": "Missing machine: macOS. Missing machine: Windows.",
        },
    ]


def selector_tsv(root: Path) -> str:
    columns = (
        "selector",
        "linux_source",
        "linux_runtime",
        "macos_runtime",
        "windows_runtime",
        "missing_machine",
    )
    lines = ["\t".join(columns)]
    for row in selector_report(root):
        lines.append("\t".join(row[column] for column in columns))
    return "\n".join(lines) + "\n"


def goal_table() -> list[dict[str, object]]:
    return task_rows()


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
    not_tested = list(census.get("not_tested") or [])
    for item in (
        "window lifecycle",
        "Chromium/Electron navigation",
        "bus reconnect",
        "false-negative case",
    ):
        if item not in not_tested:
            not_tested.append(item)
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
        "not_tested": not_tested,
    }


def guarded_receipts() -> list[dict[str, object]]:
    candidates = [
        _candidate("type-verification-value", "browser_type"),
        _candidate("submit-form", "browser_click"),
        _candidate("reobserve", None),
        _candidate("abstain", None),
    ]
    plan = admit_guarded_run(
        candidates,
        Decision("run", ("type-verification-value", "submit-form")),
        token="proof",
        submit_ref="ref-submit",
    )
    assert plan is not None
    single = admit_guarded_run(
        candidates,
        Decision("single", ("type-verification-value",)),
        token="proof",
        submit_ref="ref-submit",
    )
    cases: list[tuple[str, ChildStatus, FreshObservation | None]] = [
        ("verified", "verified", FreshObservation("proof", "ref-submit", "capture-2")),
        ("refuted", "refuted", FreshObservation("proof", "ref-submit", "capture-2")),
        ("unknown", "unknown", FreshObservation("proof", "ref-submit", "capture-2")),
        ("stale", "stale", None),
        ("rebound", "verified", FreshObservation("proof", "ref-other", "capture-2")),
        ("refused", "refused", FreshObservation("proof", "ref-submit", "capture-2")),
    ]
    rows = []
    for name, status, fresh in cases:
        rows.append(
            {
                "case": name,
                "admitted": True,
                "second_dispatch": second_child_allowed(status, fresh, plan),
                "wall_time_ms": None,
            }
        )
    rows.append({"case": "single-action-choice", "admitted": single is not None, "second_dispatch": False, "wall_time_ms": None})
    return rows


def stale_receipts() -> list[dict[str, object]]:
    children = [
        Child("field", Target("id-field", "field")),
        Child("submit", Target("id-submit", "submit")),
    ]

    def trace_for(world: dict[str, Target], status: str) -> dict[str, object]:
        current = dict(world)

        def apply() -> str:
            if status == "ok-disappear":
                current.pop("submit", None)
                return "ok"
            if status == "ok-rebind":
                current["submit"] = Target("id-submit-2", "submit")
                return "ok"
            return status

        traced = run_batch(children, lambda label: current.get(label), apply)
        return {
            "status": status,
            "preflight": traced.preflight,
            "dispatched": traced.dispatched,
            "refused": traced.refused,
            "elapsed_ms": None,
        }

    base = {"field": Target("id-field", "field"), "submit": Target("id-submit", "submit")}
    return [trace_for(base, status) for status in ("ok", "ok-disappear", "ok-rebind", "failed", "unknown")]


def write_all(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    root = directory.parents[2]
    census_path = directory.parent / "atspi-census-20260925.json"
    census = json.loads(census_path.read_text(encoding="utf-8"))
    (directory / "issue-20-classification.json").write_text(
        json.dumps(linux_classification(census), indent=2) + "\n"
    )
    (directory / "issue-17-transitions.json").write_text(json.dumps(browser_transitions(), indent=2) + "\n")
    (directory / "issue-17-not-run.json").write_text(json.dumps(browser_not_run(), indent=2) + "\n")
    (directory / "issue-33-injections.json").write_text(json.dumps(injection_report(), indent=2) + "\n")
    (directory / "issue-36-sessions.json").write_text(json.dumps(session_isolation(), indent=2) + "\n")
    (directory / "issue-9-coverage.json").write_text(json.dumps(coverage_report(), indent=2) + "\n")
    (directory / "issue-16-matrix.tsv").write_text(selector_tsv(root))
    (directory / "issue-21-comparison.json").write_text(json.dumps(replay_comparison(), indent=2) + "\n")
    (directory / "issue-23-goals.json").write_text(json.dumps(goal_table(), indent=2) + "\n")
    (directory / "issue-24-battery.json").write_text(json.dumps(battery_table(), indent=2) + "\n")
    (directory / "issue-25-caps.json").write_text(json.dumps(cap_report(), indent=2) + "\n")
    (directory / "issue-33-dispatch.json").write_text(json.dumps(dispatch_counts(), indent=2) + "\n")
    (directory / "issue-44-routing.json").write_text(json.dumps(routing_table(), indent=2) + "\n")
    (directory / "issue-5-receipts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in guarded_receipts()))
    (directory / "issue-6-receipts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in stale_receipts()))


if __name__ == "__main__":
    import json

    write_all(Path(__file__).resolve().parents[5] / "scripts" / "repro" / "handoff")
