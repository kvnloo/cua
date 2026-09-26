"""Passive rows are readable and never actionable. kvnloo/cua#8."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    identity: str
    text: str
    passive: bool


class AuthorityError(ValueError):
    pass


def action_target(row: Row) -> str:
    if row.passive:
        raise AuthorityError(f"{row.identity} is observable and not an action target")
    return row.identity


def verification_text(rows: list[Row], identity: str) -> str | None:
    for row in rows:
        if row.identity == identity:
            return row.text
    return None
