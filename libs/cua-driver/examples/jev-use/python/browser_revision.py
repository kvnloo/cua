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


def transition_rows() -> list[dict[str, str]]:
    """Bind outcomes for the current node. A live browser battery is not included."""
    current = BrowserNode("ref-submit", 1, "Submit")
    bound = bind(current, "ref-submit", 1)
    rows = [
        {
            "state": "current",
            "event": "same ref and generation",
            "next": "bound",
            "dispatch": "allowed",
            "old_ref": current.ref,
            "new_ref": bound.ref,
            "generation": str(bound.generation),
            "refusal": "",
        }
    ]
    samples = (
        ("same label, new generation", BrowserNode("ref-submit", 2, "Submit"), "ref-submit", 1),
        ("ref missing", BrowserNode("ref-other", 1, "Submit"), "ref-submit", 1),
    )
    for event, node, ref, generation in samples:
        refusal = ""
        try:
            bind(node, ref, generation)
            nxt, dispatch = "bound", "allowed"
        except StaleRefError as exc:
            nxt, dispatch = "stale", "refused"
            refusal = str(exc)
        rows.append(
            {
                "state": "current",
                "event": event,
                "next": nxt,
                "dispatch": dispatch,
                "old_ref": ref,
                "new_ref": node.ref,
                "generation": str(node.generation),
                "refusal": refusal,
            }
        )
    return rows
