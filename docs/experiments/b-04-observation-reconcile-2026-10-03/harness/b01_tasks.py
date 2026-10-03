"""Experiment-owned jev-use task specs for the #24 toggle->confirm and modal->act pages.

They implement the jev-use ``Task`` protocol (``python/tasks.py``) so the B-01
runner can reuse jev-use's candidate building (``task_candidates_for_step``),
the deterministic mock chooser (``choose_mock_for_task`` via
``mock_preferences``) and the live request builder (``choose_for_task``)
unchanged. Candidates come only from the page-structure source; the oracle is
the #24 fixture server's ``/state`` with ``oracle_ok`` semantics from
kvnloo/cua 5474aa31f. Neither task is ``FIXTURE_TASK_ID``, so PR 4316's
``plan_guarded_completion`` binds nothing for them at the tested source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.request import Request, urlopen

from b01_fixtures import oracle_ok
from tasks import TaskParameter, TaskSources, _reserved_candidates, history_entry, redact_token

TOGGLE_TASK_ID = "issue24-toggle-confirm"
MODAL_TASK_ID = "issue24-modal"


def _is_checked(control: Any) -> bool:
    """semantic_v2 reports ``states`` as a mapping, e.g. ``{"checked": "true"}``."""
    handle = getattr(control, "handle", None)
    states = handle.get("states") if isinstance(handle, Mapping) else None
    if isinstance(states, Mapping):
        return str(states.get("checked")).lower() == "true"
    return False


def _read_state(origin: str) -> dict[str, Any]:
    with urlopen(f"{origin.rstrip('/')}/state", timeout=2) as response:
        return json.loads(response.read())


def _reset(origin: str) -> None:
    request = Request(f"{origin.rstrip('/')}/reset", method="POST", data=b"")
    with urlopen(request, timeout=2) as response:
        if response.status != 204:
            raise RuntimeError(f"fixture reset failed: HTTP {response.status}")


@dataclass(frozen=True)
class _Issue24Task:
    token: str
    origin: str
    max_steps: int = 4

    @property
    def parameters(self) -> tuple[TaskParameter, ...]:
        return (TaskParameter("trial_token", self.token, secret=True),)

    def redact(self, value: Any) -> Any:
        return redact_token(value, self.token)

    def history_entry(self, step: int, candidate_id: str, *, refusal: str | None = None) -> dict[str, Any]:
        return history_entry(step, candidate_id, refusal=refusal)

    def reset(self) -> None:
        _reset(self.origin)

    def read_oracle(self) -> Mapping[str, Any]:
        return _read_state(self.origin)


@dataclass(frozen=True)
class ToggleConfirmTask(_Issue24Task):
    """Check the 'feature' checkbox, then click Confirm (#24 'toggle-confirm')."""

    id: str = field(default=TOGGLE_TASK_ID, init=False)
    goal: str = field(default="Turn on the feature checkbox, then confirm the change.", init=False)
    page_path: str = field(default="toggle-confirm", init=False)
    allowed_action_kinds: frozenset[str] = field(default=frozenset({"browser_click"}), init=False)
    completion_candidate_ids: frozenset[str] = field(default=frozenset({"click-confirm"}), init=False)
    mock_preferences: tuple[str, ...] = field(default=("toggle-feature", "click-confirm"), init=False)

    def candidates(self, sources: TaskSources) -> list:
        page = sources.require_page()
        page.require_target()
        box = page.find("checkbox", "feature")
        button = page.find("button", "Confirm")
        out = []
        if box is not None and not _is_checked(box):
            out.append(page.click(box, candidate_id="toggle-feature",
                                  description="Click the 'feature' checkbox to turn the feature on."))
        elif box is not None and _is_checked(box) and button is not None:
            out.append(page.click(button, candidate_id="click-confirm",
                                  description="Click Confirm. The observed state reports that the "
                                  "feature checkbox is already checked."))
        return out + _reserved_candidates()

    def state_summary(self, sources: TaskSources) -> dict[str, str]:
        page = sources.require_page()
        box = page.find("checkbox", "feature")
        button = page.find("button", "Confirm")
        return {
            "feature_checkbox": "not_found" if box is None else
            ("checked" if _is_checked(box) else "unchecked"),
            "confirm_button": "available" if button is not None else "not_found",
        }

    def classify(self, oracle: Mapping[str, Any], *, steps: int) -> str:
        if oracle_ok("toggle-confirm", dict(oracle), self.token):
            return "verified"
        if oracle.get("checked") is False:
            return "refuted"
        return "budget_exhausted" if steps >= self.max_steps else "unknown"


@dataclass(frozen=True)
class ModalTask(_Issue24Task):
    """Open the dialog, then click 'Confirm choice' (#24 'modal')."""

    id: str = field(default=MODAL_TASK_ID, init=False)
    goal: str = field(default="Open the dialog, then confirm the choice inside it.", init=False)
    page_path: str = field(default="modal", init=False)
    allowed_action_kinds: frozenset[str] = field(default=frozenset({"browser_click"}), init=False)
    completion_candidate_ids: frozenset[str] = field(default=frozenset({"confirm-choice"}), init=False)
    mock_preferences: tuple[str, ...] = field(default=("confirm-choice", "open-dialog"), init=False)

    def candidates(self, sources: TaskSources) -> list:
        page = sources.require_page()
        page.require_target()
        opener = page.find("button", "Open dialog")
        confirm = page.find("button", "Confirm choice")
        out = []
        if confirm is not None:
            out.append(page.click(confirm, candidate_id="confirm-choice",
                                  description="Click 'Confirm choice' in the open dialog."))
        elif opener is not None:
            out.append(page.click(opener, candidate_id="open-dialog",
                                  description="Click 'Open dialog' to reveal the dialog."))
        return out + _reserved_candidates()

    def state_summary(self, sources: TaskSources) -> dict[str, str]:
        page = sources.require_page()
        return {
            "open_button": "available" if page.find("button", "Open dialog") else "not_found",
            "confirm_choice_button": "available" if page.find("button", "Confirm choice") else "not_visible",
        }

    def classify(self, oracle: Mapping[str, Any], *, steps: int) -> str:
        if oracle_ok("modal", dict(oracle), self.token):
            return "verified"
        return "budget_exhausted" if steps >= self.max_steps else "unknown"
