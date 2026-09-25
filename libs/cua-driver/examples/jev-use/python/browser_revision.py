"""Browser ref stays bound to the node generation that minted it. kvnloo/cua#17."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserNode:
    ref: str
    generation: int
    label: str


class StaleRefError(ValueError):
    pass


def bind(node: BrowserNode, ref: str, generation: int) -> BrowserNode:
    if node.ref != ref or node.generation != generation:
        raise StaleRefError("ref does not match the current node generation")
    return node
