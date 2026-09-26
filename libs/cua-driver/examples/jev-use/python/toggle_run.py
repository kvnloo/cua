"""Toggle then confirm. kvnloo/cua#43.

This file does not import the form-fill run. Freshness here is a boolean
setting, not a submit ref.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Status = Literal["verified", "refuted", "unknown", "refused"]


@dataclass(frozen=True)
class TogglePlan:
    first: str
    second: str


def admit_toggle(kind: str, child_ids: tuple[str, ...]) -> TogglePlan | None:
    if kind != "run" or child_ids != ("toggle-setting", "confirm-dialog"):
        return None
    return TogglePlan(child_ids[0], child_ids[1])


def second_toggle_allowed(status: Status, toggled: bool | None) -> bool:
    return status == "verified" and toggled is True
