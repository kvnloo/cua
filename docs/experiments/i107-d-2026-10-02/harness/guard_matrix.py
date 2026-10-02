"""UNIT evidence: what the tested caller decides at step 2 under each dependency control.

Runs the real jev-use caller code at the tested source (``tasks.FixtureFormTask``
candidates, ``jev_adapter.choose_mock_for_task``, ``core.validate_choice`` and
PR 4316's ``plan_guarded_completion`` / ``resolve_guarded_completion``) over
synthetic semantic_v2 snapshots shaped like ``semantic_ref_value`` output
(tools.rs) for the state each control leaves at the step-2 snapshot. Every ref
carries a hidden marker (``real`` / ``competing`` / ``decoy``) kept outside the
snapshot, so the result says which element each arm would act on.

This is caller logic only. Where the snapshot shape depends on the Driver or
Chrome (visibility class, AX disabled state, AX name from CSS content) both
branches are listed and labelled conditional; REAL runs are BLOCKED (hostless
browser-launch blocker), so no branch is claimed as observed.

    JEV_USE_DIR=<jev-use> python guard_matrix.py > raw/unit/guard-matrix.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
JEV = Path(os.environ.get("JEV_USE_DIR", HERE.parents[3] / "libs/cua-driver/examples/jev-use"))
sys.path[:0] = [str(JEV / "python"), str(JEV)]

from core import validate_choice  # noqa: E402
from guarded_completion import plan_guarded_completion, resolve_guarded_completion  # noqa: E402
from jev_adapter import choose_mock_for_task  # noqa: E402
from tasks import FixtureFormTask, fixture_sources  # noqa: E402

TOKEN = "proof-token-i107-unit"
SESSION = "jev-python-unit"
DET = "UNIT (caller logic over a control-shaped snapshot; REAL BLOCKED)"
COND = "UNIT (branch conditional on Driver/Chrome; REAL BLOCKED)"


def button(marker: str, *, name: str = "Submit", visibility: str = "in_viewport",
           actions: tuple[str, ...] = ("click",)) -> dict[str, Any]:
    return {"marker": marker, "name": name, "visibility": visibility, "actions": list(actions)}


def snapshot(snap: int, value: str, buttons: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    """semantic_v2-shaped result; returns (snapshot, ref -> marker). Content refs are not action refs."""
    refs = [{"ref": f"p{snap}:0", "role": "textbox", "name": "verification value", "value": value,
             "states": {"editable": "plaintext", "focusable": True}, "actions": ["type", "click"],
             "frame": "main", "visibility": "in_viewport"}]
    content, markers = [], {}
    for i, b in enumerate(buttons, start=1):
        entry = {"ref": f"p{snap}:{i}", "role": "button", "name": b["name"], "value": None,
                 "states": {"focusable": True}, "actions": b["actions"], "frame": "main",
                 "visibility": b["visibility"]}
        markers[entry["ref"]] = b["marker"]
        (refs if b["actions"] else content).append(entry)
    return {"status": "ok", "target_id": "target", "tab_id": "tab", "refs": refs, "content_refs": content}, markers


def decide(task: FixtureFormTask, sources: Any) -> tuple[str | None, Any]:
    candidates = task.candidates(sources)
    choice, _conf, _probs = choose_mock_for_task(task, sources, candidates, [])
    return choice, (validate_choice(choice, candidates, current_capture_id=None) if choice else None)


def target_of(candidate: Any, markers: dict[str, str]) -> str | None:
    if candidate is None or candidate.tool != "browser_click":
        return None
    return markers.get(candidate.arguments.get("ref"))


# (control, branch, step-2 value, step-2 buttons, label, extra)
SCENARIOS: list[tuple[str, str, str, list[dict[str, Any]], str, dict[str, Any]]] = [
    ("baseline", "only", TOKEN, [button("real")], DET, {}),
    ("DC01", "only", "changed-by-page", [button("real")], DET, {}),
    ("DC17a", "only", "", [button("real")], DET, {}),
    ("DC03", "only", TOKEN, [button("competing"), button("real")], DET, {}),
    ("DC04", "only", TOKEN, [], DET, {}),
    ("DC05a", "only", TOKEN, [button("real")], DET, {}),
    ("DC06", "only", TOKEN, [button("decoy")], DET,
     {"missing_fact": "the Submit's form/ancestor scope (PR 4316 binds role + name + uniqueness only)"}),
    ("DC15", "only", TOKEN, [button("real")], DET, {}),
    ("DC12", "submit_omitted_css_hidden", TOKEN, [], COND, {}),
    ("DC12", "submit_kept_no_layout", TOKEN, [button("real", visibility="no_layout")], COND, {}),
    ("DC13", "submit_kept_offscreen", TOKEN, [button("real", visibility="offscreen")], COND, {}),
    ("DC14a", "submit_omitted_page_occluded", TOKEN, [], COND, {}),
    ("DC14a", "submit_kept", TOKEN, [button("real")], COND, {}),
    ("DC16a", "ax_disabled_no_actions", TOKEN, [button("real", actions=())], COND, {}),
    ("DC16a", "ax_enabled", TOKEN, [button("real")], COND, {}),
    ("DC16b", "ax_disabled_no_actions", TOKEN, [button("real", actions=())], COND, {}),
    ("DC16b", "ax_enabled", TOKEN, [button("real")], COND, {}),
    ("DC17b", "ax_name_includes_before", TOKEN, [button("real", name="Do not Submit")], COND, {}),
    ("DC17b", "ax_name_unchanged", TOKEN, [button("real")], COND, {}),
]
# The mutation lands after the step-2 snapshot (check-to-dispatch), or the fault is in transport/fixture:
# the guard sees the baseline snapshot; the outcome belongs to the Driver and the fixture.
for _cid in ("DC05b", "DC07", "DC10", "DC14b", "DC20a", "DC20b"):
    SCENARIOS.append((_cid, "only", TOKEN, [button("real")], DET, {"outcome_owner": "driver_or_fixture"}))


def compute() -> list[dict[str, Any]]:
    rows = []
    for control, branch, value, buttons, label, extra in SCENARIOS:
        task = FixtureFormTask(TOKEN, "http://127.0.0.1:9/", 4)
        snap1, _m1 = snapshot(1, "", [button("real")])
        s1 = fixture_sources(snap1)
        choice1, cand1 = decide(task, s1)
        assert choice1 == "type-verification-value", choice1
        plan = plan_guarded_completion(task, s1, cand1, session=SESSION)
        assert plan is not None
        snap2, markers = snapshot(2, value, buttons)
        s2 = fixture_sources(snap2)
        a_choice, a_cand = decide(task, s2)
        res = resolve_guarded_completion(plan, task, s2, task.candidates(s2), session=SESSION)
        if res.candidate is not None:
            d_choice, d_cand, d_decisions = res.candidate.id, res.candidate, 0
        else:
            d_choice, d_cand = decide(task, s2)
            d_decisions = 1
        rows.append({
            "control": control, "branch": branch, "evidence": label,
            "step2_snapshot": {"field": "token" if value == TOKEN else ("empty" if value == "" else "other"),
                               "buttons": [{k: b[k] for k in ("marker", "name", "visibility")} |
                                           {"action_ref": bool(b["actions"])} for b in buttons]},
            "A": {"choice": a_choice, "target": target_of(a_cand, markers), "decisions_step2": 1},
            "D": {"guard": {"status": res.telemetry["status"], "reason": res.telemetry.get("reason")},
                  "prior_ref": plan.prior_ref, "fresh_ref": res.telemetry.get("fresh_ref"),
                  "choice": d_choice, "target": target_of(d_cand, markers), "decisions_step2": d_decisions},
            "missing_fact": extra.get("missing_fact"),
            "outcome_owner": extra.get("outcome_owner", "caller"),
        })
    return rows


if __name__ == "__main__":
    print(json.dumps(compute(), indent=1, sort_keys=True))
