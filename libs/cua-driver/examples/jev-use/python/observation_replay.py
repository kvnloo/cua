"""Phase 2B upper bound from traces. kvnloo/cua#21.

No capture is skipped in the running driver. A false reuse kills the policy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    revision: str
    invalidators: frozenset[str]
    changed: bool
    source: str  # "recorded" or "synthetic"


@dataclass(frozen=True)
class ReplayResult:
    policy: str
    skips: int
    false_reuses: int
    recaptures: int


def replay(trace: list[Observation], policy: str) -> ReplayResult:
    skips = false_reuses = recaptures = 0
    previous: Observation | None = None
    for step in trace:
        reuse = False
        if previous is not None and policy == "no_trusted_invalidator":
            # `changed` is ground truth. The policy cannot see it if it skips.
            reuse = not step.invalidators and step.revision == previous.revision
        if reuse:
            skips += 1
            if step.changed:
                false_reuses += 1
        else:
            recaptures += 1
        previous = step
    return ReplayResult(policy, skips, false_reuses, recaptures)


def policy_killed(result: ReplayResult) -> bool:
    return result.false_reuses > 0
