"""Stale-target contract for kvnloo/cua#6.

Preflight does not authorize a later child after an earlier mutation.
The second child is resolved again immediately before dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class Target:
    identity: str
    label: str


@dataclass(frozen=True)
class Child:
    label: str
    planned: Target


Status = Literal["ok", "failed", "unknown"]


@dataclass
class Trace:
    preflight: list[bool]
    dispatched: list[str]
    refused: list[str]


def run_batch(
    children: list[Child],
    resolve: Callable[[str], Target | None],
    apply_first: Callable[[], Status],
) -> Trace:
    trace = Trace(preflight=[resolve(child.label) is not None for child in children], dispatched=[], refused=[])
    if not children:
        return trace
    if not trace.preflight[0]:
        trace.refused.append(children[0].label)
        return trace
    status = apply_first()
    trace.dispatched.append(children[0].label)
    if status != "ok" or len(children) == 1:
        return trace
    second = children[1]
    fresh = resolve(second.label)
    if fresh is None or fresh.identity != second.planned.identity:
        trace.refused.append(second.label)
        return trace
    trace.dispatched.append(second.label)
    return trace
