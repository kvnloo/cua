"""Where a slow accessibility walk spends time. kvnloo/cua#13.

Mirrors `WalkBudget`: the shared budget starts at the first admitted node.
Setup before that admit is outside the walk budget.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WalkSplit:
    setup_ms: int
    walk_ms: int
    native_call_ms: int

    def owner(self) -> str:
        if self.setup_ms > self.walk_ms and self.setup_ms > self.native_call_ms:
            return "setup is outside WalkBudget and needs its existing backstop, not a second budget"
        if self.native_call_ms > self.walk_ms:
            return "a single native call exceeded the walk; a per-request timeout is the missing bound"
        return "WalkBudget already owns per-walk admission"
